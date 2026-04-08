import React, { useEffect, useState, useCallback } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Search, Plus, Filter, ChevronLeft, ChevronRight, X } from 'lucide-react';
import { api } from '../lib/api';
import { formatCurrency, formatDate, tenure, statusBadgeClass, levelColor, getInitials, avatarColor } from '../lib/utils';
import EmployeeModal from '../components/employees/EmployeeModal';

const STATUSES = ['Active', 'Probation', 'On Leave', 'Resigned', 'Terminated'];
const LOCATIONS = ['Bengaluru', 'Mumbai', 'Hyderabad', 'Pune', 'Remote'];

export default function Employees() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [data, setData] = useState({ employees: [], total: 0, pages: 1 });
  const [departments, setDepartments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showFilters, setShowFilters] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [editEmp, setEditEmp] = useState(null);

  const page = parseInt(searchParams.get('page') || '1');
  const search = searchParams.get('search') || '';
  const dept = searchParams.get('dept') || '';
  const status = searchParams.get('status') || '';
  const location = searchParams.get('location') || '';

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.getEmployees({ page, search, dept, status, location, limit: 15 });
      setData(res);
    } finally {
      setLoading(false);
    }
  }, [page, search, dept, status, location]);

  useEffect(() => { fetchData(); }, [fetchData]);
  useEffect(() => { api.getDepartments().then(setDepartments); }, []);

  const setParam = (key, val) => {
    const p = new URLSearchParams(searchParams);
    if (val) p.set(key, val); else p.delete(key);
    p.delete('page');
    setSearchParams(p);
  };

  const clearFilters = () => setSearchParams({});

  const hasFilters = dept || status || location;

  return (
    <div className="p-8 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="font-display text-2xl font-bold text-gray-900">Employees</h1>
          <p className="text-sm text-gray-500 mt-0.5">{data.total} total records</p>
        </div>
        <button onClick={() => { setEditEmp(null); setShowModal(true); }} className="btn-primary flex items-center gap-2">
          <Plus size={15} /> Add Employee
        </button>
      </div>

      {/* Search + Filters */}
      <div className="card p-3 mb-5">
        <div className="flex gap-3">
          <div className="relative flex-1">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              value={search}
              onChange={e => setParam('search', e.target.value)}
              placeholder="Search by name, ID, email, designation…"
              className="input-base pl-9"
            />
          </div>
          <button onClick={() => setShowFilters(!showFilters)} className={`btn-secondary flex items-center gap-2 ${hasFilters ? 'border-brand-400 text-brand-600 bg-brand-50' : ''}`}>
            <Filter size={14} /> Filters {hasFilters && <span className="w-4 h-4 bg-brand-500 text-white text-xs rounded-full flex items-center justify-center">!</span>}
          </button>
          {hasFilters && (
            <button onClick={clearFilters} className="btn-ghost flex items-center gap-1 text-rose-500 hover:text-rose-600 hover:bg-rose-50">
              <X size={14} /> Clear
            </button>
          )}
        </div>

        {showFilters && (
          <div className="mt-3 pt-3 border-t border-gray-100 flex gap-3 flex-wrap">
            <select value={dept} onChange={e => setParam('dept', e.target.value)} className="input-base w-auto min-w-40 text-xs">
              <option value="">All Departments</option>
              {departments.map(d => <option key={d.id} value={d.name}>{d.name}</option>)}
            </select>
            <select value={status} onChange={e => setParam('status', e.target.value)} className="input-base w-auto text-xs">
              <option value="">All Statuses</option>
              {STATUSES.map(s => <option key={s}>{s}</option>)}
            </select>
            <select value={location} onChange={e => setParam('location', e.target.value)} className="input-base w-auto text-xs">
              <option value="">All Locations</option>
              {LOCATIONS.map(l => <option key={l}>{l}</option>)}
            </select>
          </div>
        )}
      </div>

      {/* Table */}
      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-100">
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Employee</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Department</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Level</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Location</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">CTC</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Joined</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Status</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={8} className="py-16 text-center">
                  <div className="flex justify-center gap-1"><span className="typing-dot"/><span className="typing-dot"/><span className="typing-dot"/></div>
                </td></tr>
              ) : data.employees.length === 0 ? (
                <tr><td colSpan={8} className="py-16 text-center text-gray-400 text-sm">No employees found</td></tr>
              ) : data.employees.map(emp => {
                const initials = getInitials(emp.first_name, emp.last_name);
                const bg = avatarColor(emp.first_name + emp.last_name);
                return (
                  <tr key={emp.id} className="border-b border-gray-50 hover:bg-indigo-50/30 transition-colors">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-semibold flex-shrink-0" style={{ background: bg }}>
                          {initials}
                        </div>
                        <div>
                          <Link to={`/employees/${emp.id}`} className="text-sm font-semibold text-gray-800 hover:text-brand-600 transition-colors">
                            {emp.first_name} {emp.last_name}
                          </Link>
                          <p className="text-xs text-gray-400">{emp.employee_id} · {emp.designation}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">{emp.department_name || '—'}</td>
                    <td className="px-4 py-3">
                      <span className={`text-xs font-semibold px-2 py-0.5 rounded-md ${levelColor(emp.level)}`}>{emp.level || '—'}</span>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">{emp.work_location || '—'}</td>
                    <td className="px-4 py-3 text-sm font-medium text-gray-800">{formatCurrency(emp.ctc_annual, true)}</td>
                    <td className="px-4 py-3 text-xs text-gray-500">
                      <div>{formatDate(emp.date_of_joining)}</div>
                      <div className="text-gray-400">{tenure(emp.date_of_joining, emp.date_of_leaving)}</div>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${statusBadgeClass(emp.employment_status)}`}>
                        {emp.employment_status}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <button onClick={() => { setEditEmp(emp); setShowModal(true); }} className="btn-ghost text-xs px-2 py-1">Edit</button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {data.pages > 1 && (
          <div className="px-4 py-3 border-t border-gray-100 flex items-center justify-between">
            <p className="text-xs text-gray-500">Page {page} of {data.pages} · {data.total} employees</p>
            <div className="flex gap-2">
              <button disabled={page <= 1} onClick={() => setParam('page', page - 1)} className="btn-secondary px-2 py-1 disabled:opacity-40">
                <ChevronLeft size={14} />
              </button>
              <button disabled={page >= data.pages} onClick={() => setParam('page', page + 1)} className="btn-secondary px-2 py-1 disabled:opacity-40">
                <ChevronRight size={14} />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Modal */}
      {showModal && (
        <EmployeeModal
          employee={editEmp}
          departments={departments}
          onClose={() => setShowModal(false)}
          onSaved={() => { setShowModal(false); fetchData(); }}
        />
      )}
    </div>
  );
}
