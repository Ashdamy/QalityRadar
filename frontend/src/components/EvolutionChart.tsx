"use client";

import type { TimelineEntry } from "@/lib/api";

const WIDTH = 820;
const HEIGHT = 230;
const LEFT = 40;
const RIGHT = 800;
const TOP = 20;
const BOTTOM = 190;

// Una caída de esta magnitud o mayor se marca y se anota: es lo que el usuario
// necesita ver primero al mirar la evolución.
const NOTABLE_DROP = 5;

function formatDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("es", { day: "2-digit", month: "short" });
}

export function EvolutionChart({ entries }: { entries: TimelineEntry[] }) {
  // Del más antiguo al más reciente, y solo los que tienen puntuación.
  const points = entries
    .filter((e) => e.overall_score !== null)
    .slice()
    .reverse();

  if (points.length < 2) {
    return (
      <p className="py-10 text-center text-[13.5px] text-faint">
        Hace falta al menos un segundo análisis para ver la evolución.
      </p>
    );
  }

  const step = points.length > 1 ? (RIGHT - LEFT - 60) / (points.length - 1) : 0;
  const coords = points.map((entry, i) => ({
    entry,
    x: LEFT + 50 + step * i,
    y: BOTTOM - ((entry.overall_score ?? 0) / 100) * (BOTTOM - TOP),
  }));

  const line = coords.map((c) => `${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(" ");
  const area = `M ${line.split(" ").join(" L ")} L ${coords[coords.length - 1].x.toFixed(1)},${BOTTOM} L ${coords[0].x.toFixed(1)},${BOTTOM} Z`;

  return (
    <svg
      width="100%"
      height={HEIGHT}
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      role="img"
      aria-label="Evolución de la puntuación en el tiempo"
      className="overflow-visible"
    >
      {[0, 25, 50, 75, 100].map((value) => {
        const y = BOTTOM - (value / 100) * (BOTTOM - TOP);
        return (
          <g key={value}>
            <line
              x1={LEFT}
              y1={y}
              x2={RIGHT}
              y2={y}
              className="stroke-border"
              strokeWidth={1}
              opacity={value === 0 ? 1 : 0.5}
            />
            <text
              x={LEFT - 10}
              y={y + 4}
              textAnchor="end"
              fontSize={10}
              className="fill-faint font-mono"
            >
              {value}
            </text>
          </g>
        );
      })}

      <path d={area} className="fill-accent" fillOpacity={0.1} />
      <polyline
        points={line}
        fill="none"
        className="stroke-accent"
        strokeWidth={2.5}
        strokeLinejoin="round"
      />

      {coords.map(({ entry, x, y }, i) => {
        const isLast = i === coords.length - 1;
        const drop = (entry.delta ?? 0) <= -NOTABLE_DROP;
        return (
          <g key={entry.id}>
            {drop && (
              <>
                <line
                  x1={x}
                  y1={y}
                  x2={x}
                  y2={y + 30}
                  className="stroke-[oklch(0.68_0.19_25)]"
                  strokeWidth={1}
                  strokeDasharray="3 2"
                />
                <text
                  x={x}
                  y={y + 44}
                  textAnchor="middle"
                  fontSize={10.5}
                  className="fill-[oklch(0.68_0.19_25)]"
                >
                  {entry.delta}
                </text>
              </>
            )}
            <circle
              cx={x}
              cy={y}
              r={isLast ? 6 : drop ? 5.5 : 4.5}
              className={
                isLast
                  ? "fill-accent"
                  : drop
                    ? "fill-bg stroke-[oklch(0.68_0.19_25)]"
                    : "fill-bg stroke-accent"
              }
              strokeWidth={2.5}
            />
            <text
              x={x}
              y={BOTTOM + 22}
              textAnchor="middle"
              fontSize={10.5}
              className="fill-faint font-mono"
            >
              {formatDate(entry.created_at)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
