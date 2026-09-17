# Database and vector schema

Runtime data lives in `DATA_DIR` (default `./data`). It is gitignored.

## SQLite `darukaa.sqlite`

### `conversations`

| Column | Type | Notes |
| --- | --- | --- |
| id | TEXT PK | Session UUID |
| created_at | TEXT | ISO timestamp |
| updated_at | TEXT | ISO timestamp |
| context_json | TEXT | `EnvironmentalContext` JSON |

### `messages`

| Column | Type | Notes |
| --- | --- | --- |
| id | INTEGER PK | Auto |
| session_id | TEXT | FK conversations |
| role | TEXT | user / assistant |
| content | TEXT | Message body |
| created_at | TEXT | ISO timestamp |

### `documents`

| Column | Type | Notes |
| --- | --- | --- |
| id | INTEGER PK | Auto |
| name | TEXT UNIQUE | File name |
| source | TEXT | Source / document name |
| document_type | TEXT | pdf_report, markdown_report, … |
| topic | TEXT | Inferred category |
| pages | INTEGER | Page count |
| checksum | TEXT | SHA-256 of extracted text |
| created_at | TEXT | ISO timestamp |

### `chunks`

| Column | Type | Notes |
| --- | --- | --- |
| id | INTEGER PK | Auto |
| document_id | INTEGER | FK documents |
| page | INTEGER | Page number where applicable |
| chunk_index | INTEGER | Order within document |
| text | TEXT | Cleaned passage |
| topic | TEXT | Chunk-level topic |

## Vector store `vectors.npz`

| Array | Meaning |
| --- | --- |
| `vectors` | float32 matrix, one L2-oriented row per chunk |
| `ids` | chunk primary keys aligned to rows |
| `backend` | embedding backend name |

Rebuild with `POST /api/knowledge/rebuild` or `python scripts/kb.py rebuild`.

## Environmental context JSON

```json
{
  "location": { "region": null, "location": null, "latitude": null, "longitude": null },
  "soil": { "ph": null, "organic_carbon": null, "organic_carbon_label": null, "moisture": null },
  "land": { "land_use": null, "land_cover": null, "crop": null, "fragmentation": null, "intercropping": null },
  "biodiversity": {
    "species_richness": null,
    "habitat_diversity": null,
    "plant_diversity": null,
    "pollinator_diversity": null,
    "microbial_diversity": null,
    "species_survival": null
  },
  "climate": {
    "temperature": null,
    "rainfall": null,
    "drought": null,
    "water_availability": null,
    "climate_stress": null
  },
  "human_impact": {
    "pollution": null,
    "deforestation": null,
    "land_degradation": null,
    "habitat_destruction": null
  }
}
```

The schema is additive: new keys can be stored without a migration if they are added to `EnvironmentalContext`.
