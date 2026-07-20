# Zand Market Intelligence Dashboard — build brief (draft 1)

**From:** Horizon · 2026-07-20 · **For:** Archos + Atlas agent, per Amanj's direction
(Telegram inbox, 2026-07-20 15:39 Baghdad) · **Status:** proposal, not yet built.

## The vision (Amanj, in his own framing)
Iraq's stock exchange (ISX) is young — the ~102 listed companies genuinely are the
whole market. It's hard for ordinary people to read, and existing brokerage apps are
paywalled and outdated, so most people never get into trading. Amanj wants Zand
Intelligence to be a modern, open dashboard on ISX/ISC/CBI data — daily analysis,
charts, and progress-tracking on the top companies — so more people in Iraq can
actually access financial information. This is core to what "Zand Intelligence"
is meant to be, not a side feature.

## Important correction to the original OCR plan
Amanj's instinct was to install the Unlimited-OCR model in Atlas hub to read this
data. **Testing shows this mostly isn't necessary.** I checked the actual PDF files
from ISC, ISX, and CBI directly (not through an image-based OCR pass) — most pages
have a normal machine-readable text layer already:

- ISC daily reports: real extractable Arabic text, no OCR needed.
- ISX daily bulletins: real extractable English/Arabic text, no OCR needed.
- CBI financial statements: real extractable text.
- ISC annual report: mixed — most pages have text, a few (cover, section-break pages)
  are image-only and would need OCR.

**Why this matters:** plain PDF text/table extraction (e.g. `pymupdf`, `pdfplumber`)
is faster, cheaper, and more accurate than running a 3B-parameter vision model, and
needs no GPU. Recommend building the core daily pipeline on direct text extraction,
and keep Unlimited-OCR in reserve only for the minority of genuinely scanned/image
pages (confirmed real and tested working today — see
[reference report](https://github.com/cen314/c314-core/blob/main/reflections/research/2026-07-20-unlimited-ocr-factcheck.md)).
This avoids provisioning GPU infrastructure just to get this dashboard running.

## Proposed pipeline (for Archos/Atlas to scope and own)
1. **Ingest** — daily fetch of new PDFs from ISC (`isc.gov.iq/en/reports/daily`), ISX
   (`isx-iq.net` market reports), and periodic CBI statements.
2. **Parse** — direct text/table extraction per company per session: ticker, name,
   price, % change, volume, trades. Fall back to OCR only where a page has no text
   layer.
3. **Store** — time-series table per company (date, ticker, price, % change, volume)
   in Supabase — either Zand's existing project (`yfinymrebcervagidhqe`) or a new
   schema, Archos/Atlas call.
4. **Present** — dashboard in cap-hub/Zand: daily gainers/losers, index trend
   (ISX60/ISX15), per-company price history chart, sector view. Framed as free/open,
   in contrast to the paywalled brokerage apps Amanj referenced.

## What's already done
- 18 real source PDFs downloaded and verified live (1 CBI, 1 ISC annual, 1 ISX daily,
  15 ISC daily reports for July 2026) — logged to Atlas activity feed (Archos,
  2026-07-20).
- Unlimited-OCR tested and confirmed working for the image-only fallback case.
- Direct text extraction confirmed working on sample pages from all 3 sources (see
  above).

## Open decisions for Archos/Atlas
- Where the data lives (Zand's existing Supabase project vs. new schema).
- Build order — is this a cap-hub/Zand feature, a standalone service, or both.
- File delivery: Amanj wants the 18 source PDFs in a new GitHub repo under `cen314`
  (his call, pending) rather than Drive, since this is agent-to-agent working material.
