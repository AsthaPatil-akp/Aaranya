# Knowledge base

Seed files in `knowledge/sources/` are **Aaranya / Darukaa syntheses**. They summarise public scientific consensus and may link to institutions such as FAO or IPBES. They are not those original reports.

| File | Topic |
|---|---|
| `01_soil_organic_carbon_biodiversity.md` | Soil carbon, pH, moisture, below-ground biodiversity |
| `02_rainfall_drought_species_survival.md` | Rainfall, drought, species survival |
| `03_monoculture_agroforestry_habitat.md` | Monoculture vs agroforestry / habitat complexity |
| `04_cover_crops_semiarid_water.md` | Cover crops and water-holding in semi-arid farming |
| `05_pollution_urban_species_richness.md` | Pollution, urban expansion, species richness |
| `06_temperature_drought_vegetation.md` | Temperature, drought, vegetation stress |
| `07_deforestation_fragmentation_biodiversity.md` | Deforestation, fragmentation, biodiversity |
| `08_land_use_change_cover.md` | Land-use change, grasslands, forests, agriculture |

Metadata lives in `knowledge/manifest.json` (`source_type: darukaa_synthesis`).

Markdown pages are stored as `page=null` / `page_is_real=false`. Ingested PDFs keep printer page numbers.

In Docker, seed sources are copied into the image. Uploaded PDFs are written to `PDF_DIR` (`/data/pdfs` in Compose) so they survive container restarts.
