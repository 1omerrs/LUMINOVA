import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { ApiRequestError } from "../../lib/http.ts";
import { createLink } from "../../lib/intent.ts";
import { useWorkspace } from "../../lib/workspace.ts";
import { formatQuantity } from "../../lib/inventory.ts";
import { fetchQuote, quoteAction, quoteStatusLabels, quoteStatusTone, sendQuote, type QuoteAction, type QuoteDetail } from "../../lib/quotes.ts";
import { formatDate, formatMoney, percentText } from "../../lib/sales.ts";
import { mailStatusLabels } from "../../lib/team.ts";
import { Alert, Button, Spinner, TextArea } from "../forms/Controls.tsx";
import { Sheet } from "../ui/Sheet.tsx";

const actionLabels: Record<QuoteAction, { label: string; pending: string }> = {
  send: { label: "Teklifi gönder", pending: "Gönderiliyor" },
  accept: { label: "Kabul edildi", pending: "Kaydediliyor" },
  reject: { label: "Reddedildi", pending: "Kaydediliyor" },
  convert: { label: "Siparişe çevir", pending: "Sipariş oluşturuluyor" },
};

export function QuoteSheet({
  quoteId,
  salesOn,
  onClose,
  onEdit,
  onChanged,
}: {
  quoteId: string;
  salesOn: boolean;
  onClose: () => void;
  onEdit: (quote: QuoteDetail) => void;
  onChanged: (quote: QuoteDetail, action: QuoteAction) => void;
}) {
  const [quote, setQuote] = useState<QuoteDetail | null>(null);
  const [loadError, setLoadError] = useState("");
  const [pending, setPending] = useState<QuoteAction | null>(null);
  const [error, setError] = useState("");
  const [composing, setComposing] = useState<"send" | "resend" | null>(null);
  const [emailOn, setEmailOn] = useState(true);
  const [message, setMessage] = useState("");
  const [shared, setShared] = useState<{ path: string; notice: string | null } | null>(null);
  const [copied, setCopied] = useState(false);
  const statusRef = useRef<HTMLDivElement>(null);
  const { modules } = useWorkspace();
  const projectsOn = modules.some((item) => item.key === "projects" && item.enabled);

  useEffect(() => {
    let cancelled = false;
    fetchQuote(quoteId)
      .then((next) => {
        if (!cancelled) setQuote(next);
      })
      .catch((caught: unknown) => {
        if (!cancelled) setLoadError(caught instanceof ApiRequestError ? caught.message : "Teklif yüklenemedi.");
      });
    return () => {
      cancelled = true;
    };
  }, [quoteId]);

  async function run(action: QuoteAction) {
    if (!quote) return;
    setPending(action);
    setError("");
    try {
      const next = await quoteAction(quote.id, action);
      setQuote(next);
      onChanged(next, action);
      requestAnimationFrame(() => statusRef.current?.focus());
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "İşlem tamamlanamadı.");
    } finally {
      setPending(null);
    }
  }

  function compose(mode: "send" | "resend") {
    setComposing(mode);
    setEmailOn(Boolean(quote?.customer_email));
    setMessage("");
    setError("");
  }

  async function deliver() {
    if (!quote || !composing) return;
    setPending("send");
    setError("");
    try {
      const next = await sendQuote(quote.id, { email: emailOn, message }, composing === "resend");
      setQuote(next);
      setShared(next.share_path ? { path: next.share_path, notice: next.email_notice } : null);
      setComposing(null);
      setCopied(false);
      onChanged(next, "send");
      requestAnimationFrame(() => statusRef.current?.focus());
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Teklif gönderilemedi.");
    } finally {
      setPending(null);
    }
  }

  const actions: QuoteAction[] = !quote || composing
    ? []
    : quote.status === "sent"
      ? ["reject", "accept"]
      : quote.status === "accepted" && !quote.order_id && salesOn
        ? ["convert"]
        : [];
  const link = shared ? `${window.location.origin}${shared.path}` : null;

  return (
    <Sheet
      wide
      title={quote?.code ?? "Teklif"}
      description={quote ? `${quote.customer_name} · ${formatDate(quote.quote_date)}` : undefined}
      busy={pending !== null}
      onClose={onClose}
      footer={
        quote && composing ? (
          <>
            <Button variant="quiet" onClick={() => setComposing(null)} disabled={pending !== null}>
              Vazgeç
            </Button>
            <Button pending={pending === "send"} pendingLabel="Gönderiliyor" onClick={() => void deliver()}>
              {composing === "resend" ? "Yeni bağlantıyı gönder" : emailOn ? "Teklifi e-postayla gönder" : "Gönderildi olarak işaretle"}
            </Button>
          </>
        ) : quote && (actions.length > 0 || quote.status === "draft") ? (
          <>
            {quote.status === "draft" ? (
              <>
                <Button variant="quiet" onClick={() => onEdit(quote)} disabled={pending !== null}>
                  Düzenle
                </Button>
                <Button onClick={() => compose("send")} disabled={pending !== null}>
                  Teklifi gönder
                </Button>
              </>
            ) : null}
            {actions.map((action) => (
              <Button
                key={action}
                variant={action === "reject" ? "quiet" : "primary"}
                className={action === "reject" ? "text-error-text" : ""}
                pending={pending === action}
                pendingLabel={actionLabels[action].pending}
                disabled={pending !== null}
                onClick={() => void run(action)}
              >
                {actionLabels[action].label}
              </Button>
            ))}
          </>
        ) : undefined
      }
    >
      {loadError ? (
        <Alert tone="error">{loadError}</Alert>
      ) : !quote ? (
        <p role="status" className="flex items-center gap-2.5 text-[14px] text-slate">
          <Spinner className="h-4 w-4 text-violet" /> Teklif yükleniyor.
        </p>
      ) : (
        <div className="space-y-6">
          <div ref={statusRef} tabIndex={-1} className="flex flex-wrap items-center justify-between gap-3 rounded-lg outline-none">
            <span className="flex items-center gap-2">
              <span className={`rounded-full px-2.5 py-1 text-[12px] font-semibold ${quoteStatusTone[quote.status]}`}>{quoteStatusLabels[quote.status]}</span>
              {quote.expired ? <span className="rounded-full bg-warning/10 px-2.5 py-1 text-[12px] font-semibold text-warning-text">Süresi doldu</span> : null}
            </span>
            <p className="text-[13px] text-slate">{quote.valid_until ? `Geçerlilik: ${formatDate(quote.valid_until)}` : "Geçerlilik tarihi yok"}</p>
          </div>
          {projectsOn && quote.status === "accepted" ? (
            <Link
              to={createLink("/panel/projeler", { id: quote.customer_id, label: quote.customer_name }, { kind: "quote", id: quote.id, label: quote.code })}
              className="inline-flex items-center gap-1.5 text-[13px] font-semibold text-violet hover:underline"
            >
              Bu tekliften proje başlat
            </Link>
          ) : null}

          {error ? <Alert tone="error">{error}</Alert> : null}

          {composing ? (
            <section aria-label="Teklifi gönder" className="space-y-4 rounded-2xl border border-violet/25 bg-violet/[0.03] p-4">
              <p className="text-[14px] font-semibold">{composing === "resend" ? "Bağlantıyı yenile ve yeniden gönder" : "Teklifi müşteriye gönder"}</p>
              <label className={`flex items-start gap-3 text-[14px] ${quote.customer_email ? "" : "text-slate"}`}>
                <input
                  type="checkbox"
                  checked={emailOn}
                  disabled={!quote.customer_email}
                  onChange={(event) => setEmailOn(event.target.checked)}
                  className="mt-0.5 h-4 w-4 accent-[#5b47d6]"
                />
                <span>
                  <span className="font-medium">{quote.customer_email ? `${quote.customer_email} adresine e-postayla gönder` : "Müşterinin e-posta adresi kayıtlı değil"}</span>
                  <span className="mt-0.5 block text-[12.5px] leading-5 text-slate">
                    E-postada teklif özeti ve müşterinin teklifi görüp kabul edebileceği veya reddedebileceği bir bağlantı olur. Müşteri e-postayı yanıtlarsa yanıt size gelir.
                  </span>
                </span>
              </label>
              {emailOn ? (
                <TextArea
                  label="Müşteriye not (isteğe bağlı)"
                  name="quote-message"
                  rows={3}
                  maxLength={1000}
                  value={message}
                  onValue={setMessage}
                />
              ) : null}
              {composing === "resend" ? <p className="text-[12.5px] text-slate">Önceki bağlantı çalışmayı bırakır.</p> : null}
            </section>
          ) : null}

          {shared ? (
            <section aria-label="Müşteri bağlantısı" className="space-y-2.5 rounded-2xl border border-mist/80 p-4">
              {shared.notice ? <p className="text-[13.5px] leading-5">{shared.notice}</p> : null}
              {link ? (
                <div className="flex flex-col gap-2 sm:flex-row">
                  <input readOnly value={link} aria-label="Teklif bağlantısı" className="h-10 min-w-0 flex-1 rounded-lg border border-mist bg-surface px-3 font-mono text-[12px]" onFocus={(event) => event.target.select()} />
                  <Button
                    variant="quiet"
                    onClick={() =>
                      void navigator.clipboard.writeText(link).then(
                        () => setCopied(true),
                        () => setCopied(false),
                      )
                    }
                  >
                    {copied ? "Kopyalandı" : "Bağlantıyı kopyala"}
                  </Button>
                </div>
              ) : null}
              <p className="text-[12px] text-slate">Bağlantı yalnızca şimdi gösterilir; kaybederseniz yenileyebilirsiniz.</p>
            </section>
          ) : null}

          {quote.status === "sent" && !composing ? (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-cloud/60 px-4 py-3 text-[13px]">
              <span>
                {quote.email_status ? (
                  <span className={quote.email_status === "failed" ? "text-error-text" : quote.email_status === "sent" ? "text-success-text" : "text-slate"}>
                    {mailStatusLabels[quote.email_status]}
                    {quote.email_error ? ` · ${quote.email_error}` : ""}
                  </span>
                ) : (
                  <span className="text-slate">Teklif e-postayla gönderilmedi.</span>
                )}
                <span className="block text-slate">Müşteri bağlantıdan kabul eder veya reddederse durum kendiliğinden güncellenir.</span>
              </span>
              <Button variant="quiet" onClick={() => compose("resend")} disabled={pending !== null}>
                Bağlantıyı yenile
              </Button>
            </div>
          ) : null}

          {quote.decided_by === "customer" && quote.decided_at ? (
            <Alert tone={quote.status === "accepted" ? "success" : "info"}>
              {quote.customer_name}, {formatDate(quote.decided_at.slice(0, 10))} tarihinde teklifi {quote.status === "accepted" ? "kabul etti" : "reddetti"}.
              {quote.customer_note ? ` Notu: “${quote.customer_note}”` : ""}
            </Alert>
          ) : null}

          {quote.order_id && quote.order_code ? (
            <Alert tone="success">
              Bu teklif {quote.order_code} siparişine çevrildi.{" "}
              <Link to="/panel/satis" className="font-semibold underline">
                Satış ve Siparişler'de aç
              </Link>
            </Alert>
          ) : quote.status === "accepted" && !salesOn ? (
            <Alert tone="info">Teklifi siparişe çevirmek için Satış ve Siparişler modülünü açın.</Alert>
          ) : null}

          <div className="overflow-hidden rounded-2xl border border-mist/80">
            <table className="w-full text-left text-[14px]">
              <thead className="bg-cloud/60 text-[12px] text-slate">
                <tr>
                  <th scope="col" className="px-4 py-2 font-medium">Ürün / açıklama</th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">Miktar</th>
                  <th scope="col" className="hidden px-3 py-2 text-right font-medium sm:table-cell">Birim fiyat</th>
                  <th scope="col" className="hidden px-3 py-2 text-right font-medium sm:table-cell">KDV</th>
                  <th scope="col" className="px-4 py-2 text-right font-medium">Tutar</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-mist/60">
                {quote.items.map((item) => (
                  <tr key={item.id}>
                    <td className="px-4 py-2.5">
                      <p className="font-medium">{item.description}</p>
                      {item.product_sku ? <p className="font-mono text-[12px] text-slate">{item.product_sku}</p> : null}
                      {item.discount_rate && item.discount_rate !== "0" ? (
                        <p className="text-[12px] text-success-text">
                          {percentText(item.discount_rate)} iskonto · −{formatMoney(item.line_discount, quote.currency)}
                        </p>
                      ) : null}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2.5 text-right tabular-nums">
                      {formatQuantity(item.quantity)} {item.product_unit ?? ""}
                    </td>
                    <td className="hidden whitespace-nowrap px-3 py-2.5 text-right tabular-nums sm:table-cell">{formatMoney(item.unit_price, quote.currency)}</td>
                    <td className="hidden px-3 py-2.5 text-right text-slate sm:table-cell">%{item.vat_rate}</td>
                    <td className="whitespace-nowrap px-4 py-2.5 text-right font-semibold tabular-nums">{formatMoney(item.line_total, quote.currency)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <dl className="space-y-1.5 border-t border-mist/70 bg-cloud/40 px-4 py-3 text-[14px]">
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
              <div className="flex justify-between text-[16px] font-semibold">
                <dt>Genel toplam</dt>
                <dd className="tabular-nums">{formatMoney(quote.total, quote.currency)}</dd>
              </div>
            </dl>
          </div>
          {quote.note ? <p className="whitespace-pre-line text-[14px] leading-6">{quote.note}</p> : null}
          <p className="text-[12px] text-slate">
            Müşteri e-postadaki bağlantıdan karar verebilir. Müşteri size telefonla veya yüz yüze dönerse durumu buradan siz de işaretleyebilirsiniz.
          </p>
        </div>
      )}
    </Sheet>
  );
}
