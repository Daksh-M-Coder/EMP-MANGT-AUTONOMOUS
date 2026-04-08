import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Users, MapPin, DollarSign, ArrowRight } from 'lucide-react';
import { api } from '../lib/api';
import { formatCurrency } from '../lib/utils';

const DEPT_COLORS = [
  'from-brand-500 to-brand-700',
  'from-violet-500 to-violet-700',
  'from-emerald-500 to-emerald-700',
  'from-amber-500 to-amber-700',
  'from-rose-500 to-rose-700',
  'from-sky-500 to-sky-700',
  'from-pink-500 to-pink-700',
  'from-teal-500 to-teal-700',
  'from-orange-500 to-orange-700',
  'from-indigo-500 to-indigo-700',
];

export default function Departments() {
  const [depts, setDepts] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => { api.getDepartments().then(setDepts).finally(() => setLoading(false)); }, []);

  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <div className="flex gap-1"><span className="typing-dot"/><span className="typing-dot"/><span className="typing-dot"/></div>
    </div>
  );

  return (
    <div className="p-8 animate-fade-in">
      <div className="mb-6">
        <h1 className="font-display text-2xl font-bold text-gray-900">Departments</h1>
        <p className="text-sm text-gray-500 mt-0.5">{depts.length} departments across all locations</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
        {depts.map((d, i) => (
          <div key={d.id} className="card overflow-hidden hover:shadow-md transition-shadow">
            <div className={`h-2 bg-gradient-to-r ${DEPT_COLORS[i % DEPT_COLORS.length]}`} />
            <div className="p-5">
              <h3 className="font-display font-semibold text-gray-900 text-base mb-1">{d.name}</h3>

              <div className="space-y-2 mt-3">
                <div className="flex items-center gap-2 text-sm text-gray-600">
                  <Users size={13} className="text-gray-400" />
                  <span><strong>{d.headcount}</strong> active employees</span>
                </div>
                {d.location && (
                  <div className="flex items-center gap-2 text-sm text-gray-600">
                    <MapPin size={13} className="text-gray-400" />
                    <span>HQ: {d.location}</span>
                  </div>
                )}
                {d.budget_inr && (
                  <div className="flex items-center gap-2 text-sm text-gray-600">
                    <DollarSign size={13} className="text-gray-400" />
                    <span>Budget: {formatCurrency(d.budget_inr, true)}</span>
                  </div>
                )}
              </div>

              <Link
                to={`/employees?dept=${encodeURIComponent(d.name)}`}
                className="mt-4 flex items-center gap-1.5 text-xs text-brand-600 hover:text-brand-700 font-medium transition-colors"
              >
                View employees <ArrowRight size={12} />
              </Link>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
