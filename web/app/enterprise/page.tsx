"use client";

import { useEffect, useRef, useState } from "react";
import { Backdrop } from "@/components/backdrop";
import { ThemeSwitcher } from "@/components/theme-switcher";
import { Alert as Notice } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Kbd } from "@/components/ui/kbd";
import { Segmented } from "@/components/ui/segmented";
import Assistant from "../components/Assistant";
import { streamChat } from "../components/chatStream";
import { Send, Stop } from "../components/icons";
import SiteNav, { Brand } from "../components/SiteNav";
import SourcesPanel, { type PanelState } from "../components/SourcesPanel";
import type { EnterpriseInfo, Msg } from "../components/types";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const ROLE_KEY = "fathom-enterprise-role";

const citedOf = (m: Msg) =>
  Array.from(new Set((m.content.match(/\[(\d+)\]/g) || []).map((x) => Number(x.slice(1, -1))))).filter((n) => (m.sources || []).some((s) => s.n === n));

/**
 * Enterprise search: one company's Slack, email, tickets, wiki and CRM, searched as a chosen role.
 * There is no login. The role is sent as a header and the server decides what that role may read.
 */
export default function Enterprise() {
  const [info, setInfo] = useState<EnterpriseInfo | null>(null);
  const [failed, setFailed] = useState(false);
  const [role, setRole] = useState("");
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [panel, setPanel] = useState<PanelState | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const abort = useRef<AbortController | null>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    fetch(`${API}/api/enterprise/roles`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((j: EnterpriseInfo) => {
        setInfo(j);
        let saved = "";
        try {
          saved = localStorage.getItem(ROLE_KEY) || "";
        } catch {}
        setRole(j.roles.some((r) => r.id === saved) ? saved : j.default);
      })
      .catch(() => setFailed(true));
  }, []);

  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [msgs]);

  useEffect(() => {
    const ta = taRef.current;
    if (ta) {
      ta.style.height = "0px";
      ta.style.height = Math.min(ta.scrollHeight, 180) + "px";
    }
  }, [input]);

  // Switching role starts a new conversation: earlier answers may contain text the new role is not allowed to read,
  // and they would otherwise be sent back to the model as chat history.
  const switchRole = (next: string) => {
    if (next === role) return;
    abort.current?.abort();
    setMsgs([]);
    setPanel(null);
    setRole(next);
    try {
      localStorage.setItem(ROLE_KEY, next);
    } catch {}
  };

  const patchLast = (fn: (m: Msg) => Msg) => setMsgs((ms) => ms.map((m, i) => (i === ms.length - 1 ? fn(m) : m)));
  const current = info?.roles.find((r) => r.id === role);

  async function send(text: string) {
    text = text.trim();
    if (!text || busy || !role) return;
    const history = msgs.filter((m) => !m.error && m.content).map((m) => ({ role: m.role, content: m.content }));
    setMsgs((ms) => [...ms, { role: "user", content: text }, { role: "assistant", content: "", trace: [], streaming: true, asRole: current?.label }]);
    setInput("");
    setBusy(true);
    const ctrl = new AbortController();
    abort.current = ctrl;
    try {
      await streamChat(`${API}/api/enterprise/chat`, { question: text, history, agent: true, rerank: true }, patchLast, ctrl.signal, { "X-Demo-Role": role });
    } catch (e: any) {
      if (e?.name !== "AbortError") patchLast((m) => ({ ...m, streaming: false, error: { message: e.message || "Request failed" } }));
    } finally {
      patchLast((m) => ({ ...m, streaming: false }));
      setBusy(false);
      abort.current = null;
    }
  }

  const canRead = (groups: string[]) => !current || current.groups === null || groups.some((g) => current.groups!.includes(g));
  const ready = !!info?.index.ready && info.index.chunks > 0;

  return (
    <div className="flex h-full bg-background text-foreground">
      <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <Backdrop />
        <header className="flex h-14 shrink-0 items-center justify-between gap-2 border-b border-border px-4">
          <div className="flex min-w-0 items-center gap-3 sm:gap-5">
            <Brand />
            <SiteNav compact />
          </div>
          <ThemeSwitcher />
        </header>

        {/* Role bar */}
        <div className="border-b border-border px-4 py-3">
          <div className="mx-auto flex max-w-3xl flex-col gap-2">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
              <span className="text-xs font-medium text-muted-foreground">Asking as</span>
              {info ? (
                <Segmented label="Role" value={role} onChange={switchRole} options={info.roles.map((r) => ({ value: r.id, label: r.label }))} />
              ) : (
                <span className="text-xs text-muted-foreground">{failed ? "unavailable" : "loading…"}</span>
              )}
            </div>
            {info && current && (
              <p className="flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
                Can read:
                {info.groups.map((g) => {
                  const ok = current.groups === null || current.groups.includes(g);
                  return (
                    <span
                      key={g}
                      className={`rounded-full border px-2 py-0.5 ${ok ? "border-success/40 text-success" : "border-border text-muted-foreground line-through opacity-60"}`}
                      title={ok ? `${current.label} can read documents in "${g}"` : `${current.label} cannot read documents in "${g}"`}
                    >
                      {g}
                    </span>
                  );
                })}
                <span className="ml-1">
                  · {info.index.chunks.toLocaleString()} passages indexed
                  {/* The full corpus is about 2.65M passages; anything well below that is a sample of it. */}
                  {info.index.chunks > 0 && info.index.chunks < 2_000_000 && " (a sample of the 512k-document corpus)"}
                </span>
              </p>
            )}
          </div>
        </div>

        {failed && (
          <Notice tone="warning" className="mx-4 mt-3 bg-background/60 py-2 text-xs backdrop-blur-sm">
            Can&apos;t reach the API. Is the backend running?
          </Notice>
        )}
        {info && !ready && (
          <Notice tone="warning" className="mx-4 mt-3 bg-background/60 py-2 text-xs backdrop-blur-sm">
            The enterprise index is not loaded on this server, so questions here will not return results.
          </Notice>
        )}

        <div ref={scroller} className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-3xl space-y-7 px-4 py-8">
            {msgs.length === 0 && (
              <div className="fade-up pt-[4vh] text-center">
                <h1 className="text-2xl font-medium sm:text-3xl">Search the company&apos;s knowledge</h1>
                <p className="mx-auto mt-3 max-w-xl text-base text-neutral-700 dark:text-neutral-400">
                  Slack, email, tickets, wiki pages, CRM records and call transcripts from one simulated company. Pick a role above:{" "}
                  <span className="highlight">each role only finds what it is allowed to read</span>.
                </p>
                <p className="mx-auto mt-2 max-w-xl text-xs text-muted-foreground">
                  No login here. The role is a demo identity, and the access check runs on the server inside the search itself.
                </p>
                <div className="mx-auto mt-7 grid max-w-xl gap-2.5">
                  {(info?.examples || []).map((ex) => {
                    const ok = canRead(ex.groups);
                    return (
                      <button key={ex.question} onClick={() => send(ex.question)} disabled={busy || !ready} className="card-chai px-4 py-3 text-left text-sm text-fg-2 hover:text-foreground disabled:opacity-60">
                        <span className="block">{ex.question}</span>
                        <span className={`mt-1.5 block text-[11px] ${ok ? "text-success" : "text-warning"}`}>
                          {ex.source} · needs {ex.groups.join(" or ")} · {ok ? `${current?.label} can read this` : `${current?.label} should not find this`}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
            {msgs.map((m, i) =>
              m.role === "user" ? (
                <div key={i} className="fade-up flex justify-end">
                  <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-secondary px-4 py-2.5 text-sm leading-relaxed text-secondary-foreground">{m.content}</div>
                </div>
              ) : (
                <div key={i} className="space-y-1.5">
                  {m.asRole && <div className="pl-10 text-[11px] text-muted-foreground">Answered as {m.asRole}</div>}
                  <Assistant
                    m={m}
                    onCite={(s) => setPanel({ sources: m.sources || [], cited: citedOf(m), focus: s.n })}
                    onOpenSources={() => setPanel({ sources: m.sources || [], cited: citedOf(m) })}
                  />
                </div>
              )
            )}
          </div>
        </div>

        <div className="px-4 pb-4 pt-2">
          <form
            className="mx-auto max-w-3xl"
            onSubmit={(e) => {
              e.preventDefault();
              send(input);
            }}
          >
            <div className="flex items-end gap-2 rounded-2xl border border-card-edge bg-background/60 p-2 backdrop-blur-sm transition-colors duration-300 focus-within:border-card-edge-hover">
              <textarea
                ref={taRef}
                rows={1}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    send(input);
                  }
                }}
                maxLength={1000}
                placeholder={current ? `Ask as ${current.label}…` : "Ask a question…"}
                aria-label="Question"
                className="max-h-[180px] flex-1 resize-none bg-transparent px-2.5 py-2 text-sm text-foreground outline-none placeholder:text-muted-foreground"
              />
              {busy ? (
                <Button type="button" variant="ghost" size="icon" onClick={() => abort.current?.abort()} aria-label="Stop generating" className="bg-surface-3">
                  <Stop width={14} height={14} />
                </Button>
              ) : (
                <Button type="submit" size="icon" disabled={!input.trim() || !role} aria-label="Send">
                  <Send />
                </Button>
              )}
            </div>
            <p className="mt-2 flex flex-wrap items-center justify-center gap-x-1.5 gap-y-1 text-center text-[11px] text-muted-foreground">
              <Kbd>Enter</Kbd> to send · Switching role starts a new conversation · Answers may contain errors, so check the sources.
            </p>
          </form>
        </div>
      </main>

      {panel && <SourcesPanel panel={panel} onClose={() => setPanel(null)} canDownload={() => false} onDownload={() => {}} />}
    </div>
  );
}
