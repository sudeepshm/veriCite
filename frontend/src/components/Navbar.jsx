import React, { useState, useEffect, useRef } from 'react';
import { 
  ShieldCheck, 
  Menu, 
  X, 
  ArrowRight, 
  FlaskConical, 
  LayoutDashboard, 
  FileText, 
  Search, 
  MessageSquare, 
  BookOpen, 
  History, 
  ChevronDown 
} from 'lucide-react';
import { Link, useRouter } from '../router';

export function Navbar() {
  const [platformOpen, setPlatformOpen] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const platformRef = useRef(null);
  const { navigate } = useRouter();

  // Close Platform dropdown on outside click
  useEffect(() => {
    function handleClickOutside(event) {
      if (platformRef.current && !platformRef.current.contains(event.target)) {
        setPlatformOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Close on Escape key
  useEffect(() => {
    function handleKeyDown(event) {
      if (event.key === 'Escape') {
        setPlatformOpen(false);
        setMobileMenuOpen(false);
      }
    }
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, []);

  return (
    <header className="home-header">
      <div className="home-header-container">
        {/* Brand */}
        <Link href="/" className="brand" aria-label="veriCite homepage">
          <span className="brand-icon">
            <ShieldCheck size={20} />
          </span>
          veri<span>Cite</span>
        </Link>

        {/* Desktop Navigation: veriCite · Platform ▾ · How it works · Open workspace */}
        <nav className="desktop-nav" aria-label="Main Navigation">
          {/* Platform Dropdown */}
          <div className="platform-dropdown-wrapper" ref={platformRef}>
            <button
              type="button"
              className={`platform-trigger ${platformOpen ? 'active' : ''}`}
              aria-expanded={platformOpen}
              aria-haspopup="true"
              onClick={() => setPlatformOpen(!platformOpen)}
            >
              <span>Platform</span>
              <ChevronDown size={15} className={`chevron-icon ${platformOpen ? 'rotated' : ''}`} />
            </button>

            {platformOpen && (
              <div className="platform-menu" role="menu" aria-label="veriCite Platform modules">
                <div className="platform-menu-inner">
                  {/* Group 1: Verify */}
                  <div className="platform-col" role="none">
                    <span className="platform-col-heading">VERIFY</span>
                    <Link
                      href="/workspace/verify"
                      className="platform-item"
                      role="menuitem"
                      onClick={() => setPlatformOpen(false)}
                    >
                      <div className="platform-item-icon">
                        <FileText size={17} />
                      </div>
                      <div className="platform-item-text">
                        <strong>Verify a document</strong>
                        <p>Upload a .txt manuscript with highlighted citation markers</p>
                      </div>
                    </Link>

                    <Link
                      href="/workspace/overview"
                      className="platform-item"
                      role="menuitem"
                      onClick={() => setPlatformOpen(false)}
                    >
                      <div className="platform-item-icon">
                        <LayoutDashboard size={17} />
                      </div>
                      <div className="platform-item-text">
                        <strong>Review claim evidence</strong>
                        <p>Inspect extracted claims, cited passages, and verdicts</p>
                      </div>
                    </Link>
                  </div>

                  {/* Group 2: Explore */}
                  <div className="platform-col" role="none">
                    <span className="platform-col-heading">EXPLORE</span>
                    <Link
                      href="/workspace/simulation"
                      className="platform-item platform-item-featured"
                      role="menuitem"
                      onClick={() => setPlatformOpen(false)}
                    >
                      <div className="platform-item-icon featured-icon">
                        <FlaskConical size={17} />
                      </div>
                      <div className="platform-item-text">
                        <div className="item-title-row">
                          <strong>Academic Simulation</strong>
                          <span className="item-badge">Planning</span>
                        </div>
                        <p>Research claim, validation environment, and comparator side by side</p>
                      </div>
                    </Link>

                    <Link
                      href="/workspace/simulation?step=4"
                      className="platform-item"
                      role="menuitem"
                      onClick={() => setPlatformOpen(false)}
                    >
                      <div className="platform-item-icon">
                        <Search size={17} />
                      </div>
                      <div className="platform-item-text">
                        <strong>Find citations</strong>
                        <p>Query registries and attach candidate baseline citations</p>
                      </div>
                    </Link>

                    <Link
                      href="/workspace/chat"
                      className="platform-item"
                      role="menuitem"
                      onClick={() => setPlatformOpen(false)}
                    >
                      <div className="platform-item-icon">
                        <MessageSquare size={17} />
                      </div>
                      <div className="platform-item-text">
                        <strong>Paper Chat</strong>
                        <p>Query claims and explore evidence with interactive Q&A</p>
                      </div>
                    </Link>
                  </div>

                  {/* Group 3: Review */}
                  <div className="platform-col" role="none">
                    <span className="platform-col-heading">REVIEW</span>
                    <Link
                      href="/workspace/references"
                      className="platform-item"
                      role="menuitem"
                      onClick={() => setPlatformOpen(false)}
                    >
                      <div className="platform-item-icon">
                        <BookOpen size={17} />
                      </div>
                      <div className="platform-item-text">
                        <strong>References</strong>
                        <p>Bibliography entries and linked claims audit trail</p>
                      </div>
                    </Link>

                    <Link
                      href="/workspace/history"
                      className="platform-item"
                      role="menuitem"
                      onClick={() => setPlatformOpen(false)}
                    >
                      <div className="platform-item-icon">
                        <History size={17} />
                      </div>
                      <div className="platform-item-text">
                        <strong>Review history</strong>
                        <p>Persistent record of auditor decisions and notes</p>
                      </div>
                    </Link>
                  </div>
                </div>
              </div>
            )}
          </div>

          <a href="#how-it-works" className="nav-item">How it works</a>
        </nav>

        {/* Right Action: Open workspace */}
        <div className="header-actions">
          <Link href="/workspace/verify" className="btn btn-primary primary-cta">
            Open workspace
            <ArrowRight size={15} />
          </Link>

          <button
            className="mobile-menu-btn"
            aria-label={mobileMenuOpen ? 'Close navigation menu' : 'Open navigation menu'}
            aria-expanded={mobileMenuOpen}
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          >
            {mobileMenuOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
      </div>

      {/* Accessible Mobile Menu Drawer */}
      {mobileMenuOpen && (
        <div className="mobile-nav-drawer" role="region" aria-label="Mobile Navigation">
          <div className="mobile-group">
            <span className="mobile-group-title">VERIFY</span>
            <Link
              href="/workspace/verify"
              className="mobile-nav-item"
              onClick={() => setMobileMenuOpen(false)}
            >
              <FileText size={17} />
              Verify a document
            </Link>
            <Link
              href="/workspace/overview"
              className="mobile-nav-item"
              onClick={() => setMobileMenuOpen(false)}
            >
              <LayoutDashboard size={17} />
              Review claim evidence
            </Link>
          </div>

          <div className="mobile-group">
            <span className="mobile-group-title">EXPLORE</span>
            <Link
              href="/workspace/simulation"
              className="mobile-nav-item mobile-featured"
              onClick={() => setMobileMenuOpen(false)}
            >
              <FlaskConical size={17} />
              Academic Simulation
            </Link>
            <Link
              href="/workspace/simulation?step=4"
              className="mobile-nav-item"
              onClick={() => setMobileMenuOpen(false)}
            >
              <Search size={17} />
              Find citations
            </Link>
            <Link
              href="/workspace/chat"
              className="mobile-nav-item"
              onClick={() => setMobileMenuOpen(false)}
            >
              <MessageSquare size={17} />
              Paper Chat
            </Link>
          </div>

          <div className="mobile-group">
            <span className="mobile-group-title">REVIEW</span>
            <Link
              href="/workspace/references"
              className="mobile-nav-item"
              onClick={() => setMobileMenuOpen(false)}
            >
              <BookOpen size={17} />
              References
            </Link>
            <Link
              href="/workspace/history"
              className="mobile-nav-item"
              onClick={() => setMobileMenuOpen(false)}
            >
              <History size={17} />
              Review history
            </Link>
          </div>

          <div className="mobile-nav-divider" />

          <a
            href="#how-it-works"
            className="mobile-nav-item"
            onClick={() => setMobileMenuOpen(false)}
          >
            How it works
          </a>

          <Link
            href="/workspace/verify"
            className="btn btn-primary mobile-open-btn"
            onClick={() => setMobileMenuOpen(false)}
          >
            Open workspace
            <ArrowRight size={15} />
          </Link>
        </div>
      )}
    </header>
  );
}
