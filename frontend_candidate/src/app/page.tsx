import PlatformActivity from "@/components/PlatformActivity";
import Link from "next/link";
import type { ReactNode } from "react";


function IconCloudUpload() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M7 18a4.5 4.5 0 0 1-.6-8.96A5.5 5.5 0 0 1 17.3 8.05 4 4 0 0 1 17 18H7Z" />
      <path d="M12 12v6" />
      <path d="m9.5 14.5 2.5-2.5 2.5 2.5" />
    </svg>
  );
}

function IconBarChart() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 3v18h18" />
      <rect x="7" y="12" width="3" height="6" />
      <rect x="12" y="8" width="3" height="10" />
      <rect x="17" y="5" width="3" height="13" />
    </svg>
  );
}

function IconSearch() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </svg>
  );
}

function IconGear() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z" />
    </svg>
  );
}

function IconFileText() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" />
      <path d="M14 2v6h6" />
      <path d="M9 13h6M9 17h6M9 9h1" />
    </svg>
  );
}

function IconMap() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 6.5 9 4l6 2.5 6-2.5v15l-6 2.5-6-2.5-6 2.5z" />
      <path d="M9 4v15" />
      <path d="M15 6.5v15" />
    </svg>
  );
}

function IconArrowUpRight() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M7 17 17 7" />
      <path d="M7 7h10v10" />
    </svg>
  );
}

function IconMail() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <path d="m3 7 9 6 9-6" />
    </svg>
  );
}

function IconSignal() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 20v-7" />
      <path d="M8.5 16.5a5 5 0 0 1 0-7" />
      <path d="M15.5 9.5a5 5 0 0 1 0 7" />
      <path d="M5.5 19.5a9 9 0 0 1 0-13" />
      <path d="M18.5 6.5a9 9 0 0 1 0 13" />
      <circle cx="12" cy="10" r="1.4" fill="currentColor" stroke="none" />
    </svg>
  );
}


function FlowStep({
  number,
  icon,
  title,
  description,
  tone,
}: {
  number: number;
  icon: ReactNode;
  title: string;
  description: string;
  tone: string;
}) {
  return (
    <div className="v6-step">
      <div className={`v6-step-icon ${tone}`}>
        <span className="v6-step-number">{number}</span>
        {icon}
      </div>

      <h3>{title}</h3>
      <p>{description}</p>
    </div>
  );
}


function ForecastChart() {
  return (
    <svg
      viewBox="0 0 340 86"
      preserveAspectRatio="none"
      className="v6-chart"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="v6BlueFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#159cff" stopOpacity=".43" />
          <stop offset="100%" stopColor="#159cff" stopOpacity="0" />
        </linearGradient>

        <linearGradient id="v6PurpleFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#a35fff" stopOpacity=".34" />
          <stop offset="100%" stopColor="#a35fff" stopOpacity="0" />
        </linearGradient>
      </defs>

      <path
        d="M0,62
        C25,58 42,42 68,43
        C99,44 112,63 139,56
        C167,49 176,26 202,31
        C232,37 245,59 271,54
        C296,49 316,35 340,39
        L340,86 L0,86 Z"
        fill="url(#v6BlueFill)"
      />

      <path
        d="M0,62
        C25,58 42,42 68,43
        C99,44 112,63 139,56
        C167,49 176,26 202,31
        C232,37 245,59 271,54
        C296,49 316,35 340,39"
        fill="none"
        stroke="#16aaff"
        strokeWidth="2"
      />

      <path
        d="M0,73
        C34,70 52,67 78,67
        C111,66 128,53 154,55
        C183,56 196,30 222,30
        C255,31 279,54 340,34
        L340,86 L0,86 Z"
        fill="url(#v6PurpleFill)"
      />

      <path
        d="M0,73
        C34,70 52,67 78,67
        C111,66 128,53 154,55
        C183,56 196,30 222,30
        C255,31 279,54 340,34"
        fill="none"
        stroke="#a25fff"
        strokeWidth="1.8"
      />
    </svg>
  );
}


function ValidationChart() {
  const dots = [
    [28, 67], [45, 61], [63, 64], [81, 54],
    [99, 57], [116, 46], [135, 50], [153, 39],
    [172, 43], [190, 33], [207, 31], [225, 25],
    [243, 28], [261, 20], [279, 17], [299, 15],
  ];

  return (
    <svg
      viewBox="0 0 340 86"
      className="v6-chart"
      aria-hidden="true"
    >
      <g stroke="#12304c" strokeWidth="1">
        <line x1="0" y1="20" x2="340" y2="20" />
        <line x1="0" y1="43" x2="340" y2="43" />
        <line x1="0" y1="66" x2="340" y2="66" />

        <line x1="55" y1="0" x2="55" y2="86" />
        <line x1="110" y1="0" x2="110" y2="86" />
        <line x1="165" y1="0" x2="165" y2="86" />
        <line x1="220" y1="0" x2="220" y2="86" />
        <line x1="275" y1="0" x2="275" y2="86" />
      </g>

      <path
        d="M20,72 L309,11"
        stroke="#a25fff"
        strokeWidth="2"
        fill="none"
      />

      {dots.map(([x, y], index) => (
        <circle
          key={index}
          cx={x}
          cy={y}
          r="3.3"
          fill={index % 4 === 0 ? "#a25fff" : "#18cfff"}
        />
      ))}
    </svg>
  );
}


