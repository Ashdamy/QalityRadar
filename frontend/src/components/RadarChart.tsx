"use client";

import type { AnalysisDimension } from "@/lib/api";
import {
  AXIS_LABELS,
  REPOSITORY_ORDER,
  SIN_MEDIR,
  URL_ORDER,
  dimensionLabel,
  splitDimensionName,
} from "@/lib/dimensiones";

/** Elige el orden de ejes según las dimensiones que traiga el análisis. */
export function axisOrderFor(names: string[]): string[] {
  const presentes = new Set(names);

  // El combinado trae las once dimensiones con origen: se dibujan primero las
  // del código y después las de producción, cada grupo en su orden habitual.
  const conOrigen = names.filter((n) => splitDimensionName(n).origin !== null);
  if (conOrigen.length > 0) {
    return [
      ...REPOSITORY_ORDER.map((n) => `codigo:${n}`),
      ...URL_ORDER.map((n) => `produccion:${n}`),
    ].filter((n) => presentes.has(n));
  }

  const coincidenciasUrl = URL_ORDER.filter((n) => presentes.has(n)).length;
  const coincidenciasRepo = REPOSITORY_ORDER.filter((n) => presentes.has(n)).length;
  const orden = coincidenciasUrl > coincidenciasRepo ? URL_ORDER : REPOSITORY_ORDER;
  // Se dibujan los ejes que el análisis trae y, al final, las características
  // de la norma que aún no se miden, para que se vea que existen.
  return [...orden.filter((n) => presentes.has(n)), ...SIN_MEDIR];
}

const SIZE = 320;
const CENTER = SIZE / 2;
const RADIUS = 110;
const RINGS = [0.25, 0.5, 0.75, 1];

function axisPoint(index: number, fraction: number, total: number) {
  // Se empieza arriba (-90°) y se reparten los ejes en circunferencia.
  const angle = (-90 + (360 / total) * index) * (Math.PI / 180);
  return {
    x: CENTER + Math.cos(angle) * RADIUS * fraction,
    y: CENTER + Math.sin(angle) * RADIUS * fraction,
  };
}

/**
 * Polígono de las notas. Los ejes sin medir no aportan vértice: si lo
 * aportaran en el centro, el dibujo diría "0" donde la verdad es "no se sabe".
 */
function polygon(axes: string[], scores: Map<string, number>): string {
  return axes
    .map((name, i) => ({ name, i }))
    .filter(({ name }) => scores.has(name))
    .map(({ name, i }) => {
      const score = scores.get(name) ?? 0;
      const p = axisPoint(i, Math.max(0, Math.min(100, score)) / 100, axes.length);
      return `${p.x.toFixed(1)},${p.y.toFixed(1)}`;
    })
    .join(" ");
}

function ringPolygon(axes: string[], fraction: number): string {
  return axes
    .map((_, i) => {
      const p = axisPoint(i, fraction, axes.length);
      return `${p.x.toFixed(1)},${p.y.toFixed(1)}`;
    })
    .join(" ");
}

export function RadarChart({
  dimensions,
  previous,
}: {
  dimensions: AnalysisDimension[];
  previous?: AnalysisDimension[];
}) {
  const axes = axisOrderFor(dimensions.map((d) => d.name));
  const current = new Map(dimensions.map((d) => [d.name, d.score]));
  const before = previous ? new Map(previous.map((d) => [d.name, d.score])) : null;

  // Un radar necesita al menos tres ejes medidos para formar un polígono.
  if (axes.filter((n) => current.has(n)).length < 3) return null;

  return (
    <svg
      width={SIZE}
      height={SIZE - 20}
      viewBox={`0 0 ${SIZE} ${SIZE}`}
      role="img"
      aria-label="Gráfico radar de las características ISO/IEC 25010:2023"
      className="overflow-visible"
    >
      {RINGS.map((r) => (
        <polygon
          key={r}
          points={ringPolygon(axes, r)}
          fill="none"
          className="stroke-border"
          strokeWidth={1}
          opacity={0.35 + r * 0.35}
        />
      ))}

      {axes.map((name, i) => {
        const p = axisPoint(i, 1, axes.length);
        return (
          <line
            key={i}
            x1={CENTER}
            y1={CENTER}
            x2={p.x}
            y2={p.y}
            className="stroke-border"
            strokeWidth={1}
            // Un eje sin medir se dibuja discontinuo: existe, pero no hay nota.
            strokeDasharray={current.has(name) ? undefined : "3 4"}
          />
        );
      })}

      {/* El análisis anterior se superpone en línea discontinua para que el
          cambio se vea sin abrir la comparación. */}
      {before && (
        <polygon
          points={polygon(axes, before)}
          fill="none"
          className="stroke-faint"
          strokeWidth={1.4}
          strokeDasharray="4 3"
          opacity={0.8}
        />
      )}

      <polygon
        points={polygon(axes, current)}
        className="fill-accent stroke-accent"
        fillOpacity={0.16}
        strokeWidth={2}
      />

      {axes
        .map((name, i) => ({ name, i }))
        .filter(({ name }) => current.has(name))
        .map(({ name, i }) => {
          const score = current.get(name) ?? 0;
          const p = axisPoint(i, Math.max(0, Math.min(100, score)) / 100, axes.length);
          return <circle key={name} cx={p.x} cy={p.y} r={3.5} className="fill-accent" />;
        })}

      {axes.map((name, i) => {
        const p = axisPoint(i, 1.19, axes.length);
        const medido = current.has(name);
        return (
          <text
            key={name}
            x={p.x}
            y={p.y}
            textAnchor="middle"
            dominantBaseline="middle"
            fontSize={11}
            className={medido ? "fill-muted" : "fill-faint"}
          >
            {dimensionLabel(name, AXIS_LABELS)}
            {!medido && (
              <tspan x={p.x} dy="1.2em" fontSize={9.5}>
                sin medir
              </tspan>
            )}
          </text>
        );
      })}
    </svg>
  );
}
