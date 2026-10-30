import type { ReactNode } from "react";

/**
 * El logo de QalitiRadar con un barrido que da vueltas, para los estados de
 * carga. Los círculos solos girando parecerían quietos: lo que se ve girar es
 * el barrido, como en una pantalla de radar.
 *
 * Con "reducir movimiento" activado en el sistema, el barrido se queda quieto.
 */
export function RadarCargando({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true" className="shrink-0">
      <circle cx="12" cy="12" r="9" className="stroke-accent" strokeWidth="1.4" />
      <circle cx="12" cy="12" r="5" className="stroke-accent" strokeWidth="1.4" opacity="0.6" />
      <g className="origin-center animate-[spin_1.6s_linear_infinite] [transform-box:view-box] motion-reduce:animate-none">
        {/* Estela de 60° detrás de la aguja, que gira en el sentido del reloj. */}
        <path d="M12 12 L12 3 A9 9 0 0 0 4.206 7.5 Z" className="fill-accent" opacity="0.25" />
        <line x1="12" y1="12" x2="12" y2="3" className="stroke-accent" strokeWidth="1.4" strokeLinecap="round" />
      </g>
      <circle cx="12" cy="12" r="1.6" className="fill-accent" />
    </svg>
  );
}

/** Texto de carga con el radar al lado. `role="status"` lo anuncia a los lectores de pantalla. */
export function Cargando({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <p role="status" className={`flex items-center gap-2 ${className}`}>
      <RadarCargando size={18} />
      {children}
    </p>
  );
}
