/**
 * Dirección pública del frontend. La usan el sitemap, el robots.txt y las
 * etiquetas de compartir, que necesitan URL absolutas: en producción tiene que
 * ser el dominio real o Google indexa localhost.
 */
export const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

export const SITE_DESCRIPTION =
  "Mide la calidad de tu software con ISO/IEC 25010. Conecta un repositorio de GitHub o la URL de tu aplicación y recibe una nota de 0 a 100, los problemas que la bajan y un plan de mejora. Gratis.";
