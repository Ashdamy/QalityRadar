import type { Metadata } from "next";

/**
 * Los informes compartidos son públicos solo para quien tiene el enlace: el
 * token ES la credencial. Un buscador que lo rastree (porque alguien pegó el
 * enlace en un foro, un tablero público o una red social) indexaría el informe
 * de esa persona y lo conservaría **aunque el enlace ya haya caducado**.
 *
 * Este layout existe únicamente para declarar `noindex`. Tiene que ser un
 * componente de servidor, y la página es de cliente, así que no puede
 * exportarlo ella misma.
 */
export const metadata: Metadata = {
  robots: {
    index: false,
    follow: false,
    nocache: true,
    googleBot: { index: false, follow: false, noimageindex: true },
  },
};

export default function SharedReportLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
