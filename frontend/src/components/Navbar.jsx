import React, { useState } from 'react';
import { ShieldCheck, Menu, X, ArrowRight, FlaskConical, LayoutDashboard, FileText } from 'lucide-react';
import { Link, useRouter } from '../router';

export function Navbar() {
  const [menuOpen, setMenuOpen] = useState(false);
  const { navigate } = useRouter();

  return (
    <header className="home-header">
      <div className="home-header-container">
        <Link href="/" className="brand" aria-label="veriCite homepage">
          <span className="brand-icon">
            <ShieldCheck size={20} />
          </span>
          veri<span>Cite</span>
        </Link>

        <nav className="desktop-nav" aria-label="Main Navigation">
          <a href="#features" className="nav-item">Features</a>
          <a href="#how-it-works" className="nav-item">How it works</a>
          <Link href="/workspace/simulation" className="nav-item simulation-nav-link">
            <FlaskConical size={16} />
            Academic Simulation
          </Link>
        </nav>

        <div className="header-actions">
          <Link href="/workspace/verify" className="btn btn-primary primary-cta">
            Open workspace
            <ArrowRight size={15} />
          </Link>

          <button
            className="mobile-menu-btn"
            aria-label={menuOpen ? 'Close navigation menu' : 'Open navigation menu'}
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen(!menuOpen)}
          >
            {menuOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
      </div>

      {menuOpen && (
        <div className="mobile-nav-drawer" role="region" aria-label="Mobile Navigation">
          <a
            href="#features"
            className="mobile-nav-item"
            onClick={() => setMenuOpen(false)}
          >
            Features
          </a>
          <a
            href="#how-it-works"
            className="mobile-nav-item"
            onClick={() => setMenuOpen(false)}
          >
            How it works
          </a>
          <Link
            href="/workspace/simulation"
            className="mobile-nav-item"
            onClick={() => setMenuOpen(false)}
          >
            <FlaskConical size={17} />
            Academic Simulation
          </Link>
          <div className="mobile-nav-divider" />
          <Link
            href="/workspace/verify"
            className="mobile-nav-item"
            onClick={() => setMenuOpen(false)}
          >
            <FileText size={17} />
            Verify document
          </Link>
          <Link
            href="/workspace/overview"
            className="mobile-nav-item"
            onClick={() => setMenuOpen(false)}
          >
            <LayoutDashboard size={17} />
            Document Overview
          </Link>
        </div>
      )}
    </header>
  );
}
