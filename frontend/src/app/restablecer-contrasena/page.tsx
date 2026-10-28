"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { ApiError, resetPassword } from "@/lib/api";
import { AuthCard } from "@/components/AuthCard";
import { TextField } from "@/components/TextField";
import { PrimaryButton } from "@/components/PrimaryButton";

export default function RestablecerContrasenaPage() {
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [hecho, setHecho] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    if (password !== confirmPassword) {
      setError("Las contraseñas no coinciden.");
      return;
    }

    // Va en el fragmento (#token=...), que el navegador no manda al servidor.
    const token = new URLSearchParams(window.location.hash.slice(1)).get("token");
    if (!token) {
      setError("Al enlace le falta el código. Pide otro desde «¿Olvidaste tu contraseña?».");
      return;
    }

    setPending(true);
    try {
      await resetPassword(token, password);
      setHecho(true);
    } catch (err) {
      if (err instanceof ApiError && err.status === 422) {
        setError("La contraseña debe tener entre 8 y 72 caracteres.");
      } else {
        setError(err instanceof ApiError ? err.message : "No se pudo contactar al servidor. Intenta de nuevo.");
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <AuthCard title={hecho ? "Contraseña cambiada" : "Elige una contraseña nueva"}>
      {hecho ? (
        <p role="status" className="text-center text-[13px] leading-[1.5] text-muted">
          Ya puedes iniciar sesión con la contraseña nueva. Por seguridad, cerramos las sesiones que
          tenías abiertas en otros dispositivos.
        </p>
      ) : (
        <form onSubmit={handleSubmit} className="flex flex-col gap-[14px]">
          <TextField
            id="password"
            label="Contraseña nueva"
            type="password"
            placeholder="Mínimo 8 caracteres"
            autoComplete="new-password"
            required
            minLength={8}
            maxLength={72}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
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
          {error && (
            <p role="alert" className="text-[12.5px] leading-[1.5] text-bad">
              {error}{" "}
              {error.includes("Pide otro") && (
                <Link href="/recuperar-contrasena" className="underline">
                  Pedir otro enlace
                </Link>
              )}
            </p>
          )}
          <PrimaryButton type="submit" disabled={pending}>
            {pending ? "Guardando…" : "Guardar contraseña"}
          </PrimaryButton>
        </form>
      )}
    </AuthCard>
  );
}
