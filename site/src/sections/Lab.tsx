import { useState } from "react";
import { pctOf, type LabExample, type Summary, type TraceHop, type Verdict } from "../data";
import { Badge, RateBar, rateTip, useTip } from "../ui";

const CONFIGS: { key: string; name: string; note: string }[] = [
  { key: "code_only", name: "Rules only", note: "ID check after every agent" },
  { key: "end_only", name: "One AI check at the end", note: "full chat, final action only" },
  { key: "lightweight", name: "Rules everywhere + AI at the end", note: "the recommended set-up" },
  { key: "every_step", name: "AI check after every agent", note: "full chat at every hand-off" },
  { key: "no_source", name: "AI checks without the chat", note: "records only, every hand-off" },
];

function Num({ children, tip }: { children: React.ReactNode; tip: React.ReactNode }) {
  return <span className="num" {...useTip(tip)}>{children}</span>;
}

function GuardTable({ s }: { s: Summary }) {
  const c = s.lab.configs;
  return (
    <div className="card">
      <h3>Which guard set-up is worth it?</h3>
      <p className="sub">
        Every set-up is scored on the same logged runs: {s.lab.handoff_faults.reached_end} planted faults that reached
        the final action, and {c.end_only.false_alarms.n} correct runs for false alarms. Thin lines show 95% intervals.
      </p>
      <div style={{ overflowX: "auto" }}>
        <table className="matrix">
          <thead>
            <tr>
              <th>Guard set-up</th>
              <th>Planted faults caught</th>
              <th>False alarms</th>
              <th className="hide-sm">Cost / 1,000 runs</th>
              <th className="hide-sm">Added delay</th>
            </tr>
          </thead>
          <tbody>
            {CONFIGS.map(({ key, name, note }) => {
              const v = c[key];
              const fa = key === "every_step" ? v.false_alarms_adjusted : v.false_alarms;
              return (
                <tr key={key} className={key === "lightweight" ? "pick" : ""}>
                  <td className="cfg"><b>{name}</b><span>{note}</span></td>
                  <td><RateBar r={v.caught} color="var(--lab)" what="of planted faults caught" /></td>
                  <td>
                    <RateBar r={fa} color="var(--text-3)" what="false alarms on correct runs" />
                    {key === "every_step" && (
                      <div className="tiny">{pctOf(v.false_alarms)}% raw; see note below</div>
                    )}
                  </td>
                  <td className="hide-sm">
                    <Num tip={<>{v.llm_calls} model calls per run</>}>${v.cost_per_1000_runs.toFixed(2)}</Num>
                  </td>
                  <td className="hide-sm">
                    <Num tip="measured while runs shared the API in parallel; indicative">{v.delay_seconds.toFixed(1)} s</Num>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="callout">
        <b>One full-context check at the end is enough.</b> Checking after every agent catches nothing extra at about
        5× the cost and 4× the delay. Rules are free but only catch invented IDs. <span className="tiny">
        Adjusted false alarms ignore flags that only dispute <code>policy_allowed</code>, an internal field the
        conversation can't confirm.</span>
      </p>
    </div>
  );
}

function PositionChart({ s }: { s: Summary }) {
  const rows = ["1", "2", "4"];
  const ns = s.lab.configs.no_source.by_position;
  const eo = s.lab.configs.end_only.by_position;
  return (
    <div className="card">
      <h3>A checker without the chat can't see early mistakes</h3>
      <p className="sub">Faults caught, by the hand-off where they were planted.</p>
      <div className="legend">
        <span><i style={{ background: "var(--lab)" }} />With the conversation (end check)</span>
        <span><i style={{ background: "var(--text-3)" }} />Records only (every hand-off)</span>
      </div>
      <div className="stack">
        {rows.map((p) => (
          <div key={p}>
            <div className="small" style={{ fontWeight: 600, marginBottom: 6 }}>
              Hand-off {p} <span className="tiny">· {p === "1" ? "right after intake" : p === "2" ? "after the verifier" : "after policy"}</span>
            </div>
            <RateBar r={eo[p]} color="var(--lab)" what={`caught with the conversation (hand-off ${p})`} />
            <div style={{ height: 6 }} />
            <RateBar r={ns[p]} color="var(--text-3)" what={`caught from records only (hand-off ${p})`} />
          </div>
        ))}
      </div>
    </div>
  );
}

function ConfirmedCard({ s }: { s: Summary }) {
  const cf = s.lab.confirmed_faults;
  const end = s.lab.configs.end_only.confirmed_caught;
  const t = useTip(rateTip(end, "of confirmed faults caught by the end check"));
  return (
    <div className="card">
      <h3>Faking a real mistake</h3>
      <p className="sub">
        The closest the lab gets to a real error: the agent reads back a wrong change and the customer says
        "Yes, please go ahead."
      </p>
      <div className="split" role="img" aria-label={`${cf.planted} planted, ${cf.took_hold} took hold`}>
        <div style={{ flex: cf.took_hold, background: "var(--lab)" }}>{cf.took_hold} took hold</div>
        <div style={{ flex: cf.planted - cf.took_hold, background: "var(--text-3)" }}>
          {cf.planted - cf.took_hold} ignored by the intake agent
        </div>
      </div>
      <p className="small muted" {...t}>
        Of the {cf.took_hold} that got through, the end check still caught <b style={{ color: "var(--text)" }}>{end.k} of {end.n}</b>:
        earlier in the chat the customer had named the right order, so the fake read-back contradicted it. Real
        mistakes don't leave that trace.
      </p>
    </div>
  );
}

// ------------------------------------------------------------------ walkthrough

const SHOW = ["action", "order_id", "item_ids", "new_item_ids", "payment_method_id", "user_id", "ownership_ok", "price_difference", "policy_allowed"];
const KIND_NAMES = {
  code: ["Rules", "IDs appear in the chat"],
  source: ["AI, full chat", "original conversation"],
  local: ["AI, records only", "no conversation"],
} as const;

function fmt(v: unknown) {
  if (v === null || v === undefined) return "—";
  if (Array.isArray(v)) return v.length ? v.join(", ") : "—";
  return String(v);
}

function Checks({ checks }: { checks: Record<"code" | "source" | "local", Verdict> }) {
  return (
    <div className="checks">
      {(["code", "source", "local"] as const).map((k) => {
        const v = checks[k];
        return (
          <div className="check" key={k}>
            <div className="kind-name">{KIND_NAMES[k][0]}<span>{KIND_NAMES[k][1]}</span></div>
            <div>
              {v.ok ? <Badge tone="neutral" icon="check">Passes</Badge> : <Badge tone="warn" icon="cross">Flags {v.wrong_fields.join(", ")}</Badge>}
              {v.explanation && <p className="small muted" style={{ margin: "6px 0 0" }}>{v.explanation}</p>}
              {k === "code" && <p className="small muted" style={{ margin: "6px 0 0" }}>{v.ok ? "Every ID is somewhere in the conversation." : "An ID never appears in the conversation."}</p>}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function Walkthrough({ ex }: { ex: LabExample }) {
  const [mode, setMode] = useState<"fault" | "clean">("fault");
  const [step, setStep] = useState(0);
  const run = ex.runs[mode];
  const clean = ex.runs.clean;
  const isFinal = step === run.hops.length;
  const hop: TraceHop | undefined = run.hops[step];
  const fields = isFinal ? (run.final.action.arguments as Record<string, unknown>) : hop!.handoff;
  const cleanFields = isFinal ? (clean.final.action.arguments as Record<string, unknown>) : clean.hops[step].handoff;
  const checks = isFinal ? run.final.checks : hop!.checks;
  const names = ["Hand-off 1 · intake", "Hand-off 2 · verifier", "Hand-off 3 · pricing", "Hand-off 4 · policy", "Final action"];
  const anyFlag = (i: number) => {
    const c = i === run.hops.length ? run.final.checks : run.hops[i].checks;
    return !c.source.ok || !c.local.ok || !c.code.ok;
  };

  return (
    <div className="card">
      <div style={{ display: "flex", justifyContent: "space-between", gap: 16, flexWrap: "wrap", alignItems: "start" }}>
        <div>
          <h3>Worked example: Isabella's return</h3>
          <p className="sub" style={{ maxWidth: 640 }}>
            Isabella wants to return the electric kettle and the keyboard from the order sent to Houston. We swap in
            her <i>other</i> real order (a garden hose and a backpack) at hand-off 1. Every agent downstream accepts it.
          </p>
        </div>
        <div className="toggle" role="group" aria-label="Which run">
          <button aria-pressed={mode === "fault"} onClick={() => setMode("fault")}>With planted fault</button>
          <button aria-pressed={mode === "clean"} onClick={() => setMode("clean")}>Clean run</button>
        </div>
      </div>
      <div className="steps" role="group" aria-label="Checkpoint">
        {names.map((n, i) => (
          <button key={n} className="step" aria-pressed={step === i} onClick={() => setStep(i)}>
            <span className="dot" style={{ background: anyFlag(i) ? "var(--bad)" : "var(--good)" }} aria-hidden="true" />
            {n}
          </button>
        ))}
      </div>
      <div className="grid-2">
        <div>
          <h4 className="eyebrow">{isFinal ? "Tool call about to run" : "What this agent passed on"}</h4>
          <dl className="fields">
            {SHOW.filter((k) => k in fields).map((k) => {
              const changed = mode === "fault" && fmt(fields[k]) !== fmt(cleanFields[k]);
              return (
                <div key={k} style={{ display: "contents" }}>
                  <dt>{k}</dt>
                  <dd className={changed ? "changed" : ""}>
                    {changed && <span className="was">{fmt(cleanFields[k])}</span>}
                    {fmt(fields[k])}
                  </dd>
                </div>
              );
            })}
          </dl>
          {mode === "fault" && <p className="tiny" style={{ marginTop: 12 }}>Highlighted: differs from the clean run.</p>}
        </div>
        <div>
          <h4 className="eyebrow">What each check says here</h4>
          <Checks checks={checks} />
        </div>
      </div>
    </div>
  );
}

export function Lab({ s, ex }: { s: Summary; ex: LabExample }) {
  const hf = s.lab.handoff_faults;
  return (
    <section id="lab">
      <div className="wrap">
        <p className="eyebrow" style={{ color: "var(--lab)" }}>Experiment 1 · In the lab</p>
        <h2>Planted mistakes are easy to catch</h2>
        <p className="lede">
          {hf.applied} faults were planted; {hf.reached_end} ({Math.round((100 * hf.reached_end) / hf.applied)}%) travelled all the way to the database write.
          The agents themselves stopped the rest, mostly invented order IDs that the verifier couldn't find.
        </p>
        <div className="stack">
          <GuardTable s={s} />
          <div className="grid-2">
            <PositionChart s={s} />
            <ConfirmedCard s={s} />
          </div>
          <Walkthrough ex={ex} />
        </div>
      </div>
    </section>
  );
}
