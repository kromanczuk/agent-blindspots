import { pct, type Summary } from "../data";
import { rateTip, useTip } from "../ui";

export const REPO = "https://github.com/kromanczuk/agent-blindspots";

function Big({ value, label, sub, color, tip }: { value: string; label: string; sub: string; color: string; tip: React.ReactNode }) {
  const t = useTip(tip);
  return (
    <div {...t}>
      <div className="big" style={{ color }}>{value}</div>
      <div className="big-label">{label}</div>
      <div className="big-sub">{sub}</div>
      <div className="meter"><span style={{ width: value, background: color }} /></div>
    </div>
  );
}

export function Hero({ s }: { s: Summary }) {
  const { planted_caught: planted, real_caught: real } = s.headline;
  return (
    <section className="hero" id="top">
      <div className="wrap">
        <p className="eyebrow">An explorable study · Explainable AI · Agent safety</p>
        <h1>
          Perfect <span className="lab">in the lab</span>,<br />
          <span className="wild">{pct(real)} in the wild.</span>
        </h1>
        <p className="lede">
          AI agents now issue refunds, exchanges and cancellations for real customers. The usual safety net is a
          checker: a second model that reviews each action before it runs. Checkers are tested on mistakes we
          plant ourselves. Does a perfect score on those tell you anything about the mistakes agents actually make?
        </p>
        <div className="byline">
          <span><b>Kuba Romanczuk</b></span>
          <span>Duke University · MEng</span>
          <span>Emerging Trends in Explainable AI · 2026</span>
          <span>Data: τ²-bench retail</span>
        </div>
        <div className="duel">
          <Big value={pct(planted)} label="of planted mistakes caught" color="var(--lab)"
               sub={`${planted.k} of ${planted.n} faults planted in a five-agent pipeline that reached the final action`}
               tip={rateTip(planted, "of planted mistakes caught")} />
          <Big value={pct(real)} label="of real mistakes caught" color="var(--wild)"
               sub={`${real.k} of ${real.n} genuine mistakes from recorded agent conversations`}
               tip={rateTip(real, "of real mistakes caught")} />
        </div>
        <p className="small muted" style={{ marginTop: 16 }}>
          Same checker model, same prompt, same full view of the conversation. The checker's own explanations show
          why it misses: it treats the customer's "yes" as proof.
        </p>
        <div className="hero-actions">
          <a className="btn primary" href="#story">Read the story ↓</a>
          <a className="btn" href="#explorer">Explore the real mistakes</a>
          <a className="btn" href={REPO}>Code &amp; data on GitHub</a>
          <a className="btn" href={`${REPO}/blob/main/docs/poster.pdf`}>Poster (PDF)</a>
        </div>
      </div>
    </section>
  );
}

const STAGES = [
  { name: "Conversation", note: "customer ↔ agent", cls: "src" },
  { name: "Intake", note: "reads the chat" },
  { name: "Verifier", note: "checks ownership" },
  { name: "Pricing", note: "works out refund" },
  { name: "Policy", note: "applies store rules" },
  { name: "Planner", note: "writes the tool call" },
  { name: "Database write", note: "the final action", cls: "out" },
];

export function Setup({ s }: { s: Summary }) {
  return (
    <section id="setup">
      <div className="wrap">
        <p className="eyebrow">The setup</p>
        <h2>Two ways to test the same checker</h2>
        <p className="lede">
          Both experiments use τ²-bench retail: 114 customer-service tasks with a real store policy, an order database
          and 1,824 recorded conversations from four agent models. The simulated customer follows a secret script the
          agent never sees, which is what makes automatic labelling possible.
        </p>

        <div className="grid-2 reveal">
          <div className="card">
            <p className="eyebrow" style={{ color: "var(--lab)" }}>Experiment 1 · In the lab</p>
            <h3>Plant a mistake, see who catches it</h3>
            <p className="sub" style={{ marginTop: 8 }}>
              {s.lab.cases} clean conversations, cut just before the agent's change, run through a five-agent chain.
              A wrong order, item or payment is planted at hand-off 1, 2 or 4, or written into the conversation as a
              wrong read-back the customer agrees to.
            </p>
          </div>
          <div className="card">
            <p className="eyebrow" style={{ color: "var(--wild)" }}>Experiment 2 · In the wild</p>
            <h3>Collect the mistakes agents really made</h3>
            <p className="sub" style={{ marginTop: 8 }}>
              Write actions from failed conversations that weren't the expected change. A strong model from another
              family, shown the customer's secret goal, labels each one. Only cases where the outcome filter and this
              adjudicator agree are kept: {s.wild.kept.mistakes} real mistakes, {s.wild.kept.correct} correct actions.
            </p>
          </div>
        </div>

        <div className="card reveal" style={{ marginTop: 24 }}>
          <h3>The lab pipeline</h3>
          <p className="sub">Only intake sees the conversation. Every hand-off and the final action can be checked.</p>
          <div className="pipeline" role="img" aria-label="Conversation, then intake, verifier, pricing, policy and planner agents, then the database write">
            {STAGES.map((st, i) => (
              <div key={st.name} style={{ display: "contents" }}>
                {i > 0 && (
                  <div className="link">
                    <div className="arrow" />
                    {i >= 2 && i <= 5 && <div className="hop">h{i - 1}</div>}
                  </div>
                )}
                <div className={`stage ${st.cls ?? ""}`}>
                  <b>{st.name}</b>
                  <span>{st.note}</span>
                </div>
              </div>
            ))}
          </div>
          <div className="kinds">
            <div className="kind"><b>Rules</b>Every ID must appear in the chat. Free, instant, no false alarms.</div>
            <div className="kind"><b>AI check, full chat</b>A model compares the hand-off with the original conversation.</div>
            <div className="kind"><b>AI check, records only</b>A model sees the looked-up records but not what the customer said.</div>
          </div>
        </div>
      </div>
    </section>
  );
}
