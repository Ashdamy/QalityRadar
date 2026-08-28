"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ApiError,
  getAnalysis,
  getGithubAuthorizationUrl,
  listRepositories,
  startRepositoryAnalysis,
  type Analysis,
  type Repository,
} from "@/lib/api";
import { clearToken, getToken } from "@/lib/auth";
import { RadarMark } from "@/components/RadarMark";
import { NotificationBell } from "@/components/NotificationBell";
import { PrimaryButton } from "@/components/PrimaryButton";
import { GithubButton } from "@/components/GithubButton";
import { AnalysisPanel } from "@/components/AnalysisPanel";

// Estados en los que el analisis sigue en marcha y hay que volver a consultar.
const IN_PROGRESS: ReadonlySet<Analysis["status"]> = new Set([
  "pending",
  "cloning",
  "running",
  "scoring",
]);
const POLL_INTERVAL_MS = 2000;
// Tope de sondeo algo mayor que el limite de 10 minutos del backend, para que
// un analisis que agota su tiempo se vea reflejado en vez de quedar colgado.
const MAX_POLLS = 330;

type LoadState =
  | { kind: "loading" }
  | { kind: "ready"; repos: Repository[] }
  | { kind: "needsGithub" }
  | { kind: "error"; message: string };

function formatLastAnalyzed(iso: string | null): string {
  if (!iso) return "Nunca analizado";

  const cuando = new Date(iso);
  const minutos = Math.floor((Date.now() - cuando.getTime()) / 60000);
  if (minutos < 1) return "Hace un momento";
  if (minutos < 60) return `Hace ${minutos} min`;

  const horas = Math.floor(minutos / 60);
  if (horas < 24) return `Hace ${horas} h`;

  const dias = Math.floor(horas / 24);
  if (dias === 1) return "Ayer";
  if (dias < 30) return `Hace ${dias} días`;
  return cuando.toLocaleDateString("es", { day: "2-digit", month: "short", year: "numeric" });
}

function RepoIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="shrink-0" aria-hidden="true">
      <path
        d="M4 2v9a2 2 0 002 2h6M4 2a2 2 0 100 4M4 2a2 2 0 110 4M12 4a2 2 0 100-4 2 2 0 000 4zm0 0v5"
        className="stroke-faint"
        strokeWidth="1.3"
        strokeLinecap="round"
      />
    </svg>
  );
}

