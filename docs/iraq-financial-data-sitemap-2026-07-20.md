# Iraq Financial Data — Full Site Map: ISC, ISX, CBI

**By:** Horizon · 2026-07-20 · **For:** Atlas agent (build), Archos (infra), Amanj.
**Status:** research complete, pipeline not yet built. **Note on location:** Amanj
asked for this to live in the `cen314/zand-data` repo — that repo doesn't exist yet
(blocked on the Cleric314 GitHub token, per Archos). This is committed to `c314-core`
for now; move it to `zand-data` once Archos creates the repo.

Three parallel deep crawls (English + Arabic, every report category, real tested
URLs) across the Iraq Securities Commission, Iraq Stock Exchange, and Central Bank of
Iraq. All three sources are richer than the first pass found — the big story is that
**two of the three have a real per-company financial-disclosure feed**, which is
exactly what "quarterly reports from companies" needs.

## Headline findings

1. **ISC runs on a public, unauthenticated JSON API** (`api.isc.gov.iq`) — every
   report type, including per-company quarterly/annual filings, is available as clean
   JSON. No HTML scraping needed at all for ISC. Every record has both `_ar` and `_en`
   fields already, so one pass covers both languages.
2. **ISX has a working per-company financials endpoint** (`companyFinancials.html`,
   tab 5) that returns a company's full history of financial-statement PDFs in one
   call, for all 158 companies ever listed (not just the ~102 currently active).
3. **CBI has a real "Monthly Report of Banks Operating in Iraq"** page — exactly what
   Amanj asked for — but it's Arabic-only and coverage is sparse (only 3 months posted
   for 2025, none yet for 2026). Treat it as real but incomplete.
4. **Arabic is the more complete language on both ISC and ISX.** ISX's English
   per-company news/disclosure feed only started 2026-01-11 and has no history before
   that — build against Arabic as primary, English as a secondary/recency check.
5. **CBI has real dead links.** Pre-2016 financial statements and older monetary
   policy reports point to `www.cbi.iq/documents/...` — confirmed 404. Any pipeline
   must HEAD-check before trusting a discovered URL, not just trust the listing page.

---

## 1. Iraq Securities Commission (isc.gov.iq / api.isc.gov.iq)

| Data | Endpoint | Notes |
|---|---|---|
| All listed companies | `GET api.isc.gov.iq/api/companies?page=N&market=M` | ~197 companies across 5 markets (Main 54, Secondary 50, Third 45 — not in site nav but in API, Non-disclosing 17, OTC 31) |
| **Per-company quarterly/annual filings** | `GET api.isc.gov.iq/api/companies/{id}/reports` | Grouped by year, q1–q4 + annual, each with a direct PDF `url`. This is the core "quarterly company reports" dataset. |
| Material/significant-event disclosures | `GET api.isc.gov.iq/api/news?category=7&page=N` | 2,215 items; PDF link is embedded inside an HTML `descr` field, needs light parsing |
| Daily/weekly trading bulletins | `GET api.isc.gov.iq/api/reports/daily` | Single JSON payload, 1,892 files, full 2018–2026 history in one call |
| ISC's own yearly/quarterly activity reports | `GET api.isc.gov.iq/api/reports/yearly` | 2008–2026 |
| Brokerage companies | `GET api.isc.gov.iq/api/broker-companies?page=N` | Profiles only, no filings found |

No separate Arabic path — bare paths (no `/en/` prefix) are Arabic, `/en/` prefix is
English, same API backend either way. `sitemap.xml` doesn't exist. A legacy
credential-gated ASP.NET portal exists (`iscgoviq2-001-site1.etempurl.com`) — that's
for companies submitting filings, not for reading, out of scope.

**Build recommendation:** hit the API directly. Don't scrape the Nuxt HTML at all.

---

## 2. Iraq Stock Exchange (isx-iq.net)

