"use client";

import { useEffect, useState } from "react";
import { RadarCargando } from "@/components/RadarCargando";
import { getAnalysis, type Analysis, type MedicionNavegador as Medicion } from "@/lib/api";

const NOTA =
  "Las páginas se abren en un navegador aislado, igual que el resto de los análisis corren en un contenedor sin acceso a tu red.";

// Cada cuánto se pregunta mientras se mide, y hasta cuándo: el contenedor se
// corta a los 90 s y la tarea a los 150 s; pasado eso algo fue mal.
const INTERVALO_MS = 4000;
const MAX_CONSULTAS = 60;

const CALIFICACION = {
  bueno: { texto: "Bueno", clase: "border-[oklch(0.72_0.15_150)] text-[oklch(0.72_0.15_150)]" },
  mejorable: { texto: "Mejorable", clase: "border-[oklch(0.80_0.14_85)] text-[oklch(0.80_0.14_85)]" },
  malo: { texto: "Malo", clase: "border-[oklch(0.68_0.19_25)] text-[oklch(0.68_0.19_25)]" },
} as const;

const numero = new Intl.NumberFormat("es", { maximumFractionDigits: 2 });

function Insignia({ children }: { children: string }) {
  return (
    <span className="rounded-[4px] border border-accent px-[5px] text-[10.5px] text-accent">{children}</span>
  );
}

function Vitales({ m }: { m: Medicion }) {
  const filas = [
    { clave: "lcp_ms", nombre: "LCP · carga del contenido principal", valor: m.lcp_ms, formato: (v: number) => `${numero.format(v / 1000)} s` },
    { clave: "tbt_ms", nombre: "TBT · tiempo bloqueado", valor: m.tbt_ms, formato: (v: number) => `${numero.format(v)} ms` },
    { clave: "cls", nombre: "CLS · saltos de diseño", valor: m.cls, formato: (v: number) => numero.format(v) },
  ] as const;

  return (
    <ul className="mt-2 flex flex-col gap-[6px]">
      {filas.map(({ clave, nombre, valor, formato }) => {
        const nota = m.ratings[clave];
        if (valor === null || !nota) return null;
        return (
          <li key={clave} className="flex items-baseline justify-between gap-3 text-[12.5px]">
            <span className="text-muted">{nombre}</span>
            <span className="flex shrink-0 items-baseline gap-2">
              <span className="font-mono">{formato(valor)}</span>
              {/* Texto además de color: se lee igual sin distinguir colores. */}
              <span className={`rounded-[4px] border px-[5px] text-[10.5px] ${CALIFICACION[nota].clase}`}>
                {CALIFICACION[nota].texto}
              </span>
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function Violaciones({ m }: { m: Medicion }) {
  const graves = m.axe_violations
    .filter((v) => v.impact === "critical" || v.impact === "serious")
    .sort((a, b) => (a.impact === b.impact ? b.nodes - a.nodes : a.impact === "critical" ? -1 : 1));

  if (graves.length === 0) {
    return <p className="mt-2 text-[12.5px] text-muted">Sin violaciones críticas ni serias.</p>;
  }
  return (
    <ul className="mt-2 flex flex-col gap-[6px]">
      {graves.map((v) => (
        <li key={v.id} className="flex items-baseline justify-between gap-3 text-[12.5px]">
          <span className="text-muted">
            <span
              className={`mr-2 rounded-[4px] border px-[5px] text-[10.5px] ${
                v.impact === "critical" ? CALIFICACION.malo.clase : CALIFICACION.mejorable.clase
              }`}
            >
              {v.impact === "critical" ? "Crítica" : "Seria"}
            </span>
            {v.help || v.id}
          </span>
          <span className="shrink-0 font-mono text-faint">
            {v.nodes} {v.nodes === 1 ? "elemento" : "elementos"}
          </span>
        </li>
      ))}
    </ul>
  );
}

/**
 * Medición en navegador real de un análisis de URL. Llega en un segundo
 * tiempo: mientras está pendiente se muestra "Midiendo en navegador…" y, si
 * hay `onAnalysisChange`, se vuelve a pedir el análisis hasta que termine.
 */
export function MedicionNavegador({
  analysis,
  onAnalysisChange,
}: {
  analysis: Analysis;
  onAnalysisChange?: (analysis: Analysis) => void;
}) {
  const m = analysis.browser;
  const pendiente = m?.status === "pending";
  const [agotado, setAgotado] = useState(false);

  useEffect(() => {
    if (!pendiente || !onAnalysisChange) return;
    let consultas = 0;
    const temporizador = setInterval(async () => {
      consultas += 1;
      try {
        const actual = await getAnalysis(analysis.id);
        if (actual.browser?.status !== "pending") {
          clearInterval(temporizador);
          onAnalysisChange(actual);
          return;
        }
      } catch {
        // Un fallo puntual de red no corta la espera; el tope sí.
      }
      if (consultas >= MAX_CONSULTAS) {
        clearInterval(temporizador);
        setAgotado(true);
      }
    }, INTERVALO_MS);
    return () => clearInterval(temporizador);
  }, [pendiente, analysis.id, onAnalysisChange]);

  if (!m) return null;

  return (
    <section aria-labelledby="medicion-navegador" className="mt-5 rounded-[8px] border border-border bg-bg p-5">
      <h3 id="medicion-navegador" className="text-[13px] font-semibold">
        Medición en navegador real
      </h3>
      <p className="mt-1 text-[11.5px] text-faint">{NOTA}</p>

      {/* aria-live: quien usa lector de pantalla se entera cuando llega. */}
      <div aria-live="polite">
        {pendiente && agotado && (
          <p className="mt-3 text-[12.5px] text-muted">
            La medición está tardando más de lo normal. Vuelve a abrir el análisis en unos minutos.
          </p>
        )}

        {pendiente && !agotado && (
          <p className="mt-3 flex items-center gap-2 text-[12.5px] text-muted">
            <RadarCargando size={18} />
            Midiendo en navegador… El resto del análisis ya está listo; esto se añadirá solo al terminar.
          </p>
        )}

        {m.status === "failed" && (
          <p role="note" className="mt-3 rounded-[6px] border border-[oklch(0.80_0.14_85)] px-3 py-2 text-[12.5px] text-muted">
            <strong className="text-[oklch(0.80_0.14_85)]">No se pudo medir en un navegador real.</strong>{" "}
            {m.reason} La eficiencia de desempeño y la accesibilidad usan el análisis estático de QalitiRadar.
          </p>
        )}

        {m.status === "ok" && (
          <>
            <div className="mt-4 flex items-center gap-2">
              <h4 className="text-[12.5px] font-semibold">Core Web Vitals</h4>
              <Insignia>Lighthouse</Insignia>
            </div>
            <Vitales m={m} />

            <div className="mt-4 flex items-center gap-2">
              <h4 className="text-[12.5px] font-semibold">Accesibilidad: violaciones críticas y serias</h4>
              <Insignia>axe-core</Insignia>
            </div>
            <Violaciones m={m} />
          </>
        )}
      </div>
    </section>
  );
}