export default function RepositoriesPage() {
  const router = useRouter();
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [githubPending, setGithubPending] = useState(false);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [analyzePending, setAnalyzePending] = useState(false);
  const [analyzeError, setAnalyzeError] = useState<string | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.replace("/");
      return;
    }

    let cancelled = false;
    listRepositories(token)
      .then((repos) => {
        if (!cancelled) setState({ kind: "ready", repos });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError) {
          if (err.status === 401) {
            clearToken();
            router.replace("/");
            return;
          }
          if (err.status === 400) {
            setState({ kind: "needsGithub" });
            return;
          }
          setState({ kind: "error", message: err.message });
          return;
        }
        setState({ kind: "error", message: "No se pudo contactar al servidor. Intenta de nuevo." });
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const filtered = useMemo(() => {
    if (state.kind !== "ready") return [];
    const q = query.trim().toLowerCase();
    if (!q) return state.repos;
    return state.repos.filter(
      (r) => r.name.toLowerCase().includes(q) || r.full_name.toLowerCase().includes(q),
    );
  }, [state, query]);

  function handleLogout() {
    clearToken();
    router.push("/");
  }

  async function handleConnectGithub() {
    setGithubPending(true);
    try {
      const { authorization_url } = await getGithubAuthorizationUrl();
      window.location.href = authorization_url;
    } catch {
      setGithubPending(false);
      setState({ kind: "error", message: "No se pudo iniciar la conexión con GitHub. Intenta de nuevo." });
    }
  }

  async function handleAnalyze() {
    const token = getToken();
    if (!selectedId || !token || analyzePending) return;

    setAnalyzeError(null);
    setAnalyzePending(true);
    setAnalysis(null);

    try {
      const { analysis_id } = await startRepositoryAnalysis(token, selectedId);

      // Se sondea hasta que el analisis deja de estar en marcha. El backend
      // corta a los 10 minutos, y MAX_POLLS deja algo de margen sobre eso.
      for (let attempt = 0; attempt < MAX_POLLS; attempt += 1) {
        const current = await getAnalysis(token, analysis_id);
        setAnalysis(current);
        if (!IN_PROGRESS.has(current.status)) {
          // La fecha de "último análisis" acaba de cambiar en el servidor: se
          // refleja aquí sin obligar al usuario a recargar la página.
          if (current.status === "completed") {
            setState((actual) =>
              actual.kind === "ready"
                ? {
                    ...actual,
                    repos: actual.repos.map((r) =>
                      r.id === selectedId
                        ? { ...r, last_analyzed_at: new Date().toISOString() }
                        : r,
                    ),
                  }
                : actual,
            );
          }
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
      }
      setAnalyzeError("El análisis está tardando más de lo esperado. Vuelve a intentarlo.");
    } catch (error) {
      setAnalysis(null);
      setAnalyzeError(
        error instanceof ApiError
          ? error.message
          : "No se pudo iniciar el análisis. Intenta de nuevo.",
      );
    } finally {
      setAnalyzePending(false);
    }
  }

  const hasSelection = !!selectedId;

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
        <div className="flex items-center gap-[14px]">
          <NotificationBell />
          <div className="h-[26px] w-[26px] rounded-[6px] border border-border bg-surface2" aria-hidden="true" />
          <button
            type="button"
            onClick={handleLogout}
            className="cursor-pointer text-[13px] text-muted hover:text-text focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2"
          >
            Cerrar sesión
          </button>
        </div>
      </div>

      <div className="mx-auto flex w-full max-w-[900px] flex-1 flex-col gap-5 p-8">
        <div>
          <h1 className="mb-1 text-[19px] font-semibold tracking-[-0.01em]">
            Selecciona un repositorio para analizar
          </h1>
          <p className="text-[13.5px] text-muted">
            Solo se muestran repositorios públicos. Los privados llegan en una fase futura.
          </p>
        </div>

        {state.kind === "loading" && (
          <div className="rounded-lg border border-border p-8 text-center text-[13.5px] text-faint">
            Cargando repositorios…
          </div>
        )}

        {state.kind === "error" && (
          <div className="rounded-lg border border-border p-8 text-center text-[13.5px] text-bad">
            {state.message}
          </div>
        )}

        {state.kind === "needsGithub" && (
          <div className="flex flex-col items-center gap-4 rounded-lg border border-border p-8 text-center">
            <p className="text-[13.5px] text-muted">
              Necesitas vincular tu cuenta de GitHub para ver tus repositorios.
            </p>
            <GithubButton
              label="Conectar GitHub"
              onClick={handleConnectGithub}
              disabled={githubPending}
            />
          </div>
        )}

        {state.kind === "ready" && (
          <>
            <div className="flex gap-[10px]">
              <label htmlFor="repo-search" className="sr-only">
                Buscar repositorio
              </label>
              <input
                id="repo-search"
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Buscar repositorio…"
                className="flex-1 rounded-[6px] border border-border bg-surface px-[12px] py-[9px] text-[13.5px] text-text placeholder:text-faint focus:border-accent focus:outline-none focus:ring-[3px] focus:ring-accentDim"
              />
              <button
                type="button"
                disabled={!hasSelection}
                onClick={() => selectedId && router.push(`/repositories/${selectedId}/history`)}
                className="whitespace-nowrap rounded-[6px] border border-border bg-surface px-[18px] py-[9px] text-[13.5px] text-text disabled:cursor-not-allowed disabled:text-faint focus:outline-none focus:ring-[3px] focus:ring-accentDim"
              >
                Ver histórico
              </button>
              <PrimaryButton
                type="button"
                disabled={!hasSelection || analyzePending}
                onClick={handleAnalyze}
                className="whitespace-nowrap"
                style={{ padding: "9px 18px" }}
              >
                {analyzePending ? "Analizando…" : "Analizar seleccionado"}
              </PrimaryButton>
            </div>

            {analyzeError && (
              <p role="alert" className="-mt-3 text-[12.5px] text-[oklch(0.68_0.19_25)]">
                {analyzeError}
              </p>
            )}

            {analysis && <AnalysisPanel analysis={analysis} onClose={() => setAnalysis(null)} />}

            {filtered.length === 0 ? (
              <div className="p-8 text-center text-[13.5px] text-faint">
                No hay repositorios que coincidan con &ldquo;{query}&rdquo;.
              </div>
            ) : (
              <div className="overflow-hidden rounded-lg border border-border">
                {filtered.map((repo) => {
                  const selected = repo.id === selectedId;
                  return (
                    <button
                      key={repo.id}
                      type="button"
                      onClick={() => setSelectedId(repo.id)}
                      className={`flex w-full cursor-pointer items-center gap-[14px] border-b border-border px-4 py-[14px] text-left last:border-b-0 hover:bg-surface2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent focus-visible:-outline-offset-2 ${
                        selected ? "bg-accentDim" : "bg-transparent"
                      }`}
                    >
                      <span
                        className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full border-[1.5px] ${
                          selected ? "border-accent bg-accent" : "border-border bg-transparent"
                        }`}
                      >
                        {selected && <span className="h-[6px] w-[6px] rounded-full bg-bg" />}
                      </span>

                      <RepoIcon />

                      <span className="min-w-0 flex-1">
                        <span className="block truncate font-mono text-[13.5px] font-medium">
                          {repo.name}
                        </span>
                        <span className="mt-0.5 block truncate text-xs text-faint">{repo.full_name}</span>
                      </span>

                      <span className="whitespace-nowrap rounded-[4px] border border-border px-[7px] py-0.5 text-[11px] text-faint">
                        {repo.is_private ? "Privado" : "Público"}
                      </span>

                      <span className="w-[150px] whitespace-nowrap text-right text-xs text-muted">
                        {formatLastAnalyzed(repo.last_analyzed_at)}
                      </span>
                    </button>
                  );
                })}
              </div>
            )}
          </>
        )}
      </div>
    </main>
  );
}
