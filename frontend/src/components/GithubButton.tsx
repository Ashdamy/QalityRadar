import { GithubMark } from "./GithubMark";

/**
 * The "surface" secondary button with the GitHub mark, used both for
 * "Continuar con GitHub" on the auth screen and "Conectar GitHub" on the
 * repositories empty state.
 */
export function GithubButton({
  label,
  onClick,
  disabled,
  className = "",
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`flex cursor-pointer items-center justify-center gap-[9px] rounded-[6px] border border-border bg-surface px-[11px] py-[11px] font-sans text-sm font-medium text-text disabled:cursor-not-allowed disabled:opacity-60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2 ${className}`}
    >
      <GithubMark size={16} />
      {label}
    </button>
  );
}
