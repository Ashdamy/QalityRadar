import type { ReactNode } from "react";
import Link from "next/link";
import { RadarMark } from "@/components/RadarMark";

/** Tarjeta centrada de las pantallas sueltas de cuenta: verificar, recuperar, restablecer. */
export function AuthCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <main className="relative flex min-h-screen w-full items-center justify-center overflow-hidden bg-bg text-text">
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.18] [background-image:linear-gradient(var(--color-border)_1px,transparent_1px),linear-gradient(90deg,var(--color-border)_1px,transparent_1px)] [background-size:32px_32px]"
        aria-hidden="true"
      />
      <div className="relative flex w-[420px] max-w-[calc(100%-32px)] flex-col gap-[18px] rounded-[10px] border border-border bg-surface p-9">
        <div className="flex flex-col items-center gap-3 text-center">
          <RadarMark size={28} />
          <h1 className="text-base font-semibold">{title}</h1>
        </div>
        {children}
        <Link
          href="/entrar"
          className="self-center text-[13px] text-accent hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2"
        >
          ← Volver a iniciar sesión
        </Link>
      </div>
    </main>
  );
}
