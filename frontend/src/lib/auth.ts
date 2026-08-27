/**
 * Minimal localStorage-backed token storage. No context provider, no hooks —
 * just plain functions, safe to call during server-side rendering.
 */

const TOKEN_KEY = "qalitiradar.token";

export function saveToken(token: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function clearToken(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOKEN_KEY);
}
