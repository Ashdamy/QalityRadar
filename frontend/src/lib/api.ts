/**
 * Typed API client for the QalitiRadar backend.
 *
 * Infrastructure only: this file exposes typed request helpers for the
 * endpoints documented for the backend. It intentionally contains no UI,
 * routing, or state-management logic.
 */

import { getRefreshToken, saveToken } from "@/lib/auth";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface RegisterResponse {
  id: string;
  email: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
  // Ausente en la respuesta de /refresh, que no lo rota.
  refresh_token?: string | null;
}

export interface Repository {
  id: string;
  name: string;
  full_name: string;
  is_private: boolean;
  last_analyzed_at: string | null;
}

export interface GithubAuthorizationUrlResponse {
  authorization_url: string;
}

/**
 * Error thrown for any non-2xx response from the backend. Carries the HTTP
 * status code and, when the backend provided one, its `detail` message.
 */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function parseErrorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body?.detail === "string" && body.detail.length > 0) {
      return body.detail;
    }
  } catch {
    // Response body was not JSON (or was empty) — fall back below.
  }
  return `Request failed with status ${response.status}`;
}

/**
 * Canjea el token de refresco por uno de acceso nuevo y lo guarda.
 *
 * Devuelve null si no hay refresco o ya no vale; en ese caso quien llame debe
 * tratar el 401 como sesión terminada.
 */
