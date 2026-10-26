import { useEffect, useState } from "react";
import { ApiRequestError } from "../../lib/http.ts";
import { fetchSalesRules, saveSalesRules, type IncomeOn, type SalesRules } from "../../lib/sales.ts";
import { fetchTemplates, type TaskTemplate } from "../../lib/tasks.ts";
import { Alert, Button, Spinner } from "../forms/Controls.tsx";
import { Sheet } from "../ui/Sheet.tsx";

const control =
  "mt-1.5 h-10 w-full rounded-lg border border-mist bg-surface px-3 text-[14px] text-graphite outline-none hover:border-stone focus:border-violet disabled:bg-cloud disabled:text-slate";

const incomeOptions: { value: IncomeOn; label: string }[] = [
  { value: "off", label: "Kapalı, gelir kaydını elle oluştururum" },
  { value: "confirmed", label: "Sipariş onaylandığında" },
  { value: "fulfilled", label: "Sipariş teslim edildiğinde" },
];

export function SalesRulesSheet({ canEdit, onClose, onSaved }: { canEdit: boolean; onClose: () => void; onSaved: () => void }) {
  const [rules, setRules] = useState<SalesRules | null>(null);
  const [templates, setTemplates] = useState<TaskTemplate[]>([]);
  const [incomeOn, setIncomeOn] = useState<IncomeOn>("off");
  const [dueDays, setDueDays] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [produce, setProduce] = useState(false);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchSalesRules()
      .then((next) => {
        if (cancelled) return;
        setRules(next);
        setIncomeOn(next.income_on);
        setDueDays(next.income_due_days === null ? "" : String(next.income_due_days));
        setTemplateId(next.confirm_template_id ?? "");
        setProduce(next.production_on_shortage);
        if (next.tasks_on) fetchTemplates().then((items) => !cancelled && setTemplates(items), () => undefined);
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(caught instanceof ApiRequestError ? caught.message : "Kurallar yüklenemedi.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function save() {
    const days = dueDays.trim() === "" ? null : Number(dueDays);
    if (days !== null && (!Number.isInteger(days) || days < 0 || days > 365)) return setError("Vade 0 ile 365 gün arasında olmalı.");
    setPending(true);
    setError("");
    try {
      await saveSalesRules({
        income_on: incomeOn,
        income_due_days: incomeOn === "off" ? null : days,
        confirm_template_id: templateId || null,
        production_on_shortage: produce,
      });
      onSaved();
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Kurallar kaydedilemedi.");
      setPending(false);
    }
  }

  return (
    <Sheet
      title="Satış kuralları"
      description="Sipariş durum değiştirdiğinde arka planda ne olacağını seçin. Her kural bir siparişe en fazla bir kez uygulanır."
      busy={pending}
      onClose={onClose}
      footer={
        canEdit ? (
          <>
            <Button variant="quiet" onClick={onClose} disabled={pending}>
              Vazgeç
            </Button>
            <Button onClick={() => void save()} pending={pending} pendingLabel="Kaydediliyor" disabled={!rules}>
              Kuralları kaydet
            </Button>
          </>
        ) : undefined
      }
    >
      {error ? <Alert tone="error">{error}</Alert> : null}
      {!rules && !error ? (
        <p className="flex items-center gap-2 text-[14px] text-slate">
          <Spinner /> Yükleniyor
        </p>
      ) : null}
      {rules ? (
        <div className="space-y-7">
          {!canEdit ? <Alert tone="info">Kuralları yalnızca şirket sahibi veya yönetici değiştirebilir.</Alert> : null}
          <section className="space-y-3 border-b border-hairline pb-6">
            <h3 className="text-[12px] font-semibold uppercase tracking-[0.08em] text-slate">Gelir kaydı</h3>
            {rules.finance_on ? (
              <>
                <label className="block text-[13px] font-medium">
                  Ne zaman oluşturulsun?
                  <select value={incomeOn} disabled={!canEdit} onChange={(event) => setIncomeOn(event.target.value as IncomeOn)} className={control}>
                    {incomeOptions.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
                {incomeOn !== "off" ? (
                  <label className="block text-[13px] font-medium">
                    Ödeme vadesi (gün, isteğe bağlı)
                    <input
                      inputMode="numeric"
                      value={dueDays}
                      disabled={!canEdit}
                      onChange={(event) => setDueDays(event.target.value)}
                      placeholder="Ör. 30"
                      className={control}
                    />
                  </label>
                ) : null}
                <p className="text-[12.5px] leading-5 text-slate">
                  Kayıt sipariş tutarıyla, “ödeme bekliyor” durumunda açılır. Sipariş iptal edilirse bekleyen gelir kaydı da iptal edilir; ödenmiş kayda dokunulmaz.
                </p>
              </>
            ) : (
              <p className="text-[13px] text-slate">Bu kural için Finansal Takip modülü açık olmalı.</p>
            )}
          </section>
          <section className="space-y-3 border-b border-hairline pb-6">
            <h3 className="text-[12px] font-semibold uppercase tracking-[0.08em] text-slate">Eksik stokta üretim</h3>
            {rules.production_on ? (
              <>
                <label className="flex items-start gap-3 text-[14px]">
                  <input
                    type="checkbox"
                    checked={produce}
                    disabled={!canEdit}
                    onChange={(event) => setProduce(event.target.checked)}
                    className="mt-0.5 h-4 w-4 accent-[#5b47d6]"
                  />
                  <span>
                    <span className="font-medium">Onaylanan siparişte stok yetmezse üretim emri aç</span>
                    <span className="mt-1 block text-[12.5px] leading-5 text-slate">
                      Eksik miktar kadar, siparişe bağlı ve planlanmış iş emri açılır; malzemeler ürün reçetesinden gelir. Reçetesi olmayan ürünler için yalnızca uyarı verilir.
                    </span>
                  </span>
                </label>
              </>
            ) : (
              <p className="text-[13px] text-slate">Bu kural için Üretim modülü açık olmalı.</p>
            )}
          </section>
          <section className="space-y-3">
            <h3 className="text-[12px] font-semibold uppercase tracking-[0.08em] text-slate">Onaylanınca görevler</h3>
            {rules.tasks_on ? (
              <>
                <label className="block text-[13px] font-medium">
                  Uygulanacak görev şablonu
                  <select value={templateId} disabled={!canEdit} onChange={(event) => setTemplateId(event.target.value)} className={control}>
                    <option value="">Görev oluşturma</option>
                    {templates.map((template) => (
                      <option key={template.id} value={template.id}>
                        {template.name} · {template.items.length} görev
                      </option>
                    ))}
                  </select>
                </label>
                <p className="text-[12.5px] leading-5 text-slate">
                  Görevler siparişe ve müşteriye bağlı oluşur, bağımlılıklarıyla birlikte. Şablonları Görevler ekranındaki “Şablonlar”dan yönetirsiniz.
                </p>
              </>
            ) : (
              <p className="text-[13px] text-slate">Bu kural için Görev ve İş Yönetimi modülü açık olmalı.</p>
            )}
          </section>
        </div>
      ) : null}
    </Sheet>
  );
}
