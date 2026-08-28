/**
 * Minimal localStorage-backed token storage. No context provider, no hooks —
 * just plain functions, safe to call during server-side rendering.
 */

const TOKEN_KEY = "qalitiradar.token";
const REFRESH_KEY = "qalitiradar.refresh";

export function saveToken(token: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function saveRefreshToken(token: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(REFRESH_KEY, token);
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(REFRESH_KEY);
}

/** Cierra la sesión por completo: sin esto quedaría el de refresco vivo. */
export function clearToken(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(REFRESH_KEY);
}
