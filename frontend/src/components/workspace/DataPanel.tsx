import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { useNavigate } from "react-router";
import { cancelClosure, closeAccount, downloadPersonalExport, downloadWorkspaceExport, fetchClosure, requestClosure, type Closure } from "../../lib/account.ts";
import { ApiRequestError } from "../../lib/http.ts";
import { useWorkspace } from "../../lib/workspace.ts";
import { Alert, Button, PasswordField, TextArea } from "../forms/Controls.tsx";
import { Sheet } from "../ui/Sheet.tsx";

const dayFormat = new Intl.DateTimeFormat("tr-TR", { day: "numeric", month: "long", year: "numeric" });

export function DataPanel() {
  const { user } = useWorkspace();
  const navigate = useNavigate();
  const owner = user.role === "owner";
  const manager = user.role !== "member";
  const [closure, setClosure] = useState<Closure | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [sheet, setSheet] = useState<"workspace" | "account" | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchClosure()
      .then((next) => {
        if (!cancelled) setClosure(next);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  async function run(key: string, action: () => Promise<void>, done?: string) {
    setBusy(key);
    setError("");
    setNotice("");
    try {
      await action();
      if (done) setNotice(done);
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "İşlem tamamlanamadı.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <section id="veri" aria-labelledby="veri-title" className="scroll-mt-24 rounded-2xl border border-mist/80 bg-surface px-5 py-5 sm:px-6">
      <h2 id="veri-title" className="text-[15px] font-semibold">
        Veri ve hesap
      </h2>
      <p className="mt-0.5 text-[13px] text-slate">Verilerinizin bir kopyasını indirin veya hesabınızı kapatın.</p>

      <div className="mt-4 space-y-3">
        {error ? <Alert tone="error">{error}</Alert> : null}
        {notice ? <Alert tone="success">{notice}</Alert> : null}
        {closure ? (
          <Alert tone="info">
            Çalışma alanı için kapatma talebi var. Planlanan kapanış: {dayFormat.format(new Date(closure.scheduled_for))}. Bu tarihe kadar her şey çalışmaya devam eder.
          </Alert>
        ) : null}
      </div>

      <ul className="mt-2 divide-y divide-mist/60">
        <Row title="Kişisel verilerim" body="Profiliniz, üyelikleriniz, size atanan görevler, destek talepleriniz ve bildirimleriniz (JSON).">
          <Button variant="quiet" pending={busy === "me"} pendingLabel="Hazırlanıyor" onClick={() => void run("me", downloadPersonalExport, "Kişisel verileriniz indirildi.")}>
            İndir
          </Button>
        </Row>
        {manager ? (
          <Row title="Çalışma alanı verileri" body="Müşteri, ürün, sipariş, teklif, görev, proje, finans, üretim ve etkinlik kayıtları; her tablo ayrı CSV dosyası (ZIP).">
            <Button variant="quiet" pending={busy === "workspace"} pendingLabel="Hazırlanıyor" onClick={() => void run("workspace", downloadWorkspaceExport, "Çalışma alanı verileri indirildi.")}>
              ZIP indir
            </Button>
          </Row>
        ) : null}
        {owner ? (
          <Row
            title="Çalışma alanını kapat"
            body="Talep açıldıktan 30 gün sonra çalışma alanı kapanır ve tüm üyelerin erişimi biter. Bu süre içinde talebi iptal edebilirsiniz."
          >
            {closure ? (
              <Button variant="quiet" pending={busy === "cancel"} pendingLabel="İptal ediliyor" onClick={() => void run("cancel", async () => { await cancelClosure(); setClosure(null); }, "Kapatma talebi iptal edildi.")}>
                Talebi iptal et
              </Button>
            ) : (
              <Button variant="quiet" className="text-error-text" onClick={() => setSheet("workspace")}>
                Kapatma talebi aç
              </Button>
            )}
          </Row>
        ) : (
          <Row title="Hesabımı kapat" body="Hesabınız kapanır ve bu çalışma alanına erişiminiz biter. Girdiğiniz kayıtlar çalışma alanında kalır.">
            <Button variant="quiet" className="text-error-text" onClick={() => setSheet("account")}>
              Hesabı kapat
            </Button>
          </Row>
        )}
      </ul>

      {sheet ? (
        <CloseSheet
          kind={sheet}
          onClose={() => setSheet(null)}
          onDone={async (result) => {
            setSheet(null);
            if (sheet === "account") {
              await navigate("/giris", { replace: true });
              return;
            }
            setClosure(result);
            setNotice("Kapatma talebi açıldı. Sahibi olarak bu bölümden iptal edebilirsiniz.");
          }}
        />
      ) : null}
    </section>
  );
}

function Row({ title, body, children }: { title: string; body: string; children: ReactNode }) {
  return (
    <li className="flex flex-wrap items-center gap-4 py-3.5">
      <span className="min-w-0 flex-1 basis-64">
        <span className="block text-[14px] font-semibold">{title}</span>
        <span className="mt-0.5 block text-[13px] leading-5 text-slate">{body}</span>
      </span>
      {children}
    </li>
  );
}

function CloseSheet({ kind, onClose, onDone }: { kind: "workspace" | "account"; onClose: () => void; onDone: (closure: Closure | null) => Promise<void> }) {
  const [password, setPassword] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const workspace = kind === "workspace";

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!password) {
      setError("Onaylamak için şifrenizi girin.");
      return;
    }
    setPending(true);
    setError("");
    try {
      if (workspace) {
        await onDone(await requestClosure(password, reason));
      } else {
        await closeAccount(password);
        await onDone(null);
      }
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "İşlem tamamlanamadı.");
      setPending(false);
    }
  }

  return (
    <Sheet
      title={workspace ? "Çalışma alanını kapat" : "Hesabımı kapat"}
      busy={pending}
      onClose={onClose}
      onSubmit={(event) => void onSubmit(event)}
      footer={
        <>
          <Button type="button" variant="quiet" onClick={onClose} disabled={pending}>
            Vazgeç
          </Button>
          <Button type="submit" variant="danger" pending={pending} pendingLabel="Gönderiliyor">
            {workspace ? "Kapatma talebi aç" : "Hesabımı kapat"}
          </Button>
        </>
      }
    >
      <div className="space-y-5">
        <Alert tone="info">
          {workspace
            ? "30 gün sonra LUMINOVA ekibi çalışma alanını kapatır; tüm üyelerin oturumu sonlanır ve giriş yapılamaz. Kapanmadan önce verilerinizi ZIP olarak indirmenizi öneririz. Verilerin ne kadar süre saklanacağı yasal saklama sürelerine göre belirlenir."
            : "Hesabınız hemen kapanır, açık oturumlarınız sonlanır ve tekrar giriş yapamazsınız. Girdiğiniz kayıtlar çalışma alanında kalır."}
        </Alert>
        {error ? <Alert tone="error">{error}</Alert> : null}
        {workspace ? <TextArea label="Neden kapatıyorsunuz? (isteğe bağlı)" value={reason} onValue={setReason} maxLength={1000} rows={3} /> : null}
        <PasswordField label="Şifreniz" autoComplete="current-password" value={password} onValue={setPassword} />
      </div>
    </Sheet>
  );
}
