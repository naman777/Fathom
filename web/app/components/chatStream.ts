import type { Msg } from "./types";

/**
 * POST a chat request and apply its SSE events to the last message through `patchLast`.
 * Shared by the document chat (/api/chat) and the enterprise chat (/api/enterprise/chat).
 * Throws on network errors and aborts; HTTP errors are written to the message.
 */
export async function streamChat(
  url: string,
  body: unknown,
  patchLast: (fn: (m: Msg) => Msg) => void,
  signal: AbortSignal,
  headers: Record<string, string> = {}
) {
  const res = await fetch(url, {
    method: "POST",
    signal,
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(body),
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
}
