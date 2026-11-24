import { useEffect, useRef, useState, type ReactNode } from "react";
import { pctOf, type Rate, type Summary } from "../data";
import { rateTip, useTip } from "../ui";

// A scrollytelling walk through the headline result: the text scrolls, the chart stays pinned and changes
// with each step.

interface Row {
  key: string;
  label: string;
  sub: string;
  r: Rate;
  color: string;
}

interface Step {
  kicker: string;
  text: ReactNode;
  title: string;
  rows?: Row[];
  waffle?: { hit: number; of: number };
  foot: ReactNode;
}

function steps(s: Summary): Step[] {
  const planted = s.headline.planted_caught;
  const real = s.wild.full.caught;
  const records = s.wild.records.caught;
  const sk = s.skeptic;
  const clue = sk.caught_with_clue.original;
  const noClue = sk.caught_without_clue.original;
  const ex = s.wild.explanations;
  const P: Row = { key: "planted", label: "Planted mistakes", sub: "end check, full chat", r: planted, color: "var(--lab)" };
  const R: Row = { key: "real", label: "Real mistakes", sub: "same check, full chat", r: real, color: "var(--wild)" };
  const N: Row = { key: "records", label: "Real mistakes", sub: "records only, no chat", r: records, color: "#8c8a85" };
  return [
    {
      kicker: "In the lab",
      text: (
        <>
          We planted <b>{planted.n} mistakes</b> in a five-agent customer-service pipeline: a wrong order, a wrong
          item, a wrong payment. One AI check at the end, reading the full conversation, caught <b>every one</b>.
        </>
      ),
      title: "A perfect score on planted mistakes",
      rows: [P],
      foot: "Share of mistakes the checker flagged before the action ran.",
    },
    {
      kicker: "In the wild",
      text: (
        <>
          Then we collected <b>{real.n} mistakes</b> that agents really made in recorded conversations. The same
          checker, with the same prompt and the same view, caught <b>{real.k}</b>: just {pctOf(real)}%.
        </>
      ),
      title: "The same checker on real mistakes",
      rows: [P, R],
      foot: `Labels: an outcome filter and an adjudicator that sees the customer's secret goal must agree.`,
    },
    {
      kicker: "Without the conversation",
      text: (
        <>
          Take the conversation away and give it only the order records, and it catches <b>{records.k} of{" "}
          {records.n}</b>. What the customer said is most of the evidence.
        </>
      ),
      title: "Context is most of the evidence",
      rows: [P, R, N],
      foot: `False alarms on ${s.wild.kept.correct} correct actions: ${pctOf(s.wild.full.false_alarms)}% with the chat, ${pctOf(s.wild.records.false_alarms)}% without.`,
    },
    {
      kicker: "Why",
      text: (
        <>
          For <b>{100 - pctOf(sk.clue_in_chat)}%</b> of real mistakes, nothing in the chat shows anything is wrong: the customer agreed to it. The
          checker caught <b>{clue.k} of {clue.n}</b> mistakes that left a clue, and <b>{noClue.k} of {noClue.n}</b> that
          didn't.
        </>
      ),
      title: "Real mistakes often leave no clue",
      rows: [
        { key: "clue", label: "Clue in the chat", sub: "a reviewer could have spotted it", r: clue, color: "var(--wild)" },
        { key: "noclue", label: "No clue in the chat", sub: "the conversation looks fine", r: noClue, color: "#8c8a85" },
      ],
      foot: "Judged per mistake by a second model: could a reviewer who sees only the chat have known?",
    },
    {
      kicker: "Its own explanations",
      text: (
        <>
          Every verdict comes with a written reason, so we can read the misses. In <b>{ex.missed_cites_request} of{" "}
          {ex.missed}</b>, the checker approved because the action "matches the customer's request". It treats the
          customer's <b>"yes"</b> as proof.
        </>
      ),
      title: `${ex.missed_cites_request} of ${ex.missed} misses: "it's what the customer asked for"`,
      waffle: { hit: ex.missed_cites_request, of: ex.missed },
      foot: `Each square is a missed mistake. ${ex.missed_cites_confirmation} of ${ex.missed} cite the customer's confirmation. Keyword rules, approximate.`,
    },
    {
      kicker: "Prompting doesn't fix it",
      text: (
        <>
          Telling the checker that a yes is not proof changes nothing: <b>{pctOf(sk.caught.skeptic)}%</b> vs.{" "}
          {pctOf(sk.caught.baseline)}% for the same prompt run again (exact McNemar p ={" "}
          {sk.skeptic_vs_baseline.mistakes.p_value.toFixed(1)}).
        </>
      ),
      title: "A skeptical prompt, same result",
      rows: [
        { key: "base", label: "Original prompt, run again", sub: `${sk.usable} cases`, r: sk.caught.baseline, color: "var(--wild)" },
        { key: "skep", label: "Skeptical prompt", sub: '"a yes is not proof"', r: sk.caught.skeptic, color: "var(--navy)" },
      ],
      foot: `Between two identical runs, ${sk.run_to_run_flips} of ${sk.usable} verdicts flipped while the totals held.`,
    },
  ];
}

function Bar({ row }: { row: Row }) {
  const tip = useTip(rateTip(row.r, `${row.label.toLowerCase()} caught`));
  return (
    <div className="sg-row" {...tip}>
      <div className="lbl">
        <b>{row.label} <span>· {row.sub}</span></b>
        <span>{row.r.k} / {row.r.n}</span>
      </div>
      <div className="sg-bar">
        <span style={{ width: `${row.r.pct}%`, background: row.color }}>{pctOf(row.r)}%</span>
      </div>
    </div>
  );
}

function Graphic({ step }: { step: Step }) {
  return (
    <div className="card" aria-live="polite">
      <div className="sg-title">{step.title}</div>
      {step.rows && (
        <div className="sg-rows">
          {step.rows.map((r) => <Bar key={r.key} row={r} />)}
        </div>
      )}
      {step.waffle && (
        <div className="waffle" role="img" aria-label={`${step.waffle.hit} of ${step.waffle.of}`}>
          {Array.from({ length: step.waffle.of }, (_, i) => <i key={i} className={i < step.waffle!.hit ? "hit" : ""} />)}
        </div>
      )}
      <div className="sg-foot">{step.foot}</div>
    </div>
  );
}

export function Story({ s }: { s: Summary }) {
  const all = steps(s);
  const [active, setActive] = useState(0);
  const refs = useRef<(HTMLDivElement | null)[]>([]);

  useEffect(() => {
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) if (e.isIntersecting) setActive(Number((e.target as HTMLElement).dataset.i));
      },
      { rootMargin: "-45% 0px -45% 0px" },
    );
    refs.current.forEach((el) => el && io.observe(el));
    return () => io.disconnect();
  }, []);

  return (
    <section className="story-section" id="story" aria-label="The result, step by step">
      <div className="wrap story">
        <div className="story-steps">
          {all.map((st, i) => (
            <div key={st.kicker} className={`story-step ${i === active ? "on" : ""}`} data-i={i} ref={(el) => { refs.current[i] = el; }}>
              <div>
                <span className="kicker">{String(i + 1).padStart(2, "0")} · {st.kicker}</span>
                {st.text}
              </div>
            </div>
          ))}
        </div>
        <div className="story-graphic">
          <Graphic step={all[active]} />
        </div>
      </div>
    </section>
  );
}
