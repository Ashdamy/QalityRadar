import type { ReactNode } from "react";
import type { AnalysisDimension, Subcaracteristica } from "@/lib/api";
import { dimensionColor, dimensionLabel, esIndicadorDeSalud } from "@/lib/dimensiones";

// De dónde sale cada parte de la nota: SonarCloud o estimado en
// mantenibilidad; Lighthouse o axe-core donde puede venir del navegador real.
const ORIGEN: Record<NonNullable<Subcaracteristica["origin"]>, { texto: string; ayuda: string }> = {
  sonarcloud: { texto: "SonarCloud", ayuda: "Medido por SonarCloud e importado" },
  lighthouse: { texto: "Lighthouse", ayuda: "Medido con Lighthouse en un navegador real" },
  "axe-core": { texto: "axe-core", ayuda: "Comprobado con axe-core en un navegador real" },
  qalitiradar: { texto: "QalitiRadar", ayuda: "Medido por el análisis estático de QalitiRadar" },
  estimado: { texto: "Estimado", ayuda: "Estimado por QalitiRadar a partir de señales indirectas" },
  sin_medir: { texto: "Sin medir", ayuda: "La norma lo define, pero aquí no se mide" },
};

function Desglose({ subs }: { subs: Subcaracteristica[] }) {
  return (
    <ul className="mt-2 flex flex-col gap-[6px] border-l border-border pl-4">
      {subs.map((s) => (
        <li
          key={s.name}
          className={`flex items-baseline justify-between gap-3 text-[12.5px] ${s.measured ? "text-muted" : "text-faint"}`}
        >
          <span>
            {s.name}
            {!s.iso && (
              <span
                className="ml-2 rounded-[4px] border border-border px-[5px] text-[10.5px] text-faint"
                title="Suma puntos, pero no es una subcaracterística de ISO/IEC 25010"
              >
                no es ISO
              </span>
            )}
            {s.origin && (
              <span
                className={`ml-2 rounded-[4px] border px-[5px] text-[10.5px] ${
                  ["sonarcloud", "lighthouse", "axe-core"].includes(s.origin)
                    ? "border-accent text-accent"
                    : "border-border text-faint"
                }`}
                title={ORIGEN[s.origin].ayuda}
              >
                {ORIGEN[s.origin].texto}
              </span>
            )}
          </span>
          <span className="shrink-0 font-mono">
            {s.measured ? `${s.earned}/${s.max}` : s.origin ? "—" : "sin medir"}
          </span>
        </li>
      ))}
    </ul>
  );
}

/**
 * Lista de dimensiones con su barra y, desplegable, el desglose por
 * subcaracterística. La comparten el panel de análisis y el informe
 * compartido. Los indicadores de salud van aparte, en `IndicadorDeSalud`.
 */
export function DimensionesDetalle({
  dimensions: todas,
  extra = {},
}: {
  dimensions: AnalysisDimension[];
  // Contenido adicional dentro del desplegable de una dimensión, por nombre
  // (hoy, la importación de SonarCloud en mantenibilidad).
  extra?: Record<string, ReactNode>;
}) {
  const dimensions = todas.filter((d) => !esIndicadorDeSalud(d.name));

  return (
    <div className="flex min-w-[300px] flex-1 flex-col gap-3">
      {dimensions.map((d) => {
        const fila = (
          <div className="flex items-center gap-4">
            <span className="w-[190px] shrink-0 text-[13px]">{dimensionLabel(d.name)}</span>
            <div className="h-[6px] flex-1 overflow-hidden rounded-full bg-surface2">
              <div
                className="h-full rounded-full"
                style={{
                  width: `${Math.max(0, Math.min(100, d.score))}%`,
                  background: dimensionColor(d.score),
                }}
              />
            </div>
            <span className="w-[62px] shrink-0 text-right font-mono text-[13px]">
              {d.score.toFixed(0)}/100
            </span>
          </div>
        );

        // Los análisis anteriores al desglose no lo traen: solo la barra, salvo
        // que haya algo más que enseñar dentro (la importación de SonarCloud).
        if (!d.subcharacteristics?.length && !extra[d.name]) return <div key={d.name}>{fila}</div>;

        return (
          <details key={d.name} className="group">
            <summary
              className="cursor-pointer list-none rounded-[4px] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent [&::-webkit-details-marker]:hidden"
              aria-label={`${dimensionLabel(d.name)}: ${d.score.toFixed(0)} de 100. Ver desglose por subcaracterística`}
            >
              {fila}
            </summary>
            {d.subcharacteristics?.length ? <Desglose subs={d.subcharacteristics} /> : null}
            {extra[d.name]}
          </details>
        );
      })}

      {dimensions.some((d) => d.subcharacteristics?.length) && (
        <p className="text-[11.5px] text-faint">Pulsa una dimensión para ver de dónde salen sus puntos.</p>
      )}
    </div>
  );
}

/**
 * Indicadores que se calculan pero no son ISO ni entran en la nota (hoy, la
 * actividad del proyecto). Van aparte del radar y de la lista para que nadie
 * los tome por calidad.
 */
export function IndicadorDeSalud({ dimensions }: { dimensions: AnalysisDimension[] }) {
  const salud = dimensions.filter((d) => esIndicadorDeSalud(d.name));
  if (salud.length === 0) return null;

  return (
    <section
      aria-labelledby="indicador-de-salud"
      className="mt-5 rounded-[8px] border border-dashed border-border bg-bg p-5"
    >
      <h3 id="indicador-de-salud" className="text-[13px] font-semibold">
        Indicador de salud del proyecto
      </h3>
      <p className="mb-3 mt-1 text-[12px] text-faint">
        No forma parte de ISO/IEC 25010 ni de la nota global: dice si el proyecto está vivo (frescura,
        cuidado e interés de terceros), no si es de calidad.
      </p>
      {salud.map((d) => (
        <div key={d.name}>
          <div className="flex items-center justify-between text-[13px]">
            <span>{dimensionLabel(d.name)}</span>
            <span className="font-mono">{d.score.toFixed(0)}/100</span>
          </div>
          {d.subcharacteristics?.length ? <Desglose subs={d.subcharacteristics} /> : null}
        </div>
      ))}
    </section>
  );
}