export default function Home() {
  return (
    <div className="v6-home">

      <section className="v6-hero">

        <div className="v6-city-panel">
          <img
            src="/images/home-v6-city-reference.png"
            alt=""
            className="v6-city-image"
          />
        </div>

        <div className="v6-city-blend" />

        <div className="v6-copy">

          <div className="v6-eyebrow">
            AI-POWERED. DATA-DRIVEN. HIGHER NETWORK PERFORMANCE.
          </div>

          <h1 className="v6-title">
            <span>Behavior-Aware</span>
            <strong>Predictive SON Platform</strong>
          </h1>

          <p className="v6-description">
            Forecast cellular traffic, validate predictions with real network data,
            and generate intelligent SON recommendations — all in one platform.
          </p>

          <div className="v6-accent" />

          <p className="v6-tagline">
            Smarter Networks for a More Connected World.
          </p>

          <div className="v6-workflow">

            <FlowStep
              number={1}
              icon={<IconCloudUpload />}
              title="Upload Network Data"
              description="Import KPIs, counters and configuration data."
              tone="blue"
            />

            <span className="v6-arrow">→</span>

            <FlowStep
              number={2}
              icon={<IconBarChart />}
              title="Run Forecast"
              description="Predict traffic and network behavior using AI/ML models."
              tone="cyan"
            />

            <span className="v6-arrow">→</span>

            <FlowStep
              number={3}
              icon={<IconSearch />}
              title="Validate with Actual Data"
              description="Compare and assess prediction accuracy."
              tone="purple"
            />

            <span className="v6-arrow">→</span>

            <FlowStep
              number={4}
              icon={<IconGear />}
              title="Generate SON Actions"
              description="Get AI-driven recommendations to optimize performance."
              tone="green"
            />

          </div>

        </div>

      </section>


      <section className="v6-cards">

        <Link href="/forecast" className="v6-card">

          <div className="v6-card-head">
            <div className="v6-card-icon blue"><IconBarChart /></div>
            <h2>Forecast</h2>
            <span className="v6-card-chevron">›</span>
          </div>

          <p>
            Predict future traffic and network behavior with advanced AI/ML models.
          </p>

          <div className="v6-card-chart">
            <ForecastChart />
          </div>

          <span className="v6-card-link">
            Create accurate forecasts
            <b>›</b>
          </span>

        </Link>


        <Link href="/validation" className="v6-card">

          <div className="v6-card-head">
            <div className="v6-card-icon blue"><IconSearch /></div>
            <h2>Test &amp; Validation</h2>
            <span className="v6-card-chevron">›</span>
          </div>

          <p>
            Validate predictions using actual network data and analyze accuracy.
          </p>

          <div className="v6-card-chart">
            <ValidationChart />
          </div>

          <span className="v6-card-link">
            Explore validation tools
            <b>›</b>
          </span>

        </Link>


        <Link href="/son" className="v6-card">

          <div className="v6-card-head">
            <div className="v6-card-icon green"><IconGear /></div>
            <h2>SON Recommendations</h2>
            <span className="v6-card-chevron">›</span>
          </div>

          <p>
            Get intelligent, prioritized SON actions to optimize network performance.
          </p>

          <div className="v6-son-list">

            <div>
              <strong className="son-green">↑</strong>
              <span>Energy Saving (ES)</span>
              <em className="high">High</em>
            </div>

            <div>
              <strong className="son-blue">○</strong>
              <span>Capacity Expansion (CAP)</span>
              <em className="medium">Medium</em>
            </div>

            <div>
              <strong className="son-purple">↓</strong>
              <span>Mobility Load Balancing (MLB)</span>
              <em className="medium">Medium</em>
            </div>

          </div>

          <span className="v6-card-link">
            View recommendations
            <b>›</b>
          </span>

        </Link>


        <Link href="/about" className="v6-card">

          <div className="v6-card-head">
            <div className="v6-card-icon blue"><IconFileText /></div>
            <h2>About &amp; Contact</h2>
            <span className="v6-card-chevron">›</span>
          </div>

          <p>
            Learn about the project, roadmap, and how to get in touch.
          </p>

          <div className="v6-about-grid">

            <div>
              <strong><IconMap /></strong>
              <span>Project Overview</span>
            </div>

            <div>
              <strong><IconArrowUpRight /></strong>
              <span>Roadmap</span>
            </div>

            <div>
              <strong><IconMail /></strong>
              <span>Contact Us</span>
            </div>

          </div>

          <span className="v6-card-link">
            Learn more
            <b>›</b>
          </span>

        </Link>

      </section>


      <footer className="v6-footer v6-footer-metrics">

        <div className="v6-footer-art">

          <img
            src="/images/home-v6-globe-reference.png"
            alt=""
            className="v6-footer-image"
          />

          <div className="v6-footer-fade" />

        </div>


        <PlatformActivity />

      </footer>

    </div>
  );
}
