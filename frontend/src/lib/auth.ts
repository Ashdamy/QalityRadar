/**
 * Estado de sesión en el navegador.
 *
 * Los tokens ya no se guardan aquí: viven en cookies `httpOnly` que el
 * servidor pone y JavaScript no puede leer. Antes estaban en `localStorage`,
 * y ahí bastaba un XSS —un comentario, una dependencia comprometida, un
 * `alert` inyectado— para llevarse 30 días de sesión de todos los usuarios.
 *
 * Lo único que queda del lado del navegador es una marca legible, `qr_sesion`,
 * que el servidor pone junto a las cookies de verdad. No es una credencial:
 * solo dice "hay sesión", que es lo que la interfaz necesita para saber si
 * enseña la pantalla o redirige al inicio. Robarla no sirve de nada.
 */

const MARCA_DE_SESION = "qr_sesion";

/** True si el servidor dejó marca de sesión abierta. */
export function haySesion(): boolean {
  if (typeof document === "undefined") return false;
  return document.cookie
    .split(";")
    .some((trozo) => trozo.trim().startsWith(`${MARCA_DE_SESION}=`));
}

/**
 * Olvida la sesión en el navegador sin avisar al servidor.
 *
 * Solo para cuando el servidor ya la ha dado por terminada (un 401): las
 * cookies de verdad las borra él, y esto deja de enseñar pantallas que ya no
 * se pueden cargar. Para cerrar sesión de verdad, `endSession`.
 */
export function clearToken(): void {
  if (typeof document === "undefined") return;
  document.cookie = `${MARCA_DE_SESION}=; Max-Age=0; path=/`;
}

/**
 * Cierra la sesión de verdad: la invalida en el servidor, que es quien borra
 * las cookies. Borrar solo en el navegador dejaría el token de refresco vivo
 * un mes.
 */
export async function endSession(): Promise<void> {
  const { logout } = await import("@/lib/api");
  await logout();
  clearToken();
}
