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
