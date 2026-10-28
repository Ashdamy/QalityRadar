import type { Metadata } from "next";

// La pagina es de cliente y no puede declarar metadatos: van aqui.
export const metadata: Metadata = {
  title: "Iniciar sesión o crear cuenta",
  alternates: { canonical: "/entrar" },
};

export default function EntrarLayout({ children }: { children: React.ReactNode }) {
  return children;
}
