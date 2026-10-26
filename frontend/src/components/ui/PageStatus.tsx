import { Spinner } from "../forms/Controls.tsx";
import { Wordmark } from "./Wordmark.tsx";

export function PageStatus({ message, failed = false }: { message: string; failed?: boolean }) {
  return (
    <main className="grid min-h-dvh place-items-center bg-cloud px-6 text-graphite">
      <div className="flex flex-col items-center text-center">
        <Wordmark className="text-sm" />
        <p role={failed ? "alert" : "status"} className={`mt-6 flex items-center gap-2.5 text-[14px] ${failed ? "text-error-text" : "text-slate"}`}>
          {failed ? null : <Spinner className="h-4 w-4 text-violet" />}
          {message}
        </p>
        {failed ? (
          <button type="button" onClick={() => window.location.reload()} className="mt-4 text-[14px] font-semibold text-violet hover:underline">
            Sayfayı yenile
          </button>
        ) : null}
      </div>
    </main>
  );
}
