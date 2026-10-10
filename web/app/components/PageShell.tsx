"use client";

import { useEffect, useState } from "react";
import { Backdrop } from "@/components/backdrop";
import { ThemeSwitcher } from "@/components/theme-switcher";
import SiteNav, { Brand } from "./SiteNav";

/** Backdrop, sticky header and the centred max-w-6xl column for the non-chat pages. */
export default function PageShell({ title, lead, children }: { title: string; lead: React.ReactNode; children: React.ReactNode }) {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 0);
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);
  return (
    <div className="min-h-full">
      <Backdrop />
      <header className={`sticky top-0 z-20 transition-[backdrop-filter,background] duration-300 ${scrolled ? "bg-background/60 backdrop-blur-md" : "bg-transparent"}`}>
        <nav className="flex items-center justify-between gap-5 px-6 py-5 sm:px-12" aria-label="Site">
          <div className="flex items-center gap-4 sm:gap-6">
            <Brand />
            <SiteNav compact />
          </div>
          <ThemeSwitcher />
        </nav>
      </header>
      <main className="mx-auto max-w-6xl p-6 pb-24 sm:p-12 sm:pb-24">
        <h1 className="text-2xl font-medium sm:text-center sm:text-3xl">{title}</h1>
        <p className="mx-auto mt-3 max-w-3xl text-base text-neutral-700 sm:text-center md:text-lg dark:text-neutral-400">{lead}</p>
        <div className="mt-12 space-y-16 sm:space-y-20">{children}</div>
      </main>
    </div>
  );
}

export function Section({ id, title, children, note }: { id?: string; title: string; children: React.ReactNode; note?: string }) {
  return (
    <section id={id} className="scroll-mt-24">
      <h2 className="text-2xl font-medium sm:text-[30px]">{title}</h2>
      {note && <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted-foreground sm:text-base">{note}</p>}
      <div className="mt-5">{children}</div>
    </section>
  );
}

export function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={`card-chai p-4 ${className}`}>{children}</div>;
}
