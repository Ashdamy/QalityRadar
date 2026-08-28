"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ApiError,
  createMonitor,
  deleteMonitor,
  getTimeline,
  listMonitors,
  listRepositories,
  type MonitorItem,
  type MonitorList,
  type Repository,
} from "@/lib/api";
import { clearToken, getToken } from "@/lib/auth";
import { RadarMark } from "@/components/RadarMark";
import { NotificationBell } from "@/components/NotificationBell";
import { Sparkline } from "@/components/Sparkline";

const ETIQUETA_INTERVALO: Record<number, string> = {
  15: "cada 15 min",
  60: "cada hora",
  360: "cada 6 h",
  1440: "cada día",
};

function scoreColor(score: number): string {
  if (score >= 80) return "text-[oklch(0.72_0.15_150)]";
  if (score >= 50) return "text-[oklch(0.80_0.14_85)]";
  return "text-[oklch(0.68_0.19_25)]";
}

function haceCuanto(iso: string | null): string {
  if (!iso) return "sin comprobar todavía";
  const minutos = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  if (minutos < 1) return "hace un momento";
  if (minutos < 60) return `hace ${minutos} min`;
  const horas = Math.floor(minutos / 60);
  if (horas < 24) return `hace ${horas} h`;
  return `hace ${Math.floor(horas / 24)} días`;
}

function GithubIcon({ apagado = false }: { apagado?: boolean }) {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 16 16"
      className={apagado ? "fill-faint" : "fill-muted"}
      aria-hidden="true"
    >
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z" />
    </svg>
  );
}

function GlobeIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      className="stroke-muted"
      strokeWidth={1.5}
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18" />
      <path d="M12 3a15 15 0 0 1 0 18a15 15 0 0 1 0-18" />
    </svg>
  );
}

/** Una tarjeta de proyecto vigilado, con su evolución reciente. */
function Vigilado({
  monitor,
  historico,
  onDejarDeVigilar,
}: {
  monitor: MonitorItem;
  historico: number[];
  onDejarDeVigilar: (id: string) => void;
}) {
  const nota = monitor.latest_score;
  // El delta se mide contra el primer análisis del histórico que tenemos, que
  // es lo que hace legible si el proyecto va a mejor o a peor.
  const delta =
    historico.length >= 2 ? Math.round(historico[historico.length - 1] - historico[0]) : null;

  const franja = !monitor.is_active
    ? "border-l-[oklch(0.80_0.14_85)]"
    : "border-l-[oklch(0.72_0.15_150)]";

  return (
    <article
      className={`grid grid-cols-[1fr_auto_auto] items-center gap-[22px] rounded-[8px] border border-border border-l-[3px] bg-surface p-[15px_18px_15px_16px] max-[720px]:grid-cols-[1fr_auto] ${franja}`}
    >
      <div className="min-w-0">
        <div className="mb-[5px] flex items-center gap-2">
          {monitor.target_type === "repository" ? (
            <GithubIcon apagado={!monitor.is_active} />
          ) : (
            <GlobeIcon />
          )}
          <span className="truncate font-mono text-[13px] font-medium">
            {monitor.target_name}
          </span>
          <span
            className={`shrink-0 rounded-[4px] border px-[7px] py-[2px] text-[10px] font-semibold uppercase tracking-[0.04em] ${
              monitor.is_active
                ? "border-[oklch(0.72_0.15_150_/_0.45)] text-[oklch(0.72_0.15_150)]"
                : "border-[oklch(0.80_0.14_85_/_0.45)] text-[oklch(0.80_0.14_85)]"
            }`}
          >
            {monitor.is_active ? "Activo" : "Pausado"}
          </span>
        </div>
        <div className="text-[11.5px] text-faint">
          {monitor.is_active ? (
            <>
              Comprobado {haceCuanto(monitor.last_checked_at)}
              {monitor.last_commit_sha && (
                <>
                  {" · "}
                  <code className="font-mono text-muted">
                    {monitor.last_commit_sha.slice(0, 7)}
                  </code>
                </>
              )}
              {" · "}
              {ETIQUETA_INTERVALO[monitor.interval_minutes] ??
                `cada ${monitor.interval_minutes} min`}
            </>
          ) : (
            "Se pausó tras varios intentos fallidos. Vuelve a engancharlo si sigue disponible."
          )}
        </div>
      </div>

      <div className="flex flex-col items-end gap-1 max-[720px]:col-span-2 max-[720px]:items-stretch">
        <Sparkline
          scores={historico}
          label={
            historico.length >= 2
              ? `Evolución: de ${Math.round(historico[0])} a ${Math.round(
                  historico[historico.length - 1],
                )}`
              : "Sin evolución todavía"
          }
        />
        <span className="font-mono text-[10.5px] text-faint">
          {historico.length > 0 ? `${historico.length} análisis` : "sin datos nuevos"}
        </span>
      </div>

      <div className="min-w-[74px] text-right">
        <div
          className={`font-mono text-[26px] font-medium leading-none tabular-nums ${
            nota === null ? "text-faint" : scoreColor(nota)
          }`}
        >
          {nota === null ? "—" : Math.round(nota)}
        </div>
        {delta !== null && delta !== 0 ? (
          <div
            className={`mt-1 font-mono text-[11.5px] tabular-nums ${
              delta > 0 ? "text-[oklch(0.72_0.15_150)]" : "text-[oklch(0.68_0.19_25)]"
            }`}
          >
            {delta > 0 ? "▲" : "▼"} {Math.abs(delta)}
          </div>
        ) : (
          <button
            type="button"
            onClick={() => onDejarDeVigilar(monitor.id)}
            className="mt-1 text-[11.5px] text-faint hover:text-text focus:outline-none focus:ring-[3px] focus:ring-accentDim"
          >
            Dejar de vigilar
          </button>
        )}
      </div>
    </article>
  );
}

