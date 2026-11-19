import React, { useEffect } from 'react';
import { Navbar } from '../components/Navbar';
import { Hero3D } from '../components/Hero3D';
import { Features } from '../components/Features';
import { WorkflowSection } from '../components/WorkflowSection';
import { SimulationPreview } from '../components/SimulationPreview';
import { Footer } from '../components/Footer';

export function HomePage() {
  useEffect(() => {
    document.title = 'veriCite — Traceable Citation Verification & Academic Simulation';
  }, []);

  return (
    <div className="home-layout">
      <Navbar />
      <main id="main-content">
        <Hero3D />
        <Features />
        <WorkflowSection />
        <SimulationPreview />
      </main>
      <Footer />
    </div>
  );
}
