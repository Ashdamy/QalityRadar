"use client";

import { useState } from "react";
import { ApiError, downloadAnalysisReport, type Analysis, type AnalysisFinding } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { RadarChart, dimensionLabel } from "@/components/RadarChart";

// Nombres tecnicos de las dimensiones ISO 25010 traducidos para el usuario.
const DIMENSION_LABELS: Record<string, string> = {
  functional_suitability: "Adecuación funcional",
  reliability: "Fiabilidad",
  security: "Seguridad",
  maintainability: "Mantenibilidad",
  portability: "Portabilidad",
  project_activity: "Actividad del proyecto",
  // Dimensiones del analisis de URL (Modo 2).
  performance: "Rendimiento",
  usability: "Usabilidad",
  accessibility: "Accesibilidad",
  compatibility: "Compatibilidad",
};

const SEVERITY_LABELS: Record<AnalysisFinding["severity"], string> = {
  critical: "Crítico",
  high: "Alto",
  medium: "Medio",
  low: "Bajo",
  info: "Info",
};

const STATUS_LABELS: Record<Analysis["status"], string> = {
  pending: "En cola…",
  cloning: "Clonando el repositorio…",
  running: "Analizando el código…",
  scoring: "Calculando la puntuación…",
  completed: "Análisis completado",
  failed: "El análisis falló",
  timeout: "El análisis tardó demasiado",
};

function dimensionColor(score: number): string {
  if (score >= 80) return "oklch(0.72 0.15 150)";
  if (score >= 50) return "oklch(0.80 0.14 85)";
  return "oklch(0.68 0.19 25)";
}

function scoreColor(score: number): string {
  if (score >= 80) return "text-[oklch(0.72_0.15_150)]";
  if (score >= 50) return "text-[oklch(0.80_0.14_85)]";
  return "text-[oklch(0.68_0.19_25)]";
}

function severityColor(severity: AnalysisFinding["severity"]): string {
  if (severity === "critical" || severity === "high") return "border-[oklch(0.68_0.19_25)] text-[oklch(0.68_0.19_25)]";
  if (severity === "medium") return "border-[oklch(0.80_0.14_85)] text-[oklch(0.80_0.14_85)]";
  return "border-border text-faint";
}

