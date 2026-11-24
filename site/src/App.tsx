import { useEffect, useState } from "react";
import { load, type Case, type LabExample, type Summary } from "./data";
import { Explorer } from "./sections/Explorer";
import { Hero, REPO, Setup } from "./sections/Intro";
import { Lab } from "./sections/Lab";
import { Story } from "./sections/Story";
import { Method, Takeaways } from "./sections/Outro";
import { Wild } from "./sections/Wild";
import { TipProvider } from "./ui";

interface Data {
  summary: Summary;
  lab: LabExample;
  cases: Case[];
}

export function App() {
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([load<Summary>("summary"), load<LabExample>("lab"), load<Case[]>("cases")])
      .then(([summary, lab, cases]) => setData({ summary, lab, cases }))
      .catch((e: Error) => setError(e.message));
  }, []);

  return (
    <TipProvider>
      <nav className="nav">
        <div className="nav-inner">
          <a className="nav-brand" href="#top">agent <i>blindspots</i></a>
          <div className="nav-links">
            <a href="#story">Story</a>
            <a href="#lab">In the lab</a>
            <a href="#wild">In the wild</a>
            <a href="#explorer">Explorer</a>
            <a href="#method">Method</a>
            <a href={REPO}>GitHub</a>
          </div>
        </div>
        <div className="progress" aria-hidden="true" />
      </nav>
      {error && <div className="loading">Couldn't load the data: {error}</div>}
      {!data && !error && <div className="loading">Loading results…</div>}
      {data && (
        <main>
          <Hero s={data.summary} />
          <Story s={data.summary} />
          <Setup s={data.summary} />
          <Lab s={data.summary} ex={data.lab} />
          <Wild s={data.summary} />
          <Explorer cases={data.cases} />
          <Takeaways s={data.summary} />
          <Method />
        </main>
      )}
      <footer>
        <div className="wrap">
          <span>Kuba Romanczuk · Emerging Trends in Explainable AI · Duke University · 2026</span>
          <a href={REPO}>Code, data and methods on GitHub</a>
        </div>
      </footer>
    </TipProvider>
  );
}
