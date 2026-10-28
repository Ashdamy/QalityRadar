import type { MetadataRoute } from "next";
import { SITE_URL } from "@/lib/sitio";

// Solo lo publico se indexa. Las pantallas con sesion no le sirven a nadie que
// llegue desde un buscador, y los informes compartidos (/r/) ya llevan noindex:
// son de quien los comparte, no contenido del sitio.
export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      disallow: [
        "/analyze",
        "/analyses",
        "/repositories",
        "/monitors",
        "/cuenta",
        "/r/",
        "/auth/",
        "/verificar-email",
        "/restablecer-contrasena",
      ],
    },
    sitemap: `${SITE_URL}/sitemap.xml`,
  };
}
