"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ApiError,
  analyzeUrl,
  getAnalysis,
  type Analysis,
} from "@/lib/api";
import { getToken } from "@/lib/auth";
import { RadarMark } from "@/components/RadarMark";
import { PrimaryButton } from "@/components/PrimaryButton";
import { AnalysisPanel } from "@/components/AnalysisPanel";

const IN_PROGRESS: ReadonlySet<Analysis["status"]> = new Set([
  "pending",
  "cloning",
  "running",
  "scoring",
]);
const POLL_INTERVAL_MS = 2000;
const MAX_POLLS = 330;

const COMPROBACIONES = [
  {
    peso: "25%",
    nombre: "Rendimiento",
    detalle: "Tiempo de respuesta, compresión, caché y peso del documento.",
  },
  {
    peso: "25%",
    nombre: "Seguridad",
    detalle: "HTTPS, HSTS, política de contenido y protección contra incrustación.",
  },
  {
    peso: "20%",
    nombre: "Usabilidad",
    detalle: "Título, descripción, encabezado y estructura semántica.",
  },
  {
    peso: "15%",
    nombre: "Accesibilidad",
    detalle: "Idioma declarado, texto alternativo y etiquetas de formulario.",
  },
  { peso: "15%", nombre: "Compatibilidad", detalle: "Adaptación a pantallas móviles." },
];

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

export default function AnalyzeUrlPage() {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);

  useEffect(() => {
    if (!getToken()) router.replace("/");
  }, [router]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const token = getToken();
    if (!token || pending || !url.trim()) return;

    setError(null);
    setPending(true);
    setAnalysis(null);

    try {
      const { analysis_id } = await analyzeUrl(token, url.trim());

      for (let intento = 0; intento < MAX_POLLS; intento += 1) {
        const actual = await getAnalysis(token, analysis_id);
        setAnalysis(actual);
        if (!IN_PROGRESS.has(actual.status)) return;
        await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
      }
      setError("El análisis está tardando más de lo esperado. Vuelve a intentarlo.");
    } catch (err) {
      setAnalysis(null);
      // El backend explica por qué rechaza una dirección (por ejemplo, que
      // apunta a una IP interna); ese mensaje es útil y se muestra tal cual.
      setError(err instanceof ApiError ? err.message : "No se pudo iniciar el análisis.");
    } finally {
      setPending(false);
    }
  }

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
          <span className="text-[14.5px] font-semibold">Analizar URL</span>
        </div>
      </div>

      <div className="mx-auto flex w-full max-w-[620px] flex-col px-8 py-12">
        <h1 className="mb-1.5 text-[20px] font-semibold tracking-[-0.01em]">
          Analiza una aplicación desplegada
        </h1>
        <p className="mb-7 text-[13.5px] leading-[1.55] text-muted">
          Pega la dirección pública de tu aplicación. No hace falta acceso al código.
        </p>

        <form onSubmit={handleSubmit}>
          <label htmlFor="url" className="mb-[7px] block text-[12.5px] font-medium text-muted">
            Dirección de la aplicación
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
            disabled={pending || !url.trim()}
            className="mt-4 w-full"
            style={{ padding: "12px" }}
          >
            {pending ? "Analizando…" : "Analizar"}
          </PrimaryButton>
        </form>

        {analysis && (
          <div className="mt-7">
            <AnalysisPanel analysis={analysis} onClose={() => setAnalysis(null)} />
          </div>
        )}

        {!analysis && (
          <>
            <div className="mt-9 rounded-[8px] border border-border bg-surface p-[20px_22px]">
              <h2 className="mb-3.5 text-[12.5px] font-semibold text-muted">Qué se comprueba</h2>
              <div className="flex flex-col gap-3">
                {COMPROBACIONES.map((c) => (
                  <div key={c.nombre} className="flex items-start gap-3">
                    <span className="w-[34px] shrink-0 pt-[1px] font-mono text-[11.5px] text-accent">
                      {c.peso}
                    </span>
                    <div>
                      <div className="text-[13px] font-medium">{c.nombre}</div>
                      <div className="mt-[2px] text-[12px] leading-[1.5] text-faint">
                        {c.detalle}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="mt-4 flex flex-col gap-[9px]">
              <p className="flex items-start gap-[9px] text-[12px] leading-[1.55] text-faint">
                <InfoIcon />
                Solo direcciones públicas. Se rechazan direcciones internas y de red local por
                seguridad.
              </p>
              <p className="flex items-start gap-[9px] text-[12px] leading-[1.55] text-faint">
                <InfoIcon />
                Se analiza una sola página, la que indiques. Se respeta el servidor: una única
                petición.
              </p>
            </div>
          </>
        )}
      </div>
    </main>
  );
}
