"use client";

import type { Combined, PlanItem } from "@/lib/api";

// Lo que aporta el modo combinado no es la nota media, sino la lectura de por
// qué el código y la producción no cuentan lo mismo. Este panel presenta esa
// comparación; el detalle por dimensión lo sigue mostrando AnalysisPanel.

const ORIGIN_LABELS: Record<PlanItem["origin"], string> = {
  codigo: "Código",
  produccion: "Producción",
  discrepancia: "Discrepancia",
};

const SEVERITY_LABELS: Record<PlanItem["severity"], string> = {
  critical: "Crítico",
  high: "Alto",
  medium: "Medio",
  low: "Bajo",
  info: "Info",
};

function scoreColor(score: number): string {
  if (score >= 80) return "text-[oklch(0.72_0.15_150)]";
  if (score >= 50) return "text-[oklch(0.80_0.14_85)]";
  return "text-[oklch(0.68_0.19_25)]";
}

function severityColor(severity: PlanItem["severity"]): string {
  if (severity === "critical" || severity === "high")
    return "border-[oklch(0.68_0.19_25)] text-[oklch(0.68_0.19_25)]";
  if (severity === "medium") return "border-[oklch(0.80_0.14_85)] text-[oklch(0.80_0.14_85)]";
  return "border-border text-faint";
}

function WarningIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      className="mt-[2px] shrink-0"
      aria-hidden="true"
    >
      <path
        d="M8 1.6 15 14H1L8 1.6Z"
        className="stroke-[oklch(0.80_0.14_85)]"
        strokeWidth={1.3}
        strokeLinejoin="round"
      />
      <path
        d="M8 6v3.4M8 11.8h.01"
        className="stroke-[oklch(0.80_0.14_85)]"
        strokeWidth={1.5}
        strokeLinecap="round"
      />
    </svg>
  );
}

/**
 * Una de las tres notas. La global se destaca porque es la conclusión; las
 * otras dos son las mitades de las que sale.
 */
function ScoreSide({
  label,
  score,
  hint,
  emphasis = false,
}: {
  label: string;
  score: number | null;
  hint: string;
  emphasis?: boolean;
}) {
  return (
    <div
      className={`flex flex-1 flex-col items-center gap-[3px] px-[10px] py-[16px] ${
        emphasis ? "bg-surface2" : ""
      }`}
    >
      <span
        className={`text-[11.5px] uppercase tracking-[0.05em] ${
          emphasis ? "text-muted" : "text-faint"
        }`}
      >
        {label}
      </span>
      <span
        className={`font-mono font-semibold leading-none ${
          emphasis ? "text-[34px]" : "text-[26px]"
        } ${score === null ? "text-faint" : scoreColor(score)}`}
      >
        {score === null ? "—" : Math.round(score)}
      </span>
      <span className="mt-[2px] text-center text-[10.5px] leading-[1.4] text-faint">{hint}</span>
    </div>
  );
}

export function CombinedPanel({
  combined,
  overallScore,
}: {
  combined: Combined;
  overallScore: number | null;
}) {
  const { correspondence: correspondencia } = combined;
  const delta = combined.delta;

  return (
    <div className="flex flex-col gap-4">
      {/* El aviso va primero: si los dos lados no son el mismo proyecto, todo
          lo que viene debajo se lee de otra manera. */}
      {correspondencia?.warning && (
        <div
          role="alert"
          className="flex items-start gap-[10px] rounded-[8px] border border-[oklch(0.80_0.14_85)] bg-[oklch(0.80_0.14_85/0.07)] p-[14px_16px]"
        >
          <WarningIcon />
          <div>
            <h3 className="mb-[4px] text-[13px] font-semibold text-[oklch(0.80_0.14_85)]">
              {correspondencia.kind === "no_deployment"
                ? "No hay aplicación desplegada en esa dirección"
                : "El repositorio y la dirección podrían no corresponder"}
            </h3>
            <p className="text-[12.5px] leading-[1.55] text-muted">{correspondencia.warning}</p>
            <ul className="mt-[8px] flex flex-col gap-[3px]">
              {correspondencia.reasons.map((motivo) => (
                <li key={motivo} className="text-[12px] leading-[1.5] text-faint">
                  · {motivo}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {/* Comparación de las dos notas. */}
      <div className="rounded-[8px] border border-border bg-surface">
        <div className="flex items-stretch divide-x divide-border">
          <ScoreSide
            label="Repositorio"
            score={combined.repository_score}
            hint="6 dimensiones del código"
          />
          <ScoreSide
            label="Producción"
            score={combined.url_score}
            hint="5 dimensiones del despliegue"
          />
          <ScoreSide label="Global" score={overallScore} hint="Las once, ponderadas" emphasis />
        </div>
        {delta !== null && (
          <div className="border-t border-border px-[16px] py-[9px] text-center text-[12px] text-faint">
            Diferencia de{" "}
            <span className="font-mono text-text">{Math.abs(Math.round(delta))}</span> puntos a
            favor {delta > 0 ? "del código" : "de producción"}
          </div>
        )}
      </div>

      {/* Explicación de la discrepancia, cuando la hay. */}
      {combined.explanation ? (
        <div className="rounded-[8px] border border-border bg-surface p-[18px_20px]">
          <h3 className="mb-[9px] text-[12.5px] font-semibold text-muted">
            Qué explica la diferencia
          </h3>
          <p className="text-[13px] leading-[1.65] text-text">{combined.explanation}</p>
          {combined.recommendations && (
            <p className="mt-[10px] border-t border-border pt-[10px] text-[12.5px] leading-[1.6] text-muted">
              {combined.recommendations}
            </p>
          )}
        </div>
      ) : (
        <p className="rounded-[8px] border border-border bg-surface p-[14px_18px] text-[12.5px] leading-[1.55] text-faint">
          El código y la producción puntúan de forma parecida: no hay una discrepancia
          significativa que explicar.
        </p>
      )}

      {/* Plan de mejora priorizado. */}
      {combined.improvement_plan.length > 0 && (
        <div className="rounded-[8px] border border-border bg-surface p-[18px_20px]">
          <h3 className="mb-[3px] text-[12.5px] font-semibold text-muted">Por dónde empezar</h3>
          <p className="mb-[13px] text-[11.5px] text-faint">
            Ordenado por gravedad, mezclando ambos análisis.
          </p>
          <ol className="flex flex-col gap-[11px]">
            {combined.improvement_plan.map((accion, indice) => (
              <li key={`${accion.origin}-${accion.title}`} className="flex items-start gap-[11px]">
                <span className="w-[18px] shrink-0 pt-[2px] text-right font-mono text-[11.5px] text-faint">
                  {indice + 1}
                </span>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-[6px]">
                    <span className="text-[13px] font-medium">{accion.title}</span>
                    <span
                      className={`rounded-[4px] border px-[6px] py-[1px] text-[10px] ${severityColor(
                        accion.severity,
                      )}`}
                    >
                      {SEVERITY_LABELS[accion.severity]}
                    </span>
                    <span className="rounded-[4px] border border-border px-[6px] py-[1px] text-[10px] text-faint">
                      {ORIGIN_LABELS[accion.origin]}
                    </span>
                  </div>
                  {accion.detail && (
                    <p className="mt-[3px] text-[12px] leading-[1.55] text-faint">
                      {accion.detail}
                    </p>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}
