import { useEffect, useState } from "react";
import { useParams } from "react-router";
import { Alert, Button, Spinner, TextArea } from "../components/forms/Controls.tsx";
import { ApiRequestError } from "../lib/http.ts";
import { formatQuantity } from "../lib/inventory.ts";
import { decidePublicQuote, fetchPublicQuote, type PublicQuote } from "../lib/quotes.ts";
import { formatDate, formatMoney, percentText } from "../lib/sales.ts";

type Decision = "accept" | "reject";

export function PublicQuotePage() {
  const { token = "" } = useParams();
  const [quote, setQuote] = useState<PublicQuote | null>(null);
  const [loadError, setLoadError] = useState("");
  const [confirming, setConfirming] = useState<Decision | null>(null);
  const [note, setNote] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    fetchPublicQuote(token)
      .then((next) => {
        if (!cancelled) setQuote(next);
      })
      .catch((caught: unknown) => {
        if (!cancelled) setLoadError(caught instanceof ApiRequestError ? caught.message : "Teklif yüklenemedi.");
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  useEffect(() => {
    document.title = quote ? `${quote.company_name} · ${quote.code}` : "Teklif";
  }, [quote]);

  async function decide(decision: Decision) {
    setPending(true);
    setError("");
    try {
      setQuote(await decidePublicQuote(token, decision, note));
      setConfirming(null);
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Kararınız kaydedilemedi. Lütfen tekrar deneyin.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="min-h-dvh bg-cloud px-4 py-8 text-graphite sm:py-12">
      <main className="mx-auto w-full max-w-[760px]">
        {loadError ? (
          <div className="rounded-2xl border border-mist/80 bg-surface px-6 py-10 text-center">
            <h1 className="text-[18px] font-semibold">Teklif açılamadı</h1>
            <p className="mx-auto mt-2 max-w-md text-[14px] leading-6 text-slate">{loadError}</p>
          </div>
        ) : !quote ? (
          <p role="status" className="flex items-center justify-center gap-2.5 py-16 text-[14px] text-slate">
            <Spinner className="h-4 w-4 text-violet" /> Teklif yükleniyor.
          </p>
        ) : (
          <article className="overflow-hidden rounded-2xl border border-mist/80 bg-surface">
            <header className="border-b border-mist/70 px-6 py-6 sm:px-8">
              <p className="text-[12px] font-semibold uppercase tracking-[0.12em] text-slate">{quote.company_name}</p>
              <div className="mt-2 flex flex-wrap items-end justify-between gap-3">
                <h1 className="font-display text-[24px] font-semibold tracking-[-0.02em] text-midnight">Teklif {quote.code}</h1>
                <p className="text-[13px] text-slate">
                  {formatDate(quote.quote_date)}
                  {quote.valid_until ? ` · ${formatDate(quote.valid_until)} tarihine kadar geçerli` : ""}
                </p>
              </div>
              <p className="mt-1 text-[14px] text-slate">Sayın {quote.customer_name}</p>
            </header>

            <div className="overflow-x-auto">
              <table className="w-full min-w-[520px] text-left text-[14px]">
                <thead className="bg-cloud/60 text-[12px] text-slate">
                  <tr>
                    <th scope="col" className="px-6 py-2.5 font-medium sm:px-8">Ürün / hizmet</th>
                    <th scope="col" className="px-3 py-2.5 text-right font-medium">Miktar</th>
                    <th scope="col" className="px-3 py-2.5 text-right font-medium">Birim fiyat</th>
                    <th scope="col" className="px-3 py-2.5 text-right font-medium">KDV</th>
                    <th scope="col" className="px-6 py-2.5 text-right font-medium sm:px-8">Tutar</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-mist/60">
                  {quote.items.map((item, index) => (
                    <tr key={index}>
                      <td className="px-6 py-3 sm:px-8">
                        <p className="font-medium">{item.description}</p>
                        {item.discount_rate !== "0" ? <p className="text-[12px] text-success-text">{percentText(item.discount_rate)} iskonto</p> : null}
                      </td>
                      <td className="whitespace-nowrap px-3 py-3 text-right tabular-nums">
                        {formatQuantity(item.quantity)} {item.unit ?? ""}
                      </td>
                      <td className="whitespace-nowrap px-3 py-3 text-right tabular-nums">{formatMoney(item.unit_price, quote.currency)}</td>
                      <td className="px-3 py-3 text-right text-slate">%{item.vat_rate}</td>
                      <td className="whitespace-nowrap px-6 py-3 text-right font-semibold tabular-nums sm:px-8">{formatMoney(item.line_total, quote.currency)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <dl className="space-y-1.5 border-t border-mist/70 bg-cloud/40 px-6 py-4 text-[14px] sm:px-8">
              {Number(quote.discount_total) > 0 ? (
                <div className="flex justify-between">
                  <dt className="text-slate">İskonto</dt>
                  <dd className="tabular-nums text-success-text">−{formatMoney(quote.discount_total, quote.currency)}</dd>
                </div>
              ) : null}
              <div className="flex justify-between">
                <dt className="text-slate">Ara toplam</dt>
                <dd className="tabular-nums">{formatMoney(quote.subtotal, quote.currency)}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-slate">KDV</dt>
                <dd className="tabular-nums">{formatMoney(quote.vat_total, quote.currency)}</dd>
              </div>
              <div className="flex justify-between text-[17px] font-semibold">
                <dt>Genel toplam</dt>
                <dd className="tabular-nums">{formatMoney(quote.total, quote.currency)}</dd>
              </div>
            </dl>
            {quote.note ? <p className="whitespace-pre-line border-t border-mist/70 px-6 py-4 text-[14px] leading-6 sm:px-8">{quote.note}</p> : null}

            <section aria-label="Kararınız" className="space-y-4 border-t border-mist/70 px-6 py-6 sm:px-8">
              {quote.status === "accepted" || quote.status === "rejected" ? (
                <Alert tone={quote.status === "accepted" ? "success" : "info"}>
                  {quote.status === "accepted" ? "Teklif kabul edildi." : "Teklif reddedildi."}
                  {quote.decided_at ? ` (${formatDate(quote.decided_at.slice(0, 10))})` : ""} {quote.company_name} bilgilendirildi.
                  {quote.customer_note ? ` Notunuz: “${quote.customer_note}”` : ""}
                </Alert>
              ) : quote.expired ? (
                <Alert tone="info">Bu teklifin geçerlilik süresi doldu. Güncel teklif için {quote.company_name} ile iletişime geçin.</Alert>
              ) : quote.can_decide ? (
                <>
                  <div>
                    <p className="text-[15px] font-semibold">Teklifi değerlendirdiniz mi?</p>
                    <p className="mt-0.5 text-[13px] text-slate">Kararınız {quote.company_name} ekibine hemen iletilir.</p>
                  </div>
                  <TextArea label="Not (isteğe bağlı)" name="customer-note" rows={3} maxLength={500} value={note} onValue={setNote} />
                  {error ? <Alert tone="error">{error}</Alert> : null}
                  {confirming ? (
                    <div className="flex flex-wrap items-center gap-3 rounded-xl bg-cloud/70 px-4 py-3">
                      <p className="flex-1 text-[14px]">
                        {confirming === "accept" ? "Teklifi kabul ettiğinizi onaylıyor musunuz?" : "Teklifi reddettiğinizi onaylıyor musunuz?"}
                      </p>
                      <Button variant="quiet" onClick={() => setConfirming(null)} disabled={pending}>
                        Vazgeç
                      </Button>
                      <Button
                        variant={confirming === "accept" ? "primary" : "danger"}
                        pending={pending}
                        pendingLabel="Kaydediliyor"
                        onClick={() => void decide(confirming)}
                      >
                        {confirming === "accept" ? "Evet, kabul ediyorum" : "Evet, reddet"}
                      </Button>
                    </div>
                  ) : (
                    <div className="flex flex-wrap gap-3">
                      <Button size="lg" onClick={() => setConfirming("accept")}>
                        Teklifi kabul ediyorum
                      </Button>
                      <Button size="lg" variant="quiet" onClick={() => setConfirming("reject")}>
                        Reddet
                      </Button>
                    </div>
                  )}
                </>
              ) : (
                <Alert tone="info">Bu teklif henüz yanıtlanmaya açık değil.</Alert>
              )}
            </section>
          </article>
        )}
        <p className="mt-6 text-center text-[12px] text-slate">Bu teklif sayfası LUMINOVA ile hazırlanmıştır.</p>
      </main>
    </div>
  );
}
