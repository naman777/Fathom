"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Logo } from "./icons";

const LINKS = [
  { href: "/", label: "Chat" },
  { href: "/architecture", label: "Architecture" },
  { href: "/results", label: "Results" },
];

/** Compact top navigation shared by the chat header and the content pages. */
export default function SiteNav({ compact = false }: { compact?: boolean }) {
  const path = usePathname();
  return (
    <nav className="flex items-center gap-1" aria-label="Primary">
      {LINKS.map((l) => {
        const active = l.href === "/" ? path === "/" : path.startsWith(l.href);
        return (
          <Link
            key={l.href}
            href={l.href}
            aria-current={active ? "page" : undefined}
            className={`rounded-md px-2.5 py-1.5 text-sm font-medium transition-colors duration-200 hover:text-brand ${
              active ? "text-foreground" : "text-muted-foreground"
            } ${compact && l.href === "/" ? "hidden sm:block" : ""}`}
          >
            {l.label}
          </Link>
        );
      })}
    </nav>
  );
}

export function Brand() {
  return (
    <Link href="/" className="flex items-center gap-2.5">
      <Logo />
      <span className="font-onest text-xl font-medium tracking-tight">Fathom</span>
    </Link>
  );
}
