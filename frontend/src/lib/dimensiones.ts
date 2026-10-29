/**
 * Nombres y orden de las dimensiones según ISO/IEC 25010:2023.
 *
 * Una sola fuente para el radar, el panel de análisis y el informe
 * compartido: antes cada pantalla tenía su copia y al cambiar la norma se
 * quedaban desfasadas entre sí. Es el espejo de `backend/app/services/iso25010.py`.
 *
 * Las claves son las internas, que conservan los nombres de 2011
 * (`usability`, `portability`): están guardadas en cada análisis. Lo que
 * cambia con la norma es la etiqueta.
 */

export const DIMENSION_LABELS: Record<string, string> = {
  functional_suitability: "Adecuación funcional",
  performance: "Eficiencia de desempeño",
  compatibility: "Compatibilidad",
  // Antes "Usabilidad".
  usability: "Capacidad de interacción",
  reliability: "Fiabilidad",
  security: "Seguridad",
  maintainability: "Mantenibilidad",
  // Antes "Portabilidad".
  portability: "Flexibilidad",
  // Nueva en 2023, todavía sin medir.
  safety: "Protección",
  // En 2023 se cubre con "inclusividad", dentro de la capacidad de interacción.
  accessibility: "Accesibilidad (inclusividad)",
  // No es ISO.
  project_activity: "Actividad del proyecto",
};

// Etiquetas cortas para los ejes del radar, donde no caben las largas.
export const AXIS_LABELS: Record<string, string> = {
  ...DIMENSION_LABELS,
  functional_suitability: "Adecuación",
  performance: "Eficiencia",
  usability: "Interacción",
  accessibility: "Accesibilidad",
  project_activity: "Actividad",
};

// Características de la norma que aún no se miden. Se enseñan como "sin
// medir" y no entran en la nota: ni 0 (castigar lo no comprobado) ni 100
// (regalarlo).
export const SIN_MEDIR = ["safety"];

// Orden fijo de los ejes: si variara entre análisis, dos radares del mismo
// proyecto no serían comparables de un vistazo, que es justo para lo que sirve.
export const REPOSITORY_ORDER = [
  "functional_suitability",
  "reliability",
  "security",
  "maintainability",
  "portability",
];

// Se calculan y se enseñan aparte, pero no son ISO/IEC 25010 ni entran en la
// nota. Espejo de HEALTH_INDICATORS en scoring_service.
export const INDICADORES_DE_SALUD = ["project_activity"];

/** True si la dimensión es un indicador de salud y no una característica ISO. */
export function esIndicadorDeSalud(name: string): boolean {
  return INDICADORES_DE_SALUD.includes(splitDimensionName(name).base);
}

// El análisis de URL mide otras cinco dimensiones, con sus propios pesos.
export const URL_ORDER = ["performance", "security", "usability", "accessibility", "compatibility"];

// En el modo combinado las dimensiones llegan como "origen:nombre", porque
// código y producción miden ambos "security" y no son lo mismo.
const ORIGIN_LABELS: Record<string, string> = {
  codigo: "código",
  produccion: "producción",
};

export function splitDimensionName(name: string): { origin: string | null; base: string } {
  const corte = name.indexOf(":");
  if (corte === -1) return { origin: null, base: name };
  return { origin: name.slice(0, corte), base: name.slice(corte + 1) };
}

/** Traduce el nombre técnico, conservando el origen cuando lo lleva. */
export function dimensionLabel(name: string, labels: Record<string, string> = DIMENSION_LABELS): string {
  const { origin, base } = splitDimensionName(name);
  const etiqueta = labels[base] ?? base;
  if (!origin) return etiqueta;
  return `${etiqueta} (${ORIGIN_LABELS[origin] ?? origin})`;
}

export function dimensionColor(score: number): string {
  if (score >= 80) return "oklch(0.72 0.15 150)";
  if (score >= 50) return "oklch(0.80 0.14 85)";
  return "oklch(0.68 0.19 25)";
}
