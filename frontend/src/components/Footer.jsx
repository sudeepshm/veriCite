import React from 'react';
import { ShieldCheck, ExternalLink, Github, ArrowUpRight } from 'lucide-react';
import { Link } from '../router';

export function Footer() {
  return (
    <footer className="public-footer">
      <div className="section-container">
        <div className="footer-top">
          <div className="footer-brand-col">
            <Link href="/" className="brand">
              <span className="brand-icon">
                <ShieldCheck size={20} />
              </span>
              veri<span>Cite</span>
            </Link>
            <p className="footer-tagline">
              Evidence first. Human judgment always. Trace manuscript claims to their cited passages, inspect verbatim evidence, and verify what the literature actually supports.
            </p>
          </div>

          <div className="footer-links-group">
            <div className="links-col">
              <h4>Navigation</h4>
              <ul>
                <li><Link href="/">Home</Link></li>
                <li><Link href="/workspace/verify">Verify document</Link></li>
                <li><Link href="/workspace/simulation">Academic Simulation</Link></li>
                <li><Link href="/workspace/overview">Workspace Overview</Link></li>
              </ul>
            </div>

            <div className="links-col">
              <h4>Resources</h4>
              <ul>
                <li><a href="#features">Core capabilities</a></li>
                <li><a href="#how-it-works">5-Stage verification</a></li>
                <li>
                  <a 
                    href="https://github.com/sudeepshm/veriCite" 
                    target="_blank" 
                    rel="noreferrer"
                    className="external-repo-link"
                  >
                    GitHub Repository
                    <ArrowUpRight size={13} />
                  </a>
                </li>
              </ul>
            </div>
          </div>
        </div>

        <div className="footer-bottom">
          <p>© {new Date().getFullYear()} veriCite · Open science citation verification and academic simulation.</p>
          <div className="footer-status-pill">
            <span className="status-live-dot" />
            <span>OpenAlex & Crossref metadata active</span>
          </div>
        </div>
      </div>
    </footer>
  );
}
