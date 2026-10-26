import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router";
import { Alert, Button } from "../../components/forms/Controls.tsx";
import { Icon } from "../../components/ui/Icon.tsx";
import { ModuleIcon } from "../../components/workspace/ModuleIcon.tsx";
import { DataPanel } from "../../components/workspace/DataPanel.tsx";
import { NotificationPreferencesPanel } from "../../components/workspace/NotificationPreferencesPanel.tsx";
import { TeamPanel } from "../../components/workspace/TeamPanel.tsx";
import { ApiRequestError } from "../../lib/http.ts";
import { requiredBy, saveModules, withRequirements, type ModuleKey } from "../../lib/modules.ts";
import { initials, useWorkspace } from "../../lib/workspace.ts";

const dateFormat = new Intl.DateTimeFormat("tr-TR", { day: "numeric", month: "long", year: "numeric" });
const sections = [
  { id: "hesap", label: "Hesap" },
  { id: "calisma-alani", label: "Çalışma alanı" },
  { id: "ekip", label: "Ekip" },
  { id: "bildirimler", label: "Bildirimler" },
  { id: "moduller", label: "Modüller" },
  { id: "veri", label: "Veri ve hesap" },
  { id: "bize-ulasin", label: "Bize ulaşın" },
  { id: "abonelik", label: "Abonelik" },
];
const roleNames: Record<string, string> = { owner: "Çalışma alanı sahibi", admin: "Yönetici", member: "Üye" };

