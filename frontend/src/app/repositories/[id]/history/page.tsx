"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ApiError,
  getComparison,
  getProgress,
  getTimeline,
  type Comparison,
  type Progress,
  type TimelineEntry,
} from "@/lib/api";
import { clearToken, getToken } from "@/lib/auth";
import { RadarMark } from "@/components/RadarMark";
import { PrimaryButton } from "@/components/PrimaryButton";
import { EvolutionChart } from "@/components/EvolutionChart";
import { ComparisonPanel } from "@/components/ComparisonPanel";

type LoadState =
  | { kind: "loading" }
  | { kind: "ready"; timeline: TimelineEntry[]; progress: Progress }
  | { kind: "empty" }
  | { kind: "error"; message: string };

function scoreColor(score: number | null): string {
  if (score === null) return "text-faint";
  if (score >= 80) return "text-[oklch(0.72_0.15_150)]";
  if (score >= 50) return "text-[oklch(0.80_0.14_85)]";
  return "text-[oklch(0.68_0.19_25)]";
}

function deltaColor(delta: number | null): string {
  if (delta === null || delta === 0) return "text-faint";
  return delta > 0 ? "text-[oklch(0.72_0.15_150)]" : "text-[oklch(0.68_0.19_25)]";
}

function formatDelta(delta: number | null): string {
  if (delta === null) return "—";
  if (delta > 0) return `+${delta.toFixed(0)}`;
  if (delta < 0) return `−${Math.abs(delta).toFixed(0)}`;
  return "0";
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("es", { day: "2-digit", month: "short" });
}

