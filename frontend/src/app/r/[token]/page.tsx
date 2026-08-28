"use client";

import { use, useEffect, useState } from "react";
import { ApiError, getSharedReport, type Analysis } from "@/lib/api";
import { RadarMark } from "@/components/RadarMark";
import { RadarChart, dimensionLabel } from "@/components/RadarChart";

// Página pública: no usa AnalysisPanel porque ese panel ofrece acciones que
// solo tienen sentido con sesión (compartir, cerrar, exportar). Aquí se
// muestra el informe y nada más.

const DIMENSION_LABELS: Record<string, string> = {
  functional_suitability: "Adecuación funcional",
  reliability: "Fiabilidad",
  security: "Seguridad",
  maintainability: "Mantenibilidad",
  portability: "Portabilidad",
  project_activity: "Actividad del proyecto",
  performance: "Rendimiento",
  usability: "Usabilidad",
  accessibility: "Accesibilidad",
  compatibility: "Compatibilidad",
};

const SEVERITY_LABELS: Record<string, string> = {
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

function dimensionColor(score: number): string {
  if (score >= 80) return "oklch(0.72 0.15 150)";
  if (score >= 50) return "oklch(0.80 0.14 85)";
  return "oklch(0.68 0.19 25)";
}

function severityColor(severity: string): string {
  if (severity === "critical" || severity === "high")
    return "border-[oklch(0.68_0.19_25)] text-[oklch(0.68_0.19_25)]";
  if (severity === "medium") return "border-[oklch(0.80_0.14_85)] text-[oklch(0.80_0.14_85)]";
  return "border-border text-faint";
}

export default function SharedReportPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = use(params);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getSharedReport(token)
      .then(setAnalysis)
      .catch((err: unknown) => {
        // El backend no distingue entre inexistente y caducado, a propósito.
        setError(
          err instanceof ApiError && err.status === 404
            ? "Este enlace no existe o ha caducado."
            : "No se pudo cargar el informe.",
        );
      });
  }, [token]);

  return (
    <main className="flex min-h-screen w-full flex-col bg-bg text-text">
      <div className="flex items-center justify-between border-b border-border px-8 py-4">
        <div className="flex items-center gap-[10px]">
          <RadarMark size={20} />
          <span className="text-[14.5px] font-semibold">QalitiRadar</span>
        </div>
        <span className="text-[12px] text-faint">Informe compartido</span>
      </div>

      <div className="mx-auto flex w-full max-w-[720px] flex-col px-8 py-12">
        {error && (
          <div className="rounded-[8px] border border-border bg-surface p-8 text-center">
            <p className="text-[14px] text-muted">{error}</p>
            <p className="mt-2 text-[12.5px] text-faint">
              Pide a quien te lo envió que genere uno nuevo.
            </p>
          </div>
        )}

        {!error && !analysis && (
          <p className="text-center text-[13.5px] text-muted">Cargando informe…</p>
        )}

        {analysis && (
          <>
            <h1 className="text-[20px] font-semibold tracking-[-0.01em]">
              {analysis.repository_full_name ?? "Informe de calidad"}
            </h1>
            <p className="mt-1 text-[13px] text-muted">
              Evaluación según el modelo ISO/IEC 25010.
            </p>

            <div className="mt-7 flex flex-wrap items-end gap-8">
              <div>
                <div className="text-[12px] uppercase tracking-wide text-faint">Puntuación</div>
                <div
                  className={`font-mono text-[44px] leading-none ${scoreColor(
                    analysis.overall_score ?? 0,
                  )}`}
                >
                  {analysis.overall_score?.toFixed(0)}
                  <span className="text-[18px] text-faint">/100</span>
                </div>
              </div>
              <div>
                <div className="text-[12px] uppercase tracking-wide text-faint">Confianza</div>
                <div className="font-mono text-[20px]">
                  {analysis.confidence_level?.toFixed(0)}%
                </div>
              </div>
            </div>

            {analysis.summary_text && (
              <p className="mt-6 rounded-[8px] border border-border bg-surface p-[18px_20px] text-[13.5px] leading-relaxed text-muted">
                {analysis.summary_text}
              </p>
            )}

            <div className="mt-8 flex flex-col items-center gap-6 md:flex-row md:items-start">
              <RadarChart dimensions={analysis.dimensions} />
              <div className="w-full flex-1">
                {analysis.dimensions.map((d) => (
                  <div key={d.name} className="mb-3">
                    <div className="mb-1 flex items-baseline justify-between text-[12.5px]">
                      <span className="text-muted">
                        {dimensionLabel(d.name, DIMENSION_LABELS)}
                      </span>
                      <span className="font-mono text-[12px]">{d.score.toFixed(0)}</span>
                    </div>
                    <div className="h-[5px] w-full overflow-hidden rounded-full bg-surface2">
                      <div
                        className="h-full rounded-full"
                        style={{
                          width: `${Math.max(0, Math.min(100, d.score))}%`,
                          background: dimensionColor(d.score),
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="mt-8">
              <h2 className="text-[13px] font-semibold text-muted">
                Hallazgos ({analysis.findings.length})
              </h2>
              {analysis.findings.length === 0 ? (
                <p className="mt-3 text-[13.5px] text-faint">
                  No se encontró ningún problema en las dimensiones analizadas.
                </p>
              ) : (
                <ul className="mt-3 flex flex-col gap-3">
                  {analysis.findings.map((f, i) => (
                    <li
                      key={`${f.title}-${i}`}
                      className="rounded-[6px] border border-border bg-surface p-4"
                    >
                      <div className="flex items-center gap-3">
                        <span
                          className={`rounded-[4px] border px-[7px] py-[1px] text-[11px] ${severityColor(
                            f.severity,
                          )}`}
                        >
                          {SEVERITY_LABELS[f.severity] ?? f.severity}
                        </span>
                        <span className="text-[13.5px] font-medium">{f.title}</span>
                      </div>
                      <p className="mt-2 text-[13px] leading-relaxed text-muted">
                        {f.description}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <p className="mt-10 text-center text-[12px] leading-[1.6] text-faint">
              Las puntuaciones son una aproximación al modelo de calidad ISO/IEC 25010. No
              constituyen una certificación oficial.
            </p>
          </>
        )}
      </div>
    </main>
  );
}
