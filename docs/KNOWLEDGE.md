# Knowledge base

## Seed syntheses

Original educational reports (not scraped papers):

| File | Domain |
| --- | --- |
| `01_soil_organic_carbon_biodiversity.md` | SOC, pH, moisture, microbes |
| `02_rainfall_drought_species_survival.md` | Water, drought, survival |
| `03_monoculture_agroforestry_habitat.md` | Land use, pollinators, agroforestry |
| `04_cover_crops_semiarid_water.md` | Cover crops, water retention |
| `05_pollution_urban_species_richness.md` | Pollution, urban land |
| `06_temperature_drought_vegetation.md` | Heat, drought, sparse vegetation |
| `07_deforestation_fragmentation_biodiversity.md` | Forest loss, corridors |
| `08_land_use_change_cover.md` | Forest, grassland, agriculture, urban |

`python scripts/build_pdfs.py` writes matching PDFs into `knowledge/pdfs/` so the PDF extraction path can be demonstrated.

## Ingest contract

Every stored chunk should retain:

- source / document name
- page number (PDF page or approximated markdown page)
- topic / category
- document type

## Expanding coverage

The system does **not** assume the seed set covers every environmental question. Out-of-scope queries must fail the relevance check and use fallback handling.

To expand:

1. Add PDFs or markdown under `knowledge/`.
2. Ingest (UI upload or CLI).
3. Confirm new rows in `/api/knowledge`.
4. Search a distinctive phrase from the new document in the Knowledge page.
