"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { clearToken, getToken } from "@/lib/auth";
import { RadarMark } from "@/components/RadarMark";

function GithubIcon() {
  return (
    <svg width="19" height="19" viewBox="0 0 16 16" className="fill-accent" aria-hidden="true">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z" />
    </svg>
  );
}

function GlobeIcon() {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      className="stroke-accent"
      strokeWidth={1.5}
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18" />
      <path d="M12 3a15 15 0 0 1 0 18a15 15 0 0 1 0-18" />
    </svg>
  );
}

function BothIcon() {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      className="stroke-accent"
      strokeWidth={1.5}
      aria-hidden="true"
    >
      <circle cx="8.5" cy="12" r="5.5" />
      <circle cx="15.5" cy="12" r="5.5" />
    </svg>
  );
}

type Modo = {
  titulo: string;
  descripcion: string;
  etiquetas: string[];
  icono: React.ReactNode;
  destino: string | null;
  recomendado?: boolean;
  proximamente?: boolean;
};

const MODOS: Modo[] = [
  {
    titulo: "Analizar repositorio",
    descripcion:
      "Evalúa el código fuente de un repositorio público de GitHub: estructura, documentación, pruebas, seguridad y dependencias.",
    etiquetas: ["6 dimensiones", "Gitleaks", "Sin ejecutar tu código"],
    icono: <GithubIcon />,
    destino: "/repositories",
  },
  {
    titulo: "Analizar URL",
    descripcion:
      "Evalúa una aplicación ya desplegada: rendimiento, cabeceras de seguridad, accesibilidad y compatibilidad móvil.",
    etiquetas: ["5 dimensiones", "Sin acceso al código", "Cualquier plataforma"],
    icono: <GlobeIcon />,
    destino: "/analyze/url",
  },
  {
    titulo: "Analizar ambos",
    descripcion:
      "Compara el código con lo que hay en producción y detecta discrepancias entre ambos.",
    etiquetas: ["Visión completa", "Discrepancias", "Nota consolidada"],
    icono: <BothIcon />,
    destino: null,
    recomendado: true,
    proximamente: true,
  },
];

export default function AnalyzePage() {
  const router = useRouter();

  // Si no hay sesion se redirige; la pantalla se dibuja igual y desaparece
  // enseguida, que es preferible a mantener un estado solo para ocultarla.
  useEffect(() => {
    if (!getToken()) router.replace("/");
  }, [router]);

  return (
    <main className="flex min-h-screen w-full flex-col bg-bg text-text">
      <div className="flex items-center justify-between border-b border-border px-8 py-4">
        <div className="flex items-center gap-[10px]">
          <RadarMark size={20} />
          <span className="text-[14.5px] font-semibold">QalitiRadar</span>
        </div>
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

      <div className="flex flex-1 flex-col items-center justify-center px-8 py-12">
        <h1 className="mb-1.5 text-[22px] font-semibold tracking-[-0.01em]">
          ¿Qué quieres analizar?
        </h1>
        <p className="mb-9 text-[13.5px] text-muted">
          Elige cómo quieres evaluar la calidad de tu proyecto.
        </p>

        <div className="grid gap-4 md:grid-cols-3">
          {MODOS.map((modo) => {
            const habilitado = modo.destino !== null;
            return (
              <button
                key={modo.titulo}
                type="button"
                disabled={!habilitado}
                onClick={() => modo.destino && router.push(modo.destino)}
                className={`relative flex min-h-[236px] w-[268px] flex-col gap-3 rounded-[10px] border bg-surface p-[24px_22px] text-left transition-colors focus:outline-none focus:ring-[3px] focus:ring-accentDim ${
                  modo.recomendado ? "border-accent" : "border-border"
                } ${habilitado ? "cursor-pointer hover:border-accent" : "cursor-not-allowed opacity-70"}`}
              >
                {modo.recomendado && (
                  <span className="absolute -top-[9px] left-[22px] rounded-[4px] bg-accent px-2 py-[2px] text-[10.5px] font-semibold uppercase tracking-[0.04em] text-[oklch(0.15_0.01_195)]">
                    {modo.proximamente ? "Próximamente" : "Recomendado"}
                  </span>
                )}

                <div className="flex h-9 w-9 items-center justify-center rounded-[8px] bg-surface2">
                  {modo.icono}
                </div>

                <div>
                  <h2 className="mb-[5px] text-[15px] font-semibold">{modo.titulo}</h2>
                  <p className="text-[12.5px] leading-[1.55] text-muted">{modo.descripcion}</p>
                </div>

                <div className="mt-auto flex flex-wrap gap-[5px]">
                  {modo.etiquetas.map((etiqueta) => (
                    <span
                      key={etiqueta}
                      className="rounded-[4px] border border-border px-[7px] py-[2px] text-[10.5px] text-faint"
                    >
                      {etiqueta}
                    </span>
                  ))}
                </div>
              </button>
            );
          })}
        </div>

        <p className="mt-8 max-w-[560px] text-center text-[12px] leading-[1.6] text-faint">
          Las puntuaciones son una aproximación al modelo de calidad ISO/IEC 25010. No constituyen
          una certificación oficial.
        </p>
      </div>
    </main>
  );
}
