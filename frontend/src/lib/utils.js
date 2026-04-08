export function formatCurrency(val, compact = false) {
  if (!val) return '—';
  const n = Number(val);
  if (compact) {
    if (n >= 10000000) return `₹${(n/10000000).toFixed(1)}Cr`;
    if (n >= 100000) return `₹${(n/100000).toFixed(1)}L`;
    return `₹${n.toLocaleString('en-IN')}`;
  }
  return `₹${n.toLocaleString('en-IN')}`;
}

export function formatDate(d) {
  if (!d) return '—';
  return new Date(d).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
}

export function tenure(doj, dol) {
  const start = new Date(doj);
  const end = dol ? new Date(dol) : new Date();
  const months = Math.floor((end - start) / (1000 * 60 * 60 * 24 * 30.44));
  const years = Math.floor(months / 12);
  const rem = months % 12;
  if (years === 0) return `${rem}m`;
  if (rem === 0) return `${years}y`;
  return `${years}y ${rem}m`;
}

export function statusBadgeClass(status) {
  const map = {
    'Active': 'badge-active',
    'Probation': 'badge-probation',
    'On Leave': 'badge-leave',
    'Resigned': 'badge-resigned',
    'Terminated': 'badge-terminated',
  };
  return map[status] || 'badge-terminated';
}

export function levelColor(level) {
  const map = { L1:'bg-gray-100 text-gray-600', L2:'bg-slate-100 text-slate-600', L3:'bg-blue-50 text-blue-700', L4:'bg-indigo-50 text-indigo-700', L5:'bg-violet-50 text-violet-700', L6:'bg-purple-50 text-purple-700', L7:'bg-brand-100 text-brand-800' };
  return map[level] || 'bg-gray-100 text-gray-600';
}

export function getInitials(first, last) {
  return `${first?.[0] || ''}${last?.[0] || ''}`.toUpperCase();
}

export function avatarColor(name) {
  const colors = ['#4f46e5','#7c3aed','#0ea5e9','#10b981','#f59e0b','#ef4444','#ec4899','#14b8a6'];
  let hash = 0;
  for (let c of (name || 'A')) hash = c.charCodeAt(0) + ((hash << 5) - hash);
  return colors[Math.abs(hash) % colors.length];
}