export default function HistoryPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const repositoryId = params.id;

  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [selected, setSelected] = useState<string[]>([]);
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [comparing, setComparing] = useState(false);
  const [compareError, setCompareError] = useState<string | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.replace("/");
      return;
    }
    let cancelled = false;

    (async () => {
      try {
        const [timeline, progress] = await Promise.all([
          getTimeline(token, repositoryId),
          getProgress(token, repositoryId),
        ]);
        if (cancelled) return;
        setState(timeline.length === 0 ? { kind: "empty" } : { kind: "ready", timeline, progress });
      } catch (error) {
        if (cancelled) return;
        if (error instanceof ApiError && error.status === 401) {
          clearToken();
          router.replace("/");
          return;
        }
        setState({
          kind: "error",
          message:
            error instanceof ApiError ? error.message : "No se pudo cargar el histórico.",
        });
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [repositoryId, router]);

  function toggle(id: string) {
    setCompareError(null);
    setSelected((current) => {
      if (current.includes(id)) return current.filter((x) => x !== id);
      // Solo tiene sentido comparar dos: al elegir un tercero se descarta el
      // más antiguo de la selección.
      return current.length >= 2 ? [current[1], id] : [...current, id];
    });
  }

  async function handleCompare() {
    const token = getToken();
    if (!token || selected.length !== 2 || comparing) return;
    setComparing(true);
    setCompareError(null);
    try {
      setComparison(await getComparison(token, selected[0], selected[1]));
    } catch (error) {
      setComparison(null);
      setCompareError(
        error instanceof ApiError ? error.message : "No se pudo comparar los análisis.",
      );
    } finally {
      setComparing(false);
    }
  }

  return (
    <main className="flex min-h-screen w-full flex-col bg-bg text-text">
      <div className="flex items-center justify-between border-b border-border px-8 py-4">
        <button
          type="button"
          onClick={() => router.push("/repositories")}
          className="flex items-center gap-[10px] focus:outline-none focus:ring-[3px] focus:ring-accentDim"
        >
          <RadarMark size={20} />
          <span className="text-[14.5px] font-semibold">QalitiRadar</span>
        </button>
        <button
          type="button"
          onClick={() => router.push("/repositories")}
          className="text-[13px] text-muted hover:text-text focus:outline-none focus:ring-[3px] focus:ring-accentDim"
        >
          Volver a repositorios
        </button>
      </div>

      <div className="mx-auto flex w-full max-w-[980px] flex-col gap-6 px-8 py-8">
        <h1 className="text-[19px] font-semibold tracking-tight">Evolución de la calidad</h1>

        {state.kind === "loading" && (
          <p className="py-10 text-center text-[13.5px] text-faint">Cargando histórico…</p>
        )}

        {state.kind === "empty" && (
          <p className="py-10 text-center text-[13.5px] text-faint">
            Este repositorio todavía no tiene análisis.
          </p>
        )}

        {state.kind === "error" && (
          <p role="alert" className="py-10 text-center text-[13.5px] text-[oklch(0.68_0.19_25)]">
            {state.message}
          </p>
        )}

        {state.kind === "ready" && (
          <>
            <div className="grid grid-cols-2 gap-3.5 md:grid-cols-4">
              {[
                {
                  label: "Puntuación actual",
                  value: state.progress.current_score?.toFixed(0) ?? "—",
                  hint: `${state.progress.total_analyses} análisis`,
                },
                {
                  label: "Mejor histórica",
                  value: state.progress.best_score?.toFixed(0) ?? "—",
                  hint: state.progress.best_score_at
                    ? formatDate(state.progress.best_score_at)
                    : "—",
                },
                {
                  label: "Cambio total",
                  value: formatDelta(state.progress.total_delta),
                  hint: "desde el primero",
                },
                {
                  label: "Periodo",
                  value:
                    state.progress.days_tracked !== null
                      ? `${state.progress.days_tracked}`
                      : "—",
                  hint: "días de seguimiento",
                },
              ].map((stat) => (
                <div
                  key={stat.label}
                  className="rounded-[8px] border border-border bg-surface p-4"
                >
                  <div className="text-[11px] uppercase tracking-wide text-faint">
                    {stat.label}
                  </div>
                  <div className="mt-1.5 font-mono text-[26px] leading-none">{stat.value}</div>
                  <div className="mt-1 text-[11.5px] text-faint">{stat.hint}</div>
                </div>
              ))}
            </div>

            <div className="rounded-[10px] border border-border bg-surface p-5">
              <h2 className="mb-4 text-[14px] font-semibold">Puntuación en el tiempo</h2>
              <EvolutionChart entries={state.timeline} />
            </div>

            <div>
              <div className="mb-3 flex items-center justify-between">
                <h2 className="text-[14px] font-semibold">Análisis realizados</h2>
                <span className="text-[12px] text-faint">
                  Selecciona dos para compararlos
                </span>
              </div>

              <div className="overflow-hidden rounded-[8px] border border-border">
                {state.timeline.map((entry) => {
                  const isSelected = selected.includes(entry.id);
                  const selectable = entry.status === "completed";
                  return (
                    <button
                      key={entry.id}
                      type="button"
                      disabled={!selectable}
                      onClick={() => toggle(entry.id)}
                      className={`flex w-full items-center gap-4 border-b border-border px-4 py-3 text-left last:border-b-0 focus:outline-none focus:ring-[3px] focus:ring-accentDim ${
                        isSelected ? "bg-accentDim" : "bg-surface hover:bg-surface2"
                      } ${selectable ? "cursor-pointer" : "cursor-not-allowed opacity-60"}`}
                    >
                      <span
                        aria-hidden="true"
                        className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-[4px] border ${
                          isSelected ? "border-accent bg-accent" : "border-border"
                        }`}
                      >
                        {isSelected && (
                          <svg width="10" height="10" viewBox="0 0 12 12">
                            <path
                              d="M2 6.5 L5 9.5 L10 3"
                              className="stroke-bg"
                              strokeWidth={2}
                              fill="none"
                              strokeLinecap="round"
                            />
                          </svg>
                        )}
                      </span>
                      <span className="w-[62px] shrink-0 font-mono text-[12.5px] text-muted">
                        {formatDate(entry.created_at)}
                      </span>
                      <span className="w-[70px] shrink-0 font-mono text-[12.5px] text-faint">
                        {entry.commit_hash?.slice(0, 8) ?? "—"}
                      </span>
                      <span className="flex-1 truncate text-[13px] text-muted">
                        {entry.status === "completed"
                          ? (entry.commit_message ?? "sin mensaje")
                          : `análisis ${entry.status}`}
                      </span>
                      <span
                        className={`w-[46px] shrink-0 text-right font-mono text-[15px] ${scoreColor(entry.overall_score)}`}
                      >
                        {entry.overall_score?.toFixed(0) ?? "—"}
                      </span>
                      <span
                        className={`w-[40px] shrink-0 text-right font-mono text-[12.5px] ${deltaColor(entry.delta)}`}
                      >
                        {formatDelta(entry.delta)}
                      </span>
                    </button>
                  );
                })}
              </div>

              {compareError && (
                <p role="alert" className="mt-3 text-[12.5px] text-[oklch(0.68_0.19_25)]">
                  {compareError}
                </p>
              )}

              <div className="mt-4 flex justify-end">
                <PrimaryButton
                  type="button"
                  disabled={selected.length !== 2 || comparing}
                  onClick={handleCompare}
                  style={{ padding: "10px 20px" }}
                >
                  {comparing ? "Comparando…" : "Comparar los 2 seleccionados"}
                </PrimaryButton>
              </div>
            </div>

            {comparison && (
              <ComparisonPanel comparison={comparison} onClose={() => setComparison(null)} />
            )}
          </>
        )}
      </div>
    </main>
  );
}
