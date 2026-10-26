import { useEffect, useState } from "react";
import { Link } from "react-router";
import { fetchHealth, type HealthState } from "../lib/health.ts";

export function StatusPage() {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<HealthState>({ phase: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    fetchHealth(controller.signal)
      .then((next) => {
        if (!controller.signal.aborted) {
          setState(next);
        }
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        if (!controller.signal.aborted) {
          setState({ phase: "unreachable" });
        }
      });
    return () => controller.abort();
  }, [attempt]);

  return (
    <main className="min-h-screen bg-cloud text-midnight">
      <div className="mx-auto grid min-h-screen max-w-5xl content-center gap-14 px-6 py-16 sm:px-10 lg:grid-cols-[minmax(0,1.4fr)_20rem]">
        <header>
          <p className="font-display text-xs font-semibold tracking-[0.22em] text-slate">GELİŞTİRME TEMELİ</p>
          <h1 className="mt-5 font-display text-5xl font-semibold tracking-[0.12em] sm:text-6xl">LUMINOVA</h1>
          <div className="mt-6 h-0.5 w-12 bg-violet" />
          <p className="mt-8 max-w-xl leading-7 text-slate">
            API ve PostgreSQL bağlantısı burada doğrulanır.
          </p>
          <Link to="/" className="mt-6 inline-flex text-sm font-medium">
            Tanıtım sayfasına dön
          </Link>
        </header>
        <section aria-live="polite" aria-busy={state.phase === "loading"} className="border-t border-midnight/15 pt-6">
          <h2 className="font-display text-sm font-semibold tracking-[0.16em]">BAĞLANTI</h2>
          <p className={`mt-4 text-lg leading-7 ${statusClass(state)}`}>{statusText(state)}</p>
          {state.phase === "ok" || state.phase === "degraded" ? (
            <dl className="mt-6 grid grid-cols-[7rem_1fr] gap-y-2 text-sm">
              <dt className="text-slate">Servis</dt>
              <dd>{state.health.service}</dd>
              <dt className="text-slate">Ortam</dt>
              <dd>{state.health.environment}</dd>
              <dt className="text-slate">Sürüm</dt>
              <dd>{state.health.version}</dd>
              <dt className="text-slate">Veritabanı</dt>
              <dd>{state.health.checks.database === "ok" ? "Yanıt veriyor" : "Yanıt vermiyor"}</dd>
            </dl>
          ) : null}
          <button
            type="button"
            className="mt-8 inline-flex h-11 items-center bg-midnight px-4 text-sm font-medium text-onink"
            onClick={() => {
              setState({ phase: "loading" });
              setAttempt((value) => value + 1);
            }}
          >
            Yeniden kontrol et
          </button>
        </section>
      </div>
    </main>
  );
}

function statusText(state: HealthState): string {
  if (state.phase === "loading") {
    return "Bağlantı kontrol ediliyor.";
  }
  if (state.phase === "ok") {
    return "API ayakta. PostgreSQL yanıt veriyor.";
  }
  if (state.phase === "degraded") {
    return "API ayakta. PostgreSQL yanıt vermiyor.";
  }
  return "API'ye ulaşılamadı. Backend sürecinin çalıştığını kontrol et.";
}

function statusClass(state: HealthState): string {
  if (state.phase === "ok") {
    return "text-success-text";
  }
  if (state.phase === "degraded" || state.phase === "unreachable") {
    return "text-error-text";
  }
  return "text-slate";
}
