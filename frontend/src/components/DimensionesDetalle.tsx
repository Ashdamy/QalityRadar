import type { AnalysisDimension, Subcaracteristica } from "@/lib/api";
import { SIN_MEDIR, dimensionColor, dimensionLabel, splitDimensionName } from "@/lib/dimensiones";

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
          </span>
          <span className="shrink-0 font-mono">
            {s.measured ? `${s.earned}/${s.max}` : "sin medir"}
          </span>
        </li>
      ))}
    </ul>
  );
}

/**
 * Lista de dimensiones con su barra y, desplegable, el desglose por
 * subcaracterística. La comparten el panel de análisis y el informe
 * compartido.
 *
 * Al final, las características de la norma que aún no se miden, sin barra:
 * no es una nota baja, es que no hay nota.
 */
export function DimensionesDetalle({ dimensions }: { dimensions: AnalysisDimension[] }) {
  // En el modo combinado ya vienen las once con origen y el listado de las
  // no medidas no aplica a ningún lado en concreto.
  const combinado = dimensions.some((d) => splitDimensionName(d.name).origin !== null);

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

        // Los análisis anteriores al desglose no lo traen: solo la barra.
        if (!d.subcharacteristics?.length) return <div key={d.name}>{fila}</div>;

        return (
          <details key={d.name} className="group">
            <summary
              className="cursor-pointer list-none rounded-[4px] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent [&::-webkit-details-marker]:hidden"
              aria-label={`${dimensionLabel(d.name)}: ${d.score.toFixed(0)} de 100. Ver desglose por subcaracterística`}
            >
              {fila}
            </summary>
            <Desglose subs={d.subcharacteristics} />
          </details>
        );
      })}

      {!combinado &&
        SIN_MEDIR.map((clave) => (
          <div key={clave} className="flex items-center gap-4 text-faint">
            <span className="w-[190px] shrink-0 text-[13px]">{dimensionLabel(clave)}</span>
            <div className="h-[6px] flex-1 rounded-full border border-dashed border-border" />
            <span className="w-[62px] shrink-0 text-right text-[12px]">sin medir</span>
          </div>
        ))}

      {dimensions.some((d) => d.subcharacteristics?.length) && (
        <p className="text-[11.5px] text-faint">Pulsa una dimensión para ver de dónde salen sus puntos.</p>
      )}
    </div>
  );
}
