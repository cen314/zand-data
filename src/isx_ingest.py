#!/usr/bin/env python3
"""
ISX/ISC daily data ingest pipeline — Zand Intelligence
=======================================================
Uses the ISC public JSON API (api.isc.gov.iq) instead of HTML scraping.
ISX bulletin is still fetched via HTML listing (no public API known yet).

ISC API endpoints (all unauthenticated):
  GET api.isc.gov.iq/api/reports/daily        — 1,892 daily reports, nested by year/month
  GET api.isc.gov.iq/api/companies?page=N     — 197 companies, 10/page, 20 pages
  GET api.isc.gov.iq/api/companies/{id}/reports — per-company Q1/Q2/Q3/Q4/annual filings

ISC bulletin PDF structure (verified 2026-07-20, 4 pages):
  Page 1: Regular listed market (يماظنلا قوسلا) — ISX60 + ISX15 index values
  Page 2: Second market (يناثلا قوسلا)
  Page 3: Non-disclosed companies
  Page 4: OTC non-listed
  Each page: header text (session totals, index values) +
    Table 1 (10 cols): top losers left | top gainers right
    Table 2 (10 cols): most active by trade value left | by shares traded right

Usage:
    python3 isx_ingest.py                       # ingest 1 new ISC file (most recent)
    python3 isx_ingest.py --dry-run             # list new files, skip download/parse
    python3 isx_ingest.py --backfill 30         # process up to 30 oldest un-ingested ISC files
    python3 isx_ingest.py --seed-companies      # seed/refresh all 197 companies from API

Move to cen314/zand-data/src/isx_ingest.py once repo exists.
"""

import argparse
import hashlib
import io
import logging
import re
from datetime import date, datetime
from typing import Optional

import boto3
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("isx_ingest")

ISC_API_BASE    = "https://api.isc.gov.iq/api"
# Arabic listing is more complete; rolling ~7 files only — poll at least daily
ISX_LISTING_URL = "http://www.isx-iq.net/isxportal/portal/uploadedFilesList.html?currLanguage=ar"
ISX_BASE_URL    = "http://www.isx-iq.net"
ISX_COMPANY_DIR = "http://www.isx-iq.net/isxportal/portal/companyGuideList.html?currLanguage=ar"

# Stage 2 per-company endpoints (POST, no auth needed):
#   Financial statements: POST companyFinancials.html?companyCode={X}&activeTab=5&currLanguage=ar
#   Disclosure headlines: POST companyStories.html?companyCode={X}&activeTab=3&currLanguage=ar
#   (English disclosure feed only starts 2026-01-11 — build against Arabic as primary)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ZandIntelligence/1.0; +https://capitaliraq.com)",
    "Accept": "application/json, text/html;q=0.9",
}
REQUEST_TIMEOUT = 30

ISC_MARKET_NAMES = {
    1: "Main",
    2: "Secondary",
    3: "Third",
    4: "Non-Disclosing",
    5: "Non-Listed/OTC",
}

# ---------------------------------------------------------------------------
# Supabase
# ---------------------------------------------------------------------------

def _ssm(name: str) -> str:
    client = boto3.client("ssm", region_name="eu-central-1")
    return client.get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"]


