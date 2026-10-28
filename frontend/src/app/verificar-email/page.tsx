"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ApiError, verifyEmail } from "@/lib/api";
import { RadarMark } from "@/components/RadarMark";

type Status = "pending" | "success" | "error";

export default function VerificarEmailPage() {
  const [status, setStatus] = useState<Status>("pending");
  const [mensaje, setMensaje] = useState("Confirmando tu correo…");
  const pedido = useRef(false);

  useEffect(() => {
    if (pedido.current) return;
    pedido.current = true;

    // El token llega en el fragmento (#token=...), que el navegador nunca
    // manda al servidor: así no queda en ningún log de acceso.
    const token = new URLSearchParams(window.location.hash.slice(1)).get("token");
    const verificacion = token
      ? verifyEmail(token)
      : Promise.reject(new ApiError(400, "Al enlace le falta el código de verificación."));

    verificacion
      .then(({ email }) => {
        setStatus("success");
        setMensaje(`${email} quedó confirmado. Ya puedes iniciar sesión.`);
      })
      .catch((err) => {
        setStatus("error");
        setMensaje(
          err instanceof ApiError ? err.message : "No se pudo contactar al servidor. Intenta de nuevo.",
        );
      });
  }, []);

  return (
    <main className="relative flex min-h-screen w-full items-center justify-center overflow-hidden bg-bg text-text">
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.18] [background-image:linear-gradient(var(--color-border)_1px,transparent_1px),linear-gradient(90deg,var(--color-border)_1px,transparent_1px)] [background-size:32px_32px]"
        aria-hidden="true"
      />
      <div className="relative flex w-[420px] max-w-[calc(100%-32px)] flex-col items-center gap-[18px] rounded-[10px] border border-border bg-surface p-9 text-center">
        <RadarMark size={28} />
        <h1 className="text-base font-semibold">
          {status === "success"
            ? "Correo confirmado"
            : status === "error"
              ? "No se pudo confirmar el correo"
              : "Confirmando…"}
        </h1>
        <p
          role={status === "error" ? "alert" : "status"}
          className={`text-[13px] leading-[1.5] ${status === "error" ? "text-bad" : "text-muted"}`}
        >
          {mensaje}
        </p>
        {status !== "pending" && (
          <Link
            href="/"
            className="text-[13px] text-accent hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2"
          >
            Ir a iniciar sesión →
          </Link>
        )}
      </div>
    </main>
  );
}
