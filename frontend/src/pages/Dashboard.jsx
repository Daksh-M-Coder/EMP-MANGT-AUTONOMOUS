import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Users, TrendingUp, MapPin, UserCheck, UserX, Clock, ArrowRight, Briefcase } from 'lucide-react';
import { api } from '../lib/api';
import { formatCurrency, formatDate, tenure, getInitials, avatarColor } from '../lib/utils';

function StatCard({ icon: Icon, label, value, sub, color = 'indigo' }) {
  const colors = {
    indigo: 'bg-indigo-50 text-indigo-600',
    emerald: 'bg-emerald-50 text-emerald-600',
    amber: 'bg-amber-50 text-amber-600',
    rose: 'bg-rose-50 text-rose-600',
    violet: 'bg-violet-50 text-violet-600',
  };
  return (
    <div className="card p-5">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</p>
          <p className="text-3xl font-display font-bold text-gray-900 mt-1">{value}</p>
          {sub && <p className="text-xs text-gray-500 mt-1">{sub}</p>}
        </div>
        <div className={`p-2.5 rounded-xl ${colors[color]}`}>
          <Icon size={20} />
        </div>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getStats().then(setStats).finally(() => setLoading(false));
  }, []);

  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <div className="flex gap-1"><span className="typing-dot"/><span className="typing-dot"/><span className="typing-dot"/></div>
    </div>
  );

  if (!stats) return <div className="p-8 text-gray-500">Failed to load dashboard</div>;

  const maleCount = stats.byGender.find(g => g.gender === 'Male')?.count || 0;
  const femaleCount = stats.byGender.find(g => g.gender === 'Female')?.count || 0;
  const diversityPct = stats.active ? Math.round((femaleCount / stats.active) * 100) : 0;

  return (
    <div className="p-8 space-y-6 animate-fade-in">
      {/* Header */}
      <div>
        <h1 className="font-display text-2xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-sm text-gray-500 mt-0.5">NexaWorks IT Solutions — Workforce Overview</p>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard icon={Users} label="Total Employees" value={stats.total} sub="Across all locations" color="indigo" />
        <StatCard icon={UserCheck} label="Active" value={stats.active} sub={`${stats.onLeave} on leave`} color="emerald" />
        <StatCard icon={Clock} label="On Probation" value={stats.probation} sub="Pending confirmation" color="amber" />
        <StatCard icon={UserX} label="Resigned" value={stats.resigned} sub="This cycle" color="rose" />
      </div>

      {/* Second row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard icon={TrendingUp} label="Total Payroll" value={formatCurrency(stats.totalPayroll, true)} sub="Annual CTC (active)" color="violet" />
        <StatCard icon={Briefcase} label="Avg CTC" value={formatCurrency(Math.round(stats.avgCtc), true)} sub="Per active employee" color="indigo" />
        <div className="card p-5">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Gender Diversity</p>
          <p className="text-3xl font-display font-bold text-gray-900 mt-1">{diversityPct}%</p>
          <p className="text-xs text-gray-500 mt-1">{femaleCount}F · {maleCount}M</p>
          <div className="mt-3 h-1.5 bg-gray-100 rounded-full overflow-hidden">
            <div className="h-full bg-brand-500 rounded-full transition-all" style={{ width: `${diversityPct}%` }} />
          </div>
        </div>
        <div className="card p-5">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Departments</p>
          <p className="text-3xl font-display font-bold text-gray-900 mt-1">{stats.byDept.length}</p>
          <p className="text-xs text-gray-500 mt-1">Largest: {stats.byDept[0]?.name?.split(' ')[0]}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Dept breakdown */}
        <div className="card p-5 lg:col-span-1">
          <h2 className="font-display font-semibold text-sm text-gray-900 mb-4">Headcount by Department</h2>
          <div className="space-y-2.5">
            {stats.byDept.map((d, i) => {
              const pct = stats.active ? Math.round((d.count / stats.active) * 100) : 0;
              return (
                <div key={i}>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-gray-600 truncate">{d.name}</span>
                    <span className="font-semibold text-gray-800 ml-2">{d.count}</span>
                  </div>
                  <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                    <div className="h-full bg-brand-500 rounded-full" style={{ width: `${pct}%` }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Location */}
        <div className="card p-5">
          <h2 className="font-display font-semibold text-sm text-gray-900 mb-4">
            <MapPin size={14} className="inline mr-1" />Location Breakdown
          </h2>
          <div className="space-y-3">
            {stats.byLocation.map((l, i) => (
              <div key={i} className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-brand-400" style={{ opacity: 1 - i * 0.18 }} />
                  <span className="text-sm text-gray-700">{l.work_location || 'Remote'}</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-20 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                    <div className="h-full bg-brand-400 rounded-full" style={{ width: `${(l.count / stats.active) * 100}%` }} />
                  </div>
                  <span className="text-xs font-semibold text-gray-700 w-6 text-right">{l.count}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Recent joiners */}
        <div className="card p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-display font-semibold text-sm text-gray-900">Recent Additions</h2>
            <Link to="/employees" className="text-xs text-brand-600 hover:text-brand-700 flex items-center gap-0.5">
              View all <ArrowRight size={12} />
            </Link>
          </div>
          <div className="space-y-3">
            {stats.recentJoiners.map((e) => {
              const initials = getInitials(e.first_name, e.last_name);
              const bg = avatarColor(e.first_name + e.last_name);
              return (
                <Link key={e.id} to={`/employees/${e.id}`} className="flex items-center gap-3 group">
                  <div className="w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-semibold flex-shrink-0" style={{ background: bg }}>
                    {initials}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-800 truncate group-hover:text-brand-600 transition-colors">
                      {e.first_name} {e.last_name}
                    </p>
                    <p className="text-xs text-gray-500 truncate">{e.designation} · {e.department}</p>
                  </div>
                  <span className="text-xs text-gray-400 whitespace-nowrap">{formatDate(e.date_of_joining)}</span>
                </Link>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
