/**
 * The QalitiRadar brand mark: three concentric circles with a filled center,
 * matching the design prototype's header logo. Used in both the auth screen
 * and the repositories top bar.
 */
export function RadarMark({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="9" className="stroke-accent" strokeWidth="1.4" />
      <circle cx="12" cy="12" r="5" className="stroke-accent" strokeWidth="1.4" opacity="0.6" />
      <circle cx="12" cy="12" r="1.6" className="fill-accent" />
    </svg>
  );
}
