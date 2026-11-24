// Types for the JSON written by `blindspots export-site`, and a tiny loader.

export interface Rate {
  k: number;
  n: number;
  pct: number;
  lo: number;
  hi: number;
}

export interface GuardConfig {
  llm_calls: number;
  caught: Rate;
  confirmed_caught: Rate;
  false_alarms: Rate;
  false_alarms_adjusted: Rate;
  right_step: Rate | null;
  right_reason: Rate;
  cost_per_1000_runs: number;
  delay_seconds: number;
  by_position: Record<string, Rate>;
  by_level: Record<string, Rate>;
}

export interface Summary {
  headline: { planted_caught: Rate; real_caught: Rate };
  lab: {
    cases: number;
    clean: { correct: number; wrong_change_written: number; stopped_by_agents: number };
    handoff_faults: { applied: number; reached_end: number; stopped_by_agents: number };
    confirmed_faults: { planted: number; took_hold: number; reached_end: number };
    configs: Record<string, GuardConfig>;
  };
  wild: {
    kept: { mistakes: number; correct: number };
    filter_overturned: Rate;
    full: { caught: Rate; false_alarms: Rate };
    records: { caught: Rate; false_alarms: Rate };
    caught_by_action: Record<string, Rate>;
    caught_by_agent: Record<string, Rate>;
    explanations: {
      missed: number;
      missed_cites_request: number;
      missed_cites_confirmation: number;
      caught: number;
      caught_cites_confirmation: number;
    };
  };
  skeptic: {
    usable: number;
    mistakes: number;
    correct: number;
    caught: Record<"original" | "baseline" | "skeptic", Rate>;
    false_alarms: Record<"original" | "baseline" | "skeptic", Rate>;
    skeptic_vs_baseline: Record<"mistakes" | "correct", { only_a: number; only_b: number; p_value: number }>;
    run_to_run_flips: number;
    clue_in_chat: Rate;
    caught_with_clue: Record<"original" | "baseline" | "skeptic", Rate>;
    caught_without_clue: Record<"original" | "baseline" | "skeptic", Rate>;
  };
}

export interface ToolCall {
  name: string;
  arguments: Record<string, unknown>;
}

export interface Message {
  role: "user" | "assistant" | "tool";
  content: string;
  tool_calls?: ToolCall[];
}

export interface Goal {
  reason_for_call?: string;
  known_info?: string;
  unknown_info?: string;
  task_instructions?: string;
}

export interface Case {
  id: string;
  case_id: string;
  task: string;
  agent: string;
  trial: number;
  label: "mistake" | "correct";
  action: ToolCall;
  adjudicator_reason: string;
  checker: { flagged: boolean; explanation: string };
  records_checker_flagged: boolean;
  rerun: null | {
    baseline_flagged: boolean;
    baseline_explanation: string;
    skeptic_flagged: boolean;
    skeptic_explanation: string;
    clue: "yes" | "no" | null;
    clue_evidence: string | null;
  };
  goal: Goal | null;
  messages: Message[];
  featured: boolean;
}

export interface Verdict {
  ok: boolean;
  wrong_fields: string[];
  explanation?: string;
}

export interface TraceHop {
  hop: number;
  handoff: Record<string, unknown>;
  checks: Record<"code" | "source" | "local", Verdict>;
}

export interface LabRun {
  level: string;
  position: number | "";
  fault?: string;
  hops: TraceHop[];
  final: { action: ToolCall; checks: Record<"code" | "source" | "local", Verdict> };
}

export interface LabExample {
  case_id: string;
  correct_action: ToolCall;
  messages: Message[];
  runs: { clean: LabRun; fault: LabRun };
}

export async function load<T>(name: string): Promise<T> {
  const res = await fetch(`${import.meta.env.BASE_URL}data/${name}.json`);
  if (!res.ok) throw new Error(`Could not load ${name}.json (${res.status})`);
  return res.json() as Promise<T>;
}

export const AGENT_NAMES: Record<string, string> = {
  "claude-3-7-sonnet-20250219": "Claude 3.7 Sonnet",
  "gpt-4.1-2025-04-14": "GPT-4.1",
  "gpt-4.1-mini-2025-04-14": "GPT-4.1 mini",
  "o4-mini-2025-04-16": "o4-mini",
};

export const ACTION_NAMES: Record<string, string> = {
  cancel_pending_order: "Cancel order",
  exchange_delivered_order_items: "Exchange items",
  modify_pending_order_address: "Change shipping address",
  modify_pending_order_items: "Change items",
  modify_pending_order_payment: "Change payment",
  modify_user_address: "Change account address",
  return_delivered_order_items: "Return items",
};

// Rounded from k/n directly: rounding the already-rounded `pct` field would turn 92.48 into 93.
export const pctOf = (r: Rate) => Math.round((100 * r.k) / r.n);
export const pct = (r: Rate) => `${pctOf(r)}%`;
