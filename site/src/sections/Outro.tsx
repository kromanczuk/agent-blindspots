import { pctOf, type Summary } from "../data";
import { REPO } from "./Intro";

export function Takeaways({ s }: { s: Summary }) {
  const lw = s.lab.configs.lightweight;
  return (
    <section id="takeaways">
      <div className="wrap narrow">
        <p className="eyebrow">If you deploy AI agents</p>
        <h2>Three takeaways</h2>
        <div className="takeaways" style={{ marginTop: 32 }}>
          <div className="takeaway">
            <div>
              <h3>Check cheaply</h3>
              <p className="muted">
                Free rule checks after every agent plus one AI check with the full chat at the end caught every planted
                mistake, with {pctOf(lw.false_alarms)}% false alarms, for ${lw.cost_per_1000_runs.toFixed(2)} per 1,000 runs.
              </p>
            </div>
          </div>
          <div className="takeaway">
            <div>
              <h3>Don't trust planted-mistake scores</h3>
              <p className="muted">
                Measure checkers on real failures. An AI judge that knows the customer's goal can label them
                automatically, as long as a second signal has to agree.
              </p>
            </div>
          </div>
          <div className="takeaway">
            <div>
              <h3>Look beyond the checker</h3>
              <p className="muted">
                About 3 in 10 real mistakes leave no trace in the chat. Make agents read back exact item details
                (size, colour, which order) and send high-risk changes to a human.
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

export function Method() {
  return (
    <section id="method">
      <div className="wrap">
        <div className="grid-2" style={{ gap: 40 }}>
          <div>
            <p className="eyebrow">Limitations</p>
            <h2>What this does not show</h2>
            <ul className="clean muted">
              <li>Customers are simulated (GPT-4.1); a simulated customer sometimes accepts a wrong change a real one wouldn't.</li>
              <li>One checker model family (Claude Haiku 5.5) and one domain (retail).</li>
              <li>Labels come from an LLM adjudicator that can be wrong; requiring agreement with the outcome filter reduces, but doesn't remove, label noise.</li>
              <li>Planted and real mistakes come from different case sets, so the 100% vs 54% gap compares two test suites, not matched pairs.</li>
              <li>Modest samples: the intervals are wide, and only 12 confirmed faults took hold.</li>
              <li>Checker verdicts change about 1 in 10 between identical runs.</li>
            </ul>
          </div>
          <div>
            <p className="eyebrow">Reproduce it</p>
            <h2>Every number recomputes from saved results</h2>
            <p className="muted">No API keys and no benchmark download needed:</p>
            <pre className="cmd">{`git clone ${REPO}
cd agent-blindspots
make setup
make reproduce`}</pre>
            <p className="muted small">
              Agents and checkers: Claude Haiku 5.5. Adjudicator and clue judge: GPT-6.2 Sol (a different family, to
              reduce self-preference). About 6,700 model calls in total, each experiment run once. Data: τ²-bench by
              Sierra Research (MIT).
            </p>
            <a className="btn" href={REPO}>Code, data and methods →</a>
          </div>
        </div>
      </div>
    </section>
  );
}
