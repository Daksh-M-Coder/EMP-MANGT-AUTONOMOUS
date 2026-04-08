import React, { useState, useEffect } from 'react';
import { NavLink } from 'react-router-dom';
import { LayoutDashboard, Users, Bot, Building2, FileText } from 'lucide-react';
import { api } from '../../lib/api.js';

const nav = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/employees', icon: Users, label: 'Employees' },
  { to: '/drafts', icon: FileText, label: 'Pending Drafts', badge: 'pendingDrafts' },
  { to: '/ai', icon: Bot, label: 'AI Assistant' },
  { to: '/departments', icon: Building2, label: 'Departments' },
];

export default function Sidebar() {
  const [pendingDrafts, setPendingDrafts] = useState(0);

  useEffect(() => {
    loadDraftStats();
    // Refresh every 30 seconds
    const interval = setInterval(loadDraftStats, 30000);
    return () => clearInterval(interval);
  }, []);

  const loadDraftStats = async () => {
    try {
      const data = await api.getDraftStats();
      setPendingDrafts(data.stats?.pending || 0);
    } catch (err) {
      console.error('Failed to load draft stats:', err);
    }
  };

  return (
    <aside className="fixed top-0 left-0 h-screen w-60 bg-brand-950 flex flex-col z-20">
      {/* Logo */}
      <div className="px-5 py-5 border-b border-brand-800">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-brand-500 flex items-center justify-center">
            <span className="text-white font-display font-bold text-sm">N</span>
          </div>
          <div>
            <p className="font-display font-semibold text-white text-sm leading-tight">NexaWorks</p>
            <p className="text-brand-400 text-xs">HRMS Platform</p>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-0.5">
        {nav.map(({ to, icon: Icon, label, badge }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all group ${
                isActive
                  ? 'bg-brand-600 text-white'
                  : 'text-brand-300 hover:bg-brand-800 hover:text-white'
              }`
            }
          >
            <Icon size={17} />
            <span className="flex-1">{label}</span>
            {badge === 'pendingDrafts' && pendingDrafts > 0 && (
              <span className="bg-yellow-500 text-brand-950 text-xs font-bold px-2 py-0.5 rounded-full">
                {pendingDrafts}
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Bottom */}
      <div className="px-4 py-4 border-t border-brand-800">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-full bg-brand-600 flex items-center justify-center">
            <span className="text-white text-xs font-semibold">HR</span>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-white text-xs font-medium truncate">Admin</p>
            <p className="text-brand-400 text-xs truncate">hr@nexaworks.in</p>
          </div>
        </div>
      </div>
    </aside>
  );
}