async function renovarAcceso(): Promise<string | null> {
  const refresco = getRefreshToken();
  if (!refresco) return null;

  const response = await fetch(`${API_BASE_URL}/api/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refresco }),
  });
  if (!response.ok) return null;

  const { access_token } = (await response.json()) as TokenResponse;
  saveToken(access_token);
  return access_token;
}

/**
 * Varias peticiones en vuelo al caducar el token pedirían cada una su
 * renovación. Se comparte la misma promesa para que solo salga una.
 */
let renovacionEnCurso: Promise<string | null> | null = null;

function renovarAccesoUnaVez(): Promise<string | null> {
  if (!renovacionEnCurso) {
    renovacionEnCurso = renovarAcceso().finally(() => {
      renovacionEnCurso = null;
    });
  }
  return renovacionEnCurso;
}

function conAutorizacion(headers: HeadersInit | undefined, token: string): HeadersInit {
  return { ...headers, Authorization: `Bearer ${token}` };
}

function llevaAutorizacion(headers: HeadersInit | undefined): boolean {
  return Boolean((headers as Record<string, string> | undefined)?.Authorization);
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  reintentar = true,
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

  // El token de acceso dura poco a propósito. Antes de dar la sesión por
  // terminada se intenta renovarlo una vez, en silencio.
  if (response.status === 401 && reintentar && llevaAutorizacion(options.headers)) {
    const nuevo = await renovarAccesoUnaVez();
    if (nuevo) {
      return request<T>(path, { ...options, headers: conAutorizacion(options.headers, nuevo) }, false);
    }
  }

  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorMessage(response));
  }

  return (await response.json()) as T;
}

export function register(
  email: string,
  password: string,
): Promise<RegisterResponse> {
  return request<RegisterResponse>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function login(email: string, password: string): Promise<TokenResponse> {
  return request<TokenResponse>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function getGithubAuthorizationUrl(): Promise<GithubAuthorizationUrlResponse> {
  return request<GithubAuthorizationUrlResponse>("/api/auth/github/login");
}

export function completeGithubCallback(
  code: string,
  state: string | null,
): Promise<TokenResponse> {
  // El `state` viaja tal cual llegó de GitHub: el backend comprueba que sea
  // uno que él emitió, y así la vuelta queda atada a la ida.
  const query = new URLSearchParams({ code });
  if (state) query.set("state", state);
  return request<TokenResponse>(`/api/auth/github/callback?${query}`);
}

export function listRepositories(token: string): Promise<Repository[]> {
  return request<Repository[]>("/api/repositories", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export interface AnalysisFinding {
  type: string;
  severity: "critical" | "high" | "medium" | "low" | "info";
  title: string;
  description: string;
  file_path: string | null;
  url: string | null;
  recommendation: string | null;
}

export interface AnalysisDimension {
  name: string;
  score: number;
  weight: number;
}

export interface Correspondence {
  kind: "ok" | "no_deployment" | "possible_mismatch";
  looks_related: boolean;
  confidence: string;
  reasons: string[];
  warning: string | null;
}

export interface PlanItem {
  severity: AnalysisFinding["severity"];
  origin: "codigo" | "produccion" | "discrepancia";
  title: string;
  detail: string | null;
}

/** Datos que solo existen en el modo combinado (código frente a producción). */
export interface Combined {
  repository_score: number | null;
  url_score: number | null;
  delta: number | null;
  explanation: string | null;
  recommendations: string | null;
  improvement_plan: PlanItem[];
  correspondence: Correspondence | null;
}

export interface Analysis {
  id: string;
  status: "pending" | "cloning" | "running" | "scoring" | "completed" | "failed" | "timeout";
  overall_score: number | null;
  confidence_level: number | null;
  commit_hash: string | null;
  commit_message: string | null;
  error_message: string | null;
  summary_text: string | null;
  summary_source: string | null;
  analysis_type: string;
  // Ausente en los análisis de URL, que no parten de un repositorio.
  repository_full_name: string | null;
  dimensions: AnalysisDimension[];
  findings: AnalysisFinding[];
  combined: Combined | null;
}

export function startRepositoryAnalysis(
  token: string,
  repositoryId: string,
): Promise<{ analysis_id: string }> {
  return request<{ analysis_id: string }>(`/api/repositories/${repositoryId}/analyze`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function getAnalysis(token: string, analysisId: string): Promise<Analysis> {
  return request<Analysis>(`/api/analyses/${analysisId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export interface TimelineEntry {
  id: string;
  status: string;
  overall_score: number | null;
  commit_hash: string | null;
  commit_message: string | null;
  created_at: string;
  delta: number | null;
}

export interface Progress {
  total_analyses: number;
  current_score: number | null;
  best_score: number | null;
  best_score_at: string | null;
  first_score: number | null;
  total_delta: number | null;
  days_tracked: number | null;
}

export interface Change {
  dimension: string;
  previous_score: number | null;
  current_score: number | null;
  delta: number;
  description: string;
  severity: string | null;
}

export interface Comparison {
  id: string;
  analysis_1_id: string;
  analysis_2_id: string;
  previous_score: number | null;
  current_score: number | null;
  score_delta: number;
  trend: "mejorando" | "empeorando" | "estable";
  summary_text: string | null;
  summary_source: string | null;
  improvements: Change[];
  regressions: Change[];
}

export function getTimeline(token: string, repositoryId: string): Promise<TimelineEntry[]> {
  return request<TimelineEntry[]>(`/api/repositories/${repositoryId}/timeline`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function getProgress(token: string, repositoryId: string): Promise<Progress> {
  return request<Progress>(`/api/repositories/${repositoryId}/progress`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function getComparison(
  token: string,
  analysisId: string,
  otherId: string,
): Promise<Comparison> {
  return request<Comparison>(`/api/analyses/${analysisId}/comparison/${otherId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

/**
 * Descarga el informe en PDF. Se usa fetch + blob en vez de un enlace directo
 * porque el endpoint exige la cabecera Authorization, que un <a href> no envía.
 */
export async function downloadAnalysisReport(token: string, analysisId: string): Promise<void> {
  let response = await fetch(`${API_BASE_URL}/api/analyses/${analysisId}/report.pdf`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (response.status === 401) {
    const nuevo = await renovarAccesoUnaVez();
    if (nuevo) {
      response = await fetch(`${API_BASE_URL}/api/analyses/${analysisId}/report.pdf`, {
        headers: { Authorization: `Bearer ${nuevo}` },
      });
    }
  }
  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorMessage(response));
  }

  const blob = await response.blob();
  const nombre =
    response.headers.get("content-disposition")?.match(/filename="([^"]+)"/)?.[1] ??
    "informe-qalitiradar.pdf";

  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = nombre;
  document.body.appendChild(link);
  link.click();
  link.remove();
  // Se libera el objeto para no retener el PDF en memoria.
  URL.revokeObjectURL(url);
}

export function analyzeUrl(
  token: string,
  url: string,
  name?: string,
): Promise<{ analysis_id: string }> {
  return request<{ analysis_id: string }>("/api/apps/analyze", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify({ url, name }),
  });
}

export function analyzeCombined(
  token: string,
  repositoryId: string,
  url: string,
): Promise<{ analysis_id: string }> {
  return request<{ analysis_id: string }>("/api/apps/analyze-combined", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify({ repository_id: repositoryId, url }),
  });
}

// --- Compartir informes ---------------------------------------------------

export interface ShareLink {
  token: string;
  expires_at: string;
}

export function shareAnalysis(
  token: string,
  analysisId: string,
  expiryDays?: number,
): Promise<ShareLink> {
  return request<ShareLink>(`/api/analyses/${analysisId}/share`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify({ expiry_days: expiryDays ?? null }),
  });
}

/** Lee un informe compartido. Sin sesión: el token del enlace es la credencial. */
export function getSharedReport(shareToken: string): Promise<Analysis> {
  return request<Analysis>(`/api/reports/shared/${encodeURIComponent(shareToken)}`);
}

// --- Avisos ---------------------------------------------------------------

export interface NotificationItem {
  id: string;
  analysis_id: string;
  kind: string;
  severity: AnalysisFinding["severity"];
  title: string;
  body: string;
  read: boolean;
  created_at: string | null;
}

export interface NotificationList {
  unread_count: number;
  notifications: NotificationItem[];
}

export function listNotifications(token: string): Promise<NotificationList> {
  return request<NotificationList>("/api/notifications", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function markAllNotificationsRead(token: string): Promise<void> {
  await fetch(`${API_BASE_URL}/api/notifications/read-all`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
}

// --- Límites de uso -------------------------------------------------------

export interface Usage {
  last_hour: number;
  max_per_hour: number;
  last_day: number;
  max_per_day: number;
  running: number;
  max_concurrent: number;
}

export function getUsage(token: string): Promise<Usage> {
  return request<Usage>("/api/usage", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

// --- Seguimiento ----------------------------------------------------------

export interface MonitorItem {
  id: string;
  target_type: "repository" | "url";
  target_name: string;
  repository_id: string | null;
  app_id: string | null;
  is_active: boolean;
  interval_minutes: number;
  last_checked_at: string | null;
  last_commit_sha: string | null;
  latest_analysis_id: string | null;
  latest_score: number | null;
  latest_at: string | null;
}

export interface MonitorList {
  monitors: MonitorItem[];
  active: number;
  max_monitors: number;
  allowed_intervals: number[];
}

export function listMonitors(token: string): Promise<MonitorList> {
  return request<MonitorList>("/api/monitors", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function createMonitor(
  token: string,
  target: { repositoryId?: string; appId?: string; intervalMinutes: number },
): Promise<{ id: string; is_active: boolean }> {
  return request<{ id: string; is_active: boolean }>("/api/monitors", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify({
      repository_id: target.repositoryId ?? null,
      app_id: target.appId ?? null,
      interval_minutes: target.intervalMinutes,
    }),
  });
}

export async function deleteMonitor(token: string, monitorId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/monitors/${monitorId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorMessage(response));
  }
}

/**
 * Cierra la sesión también en el servidor. Sin esta llamada, el token de
 * refresco seguiría siendo válido 30 días aunque se borre del navegador.
 */
export async function logout(refreshToken: string): Promise<void> {
  await fetch(`${API_BASE_URL}/api/auth/logout`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  }).catch(() => {
    // Si la petición falla, el token local se borra igual: es preferible
    // cerrar sesión aquí a dejar al usuario dentro por un fallo de red.
  });
}
