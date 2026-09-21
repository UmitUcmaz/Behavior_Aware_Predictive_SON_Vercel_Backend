"use client";

import {
  useState,
} from "react";


type IconName =
  | "tower"
  | "chart"
  | "brain"
  | "users"
  | "globe"
  | "search"
  | "gear"
  | "layers"
  | "map"
  | "person"
  | "mail"
  | "linkedin"
  | "medium"
  | "github"
  | "arrow";


function LineIcon({
  name,
}: {
  name: IconName;
}) {

  const common = {
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap:
      "round" as const,
    strokeLinejoin:
      "round" as const,
  };


  if (name === "chart") {
    return (
      <svg
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <path
          {...common}
          d="M5 20V12M12 20V7M19 20V3"
        />
      </svg>
    );
  }


  if (name === "brain") {
    return (
      <svg
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <path
          {...common}
          d="M9 5a3 3 0 0 0-5 2.2A3.4 3.4 0 0 0 4.8 13 3 3 0 0 0 9 18"
        />
        <path
          {...common}
          d="M15 5a3 3 0 0 1 5 2.2A3.4 3.4 0 0 1 19.2 13 3 3 0 0 1 15 18"
        />
        <path
          {...common}
          d="M9 5v14M15 5v14M9 9h3M12 15h3"
        />
      </svg>
    );
  }


  if (name === "users") {
    return (
      <svg
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <circle
          {...common}
          cx="9"
          cy="8"
          r="3"
        />
        <circle
          {...common}
          cx="17"
          cy="9"
          r="2.4"
        />
        <path
          {...common}
          d="M3 20c.5-4 2.6-6 6-6s5.5 2 6 6M14 15c3.7-.8 6.2 1.1 7 4"
        />
      </svg>
    );
  }


  if (name === "globe") {
    return (
      <svg
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <circle
          {...common}
          cx="12"
          cy="12"
          r="9"
        />
        <path
          {...common}
          d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"
        />
      </svg>
    );
  }


  if (name === "search") {
    return (
      <svg
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <circle
          {...common}
          cx="10"
          cy="10"
          r="6"
        />
        <path
          {...common}
          d="m15 15 5 5"
        />
      </svg>
    );
  }


  if (name === "gear") {
    return (
      <svg
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <circle
          {...common}
          cx="12"
          cy="12"
          r="3"
        />
        <path
          {...common}
          d="M12 2v3M12 19v3M4.9 4.9 7 7M17 17l2.1 2.1M2 12h3M19 12h3M4.9 19.1 7 17M17 7l2.1-2.1"
        />
      </svg>
    );
  }


  if (name === "layers") {
    return (
      <svg
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <path
          {...common}
          d="m12 3 9 5-9 5-9-5 9-5Z"
        />
        <path
          {...common}
          d="m3 12 9 5 9-5M3 16l9 5 9-5"
        />
      </svg>
    );
  }


  if (name === "map") {
    return (
      <svg
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <path
          {...common}
          d="m3 5 6-2 6 2 6-2v16l-6 2-6-2-6 2V5Z"
        />
        <path
          {...common}
          d="M9 3v16M15 5v16"
        />
      </svg>
    );
  }


  if (name === "person") {
    return (
      <svg
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <circle
          {...common}
          cx="12"
          cy="7"
          r="4"
        />
        <path
          {...common}
          d="M4 21c.7-5 3.3-7 8-7s7.3 2 8 7"
        />
      </svg>
    );
  }


  if (name === "mail") {
    return (
      <svg
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <rect
          {...common}
          x="3"
          y="5"
          width="18"
          height="14"
          rx="2"
        />
        <path
          {...common}
          d="m4 7 8 6 8-6"
        />
      </svg>
    );
  }


  if (name === "linkedin") {
    return (
      <svg
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <rect
          {...common}
          x="3"
          y="3"
          width="18"
          height="18"
          rx="2"
        />
        <path
          {...common}
          d="M7 10v7M7 7.5v.1M11 17v-7M11 13c.7-2.1 5-2.4 5 1v3M16 17v-4"
        />
      </svg>
    );
  }


  if (name === "medium") {
    return (
      <svg
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <circle
          {...common}
          cx="12"
          cy="12"
          r="9"
        />
        <path
          {...common}
          d="M7 16V8l5 6 5-6v8"
        />
      </svg>
    );
  }


  if (name === "github") {
    return (
      <svg
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <path
          {...common}
          d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.9a3.4 3.4 0 0 0-.9-2.6c3 0 6.1-1.5 6.1-6.8a5.3 5.3 0 0 0-1.4-3.7 5 5 0 0 0-.1-3.7S18.6 1 16 2.7a13.4 13.4 0 0 0-7 0C6.4 1 5.3 1.3 5.3 1.3A5 5 0 0 0 5.2 5a5.3 5.3 0 0 0-1.4 3.7c0 5.3 3.1 6.8 6.1 6.8a3.4 3.4 0 0 0-.9 2.6V22"
        />
      </svg>
    );
  }


  if (name === "arrow") {
    return (
      <svg
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <path
          {...common}
          d="M5 12h14M14 7l5 5-5 5"
        />
      </svg>
    );
  }


  return (
    <svg
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <path
        {...common}
        d="M12 3v18M8 21h8M9 8l3-5 3 5M7 12l5-4 5 4M5 16l7-4 7 4"
      />
      <path
        {...common}
        d="M5 6C2 8 2 12 5 14M19 6c3 2 3 6 0 8"
      />
    </svg>
  );
}


