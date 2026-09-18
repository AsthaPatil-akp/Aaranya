import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

type Props = {
  latitude: number | null;
  longitude: number | null;
  onSelect: (latitude: number, longitude: number) => void;
  expanded?: boolean;
};

export function LocationPicker({ latitude, longitude, onSelect, expanded = false }: Props) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const markerRef = useRef<L.CircleMarker | null>(null);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  function placeMarker(map: L.Map, lat: number, lng: number) {
    markerRef.current?.remove();
    markerRef.current = L.circleMarker([lat, lng], {
      radius: 8,
      color: "#16382c",
      fillColor: "#c6e07a",
      fillOpacity: 1,
      weight: 2,
    }).addTo(map);
    map.setView([lat, lng], Math.max(map.getZoom() || 4, 11));
    window.setTimeout(() => map.invalidateSize(), 50);
    window.setTimeout(() => map.invalidateSize(), 220);
  }

  useEffect(() => {
    if (!hostRef.current || mapRef.current) return;
    const start: L.LatLngExpression =
      latitude != null && longitude != null ? [latitude, longitude] : [22.5, 79];
    const map = L.map(hostRef.current, { scrollWheelZoom: false }).setView(start, latitude != null ? 11 : 4);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap",
      maxZoom: 18,
    }).addTo(map);
    map.on("click", (event: L.LeafletMouseEvent) => {
      onSelectRef.current(Number(event.latlng.lat.toFixed(5)), Number(event.latlng.lng.toFixed(5)));
    });
    mapRef.current = map;
    if (latitude != null && longitude != null) placeMarker(map, latitude, longitude);
    const redraw = () => map.invalidateSize();
    setTimeout(redraw, 80);
    setTimeout(redraw, 250);
    const observer = new ResizeObserver(() => redraw());
    observer.observe(hostRef.current);
    return () => {
      observer.disconnect();
      map.remove();
      mapRef.current = null;
      markerRef.current = null;
    };
    // Initial view only; later moves are handled below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || latitude == null || longitude == null) return;
    placeMarker(map, latitude, longitude);
  }, [latitude, longitude]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (expanded) map.scrollWheelZoom.enable();
    else map.scrollWheelZoom.disable();
    const first = window.setTimeout(() => map.invalidateSize(), 60);
    const second = window.setTimeout(() => map.invalidateSize(), 220);
    return () => {
      window.clearTimeout(first);
      window.clearTimeout(second);
    };
  }, [expanded]);

  return <div className={`land-map${expanded ? " expanded" : ""}`} ref={hostRef} role="application" aria-label="Select a point on the map" />;
}
