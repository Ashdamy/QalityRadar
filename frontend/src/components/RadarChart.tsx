"use client";

import type { AnalysisDimension } from "@/lib/api";

// Orden fijo de los ejes: si variara entre análisis, dos radares del mismo
// proyecto no serían comparables de un vistazo, que es justo para lo que sirve.
export const DIMENSION_ORDER = [
  "functional_suitability",
  "reliability",
  "security",
  "maintainability",
  "portability",
  "project_activity",
] as const;

export const DIMENSION_LABELS: Record<string, string> = {
  functional_suitability: "Adecuación",
  reliability: "Fiabilidad",
  security: "Seguridad",
  maintainability: "Mantenibilidad",
  portability: "Portabilidad",
  project_activity: "Actividad",
};

const SIZE = 320;
const CENTER = SIZE / 2;
const RADIUS = 110;
const RINGS = [0.25, 0.5, 0.75, 1];

function axisPoint(index: number, fraction: number) {
  // Se empieza arriba (-90°) y se reparten los ejes en circunferencia.
  const angle = (-90 + (360 / DIMENSION_ORDER.length) * index) * (Math.PI / 180);
  return {
    x: CENTER + Math.cos(angle) * RADIUS * fraction,
    y: CENTER + Math.sin(angle) * RADIUS * fraction,
  };
}

function polygon(scores: Map<string, number>, fractionScale = 1): string {
  return DIMENSION_ORDER.map((name, i) => {
    const score = scores.get(name) ?? 0;
    const p = axisPoint(i, (Math.max(0, Math.min(100, score)) / 100) * fractionScale);
    return `${p.x.toFixed(1)},${p.y.toFixed(1)}`;
  }).join(" ");
}

function ringPolygon(fraction: number): string {
  return DIMENSION_ORDER.map((_, i) => {
    const p = axisPoint(i, fraction);
    return `${p.x.toFixed(1)},${p.y.toFixed(1)}`;
  }).join(" ");
}

export function RadarChart({
  dimensions,
  previous,
}: {
  dimensions: AnalysisDimension[];
  previous?: AnalysisDimension[];
}) {
  const current = new Map(dimensions.map((d) => [d.name, d.score]));
  const before = previous ? new Map(previous.map((d) => [d.name, d.score])) : null;

  return (
    <svg
      width={SIZE}
      height={SIZE - 20}
      viewBox={`0 0 ${SIZE} ${SIZE}`}
      role="img"
      aria-label="Gráfico radar de las dimensiones ISO 25010"
      className="overflow-visible"
    >
      {RINGS.map((r) => (
        <polygon
          key={r}
          points={ringPolygon(r)}
          fill="none"
          className="stroke-border"
          strokeWidth={1}
          opacity={0.35 + r * 0.35}
        />
      ))}

      {DIMENSION_ORDER.map((_, i) => {
        const p = axisPoint(i, 1);
        return (
          <line
            key={i}
            x1={CENTER}
            y1={CENTER}
            x2={p.x}
            y2={p.y}
            className="stroke-border"
            strokeWidth={1}
          />
        );
      })}

      {/* El análisis anterior se superpone en línea discontinua para que el
          cambio se vea sin abrir la comparación. */}
      {before && (
        <polygon
          points={polygon(before)}
          fill="none"
          className="stroke-faint"
          strokeWidth={1.4}
          strokeDasharray="4 3"
          opacity={0.8}
        />
      )}

      <polygon
        points={polygon(current)}
        className="fill-accent stroke-accent"
        fillOpacity={0.16}
        strokeWidth={2}
      />

      {DIMENSION_ORDER.map((name, i) => {
        const score = current.get(name) ?? 0;
        const p = axisPoint(i, Math.max(0, Math.min(100, score)) / 100);
        return <circle key={name} cx={p.x} cy={p.y} r={3.5} className="fill-accent" />;
      })}

      {DIMENSION_ORDER.map((name, i) => {
        const p = axisPoint(i, 1.19);
        return (
          <text
            key={name}
            x={p.x}
            y={p.y}
            textAnchor="middle"
            dominantBaseline="middle"
            fontSize={11}
            className="fill-muted"
          >
            {DIMENSION_LABELS[name] ?? name}
          </text>
        );
      })}
    </svg>
  );
}
