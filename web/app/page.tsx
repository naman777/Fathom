"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Assistant from "./components/Assistant";
import { Check, Close, Download, File, Logo, Menu, Moon, Plus, Send, Sparkle, Stop, Sun, Trash, Upload } from "./components/icons";
import SourcesPanel, { type PanelState } from "./components/SourcesPanel";
import type { Conv, Doc, Msg } from "./components/types";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const uid = () => Math.random().toString(36).slice(2, 10);
const CONVS_KEY = "fathom-convs";

type Job = { id: string; name: string; pct: number; stage: "queued" | "uploading" | "indexing" | "done" | "error"; msg?: string };
const ALLOWED = [".txt", ".md", ".pdf"];

export default function Home() {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [convs, setConvs] = useState<Conv[]>([]);
  const [convId, setConvId] = useState<string>(uid());
  const [convsLoaded, setConvsLoaded] = useState(false);
  const [tab, setTab] = useState<"chats" | "docs">("docs");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [confirmId, setConfirmId] = useState<number | null>(null);
  const [busyDocs, setBusyDocs] = useState<Record<number, "deleting" | "downloading">>({});
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [docs, setDocs] = useState<Doc[]>([]);
  const [docsLoaded, setDocsLoaded] = useState(false);
  const [agent, setAgent] = useState(true);
  const [rerank, setRerank] = useState(true);
  const [panel, setPanel] = useState<PanelState | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [dark, setDark] = useState(true);
  const [sidebar, setSidebar] = useState(false);
  const [dragging, setDragging] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);
  const abort = useRef<AbortController | null>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    setDark(document.documentElement.dataset.theme !== "light");
  }, []);
  const toggleTheme = () => {
    const next = dark ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("fathom-theme", next);
    } catch {}
    setDark(!dark);
  };

  const loadDocs = useCallback(async () => {
    try {
      setDocs(await (await fetch(`${API}/api/documents`)).json());
    } catch {
      setNotice("Can't reach the API. Is the backend running?");
    } finally {
      setDocsLoaded(true);
    }
  }, []);
  useEffect(() => {
    loadDocs();
  }, [loadDocs]);

  // keep pinned to the bottom while streaming
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

  // Chat history lives in this browser only (localStorage).
  useEffect(() => {
    try {
      setConvs(JSON.parse(localStorage.getItem(CONVS_KEY) || "[]"));
    } catch {}
    setConvsLoaded(true);
  }, []);
  useEffect(() => {
    if (!convsLoaded || busy || msgs.length === 0) return;
    const title = (msgs.find((m) => m.role === "user")?.content || "New chat").slice(0, 48);
    setConvs((cs) => {
      const next = [{ id: convId, title, msgs, updated: Date.now() }, ...cs.filter((c) => c.id !== convId)].slice(0, 30);
      try {
        localStorage.setItem(CONVS_KEY, JSON.stringify(next));
      } catch {}
      return next;
    });
  }, [msgs, busy, convId, convsLoaded]);

  const newChat = () => {
    abort.current?.abort();
    setMsgs([]);
    setConvId(uid());
    setSidebar(false);
  };
  const openConv = (c: Conv) => {
    abort.current?.abort();
    setMsgs(c.msgs.map((m) => ({ ...m, streaming: false })));
    setConvId(c.id);
    setSidebar(false);
  };
  const deleteConv = (id: string) => {
    setConvs((cs) => {
      const next = cs.filter((c) => c.id !== id);
      try {
        localStorage.setItem(CONVS_KEY, JSON.stringify(next));
      } catch {}
      return next;
    });
    if (id === convId) {
      setMsgs([]);
      setConvId(uid());
    }
  };

  const patchLast = (fn: (m: Msg) => Msg) => setMsgs((ms) => ms.map((m, i) => (i === ms.length - 1 ? fn(m) : m)));

  async function send(text: string) {
    text = text.trim();
    if (!text || busy) return;
    const history = msgs.filter((m) => !m.error && m.content).map((m) => ({ role: m.role, content: m.content }));
    setMsgs((ms) => [...ms, { role: "user", content: text }, { role: "assistant", content: "", trace: [], streaming: true }]);
    setInput("");
    setBusy(true);
    const ctrl = new AbortController();
    abort.current = ctrl;
    try {
      const res = await fetch(`${API}/api/chat`, {
        method: "POST",
        signal: ctrl.signal,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: text, history, agent, rerank }),
      });
      if (!res.ok) {
        let detail = `Request failed (${res.status})`;
        let retry: number | undefined;
        try {
          const j = await res.json();
          detail = typeof j.detail === "string" ? j.detail : detail;
          retry = j.retry_after;
        } catch {}
        patchLast((m) => ({ ...m, streaming: false, error: { message: detail, retryAfter: retry } }));
        return;
      }
      if (!res.body) throw new Error("No response stream");
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let idx;
        while ((idx = buf.indexOf("\n\n")) >= 0) {
          const block = buf.slice(0, idx);
          buf = buf.slice(idx + 2);
          const ev = /^event: (.*)$/m.exec(block)?.[1];
          const dataLine = /^data: (.*)$/m.exec(block)?.[1];
          if (!ev || dataLine === undefined) continue;
          const data = JSON.parse(dataLine);
          if (ev === "trace")
            patchLast((m) => ({ ...m, trace: [...(m.trace || []), data], sources: data.type === "sources" ? data.chunks : m.sources }));
          else if (ev === "retrieval_done") patchLast((m) => ({ ...m, timing: { ...m.timing, retrieval: data.ms } }));
          else if (ev === "first_token") patchLast((m) => ({ ...m, timing: { ...m.timing, first: data.ms } }));
          else if (ev === "token") patchLast((m) => ({ ...m, content: m.content + data }));
          else if (ev === "done") patchLast((m) => ({ ...m, streaming: false, timing: { ...m.timing, total: data.ms } }));
          else if (ev === "error") patchLast((m) => ({ ...m, streaming: false, error: { message: String(data) } }));
        }
      }
    } catch (e: any) {
      if (e?.name !== "AbortError") patchLast((m) => ({ ...m, streaming: false, error: { message: e.message || "Request failed" } }));
    } finally {
      patchLast((m) => ({ ...m, streaming: false }));
      setBusy(false);
      abort.current = null;
    }
  }

  const patchJob = (id: string, p: Partial<Job>) => setJobs((js) => js.map((j) => (j.id === id ? { ...j, ...p } : j)));

  function sendFile(f: File, id: string): Promise<void> {
    return new Promise((resolve) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${API}/api/documents`);
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) patchJob(id, { stage: "uploading", pct: Math.round((e.loaded / e.total) * 100) });
      };
      xhr.upload.onload = () => patchJob(id, { stage: "indexing", pct: 100 });
      xhr.onload = () => {
        let body: any = {};
        try {
          body = JSON.parse(xhr.responseText);
        } catch {}
        if (xhr.status >= 200 && xhr.status < 300) {
          patchJob(id, { stage: "done", msg: body.chunks ? `${body.chunks} passages indexed` : "Added" });
          loadDocs();
          setTimeout(() => setJobs((js) => js.filter((j) => j.id !== id)), 4000);
        } else {
          const msg = xhr.status === 429 ? "Too many uploads — try again later" : body.detail || `Upload failed (${xhr.status})`;
          patchJob(id, { stage: "error", msg: String(msg) });
        }
        resolve();
      };
      xhr.onerror = () => {
        patchJob(id, { stage: "error", msg: "Network error — is the server reachable?" });
        resolve();
      };
      const fd = new FormData();
      fd.append("file", f);
      xhr.send(fd);
    });
  }

  const uploading = jobs.some((j) => j.stage === "queued" || j.stage === "uploading" || j.stage === "indexing");
  const queue = useRef<Promise<void>>(Promise.resolve());

  function upload(files: FileList | File[] | null) {
    if (!files || !files.length) return;
    setTab("docs");
    for (const f of Array.from(files)) {
      const id = uid();
      const ok = ALLOWED.some((ext) => f.name.toLowerCase().endsWith(ext));
      setJobs((js) => [...js, { id, name: f.name, pct: 0, stage: ok ? "queued" : "error", msg: ok ? undefined : "Only .txt, .md and .pdf files are supported" }]);
      if (ok) queue.current = queue.current.then(() => (patchJob(id, { stage: "uploading" }), sendFile(f, id)));
    }
  }

  async function removeDoc(id: number) {
    setConfirmId(null);
    setBusyDocs((b) => ({ ...b, [id]: "deleting" }));
    try {
      const r = await fetch(`${API}/api/documents/${id}`, { method: "DELETE" });
      if (!r.ok) setNotice((await r.json().catch(() => ({}))).detail || "Delete failed");
    } catch {
      setNotice("Delete failed — is the server reachable?");
    }
    await loadDocs();
    setBusyDocs((b) => {
      const { [id]: _, ...rest } = b;
      return rest;
    });
  }

  async function downloadDoc(id: number) {
    setBusyDocs((b) => ({ ...b, [id]: "downloading" }));
    try {
      const r = await fetch(`${API}/api/documents/${id}/download`);
      if (!r.ok) setNotice((await r.json().catch(() => ({}))).detail || "Download failed");
      else window.open((await r.json()).url, "_blank", "noopener");
    } catch {
      setNotice("Download failed — is the server reachable?");
    }
    setBusyDocs((b) => {
      const { [id]: _, ...rest } = b;
      return rest;
    });
  }

  const totalChunks = docs.reduce((a, d) => a + d.chunks, 0);
  const suggestions =
    docs.length > 0
      ? [
          `Summarize the key facts about ${docs[0].title}`,
          docs.length > 1 ? `Compare ${docs[0].title} with ${docs[1].title}` : `What are the most important numbers in ${docs[0].title}?`,
          docs.length > 2 ? `What are the main risks or incidents mentioned in ${docs[2].title}?` : "List the people named across the documents",
        ]
      : [];

  return (
    <div className="flex h-full bg-bg text-fg">
      {/* Sidebar */}
      {sidebar && <div className="fixed inset-0 z-20 bg-black/50 md:hidden" onClick={() => setSidebar(false)} />}
      <aside
        className={`fixed inset-y-0 left-0 z-30 flex w-[288px] shrink-0 flex-col border-r border-border bg-surface transition-transform md:static md:translate-x-0 ${
          sidebar ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex items-center gap-2.5 px-4 pb-3 pt-4">
          <Logo />
          <div className="leading-tight">
            <div className="text-[15px] font-semibold tracking-tight">Fathom</div>
            <div className="text-[11px] text-muted">Document intelligence</div>
          </div>
        </div>

        <div className="px-3">
          <button
            onClick={newChat}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-accent-strong px-3 py-2 text-sm font-medium text-white shadow-sm transition hover:brightness-110"
          >
            <Plus /> New chat
          </button>
        </div>

        <div className="mx-3 mt-4 grid grid-cols-2 gap-1 rounded-lg bg-surface-2 p-1 text-xs font-medium">
          {(["docs", "chats"] as const).map((t) => (
            <button key={t} onClick={() => setTab(t)} className={`rounded-md py-1.5 transition ${tab === t ? "bg-surface text-fg shadow-sm" : "text-muted hover:text-fg-2"}`}>
              {t === "docs" ? `Documents (${docs.length})` : `History (${convs.length})`}
            </button>
          ))}
        </div>

        {tab === "chats" && (
          <ul className="mt-3 flex-1 space-y-0.5 overflow-y-auto px-2 pb-2">
            {convs.length === 0 && <li className="px-3 py-6 text-center text-xs text-muted">No saved chats yet.</li>}
            {convs.map((c) => (
              <li key={c.id} className={`group flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm hover:bg-surface-2 ${c.id === convId ? "bg-surface-2" : ""}`}>
                <button onClick={() => openConv(c)} className="min-w-0 flex-1 text-left">
                  <div className="truncate text-fg-2">{c.title}</div>
                  <div className="text-[11px] text-muted">{new Date(c.updated).toLocaleDateString()} · {Math.ceil(c.msgs.length / 2)} Q</div>
                </button>
                <button onClick={() => deleteConv(c.id)} className="hidden text-muted hover:text-danger group-hover:block" aria-label="Delete chat">
                  <Trash width={14} height={14} />
                </button>
              </li>
            ))}
          </ul>
        )}

        {tab === "docs" && (
          <>
        <div className="mt-5 flex items-center justify-between px-4 text-[11px] font-medium uppercase tracking-wider text-muted">
          <span>Knowledge base</span>
          <span className="normal-case tracking-normal tabular-nums">
            {docs.length} docs · {totalChunks} chunks
          </span>
        </div>

        <div className="px-3 pt-2">
          <label
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              upload(e.dataTransfer.files);
            }}
            className={`flex cursor-pointer flex-col items-center gap-1 rounded-xl border border-dashed px-3 py-3.5 text-center text-xs transition ${
              dragging ? "border-accent bg-accent-soft text-accent" : "border-border-strong text-muted hover:border-accent/60 hover:text-fg-2"
            }`}
          >
            <Upload width={18} height={18} />
            <span className="font-medium">{dragging ? "Release to upload" : "Drop files or click to upload"}</span>
            <span className="text-[11px] opacity-70">.txt · .md · .pdf · multiple files OK</span>
            <input type="file" multiple accept=".txt,.md,.pdf" className="hidden" onChange={(e) => (upload(e.target.files), (e.target.value = ""))} />
          </label>
        </div>

        {jobs.length > 0 && (
          <ul className="mx-3 mt-2 space-y-1.5">
            {jobs.map((j) => (
              <li key={j.id} className="fade-up rounded-lg border border-border bg-surface-2 px-2.5 py-2 text-xs">
                <div className="flex items-center gap-2">
                  {j.stage === "done" ? (
                    <Check width={14} height={14} className="shrink-0 text-success" />
                  ) : j.stage === "error" ? (
                    <Close width={14} height={14} className="shrink-0 text-danger" />
                  ) : (
                    <span className="h-3.5 w-3.5 shrink-0 animate-spin rounded-full border-2 border-border-strong border-t-accent" />
                  )}
                  <span className="flex-1 truncate text-fg-2" title={j.name}>{j.name}</span>
                  {j.stage === "uploading" && <span className="tabular-nums text-muted">{j.pct}%</span>}
                  {j.stage === "error" && (
                    <button onClick={() => setJobs((js) => js.filter((x) => x.id !== j.id))} className="text-muted hover:text-fg" aria-label="Dismiss">
                      <Close width={12} height={12} />
                    </button>
                  )}
                </div>
                {(j.stage === "uploading" || j.stage === "indexing") && (
                  <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-surface-3">
                    <div className={`h-full rounded-full bg-accent transition-all ${j.stage === "indexing" ? "shimmer w-full" : ""}`} style={j.stage === "uploading" ? { width: `${j.pct}%` } : undefined} />
                  </div>
                )}
                <div className={`mt-1 ${j.stage === "error" ? "text-danger" : j.stage === "done" ? "text-success" : "text-muted"}`}>
                  {j.stage === "queued" && "Waiting…"}
                  {j.stage === "uploading" && "Uploading…"}
                  {j.stage === "indexing" && "Reading, chunking & embedding — this can take a few seconds…"}
                  {(j.stage === "done" || j.stage === "error") && j.msg}
                </div>
              </li>
            ))}
          </ul>
        )}

        <ul className="mt-2 flex-1 space-y-0.5 overflow-y-auto px-2 pb-2">
          {!docsLoaded && [0, 1, 2, 3].map((i) => <li key={i} className="shimmer mx-1 my-1.5 h-8 rounded-lg" />)}
          {docsLoaded && docs.length === 0 && <li className="px-3 py-6 text-center text-xs text-muted">No documents yet.</li>}
          {docs.map((d) => {
            const st = busyDocs[d.id];
            return (
              <li key={d.id} className={`group flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm hover:bg-surface-2 ${st === "deleting" ? "opacity-50" : ""}`}>
                <File width={15} height={15} className="shrink-0 text-muted" />
                <span className="flex-1 truncate text-fg-2" title={d.title}>
                  {d.title}
                </span>
                {st ? (
                  <span className="flex items-center gap-1.5 text-[11px] text-muted">
                    <span className="h-3 w-3 animate-spin rounded-full border-2 border-border-strong border-t-accent" />
                    {st === "deleting" ? "Deleting…" : "Preparing…"}
                  </span>
                ) : confirmId === d.id ? (
                  <span className="flex items-center gap-1 text-[11px]">
                    <span className="text-muted">Delete?</span>
                    <button onClick={() => removeDoc(d.id)} className="rounded px-1.5 py-0.5 font-medium text-danger hover:bg-danger/10">Yes</button>
                    <button onClick={() => setConfirmId(null)} className="rounded px-1.5 py-0.5 text-muted hover:bg-surface-3">No</button>
                  </span>
                ) : (
                  <>
                    <span className="text-[11px] tabular-nums text-muted" title={`${d.chunks} passages`}>{d.chunks}</span>
                    {d.stored && (
                      <button onClick={() => downloadDoc(d.id)} className="text-muted opacity-60 hover:text-fg group-hover:opacity-100" aria-label={`Download ${d.title}`} title="Download original">
                        <Download width={14} height={14} />
                      </button>
                    )}
                    <button onClick={() => setConfirmId(d.id)} className="text-muted opacity-60 hover:text-danger group-hover:opacity-100" aria-label={`Delete ${d.title}`} title="Delete">
                      <Trash width={14} height={14} />
                    </button>
                  </>
                )}
              </li>
            );
          })}
        </ul>
          </>
        )}

        <div className="space-y-2.5 border-t border-border p-4 text-sm">
          <div className="text-[11px] font-medium uppercase tracking-wider text-muted">Pipeline</div>
          <Toggle label="Agent loop" hint="Decompose & multi-hop" on={agent} set={setAgent} />
          <Toggle label="Reranker" hint="Better precision, slower" on={rerank} set={setRerank} />
        </div>
      </aside>

      {/* Main */}
      <main className="relative flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-bg/80 px-4 backdrop-blur">
          <div className="flex items-center gap-3">
            <button className="rounded-lg p-1.5 text-fg-2 hover:bg-surface-2 md:hidden" onClick={() => setSidebar(true)} aria-label="Open menu">
              <Menu width={18} height={18} />
            </button>
            <div className="text-sm font-medium text-fg-2">{msgs.length ? "Conversation" : "New conversation"}</div>
          </div>
          <div className="flex items-center gap-2">
            <span className="hidden items-center gap-1.5 rounded-full border border-border bg-surface px-2.5 py-1 text-[11px] text-muted sm:flex">
              <span className={`h-1.5 w-1.5 rounded-full ${notice?.includes("API") ? "bg-danger" : "bg-success"}`} />
              Hybrid search · {rerank ? "rerank on" : "rerank off"}
            </span>
            <button onClick={toggleTheme} className="rounded-lg border border-border bg-surface p-2 text-fg-2 hover:bg-surface-2" aria-label="Toggle theme">
              {dark ? <Sun /> : <Moon />}
            </button>
          </div>
        </header>

        {notice && (
          <div className="mx-4 mt-3 flex items-center justify-between rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-warning">
            <span>{notice}</span>
            <button onClick={() => setNotice(null)} aria-label="Dismiss">
              <Close width={14} height={14} />
            </button>
          </div>
        )}

        <div ref={scroller} className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-3xl space-y-7 px-4 py-8">
            {msgs.length === 0 && (
              <div className="fade-up pt-[8vh] text-center">
                <div className="mx-auto mb-5 flex h-12 w-12 items-center justify-center rounded-2xl bg-accent-soft text-accent">
                  <Sparkle width={22} height={22} />
                </div>
                <h2 className="text-2xl font-semibold tracking-tight">What would you like to know?</h2>
                <p className="mx-auto mt-2 max-w-md text-sm text-muted">
                  Ask across your documents. Answers are grounded in retrieved passages and cite their sources.
                </p>
                <div className="mx-auto mt-8 grid max-w-xl gap-2.5">
                  {suggestions.length === 0 && docsLoaded && <p className="text-sm text-muted">Upload a document to get started.</p>}
                  {suggestions.map((s) => (
                    <button
                      key={s}
                      onClick={() => send(s)}
                      className="rounded-xl border border-border bg-surface px-4 py-3 text-left text-sm text-fg-2 shadow-sm transition hover:-translate-y-px hover:border-accent/50 hover:bg-surface-2 hover:text-fg"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {msgs.map((m, i) =>
              m.role === "user" ? (
                <div key={i} className="fade-up flex justify-end">
                  <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-accent-strong px-4 py-2.5 text-sm leading-relaxed text-white shadow-sm">
                    {m.content}
                  </div>
                </div>
              ) : (
                <Assistant
                  key={i}
                  m={m}
                  onCite={(s) => setPanel({ sources: m.sources || [], cited: citedOf(m), focus: s.n })}
                  onOpenSources={() => setPanel({ sources: m.sources || [], cited: citedOf(m) })}
                />
              )
            )}
          </div>
        </div>

        {/* Composer */}
        <div className="shrink-0 bg-gradient-to-t from-bg via-bg to-transparent px-4 pb-4 pt-2">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              send(input);
            }}
            className="mx-auto max-w-3xl"
          >
            <div className="flex items-end gap-2 rounded-2xl border border-border-strong bg-surface p-2 shadow-[var(--shadow)] transition focus-within:border-accent">
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
                placeholder="Ask a question about your documents…"
                className="max-h-[180px] flex-1 resize-none bg-transparent px-2.5 py-2 text-sm text-fg outline-none placeholder:text-muted"
              />
              {busy ? (
                <button type="button" onClick={() => abort.current?.abort()} className="flex h-9 w-9 items-center justify-center rounded-xl bg-surface-3 text-fg hover:bg-border-strong" aria-label="Stop generating">
                  <Stop width={14} height={14} />
                </button>
              ) : (
                <button
                  disabled={!input.trim()}
                  className="flex h-9 w-9 items-center justify-center rounded-xl bg-accent-strong text-white transition hover:brightness-110 disabled:bg-surface-3 disabled:text-muted"
                  aria-label="Send"
                >
                  <Send />
                </button>
              )}
            </div>
            <p className="mt-2 text-center text-[11px] text-muted">Enter to send · Shift+Enter for a new line · Answers may contain errors — check the sources.</p>
          </form>
        </div>
      </main>

      {panel && (
        <SourcesPanel
          panel={panel}
          onClose={() => setPanel(null)}
          canDownload={(t) => !!docs.find((d) => d.title === t && d.stored)}
          onDownload={(t) => {
            const d = docs.find((x) => x.title === t);
            if (d) downloadDoc(d.id);
          }}
        />
      )}

    </div>
  );
}

const citedOf = (m: Msg) =>
  Array.from(new Set((m.content.match(/\[(\d+)\]/g) || []).map((x) => Number(x.slice(1, -1))))).filter((n) => (m.sources || []).some((s) => s.n === n));

function Toggle({ label, hint, on, set }: { label: string; hint: string; on: boolean; set: (v: boolean) => void }) {
  return (
    <button type="button" role="switch" aria-checked={on} onClick={() => set(!on)} className="flex w-full items-center justify-between gap-3 text-left">
      <span>
        <span className="block text-[13px] font-medium text-fg-2">{label}</span>
        <span className="block text-[11px] text-muted">{hint}</span>
      </span>
      <span className={`relative h-5 w-9 shrink-0 rounded-full transition ${on ? "bg-accent-strong" : "bg-surface-3"}`}>
        <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-all ${on ? "left-[18px]" : "left-0.5"}`} />
      </span>
    </button>
  );
}
