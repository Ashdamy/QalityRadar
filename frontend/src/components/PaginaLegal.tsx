import type { ReactNode } from "react";
import Link from "next/link";
import { RadarMark } from "@/components/RadarMark";

/** Marco de las páginas legales: cabecera mínima y texto legible. */
export function PaginaLegal({
  titulo,
  actualizada,
  children,
}: {
  titulo: string;
  actualizada: string;
  children: ReactNode;
}) {
  return (
    <div className="w-full bg-bg text-text">
      <header className="border-b border-border">
        <nav aria-label="Principal" className="mx-auto flex max-w-[760px] items-center justify-between px-6 py-4">
          <Link href="/" className="flex items-center gap-2.5">
            <RadarMark size={20} />
            <span className="font-semibold">QalitiRadar</span>
          </Link>
          <Link href="/entrar" className="text-sm text-muted hover:text-text">
            Iniciar sesión
          </Link>
        </nav>
      </header>
      <main className="mx-auto max-w-[760px] px-6 py-14">
        <h1 className="mb-2 text-[32px] font-bold tracking-[-0.02em]">{titulo}</h1>
        <p className="mb-10 text-sm text-muted">Última actualización: {actualizada}</p>
        <article className="flex flex-col gap-4 text-[15.5px] leading-[1.7] text-muted [&_h2]:mt-8 [&_h2]:text-[20px] [&_h2]:font-semibold [&_h2]:text-text [&_li]:ml-5 [&_li]:list-disc [&_strong]:text-text [&_a]:text-accent [&_a:hover]:underline">
          {children}
        </article>
      </main>
      <footer className="border-t border-border px-6 py-8">
        <nav aria-label="Pie de página" className="mx-auto flex max-w-[760px] flex-wrap gap-6 text-sm text-muted">
          <Link href="/" className="hover:text-text">Inicio</Link>
          <Link href="/privacidad" className="hover:text-text">Privacidad</Link>
          <Link href="/terminos" className="hover:text-text">Términos</Link>
        </nav>
      </footer>
    </div>
  );
}
