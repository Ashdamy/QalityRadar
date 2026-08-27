import type { InputHTMLAttributes } from "react";

interface TextFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  id: string;
  label: string;
  /** Visually hide the label while keeping it in the accessibility tree. */
  hideLabel?: boolean;
}

/**
 * A labeled text input matching the prototype's form field style: a small
 * muted label above a surface-colored input with a visible accent focus
 * ring.
 */
export function TextField({ id, label, hideLabel, className = "", ...props }: TextFieldProps) {
  return (
    <label htmlFor={id} className="flex flex-col gap-[6px]">
      <span className={`text-[12.5px] font-medium text-muted ${hideLabel ? "sr-only" : ""}`}>
        {label}
      </span>
      <input
        id={id}
        {...props}
        className={`rounded-[6px] border border-border bg-surface px-[12px] py-[10px] font-sans text-sm text-text placeholder:text-faint focus:border-accent focus:outline-none focus:ring-[3px] focus:ring-accentDim ${className}`}
      />
    </label>
  );
}
