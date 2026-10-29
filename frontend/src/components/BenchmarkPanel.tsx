"use client";

import { useEffect, useState } from "react";
import { getBenchmark, type Benchmark } from "@/lib/api";

/**
 * Compara las notas del último análisis con una referencia por lenguaje.
 *
 * Hoy esa referencia es SIMULADA (no hay todavía suficientes análisis reales
 * para calcularla): mientras el backend diga `is_simulated`, la etiqueta
 * "Referencia simulada, no son datos reales" va delante de todo, no en letra
 * pequeña. Si el lenguaje no tiene referencia, no se enseña nada.
 */
export function BenchmarkPanel({ repositoryId }: { repositoryId: string }) {
  const [datos, setDatos] = useState<Benchmark | null>(null);

  useEffect(() => {
    let vigente = true;
    getBenchmark(repositoryId)
      .then((b) => vigente && setDatos(b ?? null))
      // Sin referencia no hay nada que enseñar; un fallo aquí no debe
      // estropear la pantalla del repositorio.
      .catch(() => vigente && setDatos(null));
    return () => {
      vigente = false;
    };
  }, [repositoryId]);

  if (!datos) return null;

  return (
    <section
      aria-labelledby="benchmark-titulo"
      className="rounded-[10px] border border-border bg-surface p-5"
    >
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <h2 id="benchmark-titulo" className="text-[14px] font-semibold">
          Frente a otros proyectos en {datos.language}
        </h2>
        {datos.is_simulated && (
          <span className="rounded-[4px] border border-[oklch(0.80_0.14_85)] px-2 py-[1px] text-[11.5px] font-semibold text-[oklch(0.80_0.14_85)]">
            Referencia simulada, no son datos reales
          </span>
        )}
      </div>
      <p className="mb-4 text-[12px] text-faint">
        {datos.is_simulated
          ? "Estos valores de referencia son una estimación de ejemplo, no medias calculadas sobre proyectos reales. Sirven para ver cómo se presentará la comparación, no para sacar conclusiones."
          : `Fuente: ${datos.source}.`}
      </p>
      <ul className="flex flex-col gap-2">
        {datos.items.map((i) => (
          <li key={i.dimension} className="flex items-center justify-between gap-4 text-[13px]">
            <span className="w-[160px] shrink-0">{i.label}</span>
            <span className="font-mono text-muted">
              {i.score.toFixed(0)} frente a {i.reference.toFixed(0)}
            </span>
            <span
              className={`w-[56px] shrink-0 text-right font-mono ${i.delta >= 0 ? "text-good" : "text-bad"}`}
            >
              {i.delta >= 0 ? "+" : ""}
              {i.delta.toFixed(0)}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
