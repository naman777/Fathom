/** `source` and `doc_id` are only set by the enterprise chat, where ids are Qdrant point ids (strings). */
export type Source = { n: number; id: number | string; title: string; position: number; content: string; source?: string; doc_id?: string };
export type Trace = { type: string; [k: string]: any };
/** Per-request observability summary sent with the SSE `done` event (see core/obs.py). */
export type Meta = {
  trace_id: string;
  wall_ms: number;
  first_token_ms: number | null;
  stages_ms: Record<string, number>;
  stage_share_pct: Record<string, number>;
  top_stage: string | null;
  tokens: { prompt: number; completion: number; calls: number };
  usage: Record<string, [number, number, number]>;
  cost_usd: number;
  unpriced_models: string[];
  status?: string;
};
export type Msg = {
  role: "user" | "assistant";
  content: string;
  trace?: Trace[];
  sources?: Source[];
  timing?: { retrieval?: number; first?: number; total?: number };
  meta?: Meta;
  traceId?: string;
  error?: { message: string; retryAfter?: number };
  streaming?: boolean;
  /** Enterprise chat: the role the question was asked as. */
  asRole?: string;
};
/** GET /api/enterprise/roles */
export type EnterpriseInfo = {
  roles: { id: string; label: string; groups: string[] | null }[];
  default: string;
  groups: string[];
  index: { ready: boolean; chunks: number; status: string };
  models: { embed: string; rerank: string; answer: string };
  examples: { question: string; groups: string[]; source: string }[];
};
export type Doc = { id: number; title: string; source: string; chunks: number; stored?: boolean; flags?: Record<string, number> };
/** Built-in sample corpus from GET /api/sample: files smallest first, plus the labelled evaluation questions. */
export type Sample = { files: { name: string; title: string; kb: number }[]; questions: { question: string; docs: string[] }[] };
export type Conv = { id: string; title: string; msgs: Msg[]; updated: number };
export type Job = { id: string; name: string; pct: number; stage: "queued" | "uploading" | "indexing" | "done" | "error"; msg?: string };
