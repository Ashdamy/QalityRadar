import { Suspense } from "react";
import { CallbackClient } from "./CallbackClient";

function CallbackFallback() {
  return (
    <main className="relative flex min-h-screen w-full items-center justify-center overflow-hidden bg-bg text-text">
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.18] [background-image:linear-gradient(var(--color-border)_1px,transparent_1px),linear-gradient(90deg,var(--color-border)_1px,transparent_1px)] [background-size:32px_32px]"
        aria-hidden="true"
      />
      <div className="relative w-[420px] max-w-[calc(100%-32px)] rounded-[10px] border border-border bg-surface p-9" />
    </main>
  );
}

export default function GithubCallbackPage() {
  return (
    <Suspense fallback={<CallbackFallback />}>
      <CallbackClient />
    </Suspense>
  );
}