// BAPS-ABOUT-CONTACT-FINAL-V1
const capabilities = [
  {
    icon: "chart" as IconName,
    title: "Forecast",
    text:
      "Forecast UL/DL PRB utilization and active users from historical cellular traffic.",
  },
  {
    icon: "search" as IconName,
    title: "Test & Validation",
    text:
      "Compare forecasts with actual network traffic using matched timestamps and KPI accuracy metrics.",
  },
  {
    icon: "gear" as IconName,
    title: "SON Recommendations",
    text:
      "Translate forecasted conditions into configurable ES, MLB and CAP recommendations.",
  },
  {
    icon: "layers" as IconName,
    title: "Modular Architecture",
    text:
      "Built for richer network context, multi-RAT evolution and future vendor-aware automation.",
  },
];


const roadmap = [
  {
    number: "1",
    title: "Multi-RAT evolution",
    text:
      "Extend capabilities across multiple radio access technologies with unified intelligence.",
  },
  {
    number: "2",
    title: "Richer network context",
    text:
      "Incorporate mobility, events, topology and additional network signals.",
  },
  {
    number: "3",
    title: "Vendor-aware automation",
    text:
      "Support multi-vendor environments with standardized recommendations and interfaces.",
  },
  {
    number: "4",
    title: "Command generation",
    text:
      "Enable assisted and closed-loop automation with ready-to-execute configuration workflows.",
  },
];


