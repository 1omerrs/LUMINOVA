import type { ReactNode } from "react";
import { Link } from "react-router";

function Arrow({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden className={`h-3.5 w-3.5 ${className}`}>
      <path d="M3 8h9.5M8.5 3.5 13 8l-4.5 4.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function PrimaryLink({ to, children, className = "" }: { to: string; children: ReactNode; className?: string }) {
  return (
    <Link
      to={to}
      className={`group relative inline-flex h-12 items-center gap-3 overflow-hidden rounded-full bg-[linear-gradient(135deg,#8E70FF_0%,#7C5CFC_45%,#6544EE_100%)] pl-6 pr-1.5 text-[15px] font-semibold tracking-[-0.01em] text-white shadow-[0_12px_32px_-12px_rgba(124,92,252,0.9),inset_0_1px_0_rgba(255,255,255,0.28)] ring-1 ring-inset ring-white/15 transition-[box-shadow,filter,transform] duration-300 hover:shadow-[0_16px_44px_-12px_rgba(124,92,252,1),inset_0_1px_0_rgba(255,255,255,0.34)] hover:brightness-110 active:scale-[0.98] ${className}`}
    >
      <span
        aria-hidden
        className="pointer-events-none absolute inset-y-0 -left-1/2 w-1/2 -skew-x-12 bg-[linear-gradient(90deg,transparent,rgba(255,255,255,0.28),transparent)] opacity-0 transition-[transform,opacity] duration-700 group-hover:translate-x-[320%] group-hover:opacity-100"
      />
      <span className="relative">{children}</span>
      <span className="relative grid h-9 w-9 place-items-center rounded-full bg-white/15 ring-1 ring-inset ring-white/20 transition-colors duration-300 group-hover:bg-white/25">
        <Arrow className="transition-transform duration-300 group-hover:translate-x-0.5" />
      </span>
    </Link>
  );
}

export function GhostButton({ onClick, children }: { onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group inline-flex h-12 items-center gap-3 rounded-full border border-white/15 bg-white/[0.04] pl-1.5 pr-6 text-[15px] font-medium tracking-[-0.01em] text-white backdrop-blur-md transition-colors duration-300 hover:border-white/30 hover:bg-white/[0.08] active:bg-white/[0.06]"
    >
      <span className="grid h-9 w-9 place-items-center rounded-full border border-white/20 bg-white/[0.06] transition-colors duration-300 group-hover:border-[#A78BFA]/60 group-hover:bg-[#7C5CFC]/20">
        <svg viewBox="0 0 16 16" aria-hidden className="ml-0.5 h-3 w-3 text-[#A78BFA]">
          <path d="M4.5 3.2v9.6c0 .5.55.8.97.53l7.2-4.8a.63.63 0 0 0 0-1.06l-7.2-4.8a.63.63 0 0 0-.97.53Z" fill="currentColor" />
        </svg>
      </span>
      {children}
    </button>
  );
}

export function HeaderLink({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link
      to={to}
      className="inline-flex h-9 items-center rounded-full px-4 text-sm font-medium text-[#A6ADBD] transition-colors duration-200 hover:bg-white/[0.07] hover:text-white"
    >
      {children}
    </Link>
  );
}

export function HeaderCta({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link
      to={to}
      className="group inline-flex h-9 items-center gap-2 rounded-full bg-surface pl-4 pr-3.5 text-sm font-semibold text-midnight shadow-[0_8px_24px_-10px_rgba(167,139,250,0.7)] ring-1 ring-inset ring-black/5 transition-[background-color,box-shadow] duration-200 hover:bg-[#F6F7FB] hover:shadow-[0_10px_30px_-10px_rgba(167,139,250,0.95)]"
    >
      {children}
      <Arrow className="text-violet transition-transform duration-200 group-hover:translate-x-0.5" />
    </Link>
  );
}
