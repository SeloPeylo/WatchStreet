// The world map. Shape carries the status, colour carries the chosen colour mode; assets
// without enough data are hatched grey so "unknown" never looks like the middle of a scale.
import * as maplibregl from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import { useEffect, useRef } from "react";
import { feature } from "topojson-client";
import type { Commodity, Json } from "./api";
import { STATUS_LABEL, day, get, num } from "./api";

export const SHAPES: Record<string, string> = {
  production: "circle",
  development: "diamond",
  exploration: "triangle",
  care_maintenance: "square",
  closed: "square",
  unknown: "square",
};
const DIVERGING = ["#b35806", "#f1a340", "#fee0b6", "#c9ced6", "#d1e5f0", "#67a9cf", "#2166ac"];
const SEQUENTIAL = ["#c6dbef", "#6baed6", "#2171b5", "#08306b"];
export const KNOWLEDGE_COLORS: Record<string, string> = {
  unexamined: "#9aa5b1",
  known: "#67a9cf",
  deep: "#2166ac",
  new: "#1a7f52",
  stale: "#b26a00",
};
export const SCALES: Record<string, { stops: number[]; colors: string[]; percent: boolean }> = {
  margin: { stops: [-0.2, 0, 0.15, 0.3, 0.45, 0.6], colors: DIVERGING, percent: true },
  delta: { stops: [-0.2, -0.1, -0.02, 0.02, 0.1, 0.2], colors: DIVERGING, percent: true },
  quality: { stops: [0.25, 0.5, 0.75], colors: SEQUENTIAL, percent: true },
};
const UNKNOWN = "hatch";
const BADGES: Record<string, string> = { running: "#1f6feb", new_result: "#1a7f52", open: "#e0a030" };
const SIZE = 26;
const DETAIL_ZOOM = 12; // close enough to tell neighbouring deposits apart

/** Background maps. Tiles come from the provider straight to the browser; "plain" needs no network. */
export const BASEMAPS: Record<string, { label: string; tiles: string[]; maxzoom: number; attribution: string }> = {
  streets: {
    label: "Karte (Orte, Strassen)",
    tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
    maxzoom: 19,
    attribution: "© OpenStreetMap-Mitwirkende",
  },
  terrain: {
    label: "Gelände (Höhenlinien)",
    tiles: ["a", "b", "c"].map((host) => `https://${host}.tile.opentopomap.org/{z}/{x}/{y}.png`),
    maxzoom: 17,
    attribution: "Kartendaten © OpenStreetMap-Mitwirkende, SRTM · Darstellung © OpenTopoMap (CC-BY-SA)",
  },
  plain: { label: "Schema (ohne Netz)", tiles: [], maxzoom: 0, attribution: "" },
};

// MapLibre 6 ships its worker as a separate module; Vite bundles it and hands us the URL.
maplibregl.setWorkerUrl(workerUrl);

/** Colour of one asset in the given mode, or "hatch" when the value is unknown. */
export function colorFor(props: Json, mode: string, commodities: Commodity[]): string {
  if (mode === "status") return commodities.find((c) => c.key === props.commodity)?.color ?? "#777";
  if (mode === "knowledge") return KNOWLEDGE_COLORS[props.knowledge] ?? "#777";
  if (props.color_value === null || props.color_value === undefined) return UNKNOWN;
  const scale = SCALES[mode];
  const index = scale.stops.findIndex((stop) => props.color_value < stop);
  return scale.colors[index === -1 ? scale.colors.length - 1 : index];
}

function tracePath(ctx: CanvasRenderingContext2D, shape: string, size: number): void {
  const c = size / 2;
  const r = size / 2 - 3;
  ctx.beginPath();
  if (shape === "circle") ctx.arc(c, c, r, 0, Math.PI * 2);
  else if (shape === "diamond") {
    ctx.moveTo(c, c - r - 1);
    ctx.lineTo(c + r + 1, c);
    ctx.lineTo(c, c + r + 1);
    ctx.lineTo(c - r - 1, c);
  } else if (shape === "triangle") {
    ctx.moveTo(c, c - r - 1);
    ctx.lineTo(c + r + 1, c + r - 1);
    ctx.lineTo(c - r - 1, c + r - 1);
  } else ctx.rect(c - r + 1, c - r + 1, 2 * r - 2, 2 * r - 2);
  ctx.closePath();
}

