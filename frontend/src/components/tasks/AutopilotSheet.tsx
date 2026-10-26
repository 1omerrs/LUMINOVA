import { useEffect, useState } from "react";
import { ApiRequestError } from "../../lib/http.ts";
import { fetchAutopilot, runAutopilot, saveAutopilot, type Autopilot } from "../../lib/insights.ts";
import type { Assignee } from "../../lib/tasks.ts";
import { Alert, Button, Spinner } from "../forms/Controls.tsx";
import { Sheet } from "../ui/Sheet.tsx";

export function AutopilotSheet({
  assignees,
  canEdit,
  enabledModules,
  onClose,
  onSaved,
}: {
  assignees: Assignee[];
  canEdit: boolean;
  enabledModules: Set<string>;
  onClose: () => void;
  onSaved: (message: string) => void;
}) {
  const [settings, setSettings] = useState<Autopilot | null>(null);
  const [enabled, setEnabled] = useState(true);
  const [kinds, setKinds] = useState<Set<string>>(new Set());
  const [assignee, setAssignee] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState<"save" | "run" | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchAutopilot()
      .then((next) => {
        if (cancelled) return;
        setSettings(next);
        setEnabled(next.enabled);
        setKinds(new Set(next.kinds.filter((kind) => kind.on).map((kind) => kind.key)));
        setAssignee(next.default_assignee_id ?? "");
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(caught instanceof ApiRequestError ? caught.message : "Ayarlar yüklenemedi.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function save() {
    setPending("save");
    setError("");
    try {
      await saveAutopilot({ enabled, kinds: [...kinds], default_assignee_id: assignee || null });
      onSaved(enabled ? "Otomatik görevler güncellendi." : "Otomatik görevler kapatıldı; açık otomatik görevler kapandı.");
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Ayarlar kaydedilemedi.");
      setPending(null);
    }
  }

  async function run() {
    setPending("run");
    setError("");
    try {
      const result = await runAutopilot();
      onSaved(result.created || result.resolved ? `${result.created} görev açıldı, ${result.resolved} görev kendiliğinden kapandı.` : "Yeni bir iş çıkmadı; görev listeniz güncel.");
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Kontrol çalıştırılamadı.");
      setPending(null);
    }
  }

  return (
    <Sheet
      title="Otomatik görevler"
      description="LUMINOVA kayıtlarınızı düzenli kontrol eder; ilgilenilmesi gereken bir durum çıktığında görev açar, durum düzelince görevi kendisi kapatır."
      busy={pending !== null}
      onClose={onClose}
      footer={
        <>
          <Button variant="quiet" className="mr-auto" onClick={() => void run()} pending={pending === "run"} pendingLabel="Kontrol ediliyor" disabled={pending !== null}>
            Şimdi kontrol et
          </Button>
          {canEdit ? (
            <Button onClick={() => void save()} pending={pending === "save"} pendingLabel="Kaydediliyor" disabled={!settings || pending !== null}>
              Kaydet
            </Button>
          ) : null}
        </>
      }
    >
      {error ? <Alert tone="error">{error}</Alert> : null}
      {!settings && !error ? (
        <p className="flex items-center gap-2 text-[14px] text-slate">
          <Spinner /> Yükleniyor
        </p>
      ) : null}
      {settings ? (
        <div className="space-y-6">
          {!canEdit ? <Alert tone="info">Ayarları şirket sahibi veya yönetici değiştirebilir; siz kontrolü elle çalıştırabilirsiniz.</Alert> : null}
          <label className="flex items-start gap-3 text-[14px]">
            <input type="checkbox" checked={enabled} disabled={!canEdit} onChange={(event) => setEnabled(event.target.checked)} className="mt-0.5 h-4 w-4 accent-[#5b47d6]" />
            <span>
              <span className="font-medium">Otomatik görevleri aç</span>
              <span className="mt-0.5 block text-[12.5px] leading-5 text-slate">
                Kontrol birkaç dakikada bir çalışır; arka plan görevi açıkken panel kapalıyken de devam eder. Elle tamamladığınız bir görev, durum sürse bile 3 gün yeniden açılmaz.
              </span>
            </span>
          </label>
          <section className="border-t border-hairline pt-5">
            <h3 className="text-[12px] font-semibold uppercase tracking-[0.08em] text-slate">Hangi durumlar için</h3>
            <ul className="mt-3 space-y-2.5">
              {settings.kinds.map((kind) => {
                const available = enabledModules.has(kind.module);
                return (
                  <li key={kind.key}>
                    <label className={`flex items-center gap-3 text-[14px] ${available ? "" : "text-slate"}`}>
                      <input
                        type="checkbox"
                        checked={kinds.has(kind.key)}
                        disabled={!canEdit || !enabled}
                        onChange={(event) =>
                          setKinds((current) => {
                            const next = new Set(current);
                            if (event.target.checked) next.add(kind.key);
                            else next.delete(kind.key);
                            return next;
                          })
                        }
                        className="h-4 w-4 accent-[#5b47d6]"
                      />
                      {kind.label}
                      {available ? null : <span className="text-[12px]">· modül kapalı</span>}
                    </label>
                  </li>
                );
              })}
            </ul>
          </section>
          <section className="border-t border-hairline pt-5">
            <label className="block text-[13px] font-medium">
              Kayıtta sorumlu yoksa kime atansın?
              <select
                value={assignee}
                disabled={!canEdit}
                onChange={(event) => setAssignee(event.target.value)}
                className="mt-1.5 h-10 w-full rounded-lg border border-mist bg-surface px-3 text-[14px] outline-none focus:border-violet"
              >
                <option value="">Şirket sahibine</option>
                {assignees.map((person) => (
                  <option key={person.id} value={person.id}>
                    {person.name}
                  </option>
                ))}
              </select>
            </label>
            <p className="mt-1.5 text-[12.5px] leading-5 text-slate">Görev, mümkünse kaydı oluşturan kişiye gider; örneğin tahsilat takibi siparişi açan kişiye.</p>
          </section>
          {settings.last_run_at ? <p className="text-[12px] text-slate">Son kontrol: {new Date(settings.last_run_at).toLocaleString("tr-TR")}</p> : null}
        </div>
      ) : null}
    </Sheet>
  );
}
