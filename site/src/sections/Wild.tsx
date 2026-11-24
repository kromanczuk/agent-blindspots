import { ACTION_NAMES, type Summary } from "../data";
import { RateBar, rateTip, useTip } from "../ui";

function ClueSplit({ s }: { s: Summary }) {
  const sk = s.skeptic;
  const withClue = sk.caught_with_clue.original;
  const noClue = sk.caught_without_clue.original;
  const t1 = useTip(rateTip(withClue, "caught when the chat held a clue"));
  const t2 = useTip(rateTip(noClue, "caught when the chat held no clue"));
  return (
    <div className="card">
      <h3>3 in 10 real mistakes leave no clue in the chat</h3>
      <p className="sub">
        A judge was asked, for each real mistake: could a reviewer who sees only the conversation have known it was wrong?
      </p>
      <div className="split" role="img" aria-label={`${withClue.n} with a clue, ${noClue.n} without`}>
        <div style={{ flex: withClue.n, background: "var(--wild)" }}>{withClue.n} with a clue</div>
        <div style={{ flex: noClue.n, background: "var(--text-3)" }}>{noClue.n} no clue</div>
      </div>
      <div className="grid-2" style={{ gap: 12, marginTop: 16 }}>
        <div className="panel" style={{ margin: 0 }} {...t1}>
          <div className="big" style={{ fontSize: 40 }}>{withClue.k}/{withClue.n}</div>
          <div className="small muted">caught when there was a clue</div>
        </div>
        <div className="panel" style={{ margin: 0 }} {...t2}>
          <div className="big" style={{ fontSize: 40 }}>{noClue.k}/{noClue.n}</div>
          <div className="small muted">caught when there was none</div>
        </div>
      </div>
      <p className="callout wild"><b>A checker that only reads the chat almost never catches these.</b> Nothing in the conversation contradicts the wrong action.</p>
    </div>
  );
}

function Skeptic({ s }: { s: Summary }) {
  const sk = s.skeptic;
  const runs = [
    { key: "original", name: "Original run" },
    { key: "baseline", name: "Same prompt, run again" },
    { key: "skeptic", name: "Skeptical prompt" },
  ] as const;
  const p = sk.skeptic_vs_baseline.mistakes.p_value;
  return (
    <div className="card">
      <h3>Telling it to be skeptical doesn't help</h3>
      <p className="sub">
        Same model and inputs, but the prompt says the customer's "yes" is not proof and asks for a check against
        what they first asked for. {sk.usable} cases.
      </p>
      <table className="matrix">
        <thead><tr><th>Checker</th><th>Real mistakes caught</th><th>False alarms</th></tr></thead>
        <tbody>
          {runs.map((r) => (
            <tr key={r.key} className={r.key === "skeptic" ? "pick" : ""}>
              <td className="cfg"><b>{r.name}</b></td>
              <td><RateBar r={sk.caught[r.key]} color="var(--wild)" what="of real mistakes caught" /></td>
              <td><RateBar r={sk.false_alarms[r.key]} color="var(--text-3)" what="false alarms" /></td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="tiny" style={{ marginTop: 12 }}>
        Exact McNemar test, skeptic vs. rerun on the same mistakes: p = {p.toFixed(2)}. Between two identical runs,
        {" "}{sk.run_to_run_flips} of {sk.usable} verdicts changed (about 1 in 10) while the totals stayed the same.
      </p>
    </div>
  );
}

function Explanations({ s }: { s: Summary }) {
  const ex = s.wild.explanations;
  return (
    <div className="card">
      <h3>What the explanations reveal</h3>
      <p className="sub">The checker justifies every verdict in words, so each miss can be audited.</p>
      <div className="grid-2" style={{ gap: 12 }}>
        <div className="panel" style={{ margin: 0 }}>
          <div className="big" style={{ fontSize: 40 }}>{ex.missed_cites_request}/{ex.missed}</div>
          <div className="small muted">missed mistakes approved because "the action matches the customer's request"</div>
        </div>
        <div className="panel" style={{ margin: 0 }}>
          <div className="big" style={{ fontSize: 40 }}>{ex.missed_cites_confirmation}/{ex.missed}</div>
          <div className="small muted">point to the customer's confirmation as the evidence</div>
        </div>
      </div>
      <p className="callout wild" style={{ marginTop: 20 }}>
        <b>It treats the customer's "yes" as proof.</b> A planted mistake contradicts the conversation; a real one
        agrees with it, because the agent misunderstood, proposed something plausible, and the customer accepted.
      </p>
      <p className="tiny">Counted with simple keyword rules on the explanations; approximate.</p>
    </div>
  );
}

function ByAction({ s }: { s: Summary }) {
  const rows = Object.entries(s.wild.caught_by_action).sort((a, b) => b[1].n - a[1].n);
  return (
    <div className="card">
      <h3>By kind of change</h3>
      <p className="sub">Real mistakes caught, by the action the agent took. Small groups have wide intervals.</p>
      <table className="matrix">
        <tbody>
          {rows.map(([name, r]) => (
            <tr key={name}>
              <td className="cfg"><b>{ACTION_NAMES[name] ?? name}</b><span>{r.n} mistakes</span></td>
              <td style={{ width: "55%" }}><RateBar r={r} color="var(--wild)" what="caught" /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Wild({ s }: { s: Summary }) {
  return (
    <section id="wild">
      <div className="wrap">
        <p className="eyebrow" style={{ color: "var(--wild)" }}>Experiment 2 · In the wild</p>
        <h2>Real mistakes are a different problem</h2>
        <p className="lede">
          Of {s.wild.filter_overturned.n} suspected mistakes, the adjudicator overturned {s.wild.filter_overturned.k}: the outcome filter alone is
          wrong about a third of the time. The {s.wild.kept.mistakes} that remain are typically the wrong one of two
          similar orders, a variant in the wrong size or colour, swapped addresses, or a return that blocks the exchange
          the customer cared about more.
        </p>
        <div className="stack">
          <div className="grid-2">
            <Explanations s={s} />
            <ClueSplit s={s} />
          </div>
          <div className="grid-2">
            <Skeptic s={s} />
            <ByAction s={s} />
          </div>
        </div>
      </div>
    </section>
  );
}
