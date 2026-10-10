"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Assistant from "./components/Assistant";
import { Backdrop } from "@/components/backdrop";
import { ThemeSwitcher } from "@/components/theme-switcher";
import { Alert as Notice } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Kbd } from "@/components/ui/kbd";
import { Segmented } from "@/components/ui/segmented";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { Switch } from "@/components/ui/switch";
import { Alert as AlertIcon, Close, Download, File, Logo, Menu, Paperclip, Plus, Send, Stop, Trash, Upload } from "./components/icons";
import SiteNav from "./components/SiteNav";
import UploadToasts from "./components/UploadToasts";
import UploadZone from "./components/UploadZone";
import SourcesPanel, { type PanelState } from "./components/SourcesPanel";
import type { Conv, Doc, Job, Msg, Sample } from "./components/types";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const uid = () => Math.random().toString(36).slice(2, 10);
const CONVS_KEY = "fathom-convs";

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
  const [sample, setSample] = useState<Sample | null>(null);
  const [sampleBusy, setSampleBusy] = useState(false);
  const [agent, setAgent] = useState(true);
  const [rerank, setRerank] = useState(true);
  const [panel, setPanel] = useState<PanelState | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [sidebar, setSidebar] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [pageDrag, setPageDrag] = useState(false);
  const picker = useRef<HTMLInputElement>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const abort = useRef<AbortController | null>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

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
  useEffect(() => {
    fetch(`${API}/api/sample`)
      .then((r) => (r.ok ? r.json() : null))
      .then(setSample)
      .catch(() => {});
  }, []);

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
          else if (ev === "meta") patchLast((m) => ({ ...m, traceId: data.trace_id }));
          else if (ev === "retrieval_done") patchLast((m) => ({ ...m, timing: { ...m.timing, retrieval: data.ms } }));
          else if (ev === "first_token") patchLast((m) => ({ ...m, timing: { ...m.timing, first: data.ms } }));
          else if (ev === "token") patchLast((m) => ({ ...m, content: m.content + data }));
          else if (ev === "done") patchLast((m) => ({ ...m, streaming: false, meta: data, timing: { ...m.timing, total: data.ms } }));
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

  const sendRef = useRef(send);
  sendRef.current = send;

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
          const msg = xhr.status === 429 ? "Too many uploads, try again later" : body.detail || `Upload failed (${xhr.status})`;
          patchJob(id, { stage: "error", msg: String(msg) });
        }
        resolve();
      };
      xhr.onerror = () => {
        patchJob(id, { stage: "error", msg: "Network error. Is the server reachable?" });
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

  // Dropping files anywhere in the window uploads them.
  const uploadRef = useRef(upload);
  uploadRef.current = upload;
  useEffect(() => {
    const hasFiles = (e: DragEvent) => Array.from(e.dataTransfer?.types || []).includes("Files");
    const over = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      setPageDrag(true);
    };
    const leave = (e: DragEvent) => {
      if (!e.relatedTarget) setPageDrag(false);
    };
    const drop = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      setPageDrag(false);
      uploadRef.current(e.dataTransfer?.files ?? null);
    };
    window.addEventListener("dragover", over);
    window.addEventListener("dragleave", leave);
    window.addEventListener("drop", drop);
    return () => {
      window.removeEventListener("dragover", over);
      window.removeEventListener("dragleave", leave);
      window.removeEventListener("drop", drop);
    };
  }, []);

  async function removeDoc(id: number) {
    setConfirmId(null);
    setBusyDocs((b) => ({ ...b, [id]: "deleting" }));
    try {
      const r = await fetch(`${API}/api/documents/${id}`, { method: "DELETE" });
      if (!r.ok) setNotice((await r.json().catch(() => ({}))).detail || "Delete failed");
    } catch {
      setNotice("Delete failed. Is the server reachable?");
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
      setNotice("Download failed. Is the server reachable?");
    }
    setBusyDocs((b) => {
      const { [id]: _, ...rest } = b;
      return rest;
    });
  }

  // Sample corpus: which of its files are indexed is derived from the document list, so it stays right after deletes.
  const sources = new Set(docs.map((d) => d.source));
  const sampleMissing = (sample?.files || []).filter((f) => !sources.has(f.name));
  const sampleTitles = new Set((sample?.files || []).filter((f) => sources.has(f.name)).map((f) => f.title));
  const sampleQs = (sample?.questions || []).filter((q) => q.docs.every((t) => sampleTitles.has(t)));
  // The first question asked is one about the smallest file: it is indexed in a couple of seconds.
  const leadQ = sample?.questions.find((q) => q.docs.length === 1 && q.docs[0] === sample.files[0]?.title);

  async function loadSample() {
    if (!sample || sampleBusy || !sampleMissing.length) return;
    setSampleBusy(true);
    setTab("docs");
    const id = uid();
    const todo = [...sampleMissing];
    const st = { done: 0, total: todo.length, failed: "" };
    const label = () => `Sample corpus · ${st.done}/${st.total} RFCs indexed`;
    setJobs((js) => [...js, { id, name: label(), pct: 0, stage: "indexing" }]);
    const one = async (f: Sample["files"][number]) => {
      try {
        const r = await fetch(`${API}/api/sample/${encodeURIComponent(f.name)}`, { method: "POST" });
        if (!r.ok) st.failed = (await r.json().catch(() => ({}))).detail || `Could not load ${f.title} (${r.status})`;
        else st.done++;
      } catch {
        st.failed = "Network error. Is the server reachable?";
      }
      patchJob(id, { name: label() });
      loadDocs();
    };
    // The lead question's RFC goes first and is asked about straight away; the rest index once that answer is in, so
    // bulk inserts do not compete with its retrieval.
    const lead = todo.findIndex((f) => f.title === leadQ?.docs[0]);
    if (lead >= 0) await one(todo.splice(lead, 1)[0]);
    if (leadQ && !st.failed) await sendRef.current(leadQ.question);
    await Promise.all([0, 1, 2].map(async () => {
      for (let f; !st.failed && (f = todo.shift()); ) await one(f);
    }));
    if (st.failed) patchJob(id, { stage: "error", msg: st.failed });
    else {
      patchJob(id, { stage: "done", msg: `${st.total} RFCs indexed` });
      setTimeout(() => setJobs((js) => js.filter((j) => j.id !== id)), 4000);
    }
    setSampleBusy(false);
  }

  const totalChunks = docs.reduce((a, d) => a + d.chunks, 0);
  const third = Math.floor(sampleQs.length / 3);
  const suggestions =
    // Newest document is a sample RFC: offer the labelled evaluation questions instead of generic templates.
    docs.length > 0 && sampleTitles.has(docs[0].title) && sampleQs.length >= 3
      ? [sampleQs[0], sampleQs[third], sampleQs[2 * third]].map((q) => q.question)
      : docs.length > 0
      ? [
          `Summarize the key facts about ${docs[0].title}`,
          docs.length > 1 ? `Compare ${docs[0].title} with ${docs[1].title}` : `What are the most important numbers in ${docs[0].title}?`,
          docs.length > 2 ? `What are the main risks or incidents mentioned in ${docs[2].title}?` : "List the people named across the documents",
        ]
      : [];

  const confirmDoc = docs.find((d) => d.id === confirmId);

  return (
    <div className="flex h-full bg-background text-foreground">
      {/* Sidebar */}
      {sidebar && <div className="fixed inset-0 z-20 bg-black/55 backdrop-blur-sm md:hidden" onClick={() => setSidebar(false)} />}
      <aside
        className={`fixed inset-y-0 left-0 z-30 flex w-[288px] shrink-0 flex-col border-r border-border bg-surface transition-transform duration-300 md:static md:translate-x-0 ${
          sidebar ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex items-center gap-2.5 px-4 pb-3 pt-4">
          <Logo />
          <div className="leading-tight">
            <div className="font-onest text-xl font-medium tracking-tight">Fathom</div>
            <div className="text-[11px] text-muted-foreground">Document intelligence</div>
          </div>
        </div>

        <div className="px-3">
          <Button variant="outline" onClick={newChat} className="w-full">
            <Plus /> New chat
          </Button>
        </div>

        <Segmented
          label="Sidebar view"
          className="mx-3 mt-4 [&>button]:flex-1"
          value={tab}
          onChange={setTab}
          options={[
            { value: "docs", label: `Documents (${docs.length})` },
            { value: "chats", label: `History (${convs.length})` },
          ]}
        />

        {tab === "chats" && (
          <ul className="mt-3 flex-1 space-y-0.5 overflow-y-auto px-2 pb-2">
            {convs.length === 0 && <li className="px-3 py-6 text-center text-xs text-muted-foreground">No saved chats yet.</li>}
            {convs.map((c) => (
              <li key={c.id} className={`group flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm transition-colors duration-200 hover:bg-surface-2 ${c.id === convId ? "bg-surface-2" : ""}`}>
                <button onClick={() => openConv(c)} className="min-w-0 flex-1 text-left">
                  <div className="truncate text-fg-2">{c.title}</div>
                  <div className="text-[11px] text-muted-foreground">{new Date(c.updated).toLocaleDateString()} · {Math.ceil(c.msgs.length / 2)} Q</div>
                </button>
                <button onClick={() => deleteConv(c.id)} className="hidden text-muted-foreground hover:text-danger group-hover:block" aria-label="Delete chat">
                  <Trash width={14} height={14} />
                </button>
              </li>
            ))}
          </ul>
        )}

        {tab === "docs" && (
          <>
            <div className="mt-5 flex items-center justify-between px-4 text-xs font-medium text-muted-foreground">
              <span>Knowledge base</span>
              <span className="tabular-nums">
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
                className={`flex cursor-pointer flex-col items-center gap-1 rounded-xl border border-dashed px-3 py-3.5 text-center text-xs transition-colors duration-200 ${
                  dragging ? "border-card-edge-hover bg-foreground/[0.06] text-foreground" : "border-border-strong text-muted-foreground hover:border-card-edge-hover hover:text-fg-2"
                }`}
              >
                <Upload width={18} height={18} />
                <span className="font-medium">{dragging ? "Release to upload" : "Drop files or click to upload"}</span>
                <span className="text-[11px] opacity-70">.txt · .md · .pdf · multiple files OK</span>
                <input type="file" multiple accept=".txt,.md,.pdf" className="hidden" onChange={(e) => (upload(e.target.files), (e.target.value = ""))} />
              </label>
            </div>

            <ul className="mt-2 flex-1 space-y-0.5 overflow-y-auto px-2 pb-2">
              {!docsLoaded && [0, 1, 2, 3].map((i) => <li key={i}><Skeleton className="mx-1 my-1.5 h-8" /></li>)}
              {docsLoaded && docs.length === 0 && <li className="px-3 py-6 text-center text-xs text-muted-foreground">No documents yet.</li>}
              {docs.map((d) => {
                const st = busyDocs[d.id];
                return (
                  <li key={d.id} className={`group flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition-colors duration-200 hover:bg-surface-2 ${st === "deleting" ? "opacity-50" : ""}`}>
                    <File width={15} height={15} className="shrink-0 text-muted-foreground" />
                    <span className="flex-1 truncate text-fg-2" title={d.title}>
                      {d.title}
                    </span>
                    {st ? (
                      <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                        <Spinner label={st === "deleting" ? "Deleting" : "Preparing download"} className="[&_svg]:size-3" />
                        {st === "deleting" ? "Deleting…" : "Preparing…"}
                      </span>
                    ) : (
                      <>
                        {d.flags && Object.keys(d.flags).length > 0 && (
                          <span className="text-warning" title={`Contains instruction-like text (${Object.keys(d.flags).join(", ")}). Fathom treats document text as data, not instructions.`}>
                            <AlertIcon width={13} height={13} />
                          </span>
                        )}
                        <span className="text-[11px] tabular-nums text-muted-foreground" title={`${d.chunks} passages`}>{d.chunks}</span>
                        {d.stored && (
                          <button onClick={() => downloadDoc(d.id)} className="text-muted-foreground opacity-60 hover:text-foreground group-hover:opacity-100" aria-label={`Download ${d.title}`} title="Download original">
                            <Download width={14} height={14} />
                          </button>
                        )}
                        <button onClick={() => setConfirmId(d.id)} className="text-muted-foreground opacity-60 hover:text-danger group-hover:opacity-100" aria-label={`Delete ${d.title}`} title="Delete">
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
          <div className="text-xs font-medium text-muted-foreground">Pipeline</div>
          <Toggle label="Agent loop" hint="Decompose and multi-hop" on={agent} set={setAgent} />
          <Toggle label="Reranker" hint="Better precision, slower" on={rerank} set={setRerank} />
        </div>
      </aside>

      {/* Main */}
      <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <Backdrop />
        <header className="flex h-14 shrink-0 items-center justify-between gap-2 border-b border-border px-4">
          <div className="flex min-w-0 items-center gap-1 sm:gap-3">
            <button className="rounded-lg p-1.5 text-fg-2 hover:bg-surface-2 md:hidden" onClick={() => setSidebar(true)} aria-label="Open menu">
              <Menu width={18} height={18} />
            </button>
            <div className="hidden text-sm font-medium text-fg-2 lg:block">{msgs.length ? "Conversation" : "New conversation"}</div>
            <SiteNav compact />
          </div>
          <div className="flex items-center gap-2">
            <Button variant="solid" size="sm" iconRight={null} onClick={() => picker.current?.click()} aria-label="Upload documents" className="max-sm:px-2.5" title="Upload documents (.txt, .md, .pdf), or drop files anywhere">
              <Upload width={15} height={15} />
              <span className="hidden sm:inline">Upload documents</span>
            </Button>
            <input ref={picker} type="file" multiple accept=".txt,.md,.pdf" className="hidden" onChange={(e) => (upload(e.target.files), (e.target.value = ""))} />
            <span className="hidden items-center gap-1.5 rounded-full border border-border-strong px-2.5 py-1 text-[11px] text-muted-foreground xl:flex">
              <span className={`h-1.5 w-1.5 rounded-full ${notice?.includes("API") ? "bg-danger" : "bg-success"}`} />
              Hybrid search · {rerank ? "rerank on" : "rerank off"}
            </span>
            <ThemeSwitcher />
          </div>
        </header>

        {notice && (
          <Notice tone="warning" className="mx-4 mt-3 items-center justify-between bg-background/60 py-2 text-xs backdrop-blur-sm [&>div]:flex-1">
            <span className="flex items-center justify-between gap-3">
              {notice}
              <button onClick={() => setNotice(null)} aria-label="Dismiss">
                <Close width={14} height={14} />
              </button>
            </span>
          </Notice>
        )}

        <div ref={scroller} className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-3xl space-y-7 px-4 py-8">
            {msgs.length === 0 && (
              <div className="fade-up pt-[6vh] text-center">
                <h1 className="text-2xl font-medium sm:text-3xl">What would you like to know?</h1>
                <p className="mx-auto mt-3 max-w-md text-base text-neutral-700 dark:text-neutral-400">
                  Ask across your documents. Answers are grounded in retrieved passages and <span className="highlight">cite their sources</span>.
                </p>
                <div className="mt-8">
                  <UploadZone onFiles={upload} busy={uploading} hasDocs={docs.length > 0} />
                </div>
                {sample && docsLoaded && sampleMissing.length > 0 && (
                  <div className="card-chai mx-auto mt-3 flex max-w-xl items-center gap-4 px-4 py-3 text-left">
                    <div className="min-w-0 flex-1">
                      <div className="font-montserrat text-[13px] font-semibold">No files handy? Try the sample corpus</div>
                      <p className="mt-0.5 text-[12px] leading-snug text-muted-foreground">
                        {sample.files.length} IETF RFCs (TCP, DNS, TLS 1.3, QUIC, OAuth 2.0, JWT…), the set Fathom is evaluated on. Loads them and asks a first question.
                      </p>
                    </div>
                    <Button variant="muted" size="sm" onClick={loadSample} disabled={sampleBusy || busy} className="shrink-0">
                      {sampleBusy ? "Loading…" : "Load sample"}
                    </Button>
                  </div>
                )}
                <div className="mx-auto mt-6 grid max-w-xl gap-2.5">
                  {suggestions.map((s) => (
                    <button key={s} onClick={() => send(s)} className="card-chai px-4 py-3 text-left text-sm text-fg-2 hover:text-foreground sm:opacity-90 sm:hover:opacity-100">
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {msgs.map((m, i) =>
              m.role === "user" ? (
                <div key={i} className="fade-up flex justify-end">
                  <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-secondary px-4 py-2.5 text-sm leading-relaxed text-secondary-foreground">
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

        <div className="px-4 pb-4 pt-2">
          <form
            className="mx-auto max-w-3xl"
            onSubmit={(e) => {
              e.preventDefault();
              send(input);
            }}
          >
            <div className="flex items-end gap-2 rounded-2xl border border-card-edge bg-background/60 p-2 backdrop-blur-sm transition-colors duration-300 focus-within:border-card-edge-hover">
              <button
                type="button"
                onClick={() => picker.current?.click()}
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors duration-200 hover:bg-surface-2 hover:text-foreground"
                aria-label="Upload documents"
                title="Upload documents"
              >
                <Paperclip width={17} height={17} />
              </button>
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
                placeholder="Ask about your documents…"
                aria-label="Question"
                className="max-h-[180px] flex-1 resize-none bg-transparent px-2.5 py-2 text-sm text-foreground outline-none placeholder:text-muted-foreground"
              />
              {busy ? (
                <Button type="button" variant="ghost" size="icon" onClick={() => abort.current?.abort()} aria-label="Stop generating" className="bg-surface-3">
                  <Stop width={14} height={14} />
                </Button>
              ) : (
                <Button type="submit" size="icon" disabled={!input.trim()} aria-label="Send">
                  <Send />
                </Button>
              )}
            </div>
            <p className="mt-2 flex flex-wrap items-center justify-center gap-x-1.5 gap-y-1 text-center text-[11px] text-muted-foreground">
              <Kbd>Enter</Kbd> to send · <Kbd>Shift</Kbd> <Kbd>Enter</Kbd> for a new line · Answers may contain errors, so check the sources.
            </p>
          </form>
        </div>
      </main>

      {pageDrag && (
        <div className="pointer-events-none fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm">
          <div className="flex flex-col items-center gap-3 rounded-2xl border border-dashed border-card-edge-hover bg-card px-14 py-12 text-center">
            <Upload width={34} height={34} className="text-highlight" />
            <div className="font-montserrat text-lg font-semibold">Drop to upload</div>
            <div className="text-sm text-muted-foreground">.txt · .md · .pdf</div>
          </div>
        </div>
      )}
      <UploadToasts jobs={jobs} onDismiss={(id) => setJobs((js) => js.filter((j) => j.id !== id))} />

      <ConfirmDialog
        open={!!confirmDoc}
        title={`Delete ${confirmDoc?.title ?? "this document"}?`}
        confirmLabel="Delete document"
        cancelLabel="Keep it"
        typeToConfirm="delete"
        onConfirm={() => confirmDoc && removeDoc(confirmDoc.id)}
        onCancel={() => setConfirmId(null)}
      >
        This removes the document and its {confirmDoc?.chunks ?? 0} indexed passages from the knowledge base
        {confirmDoc?.stored ? ", and deletes the stored original file" : ""}. The knowledge base is shared, so it disappears for everyone using this
        Fathom, and new answers can no longer cite it. This cannot be undone.
      </ConfirmDialog>

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
    <label className="flex w-full cursor-pointer items-center justify-between gap-3">
      <span>
        <span className="block text-[13px] font-medium text-fg-2">{label}</span>
        <span className="block text-[11px] text-muted-foreground">{hint}</span>
      </span>
      <Switch checked={on} onCheckedChange={set} aria-label={label} />
    </label>
  );
}
