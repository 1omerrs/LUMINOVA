import { Link } from "react-router";

export function Wordmark({ tone = "dark", className = "" }: { tone?: "dark" | "light"; className?: string }) {
  return (
    <Link
      to="/"
      className={`font-display font-semibold tracking-[0.16em] ${tone === "light" ? "text-white" : "text-midnight"} ${className}`}
    >
      LUMINOVA
    </Link>
  );
}
