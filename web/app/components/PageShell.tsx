"use client";

import { useEffect, useState } from "react";
import { Moon, Sun } from "./icons";
import SiteNav, { Brand } from "./SiteNav";

/** Header + centred content column for the non-chat pages. */
export default function PageShell({ title, lead, children }: { title: string; lead: string; children: React.ReactNode }) {
  const [dark, setDark] = useState(true);
  useEffect(() => setDark(document.documentElement.dataset.theme !== "light"), []);
  const toggle = () => {
    const next = dark ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("fathom-theme", next);
    } catch {}
    setDark(!dark);
  };
  return (
    <div className="min-h-full bg-bg text-fg">
      <header className="sticky top-0 z-20 flex h-14 items-center justify-between gap-3 border-b border-border bg-bg/85 px-4 backdrop-blur">
        <div className="flex items-center gap-4">
          <Brand />
          <SiteNav />
        </div>
        <button onClick={toggle} className="rounded-lg border border-border bg-surface p-2 text-fg-2 hover:bg-surface-2" aria-label="Toggle theme">
          {dark ? <Sun /> : <Moon />}
        </button>
      </header>
      <main className="mx-auto max-w-5xl px-4 pb-24 pt-10">
        <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
        <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-muted">{lead}</p>
        <div className="mt-10 space-y-14">{children}</div>
      </main>
    </div>
  );
}

export function Section({ id, title, children, note }: { id?: string; title: string; children: React.ReactNode; note?: string }) {
  return (
    <section id={id} className="scroll-mt-20">
      <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
      {note && <p className="mt-1 max-w-2xl text-[13px] leading-relaxed text-muted">{note}</p>}
      <div className="mt-4">{children}</div>
    </section>
  );
}

export function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={`rounded-xl border border-border bg-surface p-4 ${className}`}>{children}</div>;
}
