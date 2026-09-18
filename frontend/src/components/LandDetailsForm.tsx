import { FormEvent, KeyboardEvent as ReactKeyboardEvent, ReactNode, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { searchLocations } from "../api";
import {
  LAND_USE_OPTIONS,
  LandDetails,
  LEVEL_OPTIONS,
  PESTICIDE_OPTIONS,
  TEMPERATURE_MAX_C,
  TEMPERATURE_MIN_C,
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
  const [mapExpanded, setMapExpanded] = useState(false);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const detailsRef = useRef(details);
  detailsRef.current = details;
  const queryRef = useRef(query);
  queryRef.current = query;
  const mapExpandedRef = useRef(false);
  mapExpandedRef.current = mapExpanded;
  const searchGeneration = useRef(0);

  function patch(partial: Partial<LandDetails>) {
    onChange({ ...detailsRef.current, ...partial });
  }

  function applyPlace(row: { label: string; latitude: number; longitude: number }, label = row.label) {
    patch({
      location: label,
      latitude: String(row.latitude),
      longitude: String(row.longitude),
    });
    setQuery(label);
  }

  function finish() {
    const location = queryRef.current.trim();
    if (location !== detailsRef.current.location) {
      onChange({ ...detailsRef.current, location });
    }
    onClose();
  }

  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialogRef.current?.focus();
    function onKey(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      if (mapExpandedRef.current) {
        event.preventDefault();
        setMapExpanded(false);
        return;
      }
      finish();
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previous;
      document.removeEventListener("keydown", onKey);
    };
    // Focus and escape handling belong to this dialog instance only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function search(event?: FormEvent, mode: "suggest" | "pin" = "suggest") {
    event?.preventDefault();
    const text = queryRef.current.trim();
    patch({ location: text });
    if (text.length < 2) {
      setResults([]);
      return;
    }
    const generation = ++searchGeneration.current;
    setSearching(true);
    setSearchError(null);
    try {
      const rows = await searchLocations(text);
      if (generation !== searchGeneration.current) return;
      setResults(rows);
      if (!rows.length) {
        setSearchError("No matching places. You can still click the map.");
        return;
      }
      if (mode === "pin") {
        applyPlace(rows[0]);
        return;
      }
      patch({
        location: text,
        latitude: String(rows[0].latitude),
        longitude: String(rows[0].longitude),
      });
    } catch {
      if (generation !== searchGeneration.current) return;
      setResults([]);
      setSearchError("Location search is unavailable. Click the map or type coordinates.");
    } finally {
      if (generation === searchGeneration.current) setSearching(false);
    }
  }

  useEffect(() => {
    const text = query.trim();
    if (text.length < 2) return;
    const handle = window.setTimeout(() => {
      void search(undefined, "suggest");
    }, 400);
    return () => window.clearTimeout(handle);
    // Search after the user pauses so a full place name can be typed first.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);

  const lat = details.latitude.trim() ? Number(details.latitude) : null;
  const lng = details.longitude.trim() ? Number(details.longitude) : null;

  const dialog = (
    <div
      className="land-dialog-backdrop"
      data-testid="land-details-dialog"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) finish();
      }}
    >
      <div
        className="land-form"
        role="dialog"
        aria-modal="true"
        aria-labelledby="land-details-title"
        data-testid="land-details-form"
        tabIndex={-1}
        ref={dialogRef}
        onKeyDown={(event: ReactKeyboardEvent<HTMLDivElement>) => {
          if (event.key === "Enter" && (event.target as HTMLElement).tagName !== "TEXTAREA") {
            event.preventDefault();
          }
        }}
      >
        <div className="land-form-head">
          <div>
            <p className="kicker">Optional land details</p>
            <h3 id="land-details-title">Add land details</h3>
            <p className="tiny">Fill only what you know. Empty fields stay empty — the scientist will ask if they are needed.</p>
          </div>
          <div className="land-form-head-actions">
            <button className="btn ghost" type="button" onClick={finish}>
              Close
            </button>
            <button className="btn primary" type="button" onClick={finish}>
              Done
            </button>
          </div>
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
            <input
              type="number"
              inputMode="decimal"
              min={TEMPERATURE_MIN_C}
              max={TEMPERATURE_MAX_C}
              step="any"
              value={details.temperature}
              onChange={(event) => patch({ temperature: event.target.value })}
              placeholder="°C"
            />
          </Field>
          <Field label="Pesticide use">
            <select value={details.pesticide_use} onChange={(event) => patch({ pesticide_use: event.target.value })}>
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
              onChange={(event) => setQuery(event.target.value)}
              onBlur={() => patch({ location: query.trim() })}
              placeholder="Search a place or type a location"
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  void search(undefined, "pin");
                }
              }}
            />
            <button className="btn ghost" type="button" onClick={() => void search(undefined, "pin")} disabled={searching}>
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
                      applyPlace(row);
                      setResults([]);
                      setSearchError(null);
                    }}
                  >
                    {row.label}
                  </button>
                </li>
              ))}
            </ul>
          )}
          {enableMap && !mapExpanded && (
            <div className="land-map-stage" data-testid="land-map-stage">
              <LocationPicker
                latitude={Number.isFinite(lat) ? lat : null}
                longitude={Number.isFinite(lng) ? lng : null}
                onSelect={(nextLat, nextLng) => patch({ latitude: String(nextLat), longitude: String(nextLng) })}
              />
              <button type="button" className="btn ghost" onClick={() => setMapExpanded(true)}>
                View large map
              </button>
            </div>
          )}
          {enableMap &&
            mapExpanded &&
            createPortal(
              <div className="land-map-stage expanded" data-testid="land-map-stage">
                <div className="land-map-toolbar">
                  <p className="tiny">Click the map to set a point</p>
                  <div className="land-form-head-actions">
                    <button
                      type="button"
                      className="land-map-x"
                      aria-label="Close large map"
                      onClick={() => setMapExpanded(false)}
                    >
                      ×
                    </button>
                    <button type="button" className="btn ghost" onClick={() => setMapExpanded(false)}>
                      Cancel
                    </button>
                  </div>
                </div>
                <LocationPicker
                  expanded
                  latitude={Number.isFinite(lat) ? lat : null}
                  longitude={Number.isFinite(lng) ? lng : null}
                  onSelect={(nextLat, nextLng) => patch({ latitude: String(nextLat), longitude: String(nextLng) })}
                />
              </div>,
              document.body,
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
    </div>
  );

  return createPortal(dialog, document.body);
}
