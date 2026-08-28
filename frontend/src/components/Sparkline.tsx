"use client";

/**
 * Minigráfica de evolución. Se dibuja con SVG y no con Canvas porque son una
 * decena de puntos: el coste es mínimo y así escala con el zoom del navegador.
 *
 * Lleva rejilla tenue, relleno de área y el último punto marcado — sin ese
 * punto no se distingue de un adorno hacia dónde va la línea.
 */

const ANCHO = 132;
const ALTO = 38;
const MARGEN = 4;

function color(scores: number[]): string {
  if (scores.length < 2) return "oklch(0.64 0.01 260)";
  const delta = scores[scores.length - 1] - scores[0];
  if (delta > 1) return "oklch(0.72 0.15 150)";
  if (delta < -1) return "oklch(0.70 0.18 25)";
  return "oklch(0.64 0.01 260)";
}

export function Sparkline({
  scores,
  label,
}: {
  scores: number[];
  label: string;
}) {
  if (scores.length === 0) {
    return (
      <svg width={ANCHO} height={ALTO} role="img" aria-label={label}>
        <line
          x1="0"
          y1={ALTO / 2}
          x2={ANCHO}
          y2={ALTO / 2}
          stroke="var(--border)"
          strokeWidth={1}
          strokeDasharray="3 4"
        />
      </svg>
    );
  }

  // Escala fija 0-100: la nota siempre está en ese rango, y una escala
  // automática exageraría variaciones de dos puntos hasta parecer desplomes.
  const puntos = scores.map((score, i) => {
    const x =
      scores.length === 1
        ? ANCHO - MARGEN
        : MARGEN + (i * (ANCHO - MARGEN * 2)) / (scores.length - 1);
    const y = MARGEN + ((100 - Math.max(0, Math.min(100, score))) * (ALTO - MARGEN * 2)) / 100;
    return { x, y };
  });

  const linea = puntos.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
  const area =
    `M${puntos[0].x.toFixed(1)} ${puntos[0].y.toFixed(1)} ` +
    puntos.slice(1).map((p) => `L${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ") +
    ` L${puntos[puntos.length - 1].x.toFixed(1)} ${ALTO} L${puntos[0].x.toFixed(1)} ${ALTO} Z`;
  const trazo = color(scores);
  const ultimo = puntos[puntos.length - 1];

  return (
    <svg width={ANCHO} height={ALTO} role="img" aria-label={label}>
      <line x1="0" y1={9.5} x2={ANCHO} y2={9.5} stroke="var(--border)" strokeWidth={1} opacity={0.35} />
      <line x1="0" y1={28.5} x2={ANCHO} y2={28.5} stroke="var(--border)" strokeWidth={1} opacity={0.35} />
      <path d={area} fill={trazo} opacity={0.13} />
      <polyline
        points={linea}
        fill="none"
        stroke={trazo}
        strokeWidth={1.6}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <circle cx={ultimo.x} cy={ultimo.y} r={2.8} fill={trazo} />
    </svg>
  );
}