export default function MonitorsPage() {
  const router = useRouter();
  const [datos, setDatos] = useState<MonitorList | null>(null);
  const [historicos, setHistoricos] = useState<Record<string, number[]>>({});
  const [repositorios, setRepositorios] = useState<Repository[]>([]);
  const [eligiendo, setEligiendo] = useState(false);
  const [repositorioId, setRepositorioId] = useState("");
  const [intervalo, setIntervalo] = useState(60);
  const [error, setError] = useState<string | null>(null);

  /**
   * Trae los monitores y el historico de cada uno. Devuelve los datos en vez
   * de guardarlos: asi el efecto puede escribir el estado dentro de un
   * callback y no en su cuerpo, que es lo que React desaconseja.
   */
  const obtener = useCallback(async (token: string) => {
    const lista = await listMonitors(token);

    // El historico alimenta la minigrafica de cada proyecto. Se piden en
    // paralelo: son consultas independientes y en serie la pantalla tardaria
    // en aparecer.
    const entradas = await Promise.all(
      lista.monitors
        .filter((m) => m.repository_id)
        .map(async (m) => {
          try {
            const linea = await getTimeline(token, m.repository_id!);
            const notas = linea
              .filter((e) => e.overall_score !== null)
              .map((e) => e.overall_score as number)
              .reverse();
            return [m.id, notas] as const;
          } catch {
            return [m.id, []] as const;
          }
        }),
    );
    return { lista, historicos: Object.fromEntries(entradas) };
  }, []);

  const manejarFallo = useCallback(
    (err: unknown) => {
      if (err instanceof ApiError && err.status === 401) {
        clearToken();
        router.replace("/");
        return;
      }
      setError("No se pudo cargar el seguimiento.");
    },
    [router],
  );

  /** Recarga tras una accion del usuario (enganchar o dejar de vigilar). */
  const refrescar = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    try {
      const { lista, historicos: nuevos } = await obtener(token);
      setDatos(lista);
      setHistoricos(nuevos);
    } catch (err) {
      manejarFallo(err);
    }
  }, [obtener, manejarFallo]);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.replace("/");
      return;
    }

    let vivo = true;
    obtener(token)
      .then(({ lista, historicos: nuevos }) => {
        if (!vivo) return;
        setDatos(lista);
        setHistoricos(nuevos);
      })
      .catch((err: unknown) => {
        if (vivo) manejarFallo(err);
      });
    return () => {
      vivo = false;
    };
  }, [obtener, manejarFallo, router]);

  async function abrirSelector() {
    setEligiendo(true);
    setError(null);
    const token = getToken();
    if (!token) return;
    try {
      const lista = await listRepositories(token);
      setRepositorios(lista.filter((r) => !r.is_private));
    } catch {
      setRepositorios([]);
      setError("No se pudieron cargar tus repositorios.");
    }
  }

  async function engancharProyecto() {
    const token = getToken();
    if (!token || !repositorioId) return;
    setError(null);
    try {
      await createMonitor(token, { repositoryId: repositorioId, intervalMinutes: intervalo });
      setEligiendo(false);
      setRepositorioId("");
      await refrescar();
    } catch (err) {
      // El backend explica el motivo (por ejemplo, el tope de proyectos), y
      // ese mensaje es más útil que uno genérico.
      setError(err instanceof ApiError ? err.message : "No se pudo enganchar el proyecto.");
    }
  }

  async function dejarDeVigilar(id: string) {
    const token = getToken();
    if (!token) return;
    try {
      await deleteMonitor(token, id);
      await refrescar();
    } catch {
      setError("No se pudo dejar de vigilar.");
    }
  }

  const sinHueco = datos !== null && datos.active >= datos.max_monitors;

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
        <div className="flex items-center gap-3">
          <NotificationBell />
          <button
            type="button"
            onClick={() => {
              clearToken();
              router.push("/");
            }}
            className="text-[13px] text-muted hover:text-text focus:outline-none focus:ring-[3px] focus:ring-accentDim"
          >
            Cerrar sesión
          </button>
        </div>
      </div>

      <div className="mx-auto w-full max-w-[940px] px-8 pb-[72px] pt-10">
        <h1 className="mb-[5px] text-[22px] font-semibold tracking-[-0.01em]">Seguimiento</h1>
        <p className="mb-7 max-w-[62ch] text-[13.5px] text-muted">
          Los proyectos que dejas enganchados se revisan solos. Cuando subes código, QalitiRadar lo
          detecta y vuelve a analizarlo: tú solo entras a ver cómo va.
        </p>

        {datos && (
          <section
            aria-label="Resumen de seguimiento"
            className="mb-7 grid grid-cols-3 gap-px overflow-hidden rounded-[10px] border border-border bg-border max-[720px]:grid-cols-1"
          >
            <div className="bg-surface p-[16px_20px]">
              <div className="mb-[6px] text-[10.5px] uppercase tracking-[0.06em] text-faint">
                Proyectos vigilados
              </div>
              <div className="font-mono text-[22px] font-medium leading-none tabular-nums">
                {datos.active}
                <span className="text-[15px] text-faint"> / {datos.max_monitors}</span>
              </div>
              <div className="mt-[5px] text-[11.5px] text-faint">
                {sinHueco ? "Has llegado al tope" : "Puedes vigilar uno más"}
              </div>
            </div>
            <div className="bg-surface p-[16px_20px]">
              <div className="mb-[6px] text-[10.5px] uppercase tracking-[0.06em] text-faint">
                Avisos
              </div>
              <div className="font-mono text-[22px] font-medium leading-none">Campana</div>
              <div className="mt-[5px] text-[11.5px] text-faint">
                Te contamos cada análisis automático
              </div>
            </div>
            <div className="bg-surface p-[16px_20px]">
              <div className="mb-[6px] text-[10.5px] uppercase tracking-[0.06em] text-faint">
                Cómo funciona
              </div>
              <div className="font-mono text-[22px] font-medium leading-none">5 min</div>
              <div className="mt-[5px] text-[11.5px] text-faint">
                Comprobar no analiza: solo mira si cambió
              </div>
            </div>
          </section>
        )}

        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-4">
          <h2 className="text-[12.5px] font-semibold text-muted">Enganchados</h2>
          {!eligiendo && (
            <button
              type="button"
              onClick={abrirSelector}
              disabled={sinHueco}
              className="rounded-[6px] bg-accent px-[13px] py-[7px] text-[12.5px] font-medium text-onAccent disabled:opacity-50 focus:outline-none focus:ring-[3px] focus:ring-accentDim"
            >
              Vigilar un proyecto
            </button>
          )}
        </div>

        {eligiendo && (
          <div className="mb-4 rounded-[8px] border border-border bg-surface p-[18px_20px]">
            <label
              htmlFor="repositorio"
              className="mb-[7px] block text-[12.5px] font-medium text-muted"
            >
              Repositorio
            </label>
            <select
              id="repositorio"
              value={repositorioId}
              onChange={(e) => setRepositorioId(e.target.value)}
              className="w-full rounded-[6px] border border-border bg-bg px-[13px] py-[10px] text-[13.5px] text-text focus:border-accent focus:outline-none focus:ring-[3px] focus:ring-accentDim"
            >
              <option value="">
                {repositorios.length === 0 ? "No hay repositorios disponibles" : "Elige uno"}
              </option>
              {repositorios.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.full_name}
                </option>
              ))}
            </select>

            <label
              htmlFor="intervalo"
              className="mb-[7px] mt-4 block text-[12.5px] font-medium text-muted"
            >
              Cada cuánto comprobar si hay cambios
            </label>
            <select
              id="intervalo"
              value={intervalo}
              onChange={(e) => setIntervalo(Number(e.target.value))}
              className="w-full rounded-[6px] border border-border bg-bg px-[13px] py-[10px] text-[13.5px] text-text focus:border-accent focus:outline-none focus:ring-[3px] focus:ring-accentDim"
            >
              {(datos?.allowed_intervals ?? [60]).map((minutos) => (
                <option key={minutos} value={minutos}>
                  {ETIQUETA_INTERVALO[minutos] ?? `cada ${minutos} min`}
                </option>
              ))}
            </select>

            <div className="mt-4 flex gap-2">
              <button
                type="button"
                onClick={engancharProyecto}
                disabled={!repositorioId}
                className="rounded-[6px] bg-accent px-[13px] py-[7px] text-[12.5px] font-medium text-onAccent disabled:opacity-50 focus:outline-none focus:ring-[3px] focus:ring-accentDim"
              >
                Empezar a vigilar
              </button>
              <button
                type="button"
                onClick={() => setEligiendo(false)}
                className="rounded-[6px] border border-border px-[13px] py-[7px] text-[12.5px] text-muted hover:text-text focus:outline-none focus:ring-[3px] focus:ring-accentDim"
              >
                Cancelar
              </button>
            </div>
          </div>
        )}

        {error && (
          <p role="alert" className="mb-4 text-[12.5px] text-[oklch(0.68_0.19_25)]">
            {error}
          </p>
        )}

        {datos && datos.monitors.length === 0 && !eligiendo && (
          <div className="rounded-[10px] border border-dashed border-border bg-panel p-[30px_24px] text-center">
            <p className="mb-1 text-[13px] text-muted">Todavía no vigilas ningún proyecto.</p>
            <p className="mx-auto max-w-[46ch] text-[12px] text-faint">
              Engancha un repositorio y QalitiRadar lo revisará solo cada vez que subas código. No
              hace falta que vuelvas a pulsar «Analizar».
            </p>
          </div>
        )}

        <div className="flex flex-col gap-[10px]">
          {datos?.monitors.map((monitor) => (
            <Vigilado
              key={monitor.id}
              monitor={monitor}
              historico={historicos[monitor.id] ?? []}
              onDejarDeVigilar={dejarDeVigilar}
            />
          ))}
        </div>

        <p className="mx-auto mt-[34px] max-w-[64ch] text-center text-[12px] leading-[1.6] text-faint">
          Comprobar si algo cambió cuesta una llamada a GitHub y no descarga tu código. El análisis
          completo solo se lanza cuando de verdad hay un commit nuevo.
        </p>
      </div>
    </main>
  );
}