export default function AboutPage() {

  const [
    imageAvailable,
    setImageAvailable,
  ] = useState(true);


  return (

    <main className="about-v1-page">

      <section className="about-v1-hero">

        <div className="about-v1-hero-copy">

          <div className="about-v1-eyebrow">
            PEOPLE · TECHNOLOGY · SMARTER NETWORKS
          </div>

          <h1>
            About &{" "}
            <span>
              Contact
            </span>
          </h1>

          <p>
            Learn about the project,
            roadmap, and how to get in touch.
          </p>

          <div className="about-v1-accent" />

        </div>


        <div className="about-v1-hero-quote">

          <em>
            AI for smarter networks.
            <br />
            A more connected world.
          </em>

          <div />

        </div>

      </section>


      <section className="about-v1-content">

        {/* ==================================================
            PROJECT OVERVIEW
        ================================================== */}

        <article className="about-v1-panel about-v1-overview">

          <div className="about-v1-overview-main">

            <div className="about-v1-large-icon">
              <LineIcon name="tower" />
            </div>


            <div>

              <h2>
                Project Overview
              </h2>

              <p>
                The Behavior-Aware Predictive SON Platform
                combines ML-based cellular traffic forecasting
                with predictive SON decision support. Using real
                network data, it forecasts UL/DL PRB utilization
                and active users, validates predictions against
                actual network traffic, and converts forecasted
                conditions into actionable ES, MLB and CAP
                recommendations. The platform is designed as a
                modular foundation for richer network context,
                multi-RAT evolution, and future vendor-aware
                automation.
              </p>

            </div>

          </div>


          <div className="about-v1-values">

            <div>

              <div className="about-v1-value-icon">
                <LineIcon name="chart" />
              </div>

              <strong>
                Data-Driven
                <br />
                Intelligence
              </strong>

              <span>
                Turn network data into
                actionable insights
              </span>

            </div>


            <div>

              <div className="about-v1-value-icon">
                <LineIcon name="brain" />
              </div>

              <strong>
                Predictive
                <br />
                SON
              </strong>

              <span>
                Anticipate,
                not just react
              </span>

            </div>


            <div>

              <div className="about-v1-value-icon">
                <LineIcon name="gear" />
              </div>

              <strong>
                Proactive
                <br />
                Operations
              </strong>

              <span>
                Forecast, validate,
                and act earlier
              </span>

            </div>


            <div>

              <div className="about-v1-value-icon">
                <LineIcon name="globe" />
              </div>

              <strong>
                A More
                <br />
                Connected World
              </strong>

              <span>
                Smarter networks
                for a brighter tomorrow
              </span>

            </div>

          </div>

        </article>


        {/* ==================================================
            MIDDLE GRID
        ================================================== */}

        <div className="about-v1-middle-grid">

          <article className="about-v1-panel">

            <div className="about-v1-section-heading">

              <div>

                <span className="about-v1-heading-icon">
                  <LineIcon name="gear" />
                </span>

                <h2>
                  Core Capabilities
                </h2>

              </div>

              <small>
                The key building blocks
                of the platform
              </small>

            </div>


            <div className="about-v1-capabilities">

              {capabilities.map(
                (
                  item
                ) => (

                  <div
                    className="about-v1-capability"
                    key={
                      item.title
                    }
                  >

                    <div className="about-v1-capability-icon">
                      <LineIcon name={item.icon} />
                    </div>

                    <h3>
                      {item.title}
                    </h3>

                    <p>
                      {item.text}
                    </p>

                  </div>

                )
              )}

            </div>

          </article>


          <article className="about-v1-panel">

            <div className="about-v1-section-heading">

              <div>

                <span className="about-v1-heading-icon">
                  <LineIcon name="map" />
                </span>

                <h2>
                  Roadmap
                </h2>

              </div>

              <small>
                Future enhancements
                and vision
              </small>

            </div>


            <div className="about-v1-roadmap">

              {roadmap.map(
                (
                  item,
                  index
                ) => (

                  <div
                    className={
                      `about-v1-roadmap-item roadmap-${index + 1}`
                    }
                    key={
                      item.number
                    }
                  >

                    <div className="about-v1-roadmap-number">
                      {item.number}
                    </div>

                    <div className="about-v1-roadmap-line" />

                    <strong>
                      {item.title}
                    </strong>

                    <p>
                      {item.text}
                    </p>

                  </div>

                )
              )}

            </div>

          </article>

        </div>


        {/* ==================================================
            BOTTOM GRID
        ================================================== */}

        <div className="about-v1-bottom-grid">

          <article className="about-v1-panel about-v1-designer">

            <div className="about-v1-section-heading about-v1-designer-title">

              <div>

                <span className="about-v1-heading-icon">
                  <LineIcon name="person" />
                </span>

                <h2>
                  Project Designer & Developer
                </h2>

              </div>

            </div>


            <div className="about-v1-designer-content">

              <div className="about-v1-profile-photo">

                <span>
                  UU
                </span>

                {imageAvailable && (

                  <img
                    src="/images/about-profile.jpg"
                    alt="Project designer profile"
                    onError={
                      () =>
                        setImageAvailable(
                          false
                        )
                    }
                  />

                )}

              </div>


              <div className="about-v1-profile-copy">

                <h3>
                  Ümit Uçmaz
                </h3>

                <strong>
                  Senior Service Delivery Engineer
                  <i>•</i>
                  SON (Self-Organizing Network) Expert
                  <i>•</i>
                  AI/Machine-Learning
                </strong>

                <p>
                  Passionate about applying AI
                  and data-driven approaches to
                  real-world telecommunications
                  problems. Focused on building
                  practical, impactful solutions
                  for smarter and more efficient
                  networks.
                </p>

              </div>


              <blockquote>

                “Turning network data
                into smarter decisions
                for a more connected world.”

                <span />

              </blockquote>

            </div>

          </article>


          <article className="about-v1-panel about-v1-contact">

            <div className="about-v1-section-heading">

              <div>

                <span className="about-v1-heading-icon">
                  <LineIcon name="mail" />
                </span>

                <div>

                  <h2>
                    Contact
                  </h2>

                  <p>
                    Connect for project questions,
                    collaboration, technical discussion,
                    or feedback.
                  </p>

                </div>

              </div>

              <small>
                Let&apos;s connect
              </small>

            </div>


            <div className="about-v1-contact-grid">

              <a
                href="https://www.linkedin.com/in/umitucmaz"
                target="_blank"
                rel="noopener noreferrer"
                aria-label="Open Ümit Uçmaz LinkedIn profile"
              >

                <span className="about-v1-contact-icon linkedin">
                  <LineIcon name="linkedin" />
                </span>

                <div>

                  <strong>
                    LinkedIn
                  </strong>

                  <p>
                    Connect professionally
                  </p>

                </div>

                <span className="about-v1-contact-arrow">
                  <LineIcon name="arrow" />
                </span>

              </a>


              <a
                href="https://medium.com/@umitucmaz.project/from-cellular-traffic-forecasting-to-behavior-aware-predictive-son-c38f5d2c4686"
                target="_blank"
                rel="noopener noreferrer"
                aria-label="Read Ümit Uçmaz project article on Medium"
              >

                <span className="about-v1-contact-icon medium">
                  <LineIcon name="medium" />
                </span>

                <div>

                  <strong>
                    Medium
                  </strong>

                  <p>
                    Read project insights
                  </p>

                </div>

                <span className="about-v1-contact-arrow">
                  <LineIcon name="arrow" />
                </span>

              </a>


              <a
                href="https://github.com/UmitUcmaz/Behavior_Aware_Predictive_SON_Vercel_Backend"
                target="_blank"
                rel="noopener noreferrer"
                aria-label="Open Ümit Uçmaz GitHub profile"
              >

                <span className="about-v1-contact-icon github">
                  <LineIcon name="github" />
                </span>

                <div>

                  <strong>
                    GitHub
                  </strong>

                  <p>
                    View source & development
                  </p>

                </div>

                <span className="about-v1-contact-arrow">
                  <LineIcon name="arrow" />
                </span>

              </a>


              <a
                href="mailto:umitucmaz.project@gmail.com?subject=Behavior-Aware%20Predictive%20SON%20Platform"
                aria-label="Email Ümit Uçmaz about the Behavior-Aware Predictive SON Platform"
              >

                <span className="about-v1-contact-icon email">
                  <LineIcon name="mail" />
                </span>

                <div>

                  <strong>
                    Email
                  </strong>

                  <p>
                    Send a project message
                  </p>

                </div>

                <span className="about-v1-contact-arrow">
                  <LineIcon name="arrow" />
                </span>

              </a>

            </div>

          </article>

        </div>

      </section>


      <footer className="about-v1-footer">

        <div>

          <span className="about-v1-footer-logo">
            <LineIcon name="tower" />
          </span>

          <p>
            Turning Network Data into
            <br />
            Smarter Decisions
          </p>

        </div>


        <div className="about-v1-footer-world" />


        <div className="about-v1-footer-tagline">

          BETTER NETWORKS ·
          BRIGHTER POSSIBILITIES.

          <span />

        </div>

      </footer>

    </main>
  );
}