function drawIcon(shape: string, color: string): ImageData {
  const size = SIZE * 2; // rendered at pixel ratio 2
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext("2d")!;
  tracePath(ctx, shape, size);
  if (color === UNKNOWN) {
    ctx.save();
    ctx.clip();
    ctx.fillStyle = "#eceff3";
    ctx.fillRect(0, 0, size, size);
    ctx.strokeStyle = "#7c8794";
    ctx.lineWidth = 3;
    for (let x = -size; x < size * 2; x += 9) {
      ctx.beginPath();
      ctx.moveTo(x, size);
      ctx.lineTo(x + size, 0);
      ctx.stroke();
    }
    ctx.restore();
    tracePath(ctx, shape, size);
    ctx.strokeStyle = "#7c8794";
  } else {
    ctx.fillStyle = color;
    ctx.fill();
    ctx.strokeStyle = "#ffffff";
  }
  ctx.lineWidth = 3.5;
  ctx.stroke();
  return ctx.getImageData(0, 0, size, size);
}

function drawDot(color: string, ring = false): ImageData {
  const size = ring ? 44 : 22;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext("2d")!;
  ctx.beginPath();
  ctx.arc(size / 2, size / 2, size / 2 - 3, 0, Math.PI * 2);
  if (!ring) {
    ctx.fillStyle = color;
    ctx.fill();
  }
  ctx.strokeStyle = ring ? color : "#fff";
  ctx.lineWidth = ring ? 4 : 3;
  ctx.stroke();
  return ctx.getImageData(0, 0, size, size);
}

const HALF_TURN = 180;

/**
 * Country shapes that cross the date line (Russia, Fiji) arrive with longitudes jumping from
 * +180 to -180, which the renderer draws as a band across the whole world. Shifting the western
 * part by a full turn keeps each ring continuous.
 */
function unwrapped(collection: Json): Json {
  const ring = (points: number[][]) =>
    points.some((point, i) => i > 0 && Math.abs(point[0] - points[i - 1][0]) > HALF_TURN)
      ? points.map(([lon, lat]) => [lon < 0 ? lon + 2 * HALF_TURN : lon, lat])
      : points;
  const polygon = (rings: number[][][]) => rings.map(ring);
  const features = collection.features.map((f: Json) => {
    const g = f.geometry;
    if (g?.type === "Polygon") return { ...f, geometry: { ...g, coordinates: polygon(g.coordinates) } };
    if (g?.type === "MultiPolygon") return { ...f, geometry: { ...g, coordinates: g.coordinates.map(polygon) } };
    return f;
  });
  return { ...collection, features };
}

/** Lines for the popup that answers "who holds this ground". Register text is set as text only. */
function claimLines(found: Json): HTMLElement[] {
  const line = (text: string, className = "") => {
    const el = document.createElement("div");
    el.textContent = text;
    el.className = className;
    return el;
  };
  if (!found.register) return [line("Für diese Region ist noch kein amtliches Register angebunden.")];
  if (found.claims.length === 0) return [line("Hier ist kein Titel eingetragen."), line(found.register.authority, "small muted")];
  const rows = found.claims.flatMap((c: Json) => [
    line(`${c.holder || "Inhaber unbekannt"}${c.other_holders ? ` (+${c.other_holders} weitere)` : ""}`, "holder"),
    line([c.kind, c.name, `Nr. ${c.number}`, c.status, c.area_ha !== null ? `${num(c.area_ha)} ha` : "", c.expires ? `gültig bis ${day(c.expires)}` : ""].filter(Boolean).join(" · "), "small"),
  ]);
  return [...rows, line(`Quelle: ${found.register.authority}, live abgefragt`, "small muted")];
}

interface Props {
  features: Json[];
  events: Json[];
  mode: string;
  commodities: Commodity[];
  selected: number[];
  active: number | null;
  company: string;
  basemap: string;
  zoomTick: number; // counts requests to zoom in on the active asset
  claims: boolean; // overlay official tenure registers and answer clicks on the ground
  focus: number[]; // asset ids to frame (e.g. those of a thesis)
  onPick: (id: number, add: boolean) => void;
  onBounds: (box: { south: number; west: number; north: number; east: number }) => void;
}

