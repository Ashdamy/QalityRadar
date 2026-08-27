import type { ButtonHTMLAttributes } from "react";

/**
 * The filled accent call-to-action button used across all three screens
 * (auth submit, GitHub callback success, repository list actions). When
 * disabled it falls back to the muted "inactive" treatment from the
 * repository list prototype.
 */
export function PrimaryButton({
  className = "",
  disabled,
  style,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      disabled={disabled}
      style={{ padding: "11px", ...style }}
      className={`rounded-[6px] border font-sans text-sm font-semibold transition-colors ${
        disabled
          ? "cursor-not-allowed border-surface2 bg-surface2 text-faint"
          : "cursor-pointer border-accentStrong bg-accentStrong text-onAccent hover:brightness-110"
      } focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2 ${className}`}
    />
  );
}