def get_supabase():
    from supabase import create_client
    url = _ssm("/c314/zand/SUPABASE_URL")
    key = _ssm("/c314/zand/SUPABASE_SERVICE_ROLE_KEY")
    return create_client(url, key)


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _get(url: str, params: Optional[dict] = None) -> dict | list:
    r = requests.get(url, headers=HEADERS, params=params, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.json()


def fetch_bytes(url: str) -> bytes:
    r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.content


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# ISC API — daily reports
# ---------------------------------------------------------------------------

def isc_api_all_reports() -> list[dict]:
    """
    Return a flat list of all ISC daily report records, newest first.
    Each item: {isc_id, url, report_date (date object)}

    API response structure:
      {firstYear, lastYear, items: [{year, items: {month_num: [report, ...]}}]}
    Each report: {id, title_ar, title_en, url, date, month, ...}
    """
    data = _get(f"{ISC_API_BASE}/reports/daily")
    result: list[dict] = []
    for year_block in data.get("items", []):
        for month_str, reports in year_block.get("items", {}).items():
            for r in reports:
                if not r.get("url"):
                    continue
                # Parse the clean ISO date from the API (no URL path guessing needed)
                raw_date = r.get("date", "")
                try:
                    report_date = date.fromisoformat(raw_date[:10])
                except (ValueError, TypeError):
                    log.warning("Unparseable date '%s' for ISC report id=%s", raw_date, r.get("id"))
                    continue
                result.append({
                    "isc_id":      r["id"],
                    "url":         r["url"],
                    "report_date": report_date,
                    "title_ar":    (r.get("title_ar") or "").strip(),
                    "title_en":    (r.get("title_en") or "").strip(),
                })
    # Sort newest first
    result.sort(key=lambda x: x["report_date"], reverse=True)
    log.info("ISC API: %d daily reports fetched", len(result))
    return result


def isc_already_ingested_ids(sb) -> set[int]:
    """Return ISC report IDs already stored in isx_sessions."""
    res = sb.schema("market").from_("isx_sessions") \
        .select("isc_report_id") \
        .eq("source", "ISC") \
        .filter("isc_report_id", "not.is", "null") \
        .execute()
    return {row["isc_report_id"] for row in (res.data or [])}


# ---------------------------------------------------------------------------
# ISC API — company seeding
# ---------------------------------------------------------------------------

def seed_companies(sb) -> int:
    """
    Fetch all 197 companies from the ISC API and upsert into market.isx_companies.
    Safe to run repeatedly — uses ON CONFLICT (ticker) DO UPDATE.
    Returns number of companies upserted.
    """
    log.info("Seeding companies from %s/companies", ISC_API_BASE)
    upserted = 0
    page = 1
    while True:
        data = _get(f"{ISC_API_BASE}/companies", params={"page": page})
        items = data.get("data", [])
        if not items:
            break
        rows = []
        for co in items:
            ticker = (co.get("code") or "").strip().upper()
            if not ticker:
                log.warning("Company id=%s has no ticker code — skipping", co.get("id"))
                continue
            rows.append({
                "ticker":           ticker,
                "name_ar":          (co.get("title_ar") or "").strip() or ticker,
                "name_en":          (co.get("title_en") or "").strip() or None,
                "market_segment":   co.get("market"),
                "sector":           ISC_MARKET_NAMES.get(co.get("market")),
                "isc_company_id":   co.get("id"),
                "capital_iqd":      co.get("capital"),
                "est_date":         co.get("estdate") if co.get("estdate") and not co.get("estdate", "").startswith("0000") else None,
                "is_active":        not bool(co.get("hidecompany") or co.get("hideallcompany")),
            })
        if rows:
            # Deduplicate within the batch — API occasionally returns duplicate tickers
            seen_tickers: set[str] = set()
            unique_rows = []
            for r in rows:
                if r["ticker"] not in seen_tickers:
                    seen_tickers.add(r["ticker"])
                    unique_rows.append(r)
            sb.schema("market").from_("isx_companies").upsert(
                unique_rows, on_conflict="ticker"
            ).execute()
            upserted += len(unique_rows)
        if not data.get("next_page_url"):
            break
        page += 1
    log.info("Companies seeded: %d", upserted)
    return upserted


# ---------------------------------------------------------------------------
# ISX listing page scraper (no API equivalent known yet)
# ---------------------------------------------------------------------------

def isx_pdf_urls(html: str) -> list[str]:
    """Extract PDF/XLSX URLs from the ISX bulletin listing page (JSP, plain HTML)."""
    urls = re.findall(r'href=["\']([^"\']*(?:\.pdf|\.xlsx))["\']', html, re.IGNORECASE)
    seen: set[str] = set()
    result = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            result.append(u if u.startswith("http") else ISX_BASE_URL + u)
    return result


def isx_ingested_urls(sb) -> set[str]:
    res = sb.table("raw_data_records") \
        .select("source_url") \
        .filter("source_url", "not.is", "null") \
        .like("source_url", "%isx-iq.net%") \
        .execute()
    return {r["source_url"] for r in (res.data or [])}


# ---------------------------------------------------------------------------
# PDF parsing — ISC bulletin (structure verified 2026-07-20)
# ---------------------------------------------------------------------------

_RE_LISTED  = re.compile(r"(\d[\d,]*)\s+ةجردملا تاكرشلا ددع")
_RE_TRADED  = re.compile(r"(\d[\d,]*)\s+ةلودتملا تاكرشلا")
_RE_GAINERS = re.compile(r"(\d[\d,]*)\s+ةعفترملا")
_RE_LOSERS  = re.compile(r"(\d[\d,]*)\s+ةضفخنملا")
_RE_STABLE  = re.compile(r"(\d[\d,]*)\s+هرقتسملا")
_RE_VALUE   = re.compile(r"([\d,]+)\s+لوادتلا ةميق")
_RE_SHARES  = re.compile(r"([\d,]+)\s+ةلوادتملا مهسلاا")
_RE_TRADES  = re.compile(r"(\d[\d,]*)\s+تاقفصلا")
_RE_OPEN    = re.compile(r"([\d.]+)\s+حاتتفلاا")
_RE_CLOSE   = re.compile(r"([\d.]+)\s+قلاغلاا")
_RE_PCT     = re.compile(r"([\d.]+)\s+%\s+ريغتلا هبسن")
_RE_PTS     = re.compile(r"([\d.]+)\s+[()هطقن]*ريغتلا رادقم")


def _clean(s: Optional[str]) -> Optional[float]:
    if not s or not str(s).strip():
        return None
    try:
        return float(str(s).strip().replace(",", ""))
    except ValueError:
        return None


def _is_ticker(s: Optional[str]) -> bool:
    return bool(s and re.fullmatch(r"[A-Z]{3,5}", str(s).strip()))


def _text_stats(text: str) -> dict:
    def first(pat, t):
        m = pat.search(t)
        return _clean(m.group(1).replace(",", "")) if m else None
    return {
        "total_listed":    first(_RE_LISTED,  text),
        "total_traded":    first(_RE_TRADED,  text),
        "total_gainers":   first(_RE_GAINERS, text),
        "total_losers":    first(_RE_LOSERS,  text),
        "total_stable":    first(_RE_STABLE,  text),
        "total_value_iqd": first(_RE_VALUE,   text),
        "total_shares":    first(_RE_SHARES,  text),
        "total_trades":    first(_RE_TRADES,  text),
    }


def _indices(text: str) -> dict:
    opens  = _RE_OPEN.findall(text)
    closes = _RE_CLOSE.findall(text)
    pcts   = _RE_PCT.findall(text)
    pts    = _RE_PTS.findall(text)
    r: dict = {}
    if len(opens)  >= 1: r["isx60_open"]       = float(opens[0])
    if len(closes) >= 1: r["isx60_close"]      = float(closes[0])
    if len(pcts)   >= 1: r["isx60_change_pct"] = float(pcts[0])
    if len(pts)    >= 1: r["isx60_change_pts"] = float(pts[0])
    if len(opens)  >= 2: r["isx15_open"]       = float(opens[1])
    if len(closes) >= 2: r["isx15_close"]      = float(closes[1])
    if len(pcts)   >= 2: r["isx15_change_pct"] = float(pcts[1])
    if len(pts)    >= 2: r["isx15_change_pts"] = float(pts[1])
    return r


def _parse_gainers_losers(table: list[list]) -> list[dict]:
    """
    Table 1 (10 cols), rows from index 2:
    [0]chg_pct [1]close [2]prev_close [3]ticker [4]name_ar  <- loser
    [5]chg_pct [6]close [7]prev_close [8]ticker [9]name_ar  <- gainer
    """
    rows = []
    for row in table[2:]:
        if not row or len(row) < 10:
            continue
        if _is_ticker(row[3]):
            rows.append({"ticker": row[3].strip(), "name_ar": (row[4] or "").strip(),
                         "prev_close": _clean(row[2]), "close": _clean(row[1]),
                         "change_pct": _clean(row[0])})
        if _is_ticker(row[8]):
            rows.append({"ticker": row[8].strip(), "name_ar": (row[9] or "").strip(),
                         "prev_close": _clean(row[7]), "close": _clean(row[6]),
                         "change_pct": _clean(row[5])})
    return rows


def _parse_most_active(table: list[list]) -> tuple[dict, dict]:
    """
    Table 2 (10 cols), rows from index 2:
    [0]close [1]pct [2]trade_value [3]ticker [4]name_ar  <- by value
    [5]close [6]pct [7]shares      [8]ticker [9]name_ar  <- by shares
    """
    by_val: dict[str, dict] = {}
    by_sh:  dict[str, dict] = {}
    for row in table[2:]:
        if not row or len(row) < 10:
            continue
        if _is_ticker(row[3]):
            t = row[3].strip()
            by_val[t] = {"ticker": t, "name_ar": (row[4] or "").strip(),
                         "close": _clean(row[0]), "trade_value_iqd": _clean(row[2])}
        if _is_ticker(row[8]):
            t = row[8].strip()
            by_sh[t] = {"ticker": t, "name_ar": (row[9] or "").strip(),
                        "close": _clean(row[5]), "shares_traded": _clean(row[7])}
    return by_val, by_sh


def parse_isc_pdf(pdf_bytes: bytes, session_id: str, session_date: date) -> tuple[dict, list[dict]]:
    """Parse a full ISC daily bulletin. Returns (session_updates, price_rows)."""
    import pdfplumber

    session_updates: dict = {}
    companies: dict[str, dict] = {}

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            text   = page.extract_text() or ""
            tables = page.extract_tables()

            # Accumulate session totals across all 4 market pages
            for k, v in _text_stats(text).items():
                if v is not None:
                    session_updates[k] = (session_updates.get(k) or 0) + v

            # Index values only on page 1 (regular listed market)
            if page_idx == 0:
                session_updates.update(_indices(text))

            def _add(row: dict, **extra):
                t = row["ticker"]
                if t not in companies:
                    companies[t] = {
                        "session_date": session_date.isoformat(),
                        "session_id":   session_id,
                        "ticker":       t,
                        "name_ar":      row.get("name_ar", ""),
                        "prev_close":   row.get("prev_close"),
                        "close":        row.get("close"),
                        "change_pct":   row.get("change_pct"),
                        "shares_traded":    None,
                        "trade_value_iqd":  None,
                        "trade_count":      None,
                        "is_most_active_value":  False,
                        "is_most_active_shares": False,
                        **extra,
                    }
                else:
                    for field in ("close", "prev_close", "change_pct"):
                        if companies[t][field] is None and row.get(field) is not None:
                            companies[t][field] = row[field]
                    for k, v in extra.items():
                        if v is not None:
                            if k in ("is_most_active_value", "is_most_active_shares"):
                                companies[t][k] = companies[t][k] or v
                            elif companies[t].get(k) is None:
                                companies[t][k] = v

            if len(tables) >= 1:
                for row in _parse_gainers_losers(tables[0]):
                    _add(row)

            if len(tables) >= 2:
                by_val, by_sh = _parse_most_active(tables[1])
                for row in by_val.values():
                    _add(row, trade_value_iqd=row["trade_value_iqd"],
                         is_most_active_value=True)
                for row in by_sh.values():
                    _add(row, shares_traded=row["shares_traded"],
                         is_most_active_shares=True)

    price_rows = list(companies.values())
    log.info("Parsed: %d companies, stats: listed=%s traded=%s vol=%s",
             len(price_rows),
             session_updates.get("total_listed"),
             session_updates.get("total_traded"),
             session_updates.get("total_value_iqd"))
    return session_updates, price_rows


# ---------------------------------------------------------------------------
# Supabase write helpers
# ---------------------------------------------------------------------------

_SOURCE_CACHE: dict[str, str] = {}

def get_or_create_source(sb, name: str, url: str,
                         source_type: str = "api",
                         access_method: str = "api") -> str:
    # source_name is the unique identifier (no source_handle column in this schema)
    if name in _SOURCE_CACHE:
        return _SOURCE_CACHE[name]
    res = sb.table("data_sources").select("id").eq("source_name", name).execute()
    if res.data:
        _SOURCE_CACHE[name] = res.data[0]["id"]
        return res.data[0]["id"]
    ins = sb.table("data_sources").insert({
        "source_name":           name,
        "base_url":              url,
        "source_type":           source_type,    # must be: official/international/news/trade/investment/geospatial/private/primary_collection
        "access_method":         access_method,  # must be: api/scrape/rss/manual_upload/pdf_download/partnership_feed/primary_collection
        "licence_type":          "open-government",
        "commercial_use_status": "allowed",
        "update_frequency":      "daily",
        "is_active":             True,
    }).execute()
    _SOURCE_CACHE[name] = ins.data[0]["id"]
    return ins.data[0]["id"]


def upsert_raw_record(sb, source_id: Optional[str], url: str, sha: str) -> str:
    # on_conflict requires a unique constraint on content_hash — insert with ignore on dup
    res = sb.table("raw_data_records").upsert({
        "source_id":        source_id,
        "source_url":       url,
        "content_hash":     sha,
        "ingestion_method": "pdf",
        "processing_status": "pending",
        "date_ingested":    datetime.utcnow().isoformat(),
    }, on_conflict="source_id,content_hash").execute()
    return res.data[0]["id"]


def upsert_session(sb, report_date: date, source: str, pdf_url: str,
                   raw_id: str, isc_id: Optional[int] = None,
                   status: str = "pending") -> str:
    payload: dict = {
        "session_date": report_date.isoformat(),
        "source":       source,
        "pdf_url":      pdf_url,
        "raw_record_id": raw_id,
        "status":       status,
    }
    if isc_id is not None:
        payload["isc_report_id"] = isc_id
    res = sb.schema("market").from_("isx_sessions").upsert(
        payload, on_conflict="session_date"
    ).execute()
    return res.data[0]["id"]


# ---------------------------------------------------------------------------
# PDF text-layer check
# ---------------------------------------------------------------------------

def has_text_layer(pdf_bytes: bytes) -> bool:
    try:
        import pymupdf
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        text = doc[0].get_text().strip()
        doc.close()
        return len(text) > 50
    except Exception as e:
        log.warning("pymupdf check failed: %s", e)
        return False


# ---------------------------------------------------------------------------
# Process one ISC report
# ---------------------------------------------------------------------------

def process_isc_report(sb, report: dict, source_id: str,
                       ingested_ids: set[int], dry_run: bool = False) -> bool:
    isc_id      = report["isc_id"]
    url         = report["url"]
    report_date = report["report_date"]

    if isc_id in ingested_ids:
        log.debug("Already ingested ISC id=%d (%s)", isc_id, report_date)
        return True

    if dry_run:
        log.info("[DRY RUN] Would ingest ISC id=%d date=%s url=%s", isc_id, report_date, url)
        return True

    log.info("Fetching ISC id=%d date=%s", isc_id, report_date)
    try:
        pdf_bytes = fetch_bytes(url)
    except requests.RequestException as e:
        log.error("Fetch failed %s: %s", url, e)
        return False

    sha    = sha256_hex(pdf_bytes)
    raw_id = upsert_raw_record(sb, source_id, url, sha)

    if not has_text_layer(pdf_bytes):
        log.warning("No text layer — flagging ocr_fallback: %s", url)
        upsert_session(sb, report_date, "ISC", url, raw_id, isc_id=isc_id, status="ocr_fallback")
        ingested_ids.add(isc_id)
        return True

    session_id = upsert_session(sb, report_date, "ISC", url, raw_id, isc_id=isc_id)

    try:
        session_updates, price_rows = parse_isc_pdf(pdf_bytes, session_id, report_date)
    except Exception as e:
        log.error("Parse failed %s: %s", url, e)
        sb.schema("market").from_("isx_sessions").update(
            {"status": "failed", "notes": str(e)[:500]}
        ).eq("id", session_id).execute()
        return False

    if price_rows:
        # Ensure all tickers exist in isx_companies (FK) — create stubs for unknowns
        known = {r["ticker"] for r in
                 (sb.schema("market").from_("isx_companies")
                  .select("ticker").execute().data or [])}
        stubs = [
            {"ticker": r["ticker"], "name_ar": r.get("name_ar") or r["ticker"],
             "is_active": True}
            for r in price_rows if r["ticker"] not in known
        ]
        if stubs:
            # Deduplicate stubs within this batch
            seen: set[str] = set()
            stubs = [s for s in stubs if not seen.__contains__(s["ticker"]) and not seen.add(s["ticker"])]  # type: ignore[func-returns-value]
            log.info("Stubbing %d unknown tickers: %s",
                     len(stubs), [s["ticker"] for s in stubs])
            sb.schema("market").from_("isx_companies").upsert(
                stubs, on_conflict="ticker"
            ).execute()

        # name_ar lives in isx_companies, not isx_daily_prices — strip before upsert
        price_cols = [
            "session_date", "session_id", "ticker", "prev_close", "close",
            "change_pct", "shares_traded", "trade_value_iqd", "trade_count",
            "is_most_active_value", "is_most_active_shares",
        ]
        def _cast(row: dict) -> dict:
            out = {k: row[k] for k in price_cols if k in row}
            for col in ("shares_traded", "trade_count"):
                if out.get(col) is not None:
                    out[col] = int(out[col])
            return out
        price_insert = [_cast(r) for r in price_rows]
        sb.schema("market").from_("isx_daily_prices").upsert(
            price_insert, on_conflict="session_date,ticker"
        ).execute()

    # Cast integer/bigint session fields — PDF parser returns floats from regex
    int_session_cols = ("total_listed", "total_traded", "total_gainers",
                        "total_losers", "total_stable", "total_shares", "total_trades")
    cast_updates = {
        k: int(v) if k in int_session_cols and v is not None else v
        for k, v in session_updates.items()
    }
    sb.schema("market").from_("isx_sessions").update({
        "status":    "parsed",
        "parsed_at": datetime.utcnow().isoformat(),
        "row_count": len(price_rows),
        **cast_updates,
    }).eq("id", session_id).execute()

    ingested_ids.add(isc_id)
    log.info("Done: ISC %s — %d companies", report_date, len(price_rows))
    return True


# ---------------------------------------------------------------------------
# Process one ISX file
# ---------------------------------------------------------------------------

def process_isx_file(sb, url: str, source_id: str,
                     ingested_urls: set[str], dry_run: bool = False) -> bool:
    if url in ingested_urls:
        log.debug("Already ingested ISX: %s", url)
        return True
    if dry_run:
        log.info("[DRY RUN] Would ingest ISX: %s", url)
        return True

    log.info("Fetching ISX: %s", url)
    try:
        pdf_bytes = fetch_bytes(url)
    except requests.RequestException as e:
        log.error("ISX fetch failed %s: %s — is isx-iq.net reachable?", url, e)
        return False

    sha    = sha256_hex(pdf_bytes)
    raw_id = upsert_raw_record(sb, source_id, url, sha)
    # ISX bulletin parsing TBD — store raw record for now, parse once format confirmed
    log.info("ISX file stored (raw_record id=%s). Parser TBD.", raw_id)
    ingested_urls.add(url)
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(dry_run: bool = False, backfill: int = 1,
        do_seed_companies: bool = False) -> None:
    sb = get_supabase()
    log.info("Connected to Supabase (Zand project)")

    if do_seed_companies:
        seed_companies(sb)
        return

    isc_source_id = get_or_create_source(
        sb, "Iraq Securities Commission — Daily Reports",
        f"{ISC_API_BASE}/reports/daily",
        source_type="official", access_method="api")
    isx_source_id = get_or_create_source(
        sb, "Iraq Stock Exchange — Daily Bulletins", ISX_LISTING_URL,
        source_type="official", access_method="scrape")

    # ---- ISC (API-first) ---------------------------------------------------
    all_reports  = isc_api_all_reports()
    ingested_ids = isc_already_ingested_ids(sb)
    new_reports  = [r for r in all_reports if r["isc_id"] not in ingested_ids]
    log.info("ISC: %d total, %d new", len(all_reports), len(new_reports))

    processed = 0
    for report in new_reports:
        if processed >= backfill:
            break
        if process_isc_report(sb, report, isc_source_id, ingested_ids, dry_run):
            processed += 1

    # ---- ISX (HTML listing — no public API known yet) ----------------------
    log.info("Fetching ISX listing: %s", ISX_LISTING_URL)
    try:
        html      = fetch_bytes(ISX_LISTING_URL).decode("utf-8", errors="replace")
        isx_urls  = isx_pdf_urls(html)
        isx_done  = isx_ingested_urls(sb)
        new_isx   = [u for u in isx_urls if u not in isx_done]
        log.info("ISX: %d total, %d new", len(isx_urls), len(new_isx))
        for url in new_isx:
            process_isx_file(sb, url, isx_source_id, isx_done, dry_run)
    except requests.RequestException as e:
        log.error("ISX listing failed: %s", e)

    log.info("Run complete.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ISX/ISC daily ingest for Zand")
    parser.add_argument("--dry-run", action="store_true",
                        help="List new files without downloading or parsing")
    parser.add_argument("--backfill", type=int, default=1, metavar="N",
                        help="Max new ISC reports per run (default 1). Use 1892 to load all history.")
    parser.add_argument("--seed-companies", action="store_true",
                        help="Seed/refresh all 197 ISX companies from the ISC API and exit")
    args = parser.parse_args()
    run(dry_run=args.dry_run, backfill=args.backfill,
        do_seed_companies=args.seed_companies)
