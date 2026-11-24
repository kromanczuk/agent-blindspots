import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { pctOf, type Rate } from "./data";

// ------------------------------------------------------------------ tooltip (one per page)

type TipState = { x: number; y: number; content: ReactNode } | null;
const TipContext = createContext<(t: TipState) => void>(() => {});

export function TipProvider({ children }: { children: ReactNode }) {
  const [tip, setTip] = useState<TipState>(null);
  return (
    <TipContext.Provider value={setTip}>
      {children}
      {tip && (
        <div className="tip" role="tooltip" style={{ left: tip.x + 14, top: tip.y + 14 }}>
          {tip.content}
        </div>
      )}
    </TipContext.Provider>
  );
}

/** Props that show `content` in the shared tooltip on hover and keyboard focus. */
export function useTip(content: ReactNode) {
  const set = useContext(TipContext);
  const show = useCallback(
    (x: number, y: number) => set({ x, y, content }),
    [set, content],
  );
  return {
    tabIndex: 0,
    onPointerMove: (e: React.PointerEvent) => show(e.clientX, e.clientY),
    onPointerLeave: () => set(null),
    onFocus: (e: React.FocusEvent) => {
      const r = (e.target as HTMLElement).getBoundingClientRect();
      show(r.left, r.bottom);
    },
    onBlur: () => set(null),
  };
}

export function rateTip(r: Rate, what: string) {
  return (
    <>
      <b>{pctOf(r)}%</b> {what}
      <br />
      {r.k} of {r.n} · 95% CI {Math.round(r.lo)}–{Math.round(r.hi)}%
    </>
  );
}

// ------------------------------------------------------------------ marks

/** A horizontal proportion bar with its Wilson interval drawn as a thin line. */
export function RateBar({ r, color, what }: { r: Rate; color: string; what: string }) {
  const tip = useTip(rateTip(r, what));
  return (
    <div className="barcell" {...tip} aria-label={`${pctOf(r)}% ${what}, ${r.k} of ${r.n}`}>
      <div className="bar">
        <span style={{ width: `${r.pct}%`, background: color }} />
        <i className="ci" style={{ left: `${r.lo}%`, width: `${Math.max(r.hi - r.lo, 0.5)}%` }} />
      </div>
      <span className="v">{pctOf(r)}%</span>
    </div>
  );
}

// ------------------------------------------------------------------ badges (icon + label, never colour alone)

const icons = {
  check: <path d="M3 7.5 5.8 10 11 4.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />,
  cross: <path d="m4 4 6 6m0-6-6 6" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />,
  dot: <circle cx="7" cy="7" r="2.5" fill="currentColor" />,
};

export function Badge({ tone, icon, children }: { tone: "good" | "bad" | "neutral" | "warn"; icon?: keyof typeof icons; children: ReactNode }) {
  return (
    <span className={`badge ${tone}`}>
      {icon && (
        <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
          {icons[icon]}
        </svg>
      )}
      {children}
    </span>
  );
}

/** How a checker verdict reads, given whether the action was really a mistake. */
export function VerdictBadge({ flagged, mistake }: { flagged: boolean; mistake: boolean }) {
  if (mistake) return flagged ? <Badge tone="good" icon="check">Caught</Badge> : <Badge tone="bad" icon="cross">Missed</Badge>;
  return flagged ? <Badge tone="bad" icon="cross">False alarm</Badge> : <Badge tone="good" icon="check">Approved</Badge>;
}