export function ProfilePage() {
  const { user, modules, replaceModules, refreshFeed } = useWorkspace();
  const location = useLocation();
  const readOnly = user.role === "member";
  const dialog = useRef<HTMLDialogElement>(null);
  const enabled = useMemo(() => new Set(modules.filter((module) => module.enabled).map((module) => module.key)), [modules]);
  const [draft, setDraft] = useState<Set<ModuleKey>>(() => new Set(enabled));
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");

  const effective = useMemo(() => withRequirements(modules, draft), [modules, draft]);
  const added = modules.filter((module) => effective.has(module.key) && !enabled.has(module.key));
  const removed = modules.filter((module) => enabled.has(module.key) && !effective.has(module.key));
  const changed = added.length + removed.length > 0;

  useEffect(() => {
    if (location.hash) {
      document.getElementById(location.hash.slice(1))?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [location.hash]);

  function toggle(key: ModuleKey) {
    setSaved("");
    setError("");
    setDraft((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function reset() {
    setDraft(new Set(enabled));
    setError("");
  }

  async function commit() {
    dialog.current?.close();
    setPending(true);
    setError("");
    try {
      const next = await saveModules([...draft]);
      replaceModules(next);
      setDraft(new Set(next.filter((module) => module.enabled).map((module) => module.key)));
      setSaved("Modül tercihleriniz kaydedildi. Menü güncellendi.");
      await refreshFeed();
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Değişiklikler kaydedilemedi.");
    } finally {
      setPending(false);
    }
  }

  function onSave() {
    if (removed.length > 0) {
      dialog.current?.showModal();
    } else {
      void commit();
    }
  }

  return (
    <div className="space-y-8">
      <section className="flex flex-wrap items-center gap-4">
        <span className="grid h-14 w-14 place-items-center rounded-full bg-graphite text-[18px] font-semibold text-onink">{initials(user)}</span>
        <div>
          <h1 className="font-display text-[22px] font-semibold tracking-[-0.02em] text-midnight sm:text-[24px]">Profil ve ayarlar</h1>
          <p className="mt-0.5 text-[14px] text-slate">Hesabınızı, çalışma alanınızı ve modül tercihlerinizi yönetin.</p>
        </div>
      </section>

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-[180px_minmax(0,1fr)]">
        <nav aria-label="Ayar bölümleri" className="hidden lg:block">
          <ul className="sticky top-24 space-y-0.5">
            {sections.map((section) => (
              <li key={section.id}>
                <a href={`#${section.id}`} className="block rounded-lg px-3 py-2 text-[14px] text-slate transition-colors hover:bg-surface hover:text-graphite">
                  {section.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <div className="min-w-0 space-y-6">
          <Panel id="hesap" title="Hesap" description="Giriş yaptığınız hesabın bilgileri.">
            <dl className="divide-y divide-mist/60">
              <Row label="Ad soyad">
                {user.first_name} {user.last_name}
              </Row>
              <Row label="E-posta">
                <span className="flex flex-wrap items-center gap-2">
                  {user.email}
                  <span className="inline-flex items-center gap-1 rounded-full bg-success/10 px-2 py-0.5 text-[11px] font-semibold text-success-text">
                    <Icon name="check" className="h-3 w-3" strokeWidth={2.4} /> Doğrulandı
                  </span>
                </span>
              </Row>
              <Row label="Üyelik başlangıcı">{dateFormat.format(new Date(user.member_since))}</Row>
              <Row label="Şifre">
                <Link to="/sifremi-unuttum" className="font-medium text-violet hover:underline">
                  Şifre sıfırlama bağlantısı iste
                </Link>
              </Row>
            </dl>
          </Panel>

          <Panel id="calisma-alani" title="Çalışma alanı" description="Verileriniz yalnızca bu çalışma alanının üyelerine görünür.">
            <dl className="divide-y divide-mist/60">
              <Row label="Şirket adı">{user.company_name}</Row>
              <Row label="Çalışma alanı adresi">
                <code className="rounded-md bg-cloud px-1.5 py-0.5 text-[13px]">{user.company_slug}</code>
              </Row>
              <Row label="Saat dilimi">{user.company_timezone === "Europe/Istanbul" ? "İstanbul (UTC+3)" : user.company_timezone}</Row>
              <Row label="Rolünüz">{roleNames[user.role] ?? user.role}</Row>
            </dl>
          </Panel>

          <TeamPanel />

          <NotificationPreferencesPanel />

          <Panel
            id="moduller"
            title="Modüller"
            description="Modül eklediğinizde menüye gelir, kaldırdığınızda erişim kapanır. Kaldırılan modüllerin verileri silinmez."
          >
            <ul className="divide-y divide-mist/60">
              {modules.map((module) => {
                const explicit = draft.has(module.key);
                const auto = !explicit && effective.has(module.key);
                const on = explicit || auto;
                const wasOn = enabled.has(module.key);
                const reason = auto ? requiredBy(modules, draft, module.key).map((item) => item.name).join(", ") : "";
                return (
                  <li key={module.key} className="flex items-center gap-4 py-3.5">
                    <span
                      className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl transition-colors ${
                        on ? "bg-paper text-ink-soft ring-1 ring-inset ring-mist" : "bg-cloud text-slate ring-1 ring-inset ring-mist/70"
                      }`}
                    >
                      <ModuleIcon name={module.key} />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex flex-wrap items-center gap-2">
                        <span className="text-[14px] font-semibold">{module.name}</span>
                        {on !== wasOn ? (
                          <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${on ? "bg-violet/10 text-violet" : "bg-warning/10 text-warning-text"}`}>
                            {on ? "Eklenecek" : "Kaldırılacak"}
                          </span>
                        ) : null}
                      </span>
                      <span id={`module-${module.key}`} className="mt-0.5 block text-[13px] leading-5 text-slate">
                        {auto ? `${reason} için gerekli.` : module.summary}
                      </span>
                    </span>
                    <button
                      type="button"
                      role="switch"
                      aria-checked={on}
                      aria-disabled={auto || readOnly || undefined}
                      aria-label={module.name}
                      aria-describedby={`module-${module.key}`}
                      onClick={() => (auto || readOnly ? undefined : toggle(module.key))}
                      className={`relative h-6 w-11 shrink-0 rounded-full transition-colors duration-200 ${
                        on ? (auto ? "bg-lavender" : "bg-violet") : "bg-[#dcd9d1] hover:bg-stone"
                      } ${auto || readOnly ? "cursor-not-allowed" : ""}`}
                    >
                      <span
                        aria-hidden
                        className={`absolute top-0.5 h-5 w-5 rounded-full bg-surface shadow-[0_1px_3px_rgba(16,19,28,0.25)] transition-[left] duration-200 ${on ? "left-[22px]" : "left-0.5"}`}
                      />
                    </button>
                  </li>
                );
              })}
            </ul>

            {readOnly ? (
              <p className="mt-4 border-t border-mist/60 pt-4 text-[13px] text-slate">Modül tercihlerini çalışma alanı sahibi veya yöneticisi değiştirebilir.</p>
            ) : (
            <div className="mt-4 space-y-3 border-t border-mist/60 pt-4">
              {error ? <Alert tone="error">{error}</Alert> : null}
              {saved && !changed ? <Alert tone="success">{saved}</Alert> : null}
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <p className="text-[13px] text-slate" aria-live="polite">
                  {effective.size === 0
                    ? "En az bir modül açık kalmalı."
                    : changed
                      ? `${added.length} eklenecek, ${removed.length} kaldırılacak.`
                      : `${effective.size} modül açık.`}
                </p>
                <div className="flex gap-2">
                  <Button variant="quiet" onClick={reset} disabled={!changed || pending}>
                    Vazgeç
                  </Button>
                  <Button onClick={onSave} disabled={!changed || effective.size === 0} pending={pending} pendingLabel="Kaydediliyor">
                    Değişiklikleri kaydet
                  </Button>
                </div>
              </div>
            </div>
            )}
          </Panel>

          <DataPanel />

          <Panel id="bize-ulasin" title="Bize ulaşın" description="Bir sorun, şikâyet veya öneriniz mi var? LUMINOVA ekibine buradan yazın; yanıtımız bildirimlerinize düşer.">
            <div className="grid gap-3 sm:grid-cols-3">
              {(
                [
                  { kind: "bug", title: "Sorun bildir", body: "Bir ekran çalışmıyor veya hata veriyor." },
                  { kind: "complaint", title: "Şikâyet ilet", body: "Memnun kalmadığınız bir durumu anlatın." },
                  { kind: "request", title: "Öneri gönder", body: "Eksik bulduğunuz bir özelliği isteyin." },
                ] as const
              ).map((item) => (
                <Link
                  key={item.kind}
                  to={`/panel/destek?yeni=1&tur=${item.kind}`}
                  className="rounded-xl border border-mist/80 px-4 py-3 transition-colors hover:border-violet/50 hover:bg-violet/[0.03]"
                >
                  <span className="block text-[14px] font-semibold">{item.title}</span>
                  <span className="mt-0.5 block text-[12.5px] leading-5 text-slate">{item.body}</span>
                </Link>
              ))}
            </div>
            <p className="mt-3 text-[12.5px] text-slate">
              Önceki konuşmalarınız{" "}
              <Link to="/panel/destek" className="font-semibold text-violet hover:underline">
                Destek
              </Link>{" "}
              sayfasında.
            </p>
          </Panel>

          <Panel id="abonelik" title="Abonelik" description="Plan ve faturalandırma bilgileri.">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <p className="flex items-center gap-2 text-[14px] font-semibold">
                  Erken erişim
                  <span className="rounded-full bg-cloud px-2 py-0.5 text-[11px] font-semibold text-slate">Ücretsiz</span>
                </p>
                <p className="mt-1 max-w-md text-[13px] leading-5 text-slate">
                  Bu sürümde ödeme alınmaz ve kart bilgisi istenmez. Planlar hazır olduğunda yönetimi bu bölümden yapılacak.
                </p>
              </div>
            </div>
          </Panel>
        </div>
      </div>

      <dialog
        ref={dialog}
        aria-labelledby="remove-title"
        className="m-auto w-[min(440px,calc(100vw-32px))] rounded-2xl border border-mist/80 bg-surface p-0 text-graphite shadow-[0_32px_64px_-24px_rgba(32,36,50,0.45)] backdrop:bg-graphite/40 backdrop:backdrop-blur-[2px]"
      >
        <div className="p-6">
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-warning/10 text-warning-text">
            <Icon name="alert" />
          </span>
          <h2 id="remove-title" className="mt-4 text-[17px] font-semibold">
            {removed.length === 1 ? "Modül kaldırılsın mı?" : `${removed.length} modül kaldırılsın mı?`}
          </h2>
          <ul className="mt-3 space-y-1.5">
            {removed.map((module) => (
              <li key={module.key} className="flex items-center gap-2 text-[14px]">
                <ModuleIcon name={module.key} className="h-4 w-4 text-slate" />
                {module.name}
              </li>
            ))}
          </ul>
          <p className="mt-4 text-[13px] leading-5 text-slate">
            {removed.length === 1 ? "Bu modüle" : "Bu modüllere"} erişim kapanır ve menüden kalkar. Girilmiş veriler silinmez; yeniden eklediğinizde kaldığınız yerden devam edersiniz.
          </p>
        </div>
        <div className="flex justify-end gap-2 border-t border-mist/70 bg-cloud/60 px-6 py-4">
          <Button variant="quiet" autoFocus onClick={() => dialog.current?.close()}>
            Vazgeç
          </Button>
          <Button variant="dark" onClick={() => void commit()}>
            Kaldır ve kaydet
          </Button>
        </div>
      </dialog>
    </div>
  );
}

function Panel({ id, title, description, children }: { id: string; title: string; description: string; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="scroll-mt-24 rounded-2xl border border-mist/80 bg-surface px-5 py-5 sm:px-6">
      <h2 id={`${id}-title`} className="text-[15px] font-semibold">
        {title}
      </h2>
      <p className="mt-0.5 text-[13px] text-slate">{description}</p>
      <div className="mt-4">{children}</div>
    </section>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid gap-1 py-3 sm:grid-cols-[180px_minmax(0,1fr)] sm:gap-4">
      <dt className="text-[13px] text-slate">{label}</dt>
      <dd className="text-[14px]">{children}</dd>
    </div>
  );
}
