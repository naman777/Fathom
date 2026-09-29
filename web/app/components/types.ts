export type Source = { n: number; id: number; title: string; position: number; content: string };
export type Trace = { type: string; [k: string]: any };
export type Msg = {
  role: "user" | "assistant";
  content: string;
  trace?: Trace[];
  sources?: Source[];
  timing?: { retrieval?: number; first?: number; total?: number };
  error?: { message: string; retryAfter?: number };
  streaming?: boolean;
};
export type Doc = { id: number; title: string; source: string; chunks: number };
