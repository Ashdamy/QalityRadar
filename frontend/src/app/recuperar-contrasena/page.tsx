"use client";

import { useState, type FormEvent } from "react";
import { ApiError, forgotPassword } from "@/lib/api";
import { AuthCard } from "@/components/AuthCard";
import { TextField } from "@/components/TextField";
import { PrimaryButton } from "@/components/PrimaryButton";

export default function RecuperarContrasenaPage() {
  const [email, setEmail] = useState("");
  const [pending, setPending] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setPending(true);
    try {
      // El servidor contesta lo mismo exista o no la cuenta: aquí no se puede
      // saber, y es a propósito.
      const { detail } = await forgotPassword(email);
      setAviso(`${detail} Revisa también la carpeta de spam. El enlace caduca en una hora.`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo contactar al servidor. Intenta de nuevo.");
    } finally {
      setPending(false);
    }
  }

  return (
    <AuthCard title="Recupera tu contraseña">
      {aviso ? (
        <p role="status" className="text-center text-[13px] leading-[1.5] text-muted">
          {aviso}
        </p>
      ) : (
        <form onSubmit={handleSubmit} className="flex flex-col gap-[14px]">
          <p className="text-center text-[13px] leading-[1.5] text-muted">
            Escribe el correo de tu cuenta y te enviaremos un enlace para elegir una contraseña nueva.
          </p>
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
          {error && (
            <p role="alert" className="text-[12.5px] leading-[1.5] text-bad">
              {error}
            </p>
          )}
          <PrimaryButton type="submit" disabled={pending}>
            {pending ? "Enviando…" : "Enviar enlace"}
          </PrimaryButton>
        </form>
      )}
    </AuthCard>
  );
}
