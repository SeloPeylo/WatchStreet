// The world map. Shape carries the status, colour carries the chosen colour mode; assets
// without enough data are hatched grey so "unknown" never looks like the middle of a scale.
import * as maplibregl from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import { useEffect, useRef } from "react";
import { feature } from "topojson-client";
import type { Commodity, Json } from "./api";
import { STATUS_LABEL } from "./api";

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

interface Props {
  features: Json[];
  events: Json[];
  mode: string;
  commodities: Commodity[];
  selected: number[];
  active: number | null;
  company: string;
  focus: number[]; // asset ids to frame (e.g. those of a thesis)
  onPick: (id: number, add: boolean) => void;
}

export function MapView(props: Props) {
  const node = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const ready = useRef(false);
  const pins = useRef<maplibregl.Marker[]>([]);
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
      attributionControl: false,
      dragRotate: false,
    });
    map.current = m;
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 14 });
    m.on("load", async () => {
      const topology = await (await fetch("/static/vendor/countries-110m.json")).json();
      m.addSource("countries", { type: "geojson", data: feature(topology, topology.objects.countries) as Json });
      m.addLayer({ id: "land", type: "fill", source: "countries", paint: { "fill-color": color("--land") } });
      m.addLayer({ id: "borders", type: "line", source: "countries", paint: { "line-color": color("--border"), "line-width": 0.6 } });
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
      ready.current = true;
      draw();
    });
    return () => m.remove();
  }, []);

  useEffect(draw, [props.features, props.events, props.mode, props.commodities, props.selected.join(","), props.company]);

  useEffect(() => {
    const m = map.current;
    const hit = props.features.find((f) => f.id === props.active);
    if (m && hit && !m.getBounds().contains(hit.geometry.coordinates)) m.easeTo({ center: hit.geometry.coordinates });
  }, [props.active]);

  useEffect(() => {
    const m = map.current;
    const points = props.features.filter((f) => props.focus.includes(f.id)).map((f) => f.geometry.coordinates);
    if (!m || points.length === 0) return;
    const bounds = points.reduce((b, point) => b.extend(point), new maplibregl.LngLatBounds(points[0], points[0]));
    m.fitBounds(bounds, { padding: 80, maxZoom: 5 });
  }, [props.focus.join(","), props.features.length]);

  return <div ref={node} className="map" data-testid="map" />;
}
