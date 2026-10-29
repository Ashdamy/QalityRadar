/**
 * Aviso de que la calidad del código solo pudo analizarse en parte del
 * proyecto (un repositorio en Java, por ejemplo). Va antes de las notas: es
 * contexto para leerlas, no un hallazgo más perdido en la lista.
 */
export function AvisoDeCobertura({ texto }: { texto?: string | null }) {
  if (!texto) return null;
  return (
    <p
      role="note"
      className="mt-4 rounded-[6px] border border-[oklch(0.80_0.14_85)] bg-bg px-3 py-2 text-[12.5px] leading-relaxed text-muted"
    >
      <strong className="text-[oklch(0.80_0.14_85)]">Atención.</strong> {texto}
    </p>
  );
}
