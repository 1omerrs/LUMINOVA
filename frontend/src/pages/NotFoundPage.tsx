import { Link } from "react-router";

export function NotFoundPage() {
  return (
    <main className="grid min-h-screen place-items-center bg-cloud px-6 text-midnight">
      <div>
        <p className="font-display text-sm font-semibold tracking-[0.16em]">LUMINOVA</p>
        <h1 className="mt-4 font-display text-4xl font-semibold">Sayfa bulunamadı.</h1>
        <Link to="/" className="mt-6 inline-flex h-11 items-center bg-midnight px-4 text-sm font-medium text-onink">
          Tanıtım sayfasına dön
        </Link>
      </div>
    </main>
  );
}
