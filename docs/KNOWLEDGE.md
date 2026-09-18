# Knowledge base

Seed files in `knowledge/sources/` are **Darukaa.Earth syntheses**. They summarise public scientific consensus and link to institutions such as FAO or IPBES. They are not those original reports.

Metadata lives in `knowledge/manifest.json` (title, source type, organisation, related URL).

Markdown pages are stored as `page=null` / `page_is_real=false`. Only ingested PDFs keep printer page numbers.

Generated copies under `knowledge/pdfs/` are not indexed when a matching markdown stem exists.
