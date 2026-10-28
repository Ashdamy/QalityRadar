"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError, verifyEmail } from "@/lib/api";
import { AuthCard } from "@/components/AuthCard";

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

  const titulo =
    status === "success"
      ? "Correo confirmado"
      : status === "error"
        ? "No se pudo confirmar el correo"
        : "Confirmando…";

  return (
    <AuthCard title={titulo}>
      <p
        role={status === "error" ? "alert" : "status"}
        className={`text-center text-[13px] leading-[1.5] ${status === "error" ? "text-bad" : "text-muted"}`}
      >
        {mensaje}
      </p>
    </AuthCard>
  );
}
