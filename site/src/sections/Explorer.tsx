import { useEffect, useMemo, useRef, useState } from "react";
import { ACTION_NAMES, AGENT_NAMES, type Case } from "../data";
import { Badge, VerdictBadge } from "../ui";

type LabelFilter = "mistake" | "correct" | "all";
type VerdictFilter = "all" | "right" | "wrong";
type ClueFilter = "all" | "yes" | "no";

const checkerRight = (c: Case) => c.checker.flagged === (c.label === "mistake");

function title(c: Case) {
  const args = c.action.arguments as Record<string, unknown>;
  const order = typeof args.order_id === "string" ? ` · ${args.order_id}` : "";
  return `${ACTION_NAMES[c.action.name] ?? c.action.name}${order}`;
}

function readHash(): string | null {
  const m = window.location.hash.match(/case=([^&]+)/);
  return m ? decodeURIComponent(m[1]) : null;
}

// ------------------------------------------------------------------ conversation

function pretty(content: string) {
  try {
    return JSON.stringify(JSON.parse(content), null, 2);
  } catch {
    return content;
  }
}

const YES = /\b(yes|yeah|yep|correct|confirm(ed)?|go ahead|proceed|that'?s right|sounds good)\b/i;

function firstSentence(text: string) {
  const m = text.match(/^.*?[.!?](\s|$)/);
  return m ? m[0].trim() : text;
}

function Line({ n, cls, role, children }: { n: number; cls: string; role: string; children: React.ReactNode }) {
  return (
    <div className={`tl ${cls}`}>
      <span className="n">{n}</span>
      <span className="r">{role}</span>
      <div className="c">{children}</div>
    </div>
  );
}

function Conversation({ c }: { c: Case }) {
  const mistake = c.label === "mistake";
  const flagged = c.checker.flagged;
  const args = JSON.stringify(c.action.arguments);
  return (
    <div className="trace">
      {c.messages.map((m, i) => {
        if (m.role === "tool") {
          return (
            <Line key={i} n={i} cls="tool" role="result">
              <details>
                <summary>{m.content}</summary>
                <pre>{pretty(m.content)}</pre>
              </details>
            </Line>
          );
        }
        const who = m.role === "user" ? "customer" : "agent";
        return (
          <div key={i} style={{ display: "contents" }}>
            {m.content && (
              <Line n={i} cls={`${m.role}${m.role === "user" && YES.test(m.content) ? " yes" : ""}`} role={who}>
                {m.content}
              </Line>
            )}
            {m.tool_calls?.map((tc, j) => (
              <Line key={`${i}-${j}`} n={i} cls="call" role="calls">
                <details>
                  <summary>{tc.name}({JSON.stringify(tc.arguments)})</summary>
                  <pre>{JSON.stringify(tc.arguments, null, 2)}</pre>
                </details>
              </Line>
            ))}
          </div>
        );
      })}
      <Line n={c.messages.length} cls="final" role="calls">
        {c.action.name}({args})
      </Line>
      <div className="anno">
        <div className={flagged ? "flag" : "ok"}>
          <b>checker → {flagged ? "BLOCK" : "APPROVE"}</b> · {firstSentence(c.checker.explanation)}
        </div>
        <div className={mistake ? "flag" : "ok"}>
          <b>answer key → {mistake ? "MISTAKE" : "ACCEPTABLE"}</b> · {firstSentence(c.adjudicator_reason)}
        </div>
      </div>
      <p className="tiny" style={{ marginTop: 14 }}>
        Highlighted customer lines contain a confirmation ("yes", "go ahead"…). Click a tool line to expand it.
      </p>
    </div>
  );
}

// ------------------------------------------------------------------ detail

function Detail({ c }: { c: Case }) {
  const mistake = c.label === "mistake";
  const goal = c.goal;
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.scrollTo({ top: 0 });
  }, [c.id]);
  return (
    <div className="ex-main" ref={ref}>
      <div className="ex-head">
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
          {mistake ? <Badge tone="warn" icon="dot">Real mistake</Badge> : <Badge tone="neutral" icon="dot">Correct action</Badge>}
          <VerdictBadge flagged={c.checker.flagged} mistake={mistake} />
          {c.rerun?.clue && <Badge tone="neutral">{c.rerun.clue === "yes" ? "Clue in chat" : "No clue in chat"}</Badge>}
        </div>
        <h3>{title(c)}</h3>
        <div className="tiny">
          Agent: {AGENT_NAMES[c.agent] ?? c.agent} · τ²-bench retail task {c.task} · trial {c.trial} ·{" "}
          <a href={`#case=${encodeURIComponent(c.id)}`}>link to this case</a>
        </div>
      </div>
      <div className="ex-body">
        <div className="ex-col">
          {goal && (
            <div className="panel secret">
              <div className="label">
                <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><path d="M3.5 6V4.5a3.5 3.5 0 0 1 7 0V6M2.5 6h9v6h-9z" fill="none" stroke="currentColor" strokeWidth="1.4" /></svg>
                The customer's secret goal (hidden from the agent and the checker)
              </div>
              {goal.reason_for_call}
              {goal.task_instructions && <div className="tiny" style={{ marginTop: 8 }}>{goal.task_instructions}</div>}
            </div>
          )}
          <h4>Verdicts</h4>
          <div className="verdicts">
            <div className="verdict key">
              <div className="vh">
                <div className="who">Adjudicator<span>sees the secret goal · the answer key</span></div>
                {mistake ? <Badge tone="warn" icon="cross">Mistake</Badge> : <Badge tone="neutral" icon="check">Acceptable</Badge>}
              </div>
              <p>{c.adjudicator_reason}</p>
            </div>
            <div className="verdict">
              <div className="vh">
                <div className="who">Checker<span>full chat, no secret goal · as deployed</span></div>
                <VerdictBadge flagged={c.checker.flagged} mistake={mistake} />
              </div>
              <p>{c.checker.explanation}</p>
            </div>
            {c.rerun && (
              <div className="verdict">
                <div className="vh">
                  <div className="who">Skeptical checker<span>same model, "a yes is not proof" prompt</span></div>
                  <VerdictBadge flagged={c.rerun.skeptic_flagged} mistake={mistake} />
                </div>
                <p>{c.rerun.skeptic_explanation}</p>
              </div>
            )}
            {c.rerun?.clue && (
              <div className="verdict">
                <div className="vh">
                  <div className="who">Clue judge<span>could the chat alone reveal the mistake?</span></div>
                  <Badge tone="neutral">{c.rerun.clue === "yes" ? "Yes" : "No"}</Badge>
                </div>
                <p>{c.rerun.clue_evidence}</p>
              </div>
            )}
            <div className="verdict">
              <div className="vh">
                <div className="who">Records-only checker<span>no conversation</span></div>
                <VerdictBadge flagged={c.records_checker_flagged} mistake={mistake} />
              </div>
            </div>
          </div>
          <h4>The action under review</h4>
          <pre className="action">{JSON.stringify(c.action, null, 2)}</pre>
        </div>
        <div className="ex-col">
          <h4>Trace: the conversation the checker saw</h4>
          <Conversation c={c} />
        </div>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ explorer

function Chips<T extends string>({ value, set, options, label }: { value: T; set: (v: T) => void; options: [T, string][]; label: string }) {
  return (
    <div className="chips" role="group" aria-label={label}>
      {options.map(([v, name]) => (
        <button key={v} className="chip" aria-pressed={value === v} onClick={() => set(v)}>{name}</button>
      ))}
    </div>
  );
}

export function Explorer({ cases }: { cases: Case[] }) {
  const [label, setLabel] = useState<LabelFilter>("mistake");
  const [verdict, setVerdict] = useState<VerdictFilter>("wrong");
  const [clue, setClue] = useState<ClueFilter>("all");
  const [agent, setAgent] = useState("all");
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<string>(() => readHash() ?? cases.find((c) => c.featured)?.id ?? cases[0].id);

  useEffect(() => {
    const onHash = () => {
      const id = readHash();
      if (id && cases.some((c) => c.id === id)) {
        setSelected(id);
        document.getElementById("explorer")?.scrollIntoView();
      }
    };
    onHash();
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, [cases]);

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return cases
      .filter((c) => label === "all" || c.label === label)
      .filter((c) => verdict === "all" || checkerRight(c) === (verdict === "right"))
      .filter((c) => clue === "all" || c.rerun?.clue === clue)
      .filter((c) => agent === "all" || c.agent === agent)
      .filter((c) => !needle || JSON.stringify([c.messages, c.goal, c.action, c.checker, c.adjudicator_reason]).toLowerCase().includes(needle))
      .sort((a, b) => Number(b.featured) - Number(a.featured));
  }, [cases, label, verdict, clue, agent, q]);

  const current = cases.find((c) => c.id === selected) ?? shown[0];
  const search = useRef<HTMLInputElement>(null);

  // "/" focuses search; j / k step through the filtered list.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      if (el.closest("input, select, textarea") || e.metaKey || e.ctrlKey || e.altKey) return;
      if (!document.getElementById("explorer")?.matches(":hover, :focus-within")) return;
      if (e.key === "/") {
        e.preventDefault();
        search.current?.focus();
      } else if (e.key === "j" || e.key === "k") {
        const i = shown.findIndex((c) => c.id === current?.id);
        const next = shown[Math.min(Math.max(i + (e.key === "j" ? 1 : -1), 0), shown.length - 1)];
        if (next) setSelected(next.id);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [shown, current]);

  return (
    <section id="explorer">
      <div className="wrap">
        <p className="eyebrow">Case explorer · the evidence</p>
        <h2>Read every real mistake for yourself</h2>
        <p className="lede">
          All {cases.length} labelled real actions, each with the conversation the checker saw, the secret goal it
          didn't, and every verdict with its explanation. It opens on the checker's misses, starting with Emma's
          water bottle.
        </p>
        <div className="explorer">
          <div className="ex-bar">
            <span className="dots" aria-hidden="true"><i /><i /><i /></span>
            <span className="path">blindspots://cases/{current ? current.id : ""}</span>
            <span className="hint"><kbd>/</kbd> search · <kbd>j</kbd> <kbd>k</kbd> next / previous</span>
          </div>
          <aside className="ex-side">
            <div className="ex-filters">
              <input ref={search} type="search" placeholder="search chats, goals, explanations" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search cases" />
              <Chips label="Label" value={label} set={setLabel} options={[["mistake", "Real mistakes"], ["correct", "Correct actions"], ["all", "All"]]} />
              <Chips label="Checker verdict" value={verdict} set={setVerdict} options={[["wrong", label === "correct" ? "False alarms" : label === "mistake" ? "Missed" : "Checker wrong"], ["right", label === "correct" ? "Approved" : label === "mistake" ? "Caught" : "Checker right"], ["all", "Any verdict"]]} />
              {label !== "correct" && (
                <Chips label="Clue" value={clue} set={setClue} options={[["all", "Any"], ["yes", "Clue in chat"], ["no", "No clue"]]} />
              )}
              <select value={agent} onChange={(e) => setAgent(e.target.value)} aria-label="Agent model">
                <option value="all">All agent models</option>
                {Object.entries(AGENT_NAMES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
              <div className="ex-count">{shown.length} of {cases.length} cases</div>
            </div>
            <div className="ex-list">
              {shown.map((c) => (
                <button key={c.id} className="ex-item" aria-current={current?.id === c.id} onClick={() => setSelected(c.id)}>
                  <div className="t"><span>{title(c)}</span>{c.featured && <span className="tiny">★ featured</span>}</div>
                  <div className="m">{AGENT_NAMES[c.agent] ?? c.agent} · task {c.task} · trial {c.trial}</div>
                  <div className="b">
                    {c.label === "mistake" ? <Badge tone="warn" icon="dot">Mistake</Badge> : <Badge tone="neutral" icon="dot">Correct</Badge>}
                    <VerdictBadge flagged={c.checker.flagged} mistake={c.label === "mistake"} />
                  </div>
                </button>
              ))}
              {!shown.length && <p className="small muted" style={{ padding: 16 }}>No cases match these filters.</p>}
            </div>
          </aside>
          {current ? <Detail c={current} /> : <div className="ex-main" />}
        </div>
      </div>
    </section>
  );
}
