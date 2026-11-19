const API_BASE = '';

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, options);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

export const checkHealth = () => request('/api/health');

export const submitDocument = (text, filename = 'document.txt') =>
  request('/api/verify', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, filename }),
  });

export const getJobStatus = (jobId) => request(`/api/verify/${jobId}`);

export const getJobClaims = (jobId) => request(`/api/verify/${jobId}/claims`);

export const getJobReport = (jobId) => request(`/api/verify/${jobId}/report`);

export const searchEvidence = (query, limit = 5) =>
  request(`/api/evidence/search?q=${encodeURIComponent(query)}&limit=${limit}`);

export const checkOpenAccess = (doi) =>
  request(`/api/evidence/open-access?doi=${encodeURIComponent(doi)}`);
