"use client";
import { useEffect, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import type { GeoJSONSource } from "maplibre-gl";
import {
  TerraDraw,
  TerraDrawPolygonMode,
  TerraDrawSelectMode,
  TerraDrawModeUndoRedo,
  TerraDrawSessionUndoRedo,
  TerraDrawUndoRedoKeyboardShortcuts,
} from "terra-draw";
import { TerraDrawMapLibreGLAdapter } from "terra-draw-maplibre-gl-adapter";
import type { FeatureCollection, Geometry } from "geojson";
import type { FieldGeometry } from "@/lib/geometry";
import { Button } from "@/components/ui/button";
import "maplibre-gl/dist/maplibre-gl.css";
export type MapItem = {
  id: string;
  name: string;
  geometry: Geometry;
  candidate?: boolean;
};
export function FieldMap({
  items,
  onDraw,
  onSelect,
  onBounds,
  focus,
  editable,
}: {
  items: MapItem[];
  onDraw: (geometry: FieldGeometry) => void;
  onSelect: (id: string) => void;
  onBounds: (bounds: number[]) => void;
  focus?: number[];
  editable?: FieldGeometry;
}) {
  const container = useRef<HTMLDivElement>(null),
    mapRef = useRef<maplibregl.Map | null>(null),
    drawRef = useRef<TerraDraw | null>(null);
  const callbacks = useRef({ onDraw, onSelect, onBounds });
  useEffect(() => {
    callbacks.current = { onDraw, onSelect, onBounds };
  }, [onDraw, onSelect, onBounds]);
  const [ready, setReady] = useState(false),
    [drawing, setDrawing] = useState(false),
    [error, setError] = useState("");
  useEffect(() => {
    if (!container.current) return;
    let map: maplibregl.Map;
    try {
      map = new maplibregl.Map({
        container: container.current,
        style: {
          version: 8,
          sources: {
            osm: {
              type: "raster",
              tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
              tileSize: 256,
              attribution:
                '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
              maxzoom: 19,
            },
          },
          layers: [
            {
              id: "base",
              type: "raster",
              source: "osm",
              paint: {
                "raster-saturation": -0.75,
                "raster-brightness-max": 0.62,
              },
            },
          ],
        },
        center: [13.035, 52.402],
        zoom: 11,
        attributionControl: { compact: true },
      });
    } catch {
      queueMicrotask(() =>
        setError(
          "WebGL недоступен. Поля доступны в списке; контур можно вставить как GeoJSON.",
        ),
      );
      return;
    }
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl(), "top-right");
    map.addControl(new maplibregl.ScaleControl(), "bottom-left");
    map.on("error", () =>
      setError(
        "Не удалось загрузить часть карты. Проверьте сеть; сохранённые контуры остаются доступны.",
      ),
    );
    map.on("load", () => {
      map.addSource("fields", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer({
        id: "fields-fill",
        type: "fill",
        source: "fields",
        paint: {
          "fill-color": ["case", ["get", "candidate"], "#dcb969", "#5df0a8"],
          "fill-opacity": 0.2,
        },
      });
      map.addLayer({
        id: "fields-line",
        type: "line",
        source: "fields",
        paint: {
          "line-color": ["case", ["get", "candidate"], "#dcb969", "#5df0a8"],
          "line-width": 2,
        },
      });
      const draw = new TerraDraw({
        undoRedo: {
          modeLevel: new TerraDrawModeUndoRedo(),
          sessionLevel: new TerraDrawSessionUndoRedo(),
          keyboardShortcuts: new TerraDrawUndoRedoKeyboardShortcuts(),
        },
        adapter: new TerraDrawMapLibreGLAdapter({
          map,
          coordinatePrecision: 7,
        }),
        modes: [
          new TerraDrawPolygonMode({
            keyEvents: { cancel: "Escape", finish: "Enter" },
          }),
          new TerraDrawSelectMode({
            flags: {
              polygon: {
                feature: {
                  draggable: true,
                  coordinates: {
                    draggable: true,
                    midpoints: true,
                    deletable: true,
                  },
                },
              },
            },
          }),
        ],
      });
      draw.start();
      drawRef.current = draw;
      draw.on("change", () => {
        if (draw.getMode() !== "select") return;
        const polygons = draw
          .getSnapshot()
          .filter(
            (f) =>
              f.properties.mode === "polygon" && f.geometry.type === "Polygon",
          );
        if (polygons.length)
          callbacks.current.onDraw({
            type: "MultiPolygon",
            coordinates: polygons.map(
              (f) => (f.geometry as GeoJSON.Polygon).coordinates,
            ),
          } as FieldGeometry);
      });
      draw.on("finish", (id) => {
        const f = draw.getSnapshot().find((f) => f.id === id);
        if (f?.geometry.type === "Polygon") {
          callbacks.current.onDraw(f.geometry as FieldGeometry);
          draw.setMode("static");
          setDrawing(false);
        }
      });
      setReady(true);
      const b = map.getBounds();
      callbacks.current.onBounds([
        b.getWest(),
        b.getSouth(),
        b.getEast(),
        b.getNorth(),
      ]);
    });
    map.on("moveend", () => {
      const b = map.getBounds();
      callbacks.current.onBounds([
        b.getWest(),
        b.getSouth(),
        b.getEast(),
        b.getNorth(),
      ]);
    });
    map.on("click", "fields-fill", (e) => {
      if (drawRef.current?.getMode() === "polygon") return;
      const id = e.features?.[0]?.properties?.id;
      if (id) callbacks.current.onSelect(String(id));
    });
    return () => {
      drawRef.current?.stop();
      drawRef.current = null;
      map.remove();
      mapRef.current = null;
    };
  }, []);
  useEffect(() => {
    if (!ready || !editable || !drawRef.current) return;
    const draw = drawRef.current;
    draw.clear();
    const coordinates =
      editable.type === "Polygon"
        ? [editable.coordinates]
        : editable.coordinates;
    draw.addFeatures(
      coordinates.map((c, i) => ({
        type: "Feature" as const,
        id: `edit-${i}`,
        geometry: { type: "Polygon" as const, coordinates: c },
        properties: { mode: "polygon" },
      })),
    );
    draw.setMode("select");
  }, [ready, editable]);
  useEffect(() => {
    if (!ready) return;
    const data: FeatureCollection = {
      type: "FeatureCollection",
      features: items.map((i) => ({
        type: "Feature",
        geometry: i.geometry,
        properties: { id: i.id, name: i.name, candidate: !!i.candidate },
      })),
    };
    (mapRef.current?.getSource("fields") as GeoJSONSource | undefined)?.setData(
      data,
    );
  }, [items, ready]);
  useEffect(() => {
    if (ready && focus?.length === 4)
      mapRef.current?.fitBounds(
        [
          [focus[0], focus[1]],
          [focus[2], focus[3]],
        ],
        {
          padding: 65,
          maxZoom: 16,
          duration: window.matchMedia("(prefers-reduced-motion: reduce)")
            .matches
            ? 0
            : 650,
        },
      );
  }, [focus, ready]);
  return (
    <div className="map-wrap">
      <div
        ref={container}
        className="map-canvas"
        role="region"
        aria-label="Карта полей"
      />
      <div className="map-tools">
        <Button
          disabled={!ready}
          onClick={() => {
            drawRef.current?.clear();
            drawRef.current?.setMode(drawing ? "static" : "polygon");
            setDrawing(!drawing);
          }}
        >
          {drawing ? "Отменить рисование" : "Нарисовать контур"}
        </Button>
        {editable && (
          <Button
            variant="outline"
            disabled={!ready}
            onClick={() => {
              drawRef.current?.setMode("select");
              setDrawing(false);
            }}
          >
            Изменить вершины
          </Button>
        )}
        {drawing && (
          <Button variant="outline" onClick={() => drawRef.current?.undo()}>
            Отменить вершину
          </Button>
        )}
        {drawing && (
          <span className="map-hint">
            Добавляйте вершины кликом. Нажмите первую точку, чтобы замкнуть
            контур. Enter — завершить, Esc — сбросить, Ctrl+Z — отменить
            вершину.
          </span>
        )}
      </div>
      {error && (
        <div className="map-error" role="status">
          {error}
        </div>
      )}
      <div className="map-legend">
        <span>
          <i />
          Ваши поля
        </span>
        <span>
          <i className="candidate" />
          Контуры OSM
        </span>
      </div>
    </div>
  );
}
