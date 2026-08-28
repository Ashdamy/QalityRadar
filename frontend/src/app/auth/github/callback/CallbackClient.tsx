"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ApiError, completeGithubCallback } from "@/lib/api";
import { saveRefreshToken, saveToken } from "@/lib/auth";
import { GithubMark } from "@/components/GithubMark";
import { PrimaryButton } from "@/components/PrimaryButton";

type Status = "pending" | "success" | "error";

function genericErrorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  return "No se pudo contactar al servidor. Intenta de nuevo.";
}

function CheckIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
      <path
        d="M2 7.5 L5.5 11 L12 3"
        className="stroke-good"
        strokeWidth="1.6"
        fill="none"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function PendingIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
      <circle cx="7" cy="7" r="5.2" className="stroke-border" strokeWidth="1.6" fill="none" />
    </svg>
  );
}

function ChecklistRow({
  checked,
  children,
}: {
  checked: boolean;
  children: ReactNode;
}) {
  return (
    <div className={`flex items-center gap-[10px] ${checked ? "text-muted" : "text-faint"}`}>
      {checked ? <CheckIcon /> : <PendingIcon />}
      {children}
    </div>
  );
}

const MISSING_CODE_MESSAGE = "Falta el código de autorización de GitHub en la URL.";

export function CallbackClient() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialCode = searchParams.get("code");
  const [status, setStatus] = useState<Status>(initialCode ? "pending" : "error");
  const [errorMessage, setErrorMessage] = useState<string | null>(
    initialCode ? null : MISSING_CODE_MESSAGE,
  );
  const requested = useRef(false);

  useEffect(() => {
    if (requested.current) return;
    const code = searchParams.get("code");
    // No code in the URL: the initial state above already reflects the
    // error, nothing to fetch.
    if (!code) return;
    requested.current = true;

    // GitHub devuelve el mismo `state` que salio en la ida; el backend lo
    // exige para comprobar que esta vuelta corresponde a esa peticion.
    completeGithubCallback(code, searchParams.get("state"))
      .then((res) => {
        saveToken(res.access_token);
        if (res.refresh_token) saveRefreshToken(res.refresh_token);
        setStatus("success");
      })
      .catch((err) => {
        setStatus("error");
        setErrorMessage(genericErrorMessage(err));
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const done = status === "success";

  return (
    <main className="relative flex min-h-screen w-full items-center justify-center overflow-hidden bg-bg text-text">
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.18] [background-image:linear-gradient(var(--color-border)_1px,transparent_1px),linear-gradient(90deg,var(--color-border)_1px,transparent_1px)] [background-size:32px_32px]"
        aria-hidden="true"
      />

      <div className="relative flex w-[420px] max-w-[calc(100%-32px)] flex-col items-center gap-[22px] rounded-[10px] border border-border bg-surface p-9">
        {status === "error" ? (
          <>
            <div className="flex h-[88px] w-[88px] items-center justify-center rounded-full border border-bad/40">
              <GithubMark size={28} className="text-bad" />
            </div>
            <div className="flex flex-col items-center gap-1 text-center">
              <h1 className="text-base font-semibold">No se pudo conectar con GitHub</h1>
              <p className="text-[13px] leading-[1.5] text-muted">{errorMessage}</p>
            </div>
            <Link
              href="/"
              className="text-[13px] text-accent hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2"
            >
              ← Volver a intentarlo
            </Link>
          </>
        ) : (
          <>
            <div className="relative flex h-[88px] w-[88px] items-center justify-center">
              <svg width="88" height="88" viewBox="0 0 88 88" className="absolute inset-0">
                <circle cx="44" cy="44" r="40" className="stroke-border" strokeWidth="1.2" fill="none" />
                <circle cx="44" cy="44" r="28" className="stroke-border" strokeWidth="1.2" fill="none" />
                {done ? (
                  <circle cx="44" cy="44" r="16" fill="none" className="stroke-accent" strokeWidth="1.6" />
                ) : (
                  <g className="animate-radar-spin">
                    <path
                      d="M44 4 A40 40 0 0 1 84 44"
                      className="stroke-accent"
                      strokeWidth="2"
                      fill="none"
                      strokeLinecap="round"
                    />
                  </g>
                )}
              </svg>
              <GithubMark size={22} className={`relative ${done ? "text-accent" : "text-faint"}`} />
            </div>

            <div className="flex flex-col items-center gap-1 text-center">
              <h1 className="text-base font-semibold">
                {done ? "Cuenta conectada" : "Conectando con GitHub…"}
              </h1>
              <p className="text-[13px] leading-[1.5] text-muted">
                {done
                  ? "Ya podemos leer tus repositorios públicos."
                  : "Esto suele tardar unos segundos."}
              </p>
            </div>

            <div className="flex w-full flex-col gap-[10px] font-mono text-[12.5px]">
              <ChecklistRow checked>Autenticado con GitHub</ChecklistRow>
              <ChecklistRow checked>
                Alcance verificado: <span className="text-faint">public_repo, read:user</span>
              </ChecklistRow>
              <ChecklistRow checked={done}>Sincronizando perfil y repositorios</ChecklistRow>
            </div>

            {done && (
              <PrimaryButton className="w-full" onClick={() => router.push("/repositories")}>
                Continuar a tus repositorios →
              </PrimaryButton>
            )}
          </>
        )}
      </div>
    </main>
  );
}
