import type { Veredicto } from "@/lib/api";

// Clases completas y no armadas con plantillas: Tailwind solo genera las que
// encuentra escritas tal cual en el código.
const COLOR: Record<Veredicto["nivel"], { borde: string; texto: string }> = {
  apto: { borde: "border-[oklch(0.72_0.15_150)]", texto: "text-[oklch(0.72_0.15_150)]" },
  apto_condicionado: { borde: "border-[oklch(0.80_0.14_85)]", texto: "text-[oklch(0.80_0.14_85)]" },
  no_apto: { borde: "border-[oklch(0.68_0.19_25)]", texto: "text-[oklch(0.68_0.19_25)]" },
};

/** Icono además del color: quien no distingue el verde del rojo lo lee igual. */
function Icono({ nivel }: { nivel: Veredicto["nivel"] }) {
  return (
    <svg viewBox="0 0 20 20" width="22" height="22" aria-hidden="true" className="shrink-0">
      <circle cx="10" cy="10" r="10" fill="currentColor" />
      <g stroke="var(--bg)" strokeWidth="2.4" strokeLinecap="round" fill="none">
        {nivel === "apto" && <polyline points="5.5,10.5 8.6,13.5 14.5,7" />}
        {nivel === "no_apto" && <path d="M6.5 6.5l7 7M13.5 6.5l-7 7" />}
        {nivel === "apto_condicionado" && <path d="M10 5.5v5.5M10 14.5v0.1" />}
      </g>
    </svg>
  );
}

/**
 * Veredicto de conformidad, lo primero que se lee del resultado. Se calcula
 * en el servidor al leer el análisis; aquí solo se presenta.
 */
export function VeredictoCard({ veredicto }: { veredicto?: Veredicto | null }) {
  if (!veredicto) return null;
  const color = COLOR[veredicto.nivel];
  return (
    <section
      aria-label={`Veredicto: ${veredicto.etiqueta}${veredicto.provisional ? ", provisional" : ""}`}
      className={`mt-6 rounded-[8px] border-2 ${color.borde} bg-surface p-5`}
    >
      <div className={`flex flex-wrap items-center gap-3 ${color.texto}`}>
        <Icono nivel={veredicto.nivel} />
        <h3 className="text-[17px] font-semibold">Veredicto: {veredicto.etiqueta}</h3>
        {veredicto.provisional && (
          <span className="rounded-[4px] border border-border px-2 py-[1px] text-[11.5px] text-muted">
            provisional
          </span>
        )}
      </div>
      <ul className="mt-3 list-disc space-y-1 pl-5 text-[13.5px] text-muted">
        {veredicto.motivos.map((m) => (
          <li key={m}>{m}</li>
        ))}
      </ul>
      <p className="mt-3 text-[12px] text-faint">{veredicto.aviso}</p>
    </section>
  );
}
