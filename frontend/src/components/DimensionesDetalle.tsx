import type { AnalysisDimension } from "@/lib/api";
import { SIN_MEDIR, dimensionColor, dimensionLabel, splitDimensionName } from "@/lib/dimensiones";

/**
 * Lista de dimensiones con su barra. La comparten el panel de análisis y el
 * informe compartido, que antes llevaban cada uno su copia.
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
      {dimensions.map((d) => (
        <div key={d.name} className="flex items-center gap-4">
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
      ))}

      {!combinado &&
        SIN_MEDIR.map((clave) => (
          <div key={clave} className="flex items-center gap-4 text-faint">
            <span className="w-[190px] shrink-0 text-[13px]">{dimensionLabel(clave)}</span>
            <div className="h-[6px] flex-1 rounded-full border border-dashed border-border" />
            <span className="w-[62px] shrink-0 text-right text-[12px]">sin medir</span>
          </div>
        ))}
    </div>
  );
}
