import { FormEvent, KeyboardEvent, ReactNode, useEffect, useState } from "react";
import { searchLocations } from "../api";
import {
  LAND_USE_OPTIONS,
  LandDetails,
  LEVEL_OPTIONS,
  PESTICIDE_OPTIONS,
} from "../landDetails";
import { LocationPicker } from "./LocationPicker";

type Props = {
  details: LandDetails;
  onChange: (next: LandDetails) => void;
  onClose: () => void;
  enableMap?: boolean;
};

function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="land-field">
      <span className="tiny">{label}</span>
      {children}
    </label>
  );
}

export function LandDetailsForm({ details, onChange, onClose, enableMap = true }: Props) {
  const [query, setQuery] = useState(details.location);
  const [results, setResults] = useState<{ label: string; latitude: number; longitude: number }[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  useEffect(() => {
    setQuery(details.location);
  }, [details.location]);

  function patch(partial: Partial<LandDetails>) {
    onChange({ ...details, ...partial });
  }

  async function search(event?: FormEvent) {
    event?.preventDefault();
    const text = query.trim();
    if (text.length < 2) {
      setResults([]);
      return;
    }
    setSearching(true);
    setSearchError(null);
    try {
      const rows = await searchLocations(text);
      setResults(rows);
      if (!rows.length) setSearchError("No matching places. You can still click the map.");
    } catch {
      setSearchError("Location search is unavailable. Click the map or type coordinates.");
    } finally {
      setSearching(false);
    }
  }

  const lat = details.latitude.trim() ? Number(details.latitude) : null;
  const lng = details.longitude.trim() ? Number(details.longitude) : null;

  return (
    <div
      className="land-form"
      data-testid="land-details-form"
      onKeyDown={(event: KeyboardEvent<HTMLDivElement>) => {
        if (event.key === "Enter" && (event.target as HTMLElement).tagName !== "TEXTAREA") {
          event.preventDefault();
        }
      }}
    >
      <div className="land-form-head">
        <div>
          <p className="kicker">Optional land details</p>
          <p className="tiny">Fill only what you know. Empty fields stay empty — the scientist will ask if they are needed.</p>
        </div>
        <button className="btn ghost" type="button" onClick={onClose}>
          Close
        </button>
      </div>
      <div className="land-grid">
        <Field label="Farm size">
          <input value={details.farm_size} onChange={(event) => patch({ farm_size: event.target.value })} placeholder="e.g. 10 acres" />
        </Field>
        <Field label="Crop / vegetation">
          <input value={details.crop} onChange={(event) => patch({ crop: event.target.value })} placeholder="e.g. wheat" />
        </Field>
        <Field label="Land-use type">
          <select value={details.land_use} onChange={(event) => patch({ land_use: event.target.value })}>
            {LAND_USE_OPTIONS.map((option) => (
              <option key={option || "blank"} value={option}>
                {option || "Not specified"}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Soil pH">
          <input inputMode="decimal" value={details.soil_ph} onChange={(event) => patch({ soil_ph: event.target.value })} placeholder="e.g. 8.1" />
        </Field>
        <Field label="Soil organic carbon">
          <input inputMode="decimal" value={details.soil_organic_carbon} onChange={(event) => patch({ soil_organic_carbon: event.target.value })} placeholder="e.g. 0.3" />
        </Field>
        <Field label="Soil moisture">
          <select value={details.soil_moisture} onChange={(event) => patch({ soil_moisture: event.target.value })}>
            {LEVEL_OPTIONS.map((option) => (
              <option key={option || "blank"} value={option}>
                {option || "Not specified"}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Rainfall">
          <select value={details.rainfall} onChange={(event) => patch({ rainfall: event.target.value })}>
            {LEVEL_OPTIONS.map((option) => (
              <option key={option || "blank"} value={option}>
                {option || "Not specified"}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Temperature">
          <input inputMode="decimal" value={details.temperature} onChange={(event) => patch({ temperature: event.target.value })} placeholder="°C" />
        </Field>
        <Field label="Pesticide use">
          <select value={details.pollution} onChange={(event) => patch({ pollution: event.target.value })}>
            {PESTICIDE_OPTIONS.map((option) => (
              <option key={option || "blank"} value={option}>
                {option || "Not specified"}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <Field label="Biodiversity observations">
        <input
          value={details.biodiversity_observations}
          onChange={(event) => patch({ biodiversity_observations: event.target.value })}
          placeholder="e.g. fewer bees and butterflies"
        />
      </Field>
      <div className="land-location">
        <p className="tiny" style={{ marginBottom: 6 }}>Location — search, or click the map</p>
        <div className="land-search-row">
          <input
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              patch({ location: event.target.value });
            }}
            placeholder="Search a place or type a location"
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                void search();
              }
            }}
          />
          <button className="btn ghost" type="button" onClick={() => void search()} disabled={searching}>
            {searching ? "Searching…" : "Search"}
          </button>
        </div>
        {searchError && <p className="tiny">{searchError}</p>}
        {results.length > 0 && (
          <ul className="land-search-results">
            {results.map((row) => (
              <li key={`${row.latitude}-${row.longitude}-${row.label}`}>
                <button
                  type="button"
                  onClick={() => {
                    patch({
                      location: row.label,
                      latitude: String(row.latitude),
                      longitude: String(row.longitude),
                    });
                    setQuery(row.label);
                    setResults([]);
                  }}
                >
                  {row.label}
                </button>
              </li>
            ))}
          </ul>
        )}
        {enableMap && (
          <LocationPicker
            latitude={Number.isFinite(lat) ? lat : null}
            longitude={Number.isFinite(lng) ? lng : null}
            onSelect={(nextLat, nextLng) => patch({ latitude: String(nextLat), longitude: String(nextLng) })}
          />
        )}
        <div className="land-grid">
          <Field label="Latitude">
            <input
              inputMode="decimal"
              value={details.latitude}
              onChange={(event) => patch({ latitude: event.target.value })}
              placeholder="optional"
            />
          </Field>
          <Field label="Longitude">
            <input
              inputMode="decimal"
              value={details.longitude}
              onChange={(event) => patch({ longitude: event.target.value })}
              placeholder="optional"
            />
          </Field>
        </div>
      </div>
    </div>
  );
}
