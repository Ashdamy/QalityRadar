"use client";

import { useState } from "react";
import { ApiError, importSonarMetrics, type Analysis, type SonarImport as Sonar } from "@/lib/api";

// Las que se enseñan; ncloc solo sirve para calcular la densidad de
// complejidad y no cuenta como métrica importada.
const VISIBLES = [
  "coverage",
  "duplicated_lines_density",
  "sqale_index",
  "sqale_rating",
  "cognitive_complexity",
] as const;

const numero = new Intl.NumberFormat("es", { maximumFractionDigits: 1 });

/** SonarCloud cuenta la deuda en minutos, con días de 8 horas. */
function deuda(minutos: number): string {
  if (minutos < 60) return `${Math.round(minutos)} min`;
  const dias = Math.floor(minutos / 480);
  const horas = Math.round((minutos % 480) / 60);
  return dias ? `${dias} d ${horas} h` : `${horas} h`;
}

function haceCuanto(iso: string): string {
  const segundos = (new Date(iso).getTime() - Date.now()) / 1000;
  const rtf = new Intl.RelativeTimeFormat("es", { numeric: "auto" });
  if (segundos > -3600) return rtf.format(Math.round(segundos / 60), "minute");
  if (segundos > -86400) return rtf.format(Math.round(segundos / 3600), "hour");
  return rtf.format(Math.round(segundos / 86400), "day");
}

function Metricas({ sonar }: { sonar: Sonar }) {
  const m = sonar.metrics;
  const filas: [string, string][] = [];
  if (m.coverage !== undefined) filas.push(["Cobertura de pruebas", `${numero.format(m.coverage)} %`]);
  if (m.duplicated_lines_density !== undefined)
    filas.push(["Líneas duplicadas", `${numero.format(m.duplicated_lines_density)} %`]);
  if (m.sqale_index !== undefined || m.sqale_rating !== undefined) {
    const nota = m.sqale_rating !== undefined ? "ABCDE"[Math.round(m.sqale_rating) - 1] : undefined;
    const valor = [m.sqale_index !== undefined ? deuda(m.sqale_index) : null, nota ? `calificación ${nota}` : null]
      .filter(Boolean)
      .join(" · ");
    filas.push(["Deuda técnica", valor]);
  }
  if (m.cognitive_complexity !== undefined)
    filas.push(["Complejidad cognitiva", numero.format(m.cognitive_complexity)]);

  const cuantas = VISIBLES.filter((k) => m[k] !== undefined).length;
  return (
    <div className="mt-2">
      <p className="text-[12px] text-muted">
        Importadas {cuantas} {cuantas === 1 ? "métrica" : "métricas"} {haceCuanto(sonar.imported_at)} de{" "}
        <span className="font-mono">{sonar.project_key}</span>
      </p>
      <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-[12.5px]">
        {filas.map(([nombre, valor]) => (
          <div key={nombre} className="contents">
            <dt className="text-faint">{nombre}</dt>
            <dd className="font-mono text-muted">{valor}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

/**
 * Métricas de SonarCloud dentro del detalle de Mantenibilidad. Sin
 * `onImported` es de solo lectura (el informe compartido): enseña lo
 * importado, si lo hay, sin el formulario.
 */
export function SonarImport({
  analysis,
  onImported,
}: {
  analysis: Analysis;
  onImported?: (analysis: Analysis) => void;
}) {
  const [clave, setClave] = useState(analysis.sonar?.project_key ?? "");
  const [importando, setImportando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!onImported && !analysis.sonar) return null;

  async function importar(e: React.FormEvent) {
    e.preventDefault();
    if (!onImported || !clave.trim()) return;
    setImportando(true);
    setError(null);
    try {
      onImported(await importSonarMetrics(analysis.id, clave.trim()));
    } catch (err) {
      setError(
        err instanceof ApiError && !err.message.startsWith("Request failed")
          ? err.message
          : "No se pudieron importar las métricas. Prueba de nuevo en un rato.",
      );
    } finally {
      setImportando(false);
    }
  }

  return (
    <section aria-label="Métricas de SonarCloud" className="mt-3 rounded-[6px] border border-border bg-bg p-3">
      <h4 className="text-[12.5px] font-semibold">Métricas de SonarCloud</h4>
      <p className="mt-1 text-[11.5px] text-faint">
        QalitiRadar no ejecuta tu código. Solo lee los resultados que SonarCloud ya calculó.
      </p>

      {analysis.sonar && <Metricas sonar={analysis.sonar} />}

      {onImported && (
        <form onSubmit={importar} className="mt-3 flex flex-wrap items-end gap-2">
          <label className="flex min-w-[220px] flex-1 flex-col gap-1 text-[12px] text-muted">
            Clave del proyecto en SonarCloud
            <input
              value={clave}
              onChange={(e) => setClave(e.target.value)}
              placeholder="mi-organizacion_mi-proyecto"
              maxLength={400}
              spellCheck={false}
              autoComplete="off"
              className="rounded-[6px] border border-border bg-surface px-3 py-[7px] font-mono text-[12.5px] text-text focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
            />
          </label>
          <button
            type="submit"
            disabled={importando || !clave.trim()}
            className="rounded-[6px] border border-border px-3 py-[7px] text-[12.5px] hover:bg-surface2 disabled:opacity-50"
          >
            {importando ? "Importando…" : analysis.sonar ? "Volver a importar" : "Importar métricas"}
          </button>
        </form>
      )}
      {error && (
        <p role="alert" className="mt-2 text-[12px] text-[oklch(0.68_0.19_25)]">
          {error}
        </p>
      )}
      {onImported && (
        <p className="mt-2 text-[11px] text-faint">
          Solo proyectos públicos. Las métricas importadas sustituyen a las estimadas en esta dimensión y
          recalculan la nota.
        </p>
      )}
    </section>
  );
}
