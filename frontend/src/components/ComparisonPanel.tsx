"use client";

import type { Comparison } from "@/lib/api";

function trendColor(delta: number): string {
  if (delta > 0) return "oklch(0.72 0.15 150)";
  if (delta < 0) return "oklch(0.68 0.19 25)";
  return "oklch(0.64 0.01 260)";
}

function formatDelta(delta: number): string {
  if (delta > 0) return `+${delta.toFixed(0)}`;
  if (delta < 0) return `−${Math.abs(delta).toFixed(0)}`;
  return "0";
}

export function ComparisonPanel({
  comparison,
  onClose,
}: {
  comparison: Comparison;
  onClose: () => void;
}) {
  const color = trendColor(comparison.score_delta);

  return (
    <section className="rounded-[10px] border border-border bg-surface p-6">
      <div className="flex items-start justify-between gap-4">
        <h2 className="text-[15px] font-semibold">Comparación entre análisis</h2>
        <button
          type="button"
          onClick={onClose}
          className="rounded-[6px] border border-border px-3 py-1 text-[12.5px] text-muted hover:text-text focus:outline-none focus:ring-[3px] focus:ring-accentDim"
        >
          Cerrar
        </button>
      </div>

      <div className="mt-5 flex flex-wrap items-center justify-center gap-10 rounded-[8px] border border-border bg-bg px-6 py-5">
        <div>
          <div className="text-[11px] uppercase tracking-wide text-faint">Anterior</div>
          <div className="mt-1 font-mono text-[36px] leading-none text-faint">
            {comparison.previous_score?.toFixed(0) ?? "—"}
          </div>
        </div>

        <div className="flex flex-col items-center gap-1">
          <svg width="42" height="20" viewBox="0 0 42 20" aria-hidden="true">
            <path
              d="M2 10 H34 M27 3 L34 10 L27 17"
              className="stroke-muted"
              strokeWidth={1.6}
              fill="none"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <div className="font-mono text-[19px] font-medium" style={{ color }}>
            {formatDelta(comparison.score_delta)}
          </div>
          <div className="text-[11px] text-faint">{comparison.trend}</div>
        </div>

        <div className="text-right">
          <div className="text-[11px] uppercase tracking-wide text-faint">Actual</div>
          <div className="mt-1 font-mono text-[36px] leading-none text-accent">
            {comparison.current_score?.toFixed(0) ?? "—"}
          </div>
        </div>
      </div>

      {comparison.summary_text && (
        <div className="mt-5 rounded-[8px] border border-border bg-bg p-5">
          <div className="mb-2 flex items-center gap-2">
            <h3 className="text-[13px] font-semibold">Resumen ejecutivo</h3>
            <span className="rounded-[4px] border border-border px-2 py-[1px] text-[11px] text-faint">
              generado automáticamente
            </span>
          </div>
          <p className="text-[13.5px] leading-relaxed text-muted">{comparison.summary_text}</p>
        </div>
      )}

      <div className="mt-5 grid gap-4 md:grid-cols-2">
        <div>
          <h3 className="mb-3 flex items-center gap-2 text-[13px] font-semibold">
            <svg width="15" height="15" viewBox="0 0 16 16" aria-hidden="true">
              <path
                d="M8 13 V4 M4 8 L8 3.5 L12 8"
                className="stroke-[oklch(0.72_0.15_150)]"
                strokeWidth={1.8}
                fill="none"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            Mejoras <span className="font-normal text-faint">({comparison.improvements.length})</span>
          </h3>
          {comparison.improvements.length === 0 ? (
            <p className="text-[13px] text-faint">Ninguna mejora detectada.</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {comparison.improvements.map((item, i) => (
                <li
                  key={`${item.description}-${i}`}
                  className="rounded-[8px] border border-[oklch(0.28_0.06_150)] bg-bg p-3.5"
                >
                  <p className="text-[12.5px] leading-relaxed text-muted">{item.description}</p>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div>
          <h3 className="mb-3 flex items-center gap-2 text-[13px] font-semibold">
            <svg width="15" height="15" viewBox="0 0 16 16" aria-hidden="true">
              <path
                d="M8 3 V12 M4 8 L8 12.5 L12 8"
                className="stroke-[oklch(0.68_0.19_25)]"
                strokeWidth={1.8}
                fill="none"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            Regresiones{" "}
            <span className="font-normal text-faint">({comparison.regressions.length})</span>
          </h3>
          {comparison.regressions.length === 0 ? (
            <p className="text-[13px] text-faint">Ninguna regresión detectada.</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {comparison.regressions.map((item, i) => (
                <li
                  key={`${item.description}-${i}`}
                  className="rounded-[8px] border border-[oklch(0.28_0.07_25)] bg-bg p-3.5"
                >
                  <p className="text-[12.5px] leading-relaxed text-muted">{item.description}</p>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </section>
  );
}
