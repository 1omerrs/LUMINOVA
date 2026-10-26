import { useCallback, useRef, useState } from "react";
import { Link } from "react-router";
import type { CurrentUser } from "../../lib/auth.ts";
import { useTheme, type ThemeChoice } from "../../lib/theme.ts";
import { useDismiss } from "../../lib/useDismiss.ts";
import { initials } from "../../lib/workspace.ts";
import { Icon } from "../ui/Icon.tsx";

const themeOptions: { value: ThemeChoice; label: string }[] = [
  { value: "light", label: "Açık" },
  { value: "dark", label: "Koyu" },
  { value: "system", label: "Sistem" },
];

export function ProfileMenu({ user, onLogout }: { user: CurrentUser; onLogout: () => Promise<void> }) {
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const [theme, setTheme] = useTheme();
  const close = useCallback(() => setOpen(false), []);
  useDismiss(open, close, root, trigger);

  async function logout() {
    setLeaving(true);
    try {
      await onLogout();
    } finally {
      setLeaving(false);
    }
  }

  const item = "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-[14px] text-graphite transition-colors hover:bg-cloud";

  return (
    <div ref={root} className="relative">
      <button
        ref={trigger}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Hesap menüsü, ${user.first_name} ${user.last_name}`}
        onClick={() => setOpen((current) => !current)}
        className={`flex items-center gap-2.5 rounded-xl py-1.5 pl-1.5 pr-2 transition-colors hover:bg-cloud ${open ? "bg-cloud" : ""}`}
      >
        <span className="grid h-8 w-8 place-items-center rounded-full bg-graphite text-[12px] font-semibold text-onink">{initials(user)}</span>
        <span className="hidden text-left sm:block">
          <span className="block max-w-[160px] truncate text-[13px] font-semibold leading-4">
            {user.first_name} {user.last_name}
          </span>
          <span className="block max-w-[160px] truncate text-[12px] leading-4 text-slate">{user.company_name}</span>
        </span>
        <Icon name="chevron-down" className={`hidden h-4 w-4 text-slate transition-transform sm:block ${open ? "rotate-180" : ""}`} />
      </button>

      {open ? (
        <div
          role="menu"
          aria-label="Hesap"
          className="absolute right-0 top-12 z-40 w-64 origin-top-right animate-[pop_160ms_ease-out] rounded-2xl border border-mist/80 bg-surface p-1.5 shadow-[0_24px_48px_-24px_rgba(32,36,50,0.35)]"
        >
          <div className="px-3 py-2.5">
            <p className="truncate text-[14px] font-semibold">
              {user.first_name} {user.last_name}
            </p>
            <p className="truncate text-[12px] text-slate">{user.email}</p>
          </div>
          <div className="my-1 h-px bg-mist/70" />
          <div className="px-3 py-2">
            <p id="theme-label" className="text-[12px] text-slate">
              Görünüm
            </p>
            <div role="radiogroup" aria-labelledby="theme-label" className="mt-1.5 grid grid-cols-3 gap-1 rounded-lg bg-cloud p-1">
              {themeOptions.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  role="radio"
                  aria-checked={theme === option.value}
                  onClick={() => setTheme(option.value)}
                  className={`h-7 rounded-md text-[12.5px] font-semibold transition-colors ${
                    theme === option.value ? "bg-surface text-graphite shadow-[0_1px_2px_rgba(16,19,28,0.12)]" : "text-slate hover:text-graphite"
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>
          <div className="my-1 h-px bg-mist/70" />
          <Link role="menuitem" to="/panel/profil" onClick={close} className={item}>
            <Icon name="user" className="h-[18px] w-[18px] text-slate" />
            Profil ve ayarlar
          </Link>
          <Link role="menuitem" to="/panel/profil#moduller" onClick={close} className={item}>
            <Icon name="settings" className="h-[18px] w-[18px] text-slate" />
            Modül tercihleri
          </Link>
          {user.is_platform_admin ? (
            <Link role="menuitem" to="/yonetim" onClick={close} className={item}>
              <Icon name="shield" className="h-[18px] w-[18px] text-slate" />
              Yönetim paneli
            </Link>
          ) : null}
          <div className="my-1 h-px bg-mist/70" />
          <button role="menuitem" type="button" disabled={leaving} onClick={() => void logout()} className={`${item} text-error-text hover:bg-error/[0.06] disabled:opacity-60`}>
            <Icon name="logout" className="h-[18px] w-[18px]" />
            {leaving ? "Çıkış yapılıyor" : "Çıkış yap"}
          </button>
        </div>
      ) : null}
    </div>
  );
}
