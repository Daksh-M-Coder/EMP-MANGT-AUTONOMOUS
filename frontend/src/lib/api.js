const BASE = '/api';

async function req(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: 'Request failed' }));
    throw new Error(err.error || `HTTP ${res.status}`);
  }
  return res.json();
}

export const api = {
  // Employees
  getEmployees: (params = {}) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([,v]) => v)).toString();
    return req(`/employees${qs ? '?' + qs : ''}`);
  },
  getEmployee: (id) => req(`/employees/${id}`),
  createEmployee: (data) => req('/employees', { method: 'POST', body: data }),
  updateEmployee: (id, data) => req(`/employees/${id}`, { method: 'PUT', body: data }),
  deleteEmployee: (id) => req(`/employees/${id}`, { method: 'DELETE' }),
  getDepartments: () => req('/employees/meta/departments'),
  getStats: () => req('/employees/meta/stats'),

  // AI
  chat: (message, history, session_id) => req('/ai/chat', { method: 'POST', body: { message, history, session_id } }),
  getSuggestions: () => req('/ai/suggestions'),

  // AI Draft Management
  createDraft: (draftData, proposedBy) => req('/ai/draft', { method: 'POST', body: { draft_data: draftData, proposed_by: proposedBy } }),
  getDrafts: (status = 'pending') => req(`/ai/drafts?status=${status}`),
  getDraft: (id) => req(`/ai/draft/${id}`),
  approveDraft: (id, reviewNotes = '', reviewedBy = 'hr_admin') => 
    req(`/ai/draft/${id}/approve`, { method: 'POST', body: { review_notes: reviewNotes, reviewed_by: reviewedBy } }),
  rejectDraft: (id, reviewNotes = '', reviewedBy = 'hr_admin') => 
    req(`/ai/draft/${id}/reject`, { method: 'POST', body: { review_notes: reviewNotes, reviewed_by: reviewedBy } }),
  getDraftStats: () => req('/ai/drafts/stats'),
};
