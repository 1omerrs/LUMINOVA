import { useEffect } from "react";
import { Link } from "react-router";
import { HeaderCta, HeaderLink } from "../components/landing/LandingActions.tsx";
import { ScrollStory } from "../components/landing/ScrollStory.tsx";
import { Wordmark } from "../components/ui/Wordmark.tsx";

export function LandingPage() {
  useEffect(() => {
    const previous = document.body.style.background;
    document.body.style.background = "#10131c";
    return () => {
      document.body.style.background = previous;
    };
  }, []);

  return (
    <div className="bg-rail text-white">
      <header className="fixed inset-x-0 top-0 z-20 flex items-center justify-between px-6 py-5 lg:px-10">
        <Wordmark tone="light" className="text-sm" />
        <nav className="flex items-center gap-1.5 sm:gap-2">
          <HeaderLink to="/giris">Giriş</HeaderLink>
          <HeaderCta to="/kayit">Ücretsiz başla</HeaderCta>
        </nav>
      </header>
      <main>
        <ScrollStory />
      </main>
      <footer className="border-t border-white/10 px-6 py-10 lg:px-10">
        <div className="mx-auto flex max-w-6xl flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="font-display text-sm font-semibold tracking-[0.16em]">LUMINOVA</p>
            <p className="mt-3 max-w-md text-sm leading-6 text-[#A6ADBD]">
              Modüler iş yönetimi. Ödeme bu sürümde yoktur.
            </p>
          </div>
          <div className="flex gap-5 text-sm">
            <Link to="/giris">Giriş</Link>
            <Link to="/kayit">Kayıt</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
