import path from "node:path";
import type { NextConfig } from "next";

// La API vive en otro origen, asi que hay que autorizarlo explicitamente o el
// propio CSP bloquea todas las llamadas del frontend. Se lee de la misma
// variable que usa el cliente HTTP, para que no haya dos sitios que mantener.
const ORIGEN_API = new URL(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
).origin;

const EN_DESARROLLO = process.env.NODE_ENV !== "production";

/**
 * Politica de seguridad de contenido.
 *
 * `'unsafe-inline'` en scripts es la concesion que hace Next: inyecta scripts
 * en linea para hidratar la pagina, y la alternativa —un nonce por peticion—
 * obliga a renderizar todo en el servidor en cada visita. Aun con esa
 * concesion, el resto de la politica sigue valiendo: nada se carga de
 * terceros, no hay `eval` en produccion, y `frame-ancestors 'none'` cierra el
 * clickjacking.
 *
 * `'unsafe-eval'` solo en desarrollo: el recargado en caliente lo necesita.
 */
const POLITICA_DE_CONTENIDO = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${EN_DESARROLLO ? " 'unsafe-eval'" : ""}`,
  // Los estilos en linea son de React (`style={{...}}`), no de datos externos.
  "style-src 'self' 'unsafe-inline'",
  // Los avatares vienen de GitHub, que puede servirlos desde varios dominios.
  "img-src 'self' data: https:",
  `connect-src 'self' ${ORIGEN_API}`,
  "font-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  // Equivalente moderno de X-Frame-Options, que se manda igualmente para los
  // navegadores que solo entienden el antiguo.
  "frame-ancestors 'none'",
].join("; ");

const nextConfig: NextConfig = {
  // Este proyecto vive anidado dentro de otra carpeta que tiene su propio
  // package-lock.json. Sin fijar la raiz, Turbopack la infiere hacia arriba
  // y avisa de que ignora ese lockfile ajeno.
  turbopack: {
    root: path.resolve(__dirname),
  },

  /**
   * La API mandaba sus cabeceras de seguridad y el frontend ninguna, que es
   * la mitad que de verdad renderiza el navegador. QalitiRadar penaliza a los
   * sitios que analiza por no enviarlas.
   *
   * HSTS no se emite aqui: la termina el proxy inverso, que es quien sabe si
   * la conexion es realmente HTTPS. Emitirla en local, por HTTP, dejaria el
   * dominio inaccesible en el navegador.
   */
  async headers() {
    return [
      {
        source: "/:ruta*",
        headers: [
          { key: "Content-Security-Policy", value: POLITICA_DE_CONTENIDO },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "no-referrer" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=()",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
