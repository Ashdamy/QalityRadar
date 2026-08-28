/**
 * Typed API client for the QalitiRadar backend.
 *
 * Infrastructure only: this file exposes typed request helpers for the
 * endpoints documented for the backend. It intentionally contains no UI,
 * routing, or state-management logic.
 */

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface RegisterResponse {
  id: string;
  email: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
}

export interface Repository {
  id: string;
  name: string;
  full_name: string;
  is_private: boolean;
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

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

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

export function completeGithubCallback(code: string): Promise<TokenResponse> {
  return request<TokenResponse>(
    `/api/auth/github/callback?code=${encodeURIComponent(code)}`,
  );
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

export interface Analysis {
  id: string;
  status: "pending" | "cloning" | "running" | "scoring" | "completed" | "failed" | "timeout";
  overall_score: number | null;
  confidence_level: number | null;
  commit_hash: string | null;
  commit_message: string | null;
  error_message: string | null;
  dimensions: AnalysisDimension[];
  findings: AnalysisFinding[];
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
  const response = await fetch(`${API_BASE_URL}/api/analyses/${analysisId}/report.pdf`, {
    headers: { Authorization: `Bearer ${token}` },
  });
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
