"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ApiError,
  cancelAnalysis,
  listAnalyses,
  retryAnalysis,
  type AnalysisListItem,
} from "@/lib/api";
import { clearToken, haySesion } from "@/lib/auth";
import { RadarMark } from "@/components/RadarMark";

// Estados desde los que todavía se puede cancelar, y desde los que se puede
// reintentar. Los mismos que aplica el backend.
const EN_MARCHA = ["pending", "cloning", "running", "scoring"];
const TERMINADOS_MAL = ["failed", "timeout", "cancelled"];

const ETIQUETA_ESTADO: Record<string, string> = {
  pending: "En cola",
  cloning: "Clonando",
  running: "Analizando",
  scoring: "Puntuando",
  completed: "Terminado",
  failed: "Falló",
  timeout: "Se agotó el tiempo",
  cancelled: "Cancelado",
};

const ETIQUETA_TIPO: Record<string, string> = {
  repository: "Repositorio",
  url: "Dirección",
  combined: "Combinado",
};

function color(nota: number | null): string {
  if (nota === null) return "text-faint";
  if (nota >= 80) return "text-[oklch(0.72_0.15_150)]";
  if (nota >= 60) return "text-[oklch(0.78_0.14_110)]";
  if (nota >= 40) return "text-[oklch(0.75_0.16_70)]";
  return "text-[oklch(0.68_0.19_25)]";
}

export default function AnalysesPage() {
  const router = useRouter();
  const [items, setItems] = useState<AnalysisListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    try {
      setItems(await listAnalyses(50));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        clearToken();
        router.replace("/entrar");
        return;
      }
      setError("No se pudieron cargar tus análisis.");
      setItems([]);
    }
  }, [router]);

  useEffect(() => {
    if (!haySesion()) {
      router.replace("/entrar");
      return;
    }

    // La carga va por la promesa y no llamando a `cargar()` a secas: cambiar
    // el estado en el cuerpo del efecto encadena renderizados.
    let vivo = true;
    listAnalyses(50)
      .then((lista) => {
        if (vivo) setItems(lista);
      })
      .catch((err: unknown) => {
        if (!vivo) return;
        if (err instanceof ApiError && err.status === 401) {
          clearToken();
          router.replace("/entrar");
          return;
        }
        setError("No se pudieron cargar tus análisis.");
        setItems([]);
      });
    return () => {
      vivo = false;
    };
  }, [router]);

  async function actuar(id: string, accion: (id: string) => Promise<unknown>) {
    setOcupado(id);
    setError(null);
    try {
      await accion(id);
      await cargar();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo completar la acción.");
    } finally {
      setOcupado(null);
    }
  }

  return (
    <main className="flex min-h-screen w-full flex-col bg-bg text-text">
      <div className="flex items-center justify-between border-b border-border px-8 py-4">
        <button
          type="button"
          onClick={() => router.push("/analyze")}
          className="flex items-center gap-[10px] focus:outline-none focus:ring-[3px] focus:ring-accentDim"
        >
          <RadarMark size={20} />
          <span className="text-[14.5px] font-semibold">QalitiRadar</span>
        </button>
      </div>

      <div className="mx-auto w-full max-w-[860px] px-8 py-10">
        <h1 className="mb-1.5 text-[22px] font-semibold tracking-[-0.01em]">Tus análisis</h1>
        <p className="mb-7 text-[13.5px] text-muted">
          Todo lo que has analizado, de lo más reciente a lo más antiguo.
        </p>

        {error && (
          <p role="alert" className="mb-4 text-[12.5px] text-[oklch(0.68_0.19_25)]">
            {error}
          </p>
        )}

        {items === null && <p className="text-[13px] text-muted">Cargando…</p>}

        {items !== null && items.length === 0 && (
          <p className="text-[13px] text-muted">
            Todavía no has analizado nada.{" "}
            <button
              type="button"
              onClick={() => router.push("/analyze")}
              className="text-accent underline focus:outline-none focus:ring-[3px] focus:ring-accentDim"
            >
              Empieza por aquí
            </button>
            .
          </p>
        )}

        <ul className="flex flex-col gap-2">
          {(items ?? []).map((item) => (
            <li
              key={item.id}
              className="flex items-center gap-4 rounded-[8px] border border-border bg-surface px-4 py-3"
            >
              <span className={`w-[54px] shrink-0 font-mono text-[17px] ${color(item.overall_score)}`}>
                {item.overall_score === null ? "—" : item.overall_score.toFixed(0)}
              </span>
              <div className="min-w-0 flex-1">
                <span className="block truncate text-[13.5px]">{item.target}</span>
                <span className="text-[11.5px] text-faint">
                  {ETIQUETA_TIPO[item.analysis_type] ?? item.analysis_type} ·{" "}
                  {ETIQUETA_ESTADO[item.status] ?? item.status} ·{" "}
                  {new Date(item.created_at).toLocaleString("es")}
                </span>
              </div>

              {item.status === "completed" && (
                <button
                  type="button"
                  onClick={() => router.push(`/analyze/url?analysis=${item.id}`)}
                  className="shrink-0 rounded-[5px] border border-border px-2 py-[3px] text-[11.5px] text-muted hover:text-text focus:outline-none focus:ring-[3px] focus:ring-accentDim"
                >
                  Ver
                </button>
              )}
              {EN_MARCHA.includes(item.status) && (
                <button
                  type="button"
                  disabled={ocupado === item.id}
                  onClick={() => actuar(item.id, cancelAnalysis)}
                  className="shrink-0 rounded-[5px] border border-border px-2 py-[3px] text-[11.5px] text-muted hover:text-text disabled:opacity-60 focus:outline-none focus:ring-[3px] focus:ring-accentDim"
                >
                  Cancelar
                </button>
              )}
              {TERMINADOS_MAL.includes(item.status) && (
                <button
                  type="button"
                  disabled={ocupado === item.id}
                  onClick={() => actuar(item.id, retryAnalysis)}
                  className="shrink-0 rounded-[5px] border border-border px-2 py-[3px] text-[11.5px] text-muted hover:text-text disabled:opacity-60 focus:outline-none focus:ring-[3px] focus:ring-accentDim"
                >
                  Reintentar
                </button>
              )}
            </li>
          ))}
        </ul>

      </div>
    </main>
  );
}
