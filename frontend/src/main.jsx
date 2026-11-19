import React, { useState, useEffect } from 'react';
import { createRoot } from 'react-dom/client';
import { RouterProvider, useRouter } from './router';
import { HomePage } from './pages/HomePage';
import { WorkspacePage } from './pages/WorkspacePage';
import { sampleText, sampleClaims } from './engine';
import { checkHealth } from './api';
import './styles.css';

const initial = () => ({
  title: 'Active learning · literature review',
  analyzedTitle: 'Active learning · literature review',
  text: sampleText,
  claims: sampleClaims(),
  mode: 'Sample demo',
  reviews: {},
  history: []
});

function restore() {
  try {
    const x = JSON.parse(localStorage.getItem('vericite-v1'));
    return x && Array.isArray(x.claims) && typeof x.text === 'string' && x.reviews && Array.isArray(x.history)
      ? { ...x, analyzedTitle: x.analyzedTitle || x.title }
      : initial();
  } catch {
    return initial();
  }
}

function RootApp() {
  const { pathname } = useRouter();
  const [state, setState] = useState(restore);
  const [backendOnline, setBackendOnline] = useState(false);

  useEffect(() => {
    checkHealth()
      .then(() => setBackendOnline(true))
      .catch(() => setBackendOnline(false));
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem('vericite-v1', JSON.stringify(state));
    } catch {
      // storage unavailable
    }
  }, [state]);

  // Route matching:
  // "/" => Public Homepage
  // "/workspace*" => Verification & Simulation Workspace
  if (pathname === '/' || pathname === '') {
    return <HomePage />;
  }

  return (
    <WorkspacePage
      state={state}
      setState={setState}
      backendOnline={backendOnline}
    />
  );
}

const root = createRoot(document.getElementById('root'));
root.render(
  <RouterProvider>
    <RootApp />
  </RouterProvider>
);
