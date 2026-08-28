"use client";

import { useEffect, useRef, useState } from "react";
import {
  listNotifications,
  markAllNotificationsRead,
  type NotificationItem,
} from "@/lib/api";
import { getToken } from "@/lib/auth";

// Los avisos solo aparecen al terminar un análisis, así que no hace falta
// sondear: basta con cargarlos al montar y al abrir la bandeja.

function severityColor(severity: string): string {
  if (severity === "critical" || severity === "high") return "bg-[oklch(0.68_0.19_25)]";
  if (severity === "medium") return "bg-[oklch(0.80_0.14_85)]";
  return "bg-border";
}

function BellIcon() {
  return (
    <svg
      width="17"
      height="17"
      viewBox="0 0 24 24"
      fill="none"
      className="stroke-muted"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.7 21a2 2 0 0 1-3.4 0" />
    </svg>
  );
}

export function NotificationBell() {
  const [abierta, setAbierta] = useState(false);
  const [avisos, setAvisos] = useState<NotificationItem[]>([]);
  const [sinLeer, setSinLeer] = useState(0);
  const contenedor = useRef<HTMLDivElement>(null);

  async function cargar() {
    const token = getToken();
    if (!token) return;
    try {
      const datos = await listNotifications(token);
      setAvisos(datos.notifications);
      setSinLeer(datos.unread_count);
    } catch {
      // La bandeja es accesoria: si falla, no debe estropear la pantalla.
    }
  }

  useEffect(() => {
    const token = getToken();
    if (!token) return;

    // La guarda evita escribir estado si el componente ya se desmontó.
    let vivo = true;
    listNotifications(token)
      .then((datos) => {
        if (!vivo) return;
        setAvisos(datos.notifications);
        setSinLeer(datos.unread_count);
      })
      .catch(() => {
        // La bandeja es accesoria: si falla, no debe estropear la pantalla.
      });
    return () => {
      vivo = false;
    };
  }, []);

  // Cerrar al pulsar fuera: sin esto la bandeja tapa la pantalla y no hay
  // forma evidente de quitarla.
  useEffect(() => {
    if (!abierta) return;
    function alPulsarFuera(evento: MouseEvent) {
      if (!contenedor.current?.contains(evento.target as Node)) setAbierta(false);
    }
    document.addEventListener("mousedown", alPulsarFuera);
    return () => document.removeEventListener("mousedown", alPulsarFuera);
  }, [abierta]);

  async function alternar() {
    const abriendo = !abierta;
    setAbierta(abriendo);
    if (!abriendo) return;

    await cargar();
    const token = getToken();
    if (token && sinLeer > 0) {
      // Abrir la bandeja es haberlos visto: marcarlos aquí evita un botón
      // extra que nadie pulsaría.
      await markAllNotificationsRead(token);
      setSinLeer(0);
    }
  }

  return (
    <div className="relative" ref={contenedor}>
      <button
        type="button"
        onClick={alternar}
        aria-label={sinLeer > 0 ? `Avisos (${sinLeer} sin leer)` : "Avisos"}
        className="relative flex h-8 w-8 items-center justify-center rounded-[6px] hover:bg-surface2 focus:outline-none focus:ring-[3px] focus:ring-accentDim"
      >
        <BellIcon />
        {sinLeer > 0 && (
          <span className="absolute right-[5px] top-[5px] h-[7px] w-[7px] rounded-full bg-[oklch(0.68_0.19_25)]" />
        )}
      </button>

      {abierta && (
        <div className="absolute right-0 top-[38px] z-20 w-[330px] rounded-[8px] border border-border bg-surface shadow-lg">
          <div className="border-b border-border px-4 py-[10px] text-[12.5px] font-semibold text-muted">
            Avisos
          </div>

          {avisos.length === 0 ? (
            <p className="px-4 py-6 text-center text-[12.5px] leading-[1.55] text-faint">
              No hay avisos. Aparecerán aquí si la calidad de un proyecto empeora entre dos
              análisis.
            </p>
          ) : (
            <ul className="max-h-[340px] overflow-y-auto">
              {avisos.map((aviso) => (
                <li key={aviso.id} className="border-b border-border px-4 py-3 last:border-b-0">
                  <div className="flex items-start gap-[9px]">
                    <span
                      className={`mt-[6px] h-[6px] w-[6px] shrink-0 rounded-full ${severityColor(
                        aviso.severity,
                      )}`}
                      aria-hidden="true"
                    />
                    <div className="min-w-0">
                      <div className="text-[12.5px] font-medium">{aviso.title}</div>
                      <p className="mt-[3px] text-[11.5px] leading-[1.5] text-faint">
                        {aviso.body}
                      </p>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
