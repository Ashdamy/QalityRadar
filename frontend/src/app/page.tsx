"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { ApiError, getGithubAuthorizationUrl, login, register } from "@/lib/api";
import { getToken, saveToken } from "@/lib/auth";
import { RadarMark } from "@/components/RadarMark";
import { TextField } from "@/components/TextField";
import { PrimaryButton } from "@/components/PrimaryButton";
import { GithubButton } from "@/components/GithubButton";

const DIMENSIONS = [
  "Adecuación",
  "Fiabilidad",
  "Seguridad",
  "Mantenibilidad",
  "Portabilidad",
  "Actividad",
];

type Mode = "login" | "register";

function genericErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    // FastAPI's validation errors (422) put a structured array in `detail`
    // rather than a string, so the shared API client's parseErrorMessage
    // falls back to a bare "Request failed with status 422". Give the one
    // 422 case in this contract (password too long) a proper message
    // instead of surfacing that fallback.
    if (err.status === 422) {
      return "La contraseña no puede superar los 72 caracteres.";
    }
    return err.message;
  }
  return "No se pudo contactar al servidor. Intenta de nuevo.";
}

export default function Home() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [githubPending, setGithubPending] = useState(false);

  useEffect(() => {
    if (getToken()) {
      router.replace("/repositories");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const isRegister = mode === "register";

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);

    if (isRegister && password !== confirmPassword) {
      setError("Las contraseñas no coinciden.");
      return;
    }

    setPending(true);
    try {
      if (isRegister) {
        await register(email, password);
      }
      const tokenResponse = await login(email, password);
      saveToken(tokenResponse.access_token);
      router.push("/repositories");
    } catch (err) {
      setError(genericErrorMessage(err));
      setPending(false);
    }
  }

  async function handleGithub() {
    setError(null);
    setGithubPending(true);
    try {
      const { authorization_url } = await getGithubAuthorizationUrl();
      window.location.href = authorization_url;
    } catch (err) {
      setError(genericErrorMessage(err));
      setGithubPending(false);
    }
  }

  return (
    <main className="grid min-h-screen w-full grid-cols-1 bg-bg text-text md:grid-cols-[1.05fr_1fr]">
      {/* LEFT: brand / radar panel */}
      <div className="relative flex flex-col justify-between overflow-hidden border-border bg-panel p-[48px] md:border-r">
        <div
          className="pointer-events-none absolute inset-0 opacity-25 [background-image:linear-gradient(var(--color-border)_1px,transparent_1px),linear-gradient(90deg,var(--color-border)_1px,transparent_1px)] [background-size:32px_32px]"
          aria-hidden="true"
        />

        <div className="relative flex items-center gap-[10px]">
          <RadarMark size={22} />
          <span className="text-[15px] font-semibold tracking-[0.01em]">QualityRadar</span>
        </div>

        <div className="relative flex flex-1 items-center justify-center py-16">
          <svg width="320" height="320" viewBox="0 0 320 320" className="max-w-full overflow-visible">
            <circle cx="160" cy="160" r="140" className="stroke-border" strokeWidth="1" fill="none" />
            <circle cx="160" cy="160" r="104" className="stroke-border" strokeWidth="1" fill="none" />
            <circle cx="160" cy="160" r="68" className="stroke-border" strokeWidth="1" fill="none" />
            <circle cx="160" cy="160" r="32" className="stroke-border" strokeWidth="1" fill="none" />
            <line x1="160" y1="20" x2="160" y2="300" className="stroke-border" strokeWidth="1" />
            <line x1="20" y1="160" x2="300" y2="160" className="stroke-border" strokeWidth="1" />

            <g className="animate-radar-sweep">
              <path
                d="M 160 160 L 160 20 A 140 140 0 0 1 253 57 Z"
                className="fill-accent"
                opacity="0.10"
              />
              <line x1="160" y1="160" x2="253" y2="57" className="stroke-accent" strokeWidth="1.4" opacity="0.8" />
            </g>

            <circle cx="205" cy="95" r="4" className="fill-accent" />
            <circle cx="120" cy="205" r="3" className="fill-muted" />
            <circle cx="230" cy="190" r="3" className="fill-muted" />
            <circle cx="105" cy="120" r="3.5" className="fill-accent" opacity="0.7" />
          </svg>
        </div>

        <div className="relative flex flex-col gap-[8px]">
          <div className="font-mono text-[12.5px] tracking-[0.02em] text-muted">
            ISO/IEC 25010 &middot; DIMENSIONES ANALIZADAS
          </div>
          <div className="flex flex-wrap gap-x-[10px] gap-y-[6px] font-mono text-[12.5px] text-faint">
            {DIMENSIONS.flatMap((dimension, i) => [
              <span key={dimension}>{dimension}</span>,
              ...(i < DIMENSIONS.length - 1 ? [<span key={`${dimension}-dot`}>&middot;</span>] : []),
            ])}
          </div>
        </div>
      </div>

      {/* RIGHT: auth form */}
      <div className="flex items-center justify-center p-[48px]">
        <div className="w-full max-w-[360px]">
          <div className="mb-[28px] flex gap-[24px] border-b border-border">
            <button
              type="button"
              onClick={() => setMode("login")}
              aria-pressed={!isRegister}
              className={`-mb-px cursor-pointer border-b-2 pb-[12px] font-sans text-sm font-semibold ${
                isRegister ? "border-transparent text-muted" : "border-accent text-text"
              }`}
            >
              Iniciar sesión
            </button>
            <button
              type="button"
              onClick={() => setMode("register")}
              aria-pressed={isRegister}
              className={`-mb-px cursor-pointer border-b-2 pb-[12px] font-sans text-sm font-semibold ${
                isRegister ? "border-accent text-text" : "border-transparent text-muted"
              }`}
            >
              Crear cuenta
            </button>
          </div>

          <h1 className="mb-[4px] text-[19px] font-semibold tracking-[-0.01em]">
            {isRegister ? "Crea tu cuenta" : "Bienvenido de vuelta"}
          </h1>
          <p className="mb-[24px] text-[13.5px] leading-[1.5] text-muted">
            {isRegister
              ? "Regístrate para empezar a analizar la calidad de tus proyectos."
              : "Ingresa a tu cuenta para ver tus análisis."}
          </p>

          <form onSubmit={handleSubmit} className="flex flex-col gap-[14px]">
            <TextField
              id="email"
              label="Correo electrónico"
              type="email"
              placeholder="tu@empresa.com"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <TextField
              id="password"
              label="Contraseña"
              type="password"
              placeholder="••••••••••••"
              autoComplete={isRegister ? "new-password" : "current-password"}
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />

            {isRegister && (
              <TextField
                id="confirmPassword"
                label="Confirmar contraseña"
                type="password"
                placeholder="••••••••••••"
                autoComplete="new-password"
                required
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
              />
            )}

            {error && (
              <p role="alert" className="text-[12.5px] leading-[1.5] text-bad">
                {error}
              </p>
            )}

            <PrimaryButton type="submit" disabled={pending} className="mt-[6px]">
              {pending
                ? isRegister
                  ? "Creando cuenta…"
                  : "Iniciando sesión…"
                : isRegister
                  ? "Crear cuenta"
                  : "Iniciar sesión"}
            </PrimaryButton>

            <div className="my-[6px] flex items-center gap-[12px]">
              <div className="h-px flex-1 bg-border" />
              <span className="text-xs text-faint">o</span>
              <div className="h-px flex-1 bg-border" />
            </div>

            <GithubButton
              label="Continuar con GitHub"
              onClick={handleGithub}
              disabled={githubPending}
            />
          </form>

          <p className="mt-[22px] text-center text-[12.5px] text-faint">
            Solo se solicita acceso de lectura a repositorios públicos.
          </p>
        </div>
      </div>
    </main>
  );
}
