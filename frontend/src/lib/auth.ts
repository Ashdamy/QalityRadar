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

/** Borra los tokens del navegador. Para cerrar sesión de verdad, `endSession`. */
export function clearToken(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(REFRESH_KEY);
}

/**
 * Cierra la sesión de verdad: la invalida en el servidor y luego borra los
 * tokens locales. Debe usarse siempre en vez de `clearToken` a secas, porque
 * borrar solo en el navegador deja el token de refresco vivo un mes.
 */
export async function endSession(): Promise<void> {
  const refresco = getRefreshToken();
  if (refresco) {
    const { logout } = await import("@/lib/api");
    await logout(refresco);
  }
  clearToken();
}