| Data | Endpoint | Notes |
|---|---|---|
| Company directory | `companyGuideList.html?currLanguage=ar` | 158 company codes, sector-grouped — includes delisted/suspended, not just the ~102 active |
| **Per-company financial statements** | `POST companyFinancials.html?companyCode=X&activeTab=5&currLanguage=ar` | Full filing history per company in one call, no pagination. Identical between AR/EN. |
| Per-company disclosure headlines | `POST companyStories.html?companyCode=X&activeTab=3&currLanguage=ar` | **Arabic mandatory** — English feed only starts 2026-01-11, no backfill |
| Market-wide weekly/monthly/semi-annual reports | `GET storyList.html?methodName=getNewsStoryList&currLanguage=ar` | 1,352 items, 15/page, paginated back to 2011. Follow `storyDetails.html?storyId=N` for the actual PDF link. |
| Market-wide announcements | `GET storyList.html?methodName=getAnnouncmentStoryList&currLanguage=ar` | General notices — supplementary, not a substitute for per-company feeds |
| Daily bulletins | `uploadedFilesList.html?currLanguage=ar` | Rolling ~7 files only — poll at least daily |

No login/session needed for any endpoint tested. Filenames are always opaque
(Arabic-script, spaces, need URL-encoding) — never construct, always scrape from the
listing response. Dead ends confirmed empty: `newsletter.html` (signup form only),
`investorGuidePortalList.html` (no data), `sitemap.html` (nothing beyond the above).

**Build recommendation:** enumerate companies once from the Arabic directory, then
poll each company's `activeTab=5` (financials) and `activeTab=3` (disclosures)
endpoints; separately poll the market-wide story feed for weekly/monthly/semi-annual
bulletins.

---

## 3. Central Bank of Iraq (cbi.iq)

Site defaults to Arabic; English is a session-cookie toggle
(`/language/change/english/...`), not a separate URL path — same `/page/N` URLs serve
either language depending on the session. All static HTML, no JS needed.

| Report | Page | Frequency / coverage |
|---|---|---|
| Annual financial statements (audited) | `/page/76` (current 2016–2025), `/page/75` (legacy 2005–2015, **mostly dead links**) | Annual. AR and EN are separate file sets, not mirrors — don't assume the same file ID works for both. |
| **Monthly Report of Banks Operating in Iraq** | `/page/173` | **Arabic-only** — English session shows nothing. Only 3 months posted for 2025 (Jul/Aug/Dec), none for 2026 yet. Real, but sparse/lagged. |
| Monthly Statistical Bulletin | `/page/122` | .xlsx, only the current file shown — no archive on the page itself |
| Financial Stability Report | `/page/147` | Annual, 2010–2024, all resolving |
| Monetary Policy Report | `/page/149` | Annual 2016–2024 on modern URLs; older years (2009–2015) on dead legacy links |
| Annual Statistical Bulletin | `/page/142` | 2003–2024, appears recently backfilled onto modern URLs — good historical baseline |
| Exchange rates | `/page/144` | .xlsx, daily data — highest-frequency dataset on the site |
| Interest rates table | `/page/143` | 2013–2024, mixed xlsx/xls/pdf |
| Balance of payments | `/page/145` | .xlsx, 2016–2024 |
| Foreign trade statistics | `/page/146` | PDF, sparse (2002/2023/2024 only) |
| Others confirmed to exist, same pattern, not deep-checked | pages 148, 150, 152, 159, 160, 161, 162, 163, 165, 170, 37, 155, 156, 157, 179 | Early warning, economic report, trade report, non-bank financial institutions, inflation analysis, interest rate structure, monetary variables, monetary stability, financial soundness indicators, research/studies, two journals |

All files served from `cbi.iq/static/uploads/up/file-<timestamp-id>.<pdf|xlsx|xls>` —
opaque, must scrape from the listing page. **Legacy `www.cbi.iq/documents/...` links
are confirmed dead** (404) — any pipeline must verify each URL before trusting it.

**Build recommendation:** the 11+ `page/N` listing URLs are the stable anchor points.
Fetch listing → parse links → HEAD-check → download. Use the English session for
sections where English exists; Arabic session is mandatory for the monthly bank
report (page/173).

---

## What this means for the pipeline (summary for Atlas/Archos)

- **ISC:** build against the API, not HTML. Cheapest and cleanest of the three.
- **ISX:** no API, but stable AJAX endpoints — scrape those directly (curl/POST),
  build in Arabic.
- **CBI:** static HTML listing pages, opaque file IDs, real dead-link risk on older
  material — HEAD-check everything, build in whichever session (AR/EN) each report
  type actually populates.
- None of the three need OCR for discovery/text — this is all native PDF/HTML/JSON.
  OCR (already tested and working, see the earlier fact-check report) stays a fallback
  for the rare image-only page, not the primary path.
