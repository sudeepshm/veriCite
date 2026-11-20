const rawBase = (typeof import.meta !== 'undefined' && import.meta.env && import.meta.env.VITE_API_BASE_URL) || '';
const API_BASE = rawBase.replace(/\/+$/, '');

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

export const submitDocumentFile = (file) => {
  const formData = new FormData();
  formData.append('file', file);
  return request('/api/verify/upload', {
    method: 'POST',
    body: formData,
  });
};

export const getJobStatus = (jobId) => request(`/api/verify/${jobId}`);

export const getJobClaims = (jobId) => request(`/api/verify/${jobId}/claims`);

export const getJobReport = (jobId) => request(`/api/verify/${jobId}/report`);

export const searchEvidence = (query, limit = 5, providers = null) =>
  request(`/api/evidence/search?q=${encodeURIComponent(query)}&limit=${limit}${providers ? `&providers=${encodeURIComponent(providers)}` : ''}`);

export const checkOpenAccess = (doi) =>
  request(`/api/evidence/open-access?doi=${encodeURIComponent(doi)}`);
