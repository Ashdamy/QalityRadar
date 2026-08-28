"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ApiError,
  analyzeCombined,
  getAnalysis,
  listRepositories,
  type Analysis,
  type Repository,
} from "@/lib/api";
import { clearToken, getToken } from "@/lib/auth";
import { RadarMark } from "@/components/RadarMark";
import { PrimaryButton } from "@/components/PrimaryButton";
import { AnalysisPanel } from "@/components/AnalysisPanel";
import { CombinedPanel } from "@/components/CombinedPanel";

const IN_PROGRESS: ReadonlySet<Analysis["status"]> = new Set([
  "pending",
  "cloning",
  "running",
  "scoring",
]);
// El combinado ejecuta los dos análisis en serie, así que se espera bastante
// más que en los otros modos antes de darlo por perdido.
const POLL_INTERVAL_MS = 3000;
const MAX_POLLS = 400;

function InfoIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 16 16"
      fill="none"
      className="mt-[1px] shrink-0"
      aria-hidden="true"
    >
      <circle cx="8" cy="8" r="6.5" className="stroke-faint" strokeWidth={1.3} />
      <path d="M8 5v3.5M8 11h.01" className="stroke-faint" strokeWidth={1.5} strokeLinecap="round" />
    </svg>
  );
}

export default function AnalyzeCombinedPage() {
  const router = useRouter();
  const [repositorios, setRepositorios] = useState<Repository[] | null>(null);
  const [repositorioId, setRepositorioId] = useState("");
  const [url, setUrl] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.replace("/");
      return;
    }
    listRepositories(token)
      // Solo los públicos: el backend rechaza los privados y es mejor no
      // ofrecer una opción que va a fallar.
      .then((lista) => setRepositorios(lista.filter((r) => !r.is_private)))
      .catch((err: unknown) => {
        // Sin distinguir el motivo, un fallo de carga se confundiria con "no
        // tienes repositorios", que manda al usuario a buscar el problema
        // donde no esta.
        if (err instanceof ApiError && err.status === 401) {
          clearToken();
          router.replace("/");
          return;
        }
        setRepositorios([]);
        setError(
          err instanceof ApiError
            ? err.message
            : "No se pudieron cargar tus repositorios.",
        );
      });
  }, [router]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const token = getToken();
    if (!token || pending || !repositorioId || !url.trim()) return;

    setError(null);
    setPending(true);
    setAnalysis(null);

    try {
      const { analysis_id } = await analyzeCombined(token, repositorioId, url.trim());

      for (let intento = 0; intento < MAX_POLLS; intento += 1) {
        const actual = await getAnalysis(token, analysis_id);
        setAnalysis(actual);
        if (!IN_PROGRESS.has(actual.status)) return;
        await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
      }
      setError("El análisis está tardando más de lo esperado. Vuelve a intentarlo.");
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        clearToken();
        router.replace("/");
        return;
      }
      setAnalysis(null);
      setError(err instanceof ApiError ? err.message : "No se pudo iniciar el análisis.");
    } finally {
      setPending(false);
    }
  }

  const sinRepositorios = repositorios !== null && repositorios.length === 0 && !error;

  return (
    <main className="flex min-h-screen w-full flex-col bg-bg text-text">
      <div className="flex items-center gap-[14px] border-b border-border px-8 py-4">
        <button
          type="button"
          onClick={() => router.push("/analyze")}
          className="text-[13px] text-muted hover:text-text focus:outline-none focus:ring-[3px] focus:ring-accentDim"
        >
          ← Volver
        </button>
        <div className="h-4 w-px bg-border" />
        <div className="flex items-center gap-[10px]">
          <RadarMark size={18} />
          <span className="text-[14.5px] font-semibold">Código frente a producción</span>
        </div>
      </div>

      <div className="mx-auto flex w-full max-w-[620px] flex-col px-8 py-12">
        <h1 className="mb-1.5 text-[20px] font-semibold tracking-[-0.01em]">
          Compara tu repositorio con su despliegue
        </h1>
        <p className="mb-7 text-[13.5px] leading-[1.55] text-muted">
          Se analizan los dos por separado y después se explica por qué no puntúan igual.
        </p>

        <form onSubmit={handleSubmit}>
          <label
            htmlFor="repositorio"
            className="mb-[7px] block text-[12.5px] font-medium text-muted"
          >
            Repositorio
          </label>
          <select
            id="repositorio"
            required
            value={repositorioId}
            disabled={repositorios === null || sinRepositorios}
            onChange={(e) => setRepositorioId(e.target.value)}
            className="w-full rounded-[6px] border border-border bg-surface px-[13px] py-[11px] text-[14px] text-text focus:border-accent focus:outline-none focus:ring-[3px] focus:ring-accentDim disabled:text-faint"
          >
            <option value="">
              {repositorios === null
                ? "Cargando repositorios…"
                : sinRepositorios
                  ? "No hay repositorios públicos disponibles"
                  : repositorios.length === 0
                    ? "No se pudieron cargar los repositorios"
                    : "Elige un repositorio"}
            </option>
            {(repositorios ?? []).map((repositorio) => (
              <option key={repositorio.id} value={repositorio.id}>
                {repositorio.full_name}
              </option>
            ))}
          </select>

          <label htmlFor="url" className="mb-[7px] mt-4 block text-[12.5px] font-medium text-muted">
            Dirección donde está desplegado
          </label>
          <input
            id="url"
            type="url"
            required
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://mi-app.vercel.app"
            className="w-full rounded-[6px] border border-border bg-surface px-[13px] py-[11px] font-mono text-[14px] text-text placeholder:text-faint focus:border-accent focus:outline-none focus:ring-[3px] focus:ring-accentDim"
          />

          {error && (
            <p role="alert" className="mt-[9px] text-[12.5px] text-[oklch(0.68_0.19_25)]">
              {error}
            </p>
          )}

          <PrimaryButton
            type="submit"
            disabled={pending || !repositorioId || !url.trim()}
            className="mt-4 w-full"
            style={{ padding: "12px" }}
          >
            {pending ? "Analizando ambos…" : "Analizar ambos"}
          </PrimaryButton>
        </form>

        {analysis?.combined && analysis.status === "completed" && (
          <div className="mt-7">
            <CombinedPanel combined={analysis.combined} overallScore={analysis.overall_score} />
          </div>
        )}

        {analysis && (
          <div className="mt-4">
            <AnalysisPanel
              analysis={analysis}
              onClose={() => setAnalysis(null)}
              // CombinedPanel ya muestra las notas y el plan; aqui se
              // repetirian.
              embedded={analysis.combined !== null}
            />
          </div>
        )}

        {!analysis && (
          <div className="mt-4 flex flex-col gap-[9px]">
            <p className="flex items-start gap-[9px] text-[12px] leading-[1.55] text-faint">
              <InfoIcon />
              Tarda más que los otros modos: se ejecutan los dos análisis completos, uno detrás del
              otro.
            </p>
            <p className="flex items-start gap-[9px] text-[12px] leading-[1.55] text-faint">
              <InfoIcon />
              Si la dirección no parece corresponder al repositorio, se avisa pero el análisis
              continúa: un dominio propio o un monorepo son casos legítimos.
            </p>
          </div>
        )}
      </div>
    </main>
  );
}