export function AnalysisPanel({ analysis, onClose }: { analysis: Analysis; onClose: () => void }) {
  const running = !["completed", "failed", "timeout"].includes(analysis.status);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  async function handleDownload() {
    const token = getToken();
    if (!token || downloading) return;
    setDownloading(true);
    setDownloadError(null);
    try {
      await downloadAnalysisReport(token, analysis.id);
    } catch (error) {
      setDownloadError(
        error instanceof ApiError ? error.message : "No se pudo generar el PDF.",
      );
    } finally {
      setDownloading(false);
    }
  }

  return (
    <section
      aria-live="polite"
      className="rounded-[8px] border border-border bg-surface p-6"
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-[15px] font-semibold">{STATUS_LABELS[analysis.status]}</h2>
          {analysis.commit_message && (
            <p className="mt-1 font-mono text-[12px] text-faint">
              {analysis.commit_hash?.slice(0, 8)} · {analysis.commit_message}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          {analysis.status === "completed" && (
            <button
              type="button"
              onClick={handleDownload}
              disabled={downloading}
              className="rounded-[6px] border border-border px-3 py-1 text-[12.5px] text-muted hover:text-text disabled:opacity-60 focus:outline-none focus:ring-[3px] focus:ring-accentDim"
            >
              {downloading ? "Generando…" : "Exportar PDF"}
            </button>
          )}
          <button
            type="button"
            onClick={onClose}
            className="rounded-[6px] border border-border px-3 py-1 text-[12.5px] text-muted hover:text-text focus:outline-none focus:ring-[3px] focus:ring-accentDim"
          >
            Cerrar
          </button>
        </div>
      </div>

      {running && (
        <div className="mt-5 flex items-center gap-3">
          <span className="h-3 w-3 animate-pulse rounded-full bg-accent" aria-hidden="true" />
          <span className="text-[13px] text-muted">Esto puede tardar hasta un par de minutos.</span>
        </div>
      )}

      {downloadError && (
        <p role="alert" className="mt-3 text-[12.5px] text-[oklch(0.68_0.19_25)]">
          {downloadError}
        </p>
      )}

      {analysis.status === "failed" && analysis.error_message && (
        <p className="mt-4 text-[13.5px] text-[oklch(0.68_0.19_25)]">{analysis.error_message}</p>
      )}

      {analysis.status === "completed" && (
        <>
          <div className="mt-6 flex flex-wrap items-end gap-8">
            <div>
              <div className="text-[12px] uppercase tracking-wide text-faint">Puntuación</div>
              <div className={`font-mono text-[44px] leading-none ${scoreColor(analysis.overall_score ?? 0)}`}>
                {analysis.overall_score?.toFixed(0)}
                <span className="text-[18px] text-faint">/100</span>
              </div>
            </div>
            <div>
              <div className="text-[12px] uppercase tracking-wide text-faint">Confianza</div>
              <div className="font-mono text-[20px]">{analysis.confidence_level?.toFixed(0)}%</div>
            </div>
          </div>

          <p className="mt-4 rounded-[6px] border border-border bg-bg px-3 py-2 text-[12.5px] text-faint">
            Puntuación sobre {analysis.dimensions.length} dimensiones del modelo ISO/IEC 25010. Es una
            aproximación al estándar, no una certificación oficial.
          </p>

          {analysis.summary_text && (
            <div className="mt-5 rounded-[8px] border border-border bg-bg p-5">
              <div className="mb-2 flex items-center gap-2">
                <h3 className="text-[13px] font-semibold">Resumen ejecutivo</h3>
                <span className="rounded-[4px] border border-border px-2 py-[1px] text-[11px] text-faint">
                  {analysis.summary_source === "modelo"
                    ? "generado con IA"
                    : "generado automáticamente"}
                </span>
              </div>
              <p className="text-[13.5px] leading-relaxed text-muted">{analysis.summary_text}</p>
            </div>
          )}

          <div className="mt-6">
            <h3 className="text-[13px] font-semibold text-muted">Dimensiones</h3>
            <div className="mt-3 flex flex-wrap items-center gap-8">
              <RadarChart dimensions={analysis.dimensions} />

              <div className="flex min-w-[300px] flex-1 flex-col gap-3">
                {analysis.dimensions.map((d) => (
                  <div key={d.name} className="flex items-center gap-4">
                    <span className="w-[170px] shrink-0 text-[13px]">
                      {dimensionLabel(d.name, DIMENSION_LABELS)}
                    </span>
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
              </div>
            </div>
          </div>

          <div className="mt-7">
            <h3 className="text-[13px] font-semibold text-muted">
              Hallazgos ({analysis.findings.length})
            </h3>
            {analysis.findings.length === 0 ? (
              <p className="mt-3 text-[13.5px] text-faint">
                No se encontró ningún problema en las dimensiones analizadas.
              </p>
            ) : (
              <ul className="mt-3 flex flex-col gap-3">
                {analysis.findings.map((f, i) => (
                  <li key={`${f.title}-${i}`} className="rounded-[6px] border border-border bg-bg p-4">
                    <div className="flex items-center gap-3">
                      <span
                        className={`rounded-[4px] border px-[7px] py-[1px] text-[11px] ${severityColor(f.severity)}`}
                      >
                        {SEVERITY_LABELS[f.severity]}
                      </span>
                      <span className="text-[13.5px] font-medium">{f.title}</span>
                    </div>
                    <p className="mt-2 text-[13px] leading-relaxed text-muted">{f.description}</p>
                    {f.recommendation && (
                      <p className="mt-2 text-[12.5px] text-faint">
                        <span className="text-muted">Recomendación: </span>
                        {f.recommendation}
                      </p>
                    )}
                    {(f.file_path ?? f.url) && (
                      <p className="mt-1 font-mono text-[12px] text-faint">{f.file_path ?? f.url}</p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </section>
  );
}
