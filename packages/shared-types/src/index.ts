// Hand-curated TS types shared between web and (in the future) native clients.
//
// Generated OpenAPI types live under ./generated/api.ts (run `pnpm gen:types`).
// That file is git-ignored; import directly from
// `@jai/shared-types/dist/generated/api` once generated, or from this index.

export type Role = "user" | "assistant" | "system" | "tool" | "reflection";

export interface Message {
  id: string;
  conversation_id: string;
  role: Role;
  content: string;
  created_at: string;
  audio_url?: string | null;
  model?: string | null;
  metadata?: Record<string, unknown>;
}

export interface Task {
  id: string;
  list_id: string;
  title: string;
  notes?: string | null;
  status: "needsAction" | "completed";
  due?: string | null;
  parent_id?: string | null;
}

export interface Note {
  id: string;
  title?: string | null;
  body?: string | null;
  color?: string;
  pinned?: boolean;
  archived?: boolean;
  labels?: string[];
  checklist?: { text: string; checked: boolean }[];
  updated_at: string;
}

export interface Skill {
  id: string;
  title: string;
  description: string;
  language: "python" | "typescript" | "bash";
  required_credentials: string[];
  required_tools: string[];
  run_count: number;
  last_run_at?: string | null;
  last_run_status?: string | null;
  is_active: boolean;
}
