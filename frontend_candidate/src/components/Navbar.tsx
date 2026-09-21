"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const mainNavItems = [
  { label: "Home", href: "/" },
  { label: "Forecast", href: "/forecast" },
  { label: "Test & Validation", href: "/validation" },
  { label: "SON Recommendations", href: "/son" },
  { label: "Action Engine", href: "/action-engine" },
];

const secondaryNavItems = [
  { label: "About & Contact", href: "/about" },
];

function TowerLogo() {
  return (
    <svg viewBox="0 0 52 52" className="tower-logo" aria-hidden="true">
      <circle cx="26" cy="11" r="2.4" fill="currentColor" />
      <path d="M26 14 L19 45" />
      <path d="M26 14 L33 45" />
      <path d="M20 24 H32" />
      <path d="M18 33 H34" />
      <path d="M16 42 H36" />
      <path d="M16 15 C9 21 9 31 16 37" />
      <path d="M36 15 C43 21 43 31 36 37" />
      <path d="M11 10 C1 18 1 34 11 42" />
      <path d="M41 10 C51 18 51 34 41 42" />
    </svg>
  );
}

export default function Navbar() {
  const pathname = usePathname();

  const isActive = (href: string) => {
    return href === "/" ? pathname === "/" : pathname.startsWith(href);
  };

  return (
    <header className="top-header">
      <div className="top-nav">
        <Link href="/" className="top-brand">
          <TowerLogo />

          <div className="top-brand-text">
            <span>Behavior-Aware Predictive SON</span>
            <strong>Platform</strong>
          </div>
        </Link>

        <div className="top-links-wrap">
          <nav className="top-links top-links-main">
            {mainNavItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={`top-link ${isActive(item.href) ? "active" : ""}`}
              >
                {item.label}
              </Link>
            ))}
          </nav>

          <nav className="top-links top-links-secondary">
            {secondaryNavItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={`top-link ${isActive(item.href) ? "active" : ""}`}
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </div>
      </div>
    </header>
  );
}