export function MapView(props: Props) {
  const node = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const ready = useRef(false);
  const pins = useRef<maplibregl.Marker[]>([]);
  const claimLayers = useRef<string[]>([]);
  const latest = useRef(props);
  latest.current = props;

  const draw = () => {
    const m = map.current;
    if (!m || !ready.current) return;
    const p = latest.current;
    const assets = p.features.map((f) => {
      const shape = SHAPES[f.properties.status] ?? "square";
      const color = colorFor(f.properties, p.mode, p.commodities);
      const icon = `${shape}-${color}`;
      if (!m.hasImage(icon)) m.addImage(icon, drawIcon(shape, color), { pixelRatio: 2 });
      const badge = f.properties.running ? "running" : f.properties.new_result ? "new_result" : f.properties.open_questions ? "open" : "";
      const dimmed = p.company !== "" && !String(f.properties.company_ids).split(",").includes(p.company);
      return { ...f, properties: { ...f.properties, icon, badge, dimmed } };
    });
    (m.getSource("assets") as maplibregl.GeoJSONSource).setData({ type: "FeatureCollection", features: assets });
    (m.getSource("events") as maplibregl.GeoJSONSource).setData({
      type: "FeatureCollection",
      features: p.events
        .filter((e) => e.lat !== null)
        .map((e) => ({ type: "Feature", geometry: { type: "Point", coordinates: [e.lon, e.lat] }, properties: { title: e.title } })),
    });
    pins.current.forEach((pin) => pin.remove());
    pins.current = p.selected.flatMap((id, index) => {
      const hit = p.features.find((f) => f.id === id);
      if (!hit) return [];
      const element = document.createElement("div");
      element.className = "pin";
      element.textContent = String(index + 1);
      return [new maplibregl.Marker({ element }).setLngLat(hit.geometry.coordinates).addTo(m)];
    });
  };

  useEffect(() => {
    const css = getComputedStyle(document.documentElement);
    const color = (name: string) => css.getPropertyValue(name).trim();
    const m = new maplibregl.Map({
      container: node.current!,
      style: { version: 8, sources: {}, layers: [{ id: "sea", type: "background", paint: { "background-color": color("--sea") } }] },
      center: [-35, 8],
      zoom: 1.5,
      attributionControl: { compact: true },
      dragRotate: false,
    });
    map.current = m;
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    m.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-right");
    const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 14 });
    m.on("load", async () => {
      const topology = await (await fetch("/static/vendor/countries-110m.json")).json();
      m.addSource("countries", { type: "geojson", data: unwrapped(feature(topology, topology.objects.countries) as Json) });
      m.addLayer({ id: "land", type: "fill", source: "countries", paint: { "fill-color": color("--land") } });
      m.addLayer({ id: "borders", type: "line", source: "countries", paint: { "line-color": color("--border"), "line-width": 0.6 } });
      for (const [key, base] of Object.entries(BASEMAPS)) {
        if (base.tiles.length === 0) continue;
        m.addSource(`base-${key}`, { type: "raster", tiles: base.tiles, tileSize: 256, maxzoom: base.maxzoom, attribution: base.attribution });
        m.addLayer({ id: `base-${key}`, type: "raster", source: `base-${key}`, layout: { visibility: key === latest.current.basemap ? "visible" : "none" } });
      }
      for (const register of (await get("/claims/registers").catch(() => [])) as Json[]) {
        m.addSource(`claims-${register.key}`, {
          type: "raster", tiles: [register.tiles], tileSize: 256, bounds: register.bounds, minzoom: register.min_zoom,
          attribution: `Konzessionen: ${register.authority}`,
        });
        m.addLayer({ id: `claims-${register.key}`, type: "raster", source: `claims-${register.key}`, paint: { "raster-opacity": 0.75 }, layout: { visibility: latest.current.claims ? "visible" : "none" } });
        claimLayers.current.push(`claims-${register.key}`);
      }
      for (const [name, hex] of Object.entries(BADGES)) m.addImage(`badge-${name}`, drawDot(hex), { pixelRatio: 2 });
      m.addImage("event", drawDot("#c0392b", true), { pixelRatio: 2 });
      const empty = { type: "FeatureCollection" as const, features: [] };
      m.addSource("assets", { type: "geojson", data: empty });
      m.addSource("events", { type: "geojson", data: empty });
      m.addLayer({ id: "events", type: "symbol", source: "events", layout: { "icon-image": "event", "icon-allow-overlap": true } });
      m.addLayer({
        id: "assets",
        type: "symbol",
        source: "assets",
        layout: { "icon-image": ["get", "icon"], "icon-allow-overlap": true },
        paint: { "icon-opacity": ["case", ["get", "dimmed"], 0.25, 1] },
      });
      m.addLayer({
        id: "badges",
        type: "symbol",
        source: "assets",
        filter: ["!=", ["get", "badge"], ""],
        layout: { "icon-image": ["concat", "badge-", ["get", "badge"]], "icon-offset": [10, -10], "icon-allow-overlap": true },
      });
      m.on("click", "assets", (e) => {
        const hit = e.features?.[0];
        if (hit) latest.current.onPick(Number(hit.properties.id), e.originalEvent.shiftKey);
      });
      m.on("click", async (e) => {
        if (!latest.current.claims || m.queryRenderedFeatures(e.point, { layers: ["assets"] }).length > 0) return;
        const box = document.createElement("div");
        box.className = "claims";
        box.textContent = "Frage das Register …";
        const info = new maplibregl.Popup({ maxWidth: "340px" }).setLngLat(e.lngLat).setDOMContent(box).addTo(m);
        try {
          const found = await get("/claims", { lat: String(e.lngLat.lat), lon: String(e.lngLat.lng) });
          box.textContent = "";
          box.append(...claimLines(found));
        } catch (error) {
          box.textContent = String((error as Error).message ?? error);
        }
        info.setDOMContent(box);
      });
      for (const layer of ["assets", "events"]) {
        m.on("mousemove", layer, (e) => {
          const hit = e.features?.[0];
          if (!hit) return;
          m.getCanvas().style.cursor = "pointer";
          const p = hit.properties;
          const text = layer === "events" ? p.title : `${p.name} · ${STATUS_LABEL[p.status] ?? p.status}${p.operator ? ` · ${p.operator}` : ""}`;
          popup.setLngLat((hit.geometry as Json).coordinates).setText(text).addTo(m);
        });
        m.on("mouseleave", layer, () => {
          m.getCanvas().style.cursor = "";
          popup.remove();
        });
      }
      const report = () => {
        const b = m.getBounds();
        latest.current.onBounds({ south: b.getSouth(), west: b.getWest(), north: b.getNorth(), east: b.getEast() });
      };
      m.on("moveend", report);
      report();
      ready.current = true;
      draw();
    });
    return () => m.remove();
  }, []);

  useEffect(draw, [props.features, props.events, props.mode, props.commodities, props.selected.join(","), props.company]);

  useEffect(() => {
    const m = map.current;
    if (!m || !ready.current) return;
    for (const id of claimLayers.current) m.setLayoutProperty(id, "visibility", props.claims ? "visible" : "none");
  }, [props.claims]);

  useEffect(() => {
    const m = map.current;
    if (!m || !ready.current) return;
    for (const key of Object.keys(BASEMAPS)) {
      if (m.getLayer(`base-${key}`)) m.setLayoutProperty(`base-${key}`, "visibility", key === props.basemap ? "visible" : "none");
    }
  }, [props.basemap]);

  useEffect(() => {
    const m = map.current;
    const hit = props.features.find((f) => f.id === props.active);
    if (m && hit && !m.getBounds().contains(hit.geometry.coordinates)) m.easeTo({ center: hit.geometry.coordinates });
  }, [props.active]);

  useEffect(() => {
    const m = map.current;
    const hit = props.features.find((f) => f.id === props.active);
    if (m && hit && props.zoomTick > 0) m.jumpTo({ center: hit.geometry.coordinates, zoom: DETAIL_ZOOM });
  }, [props.zoomTick]);

  useEffect(() => {
    const m = map.current;
    const points = props.features.filter((f) => props.focus.includes(f.id)).map((f) => f.geometry.coordinates);
    if (!m || points.length === 0) return;
    const bounds = points.reduce((b, point) => b.extend(point), new maplibregl.LngLatBounds(points[0], points[0]));
    m.fitBounds(bounds, { padding: 80, maxZoom: DETAIL_ZOOM });
  }, [props.focus.join(","), props.features.length]);

  return <div ref={node} className="map" data-testid="map" />;
}
