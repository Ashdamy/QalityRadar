"use client";

import { useState } from "react";

type Modo = "repo" | "url" | "combinado";

const MODOS: Record<
  Modo,
  {
    etiqueta: string;
    subtitulo: string;
    titulo: string;
    texto: string;
    dato: string;
    dims: { nombre: string; origen: string }[];
  }
> = {
  repo: {
    etiqueta: "Código",
    subtitulo: "MODO REPOSITORIO",
    titulo: "Lo que hay dentro de tu repositorio",
    texto:
      "Lee el código de un repositorio de GitHub: secretos expuestos, dependencias vulnerables, pruebas, estructura, documentación y cuánto se mantiene vivo el proyecto.",
    dato: "5 características ISO · repositorios de GitHub",
    dims: [
      { nombre: "Seguridad", origen: "Gitleaks · Semgrep · OSV" },
      { nombre: "Fiabilidad", origen: "pruebas · CI" },
      { nombre: "Mantenibilidad", origen: "estructura · deuda" },
      { nombre: "Adecuación funcional", origen: "documentación · licencia" },
      { nombre: "Flexibilidad", origen: "contenedores · config" },
      { nombre: "Salud del proyecto (aparte, no es ISO)", origen: "commits · issues" },
    ],
  },
  url: {
    etiqueta: "Producción",
    subtitulo: "MODO URL",
    titulo: "Lo que reciben tus usuarios",
    texto:
      "Analiza la aplicación ya desplegada, sin acceso al código: velocidad, cabeceras de seguridad, accesibilidad y cómo se comporta en distintos navegadores.",
    dato: "5 dimensiones · cualquier aplicación pública",
    dims: [
      { nombre: "Eficiencia de desempeño", origen: "Lighthouse" },
      { nombre: "Seguridad", origen: "cabeceras · HTTPS" },
      { nombre: "Capacidad de interacción", origen: "Lighthouse" },
      { nombre: "Accesibilidad (inclusividad)", origen: "Lighthouse" },
      { nombre: "Compatibilidad", origen: "estándares web" },
    ],
  },
  combinado: {
    etiqueta: "Código frente a producción",
    subtitulo: "MODO COMBINADO · RECOMENDADO",
    titulo: "Por qué no puntúan igual",
    texto:
      "Analiza las dos caras y explica las diferencias. Si tu proveedor te regala HTTPS y compresión, esa ventaja no es tuya. Si el código es bueno pero el despliegue no, tu calidad no llega a quien usa la aplicación.",
    dato: "10 características · un plan de mejora único",
    dims: [
      { nombre: "Las 5 del código", origen: "repositorio" },
      { nombre: "Las 5 de producción", origen: "URL" },
      { nombre: "Discrepancias explicadas", origen: "código ≠ producción" },
      { nombre: "Plan de mejora priorizado", origen: "lo que más sube primero" },
    ],
  },
};

const ORDEN: Modo[] = ["repo", "url", "combinado"];

/** Selector de la landing: enseña qué mide cada modo de análisis. */
export function ModosDeAnalisis() {
  const [modo, setModo] = useState<Modo>("combinado");
  const actual = MODOS[modo];

  return (
    <>
      <div role="group" aria-label="Modos de análisis" className="mb-6 flex flex-wrap gap-2">
        {ORDEN.map((id) => {
          const activo = id === modo;
          return (
            <button
              key={id}
              type="button"
              aria-pressed={activo}
              onClick={() => setModo(id)}
              className={`min-h-[44px] cursor-pointer rounded-full border px-[18px] text-[15px] transition-colors duration-150 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ${
                activo
                  ? "border-accent bg-accent font-semibold text-onAccent"
                  : "border-border font-medium text-text hover:border-muted"
              }`}
            >
              {MODOS[id].etiqueta}
            </button>
          );
        })}
      </div>

      <div className="grid grid-cols-1 gap-8 rounded-2xl border border-border bg-surface p-6 md:grid-cols-2 md:p-10">
        <div>
          <p className="mb-2.5 font-mono text-[13px] text-muted">{actual.subtitulo}</p>
          <h3 className="mb-3.5 text-[26px] font-semibold leading-tight">{actual.titulo}</h3>
          <p className="mb-6 text-[16.5px] text-muted">{actual.texto}</p>
          <p className="inline-flex rounded-full bg-surface2 px-3.5 py-2 text-sm">{actual.dato}</p>
        </div>
        <div>
          <p className="mb-3.5 text-sm text-muted">Dimensiones que mide</p>
          <ul className="flex flex-col gap-2.5">
            {actual.dims.map((d) => (
              <li
                key={d.nombre}
                className="flex items-center justify-between gap-4 rounded-[10px] border border-border bg-panel px-4 py-3.5"
              >
                <span className="font-medium">{d.nombre}</span>
                <span className="text-right font-mono text-[12.5px] text-muted">{d.origen}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </>
  );
}
