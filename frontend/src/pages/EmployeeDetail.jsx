import React, { useEffect, useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { ArrowLeft, Mail, Phone, MapPin, Calendar, Star, TrendingUp, Plane, Package, Users, Edit, Trash2 } from 'lucide-react';
import { api } from '../lib/api';
import { formatCurrency, formatDate, tenure, statusBadgeClass, levelColor, getInitials, avatarColor } from '../lib/utils';
import EmployeeModal from '../components/employees/EmployeeModal';

function Section({ title, icon: Icon, children }) {
  return (
    <div className="card p-5">
      <div className="flex items-center gap-2 mb-4">
        <Icon size={15} className="text-brand-500" />
        <h3 className="font-display font-semibold text-sm text-gray-800">{title}</h3>
      </div>
      {children}
    </div>
  );
}

function Field({ label, value }) {
  return (
    <div>
      <p className="text-xs text-gray-400 mb-0.5">{label}</p>
      <p className="text-sm text-gray-800 font-medium">{value || '—'}</p>
    </div>
  );
}

export default function EmployeeDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [emp, setEmp] = useState(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [departments, setDepartments] = useState([]);

  useEffect(() => {
    setLoading(true);
    api.getEmployee(id).then(setEmp).finally(() => setLoading(false));
    api.getDepartments().then(setDepartments);
  }, [id]);

  const handleDelete = async () => {
    if (!confirm(`Terminate ${emp.first_name} ${emp.last_name}? This will mark them as Terminated.`)) return;
    await api.deleteEmployee(id);
    navigate('/employees');
  };

  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <div className="flex gap-1"><span className="typing-dot"/><span className="typing-dot"/><span className="typing-dot"/></div>
    </div>
  );

  if (!emp) return <div className="p-8 text-gray-500">Employee not found</div>;

  const initials = getInitials(emp.first_name, emp.last_name);
  const bg = avatarColor(emp.first_name + emp.last_name);
  const totalLeaveDays = emp.leaves?.reduce((s, l) => s + l.days_taken, 0) || 0;
  const avgRating = emp.reviews?.length ? (emp.reviews.reduce((s, r) => s + r.rating, 0) / emp.reviews.length).toFixed(1) : null;

  return (
    <div className="p-8 animate-fade-in">
      {/* Back */}
      <Link to="/employees" className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-brand-600 transition-colors mb-6">
        <ArrowLeft size={14} /> Back to Employees
      </Link>

      {/* Hero */}
      <div className="card p-6 mb-6">
        <div className="flex items-start gap-5">
          <div className="w-16 h-16 rounded-2xl flex items-center justify-center text-white text-xl font-display font-bold flex-shrink-0" style={{ background: bg }}>
            {initials}
          </div>
          <div className="flex-1">
            <div className="flex items-start justify-between">
              <div>
                <h1 className="font-display text-2xl font-bold text-gray-900">{emp.first_name} {emp.last_name}</h1>
                <p className="text-gray-500 text-sm mt-0.5">{emp.designation} · {emp.department_name}</p>
                <div className="flex items-center gap-3 mt-2 flex-wrap">
                  <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${statusBadgeClass(emp.employment_status)}`}>
                    {emp.employment_status}
                  </span>
                  <span className={`text-xs font-semibold px-2 py-0.5 rounded-md ${levelColor(emp.level)}`}>{emp.level}</span>
                  <span className="text-xs text-gray-500 bg-gray-100 px-2 py-0.5 rounded-md">{emp.employee_id}</span>
                  <span className="text-xs text-gray-500">{emp.work_location}</span>
                  <span className="text-xs text-gray-500">{tenure(emp.date_of_joining, emp.date_of_leaving)} tenure</span>
                </div>
              </div>
              <div className="flex gap-2">
                <button onClick={() => setEditing(true)} className="btn-secondary flex items-center gap-1.5 text-xs">
                  <Edit size={13} /> Edit
                </button>
                <button onClick={handleDelete} className="btn-ghost text-rose-500 hover:bg-rose-50 hover:text-rose-600 flex items-center gap-1.5 text-xs">
                  <Trash2 size={13} /> Terminate
                </button>
              </div>
            </div>

            {/* Quick stats */}
            <div className="grid grid-cols-4 gap-4 mt-4 pt-4 border-t border-gray-100">
              <div>
                <p className="text-xs text-gray-400">Annual CTC</p>
                <p className="font-semibold text-gray-900 text-sm mt-0.5">{formatCurrency(emp.ctc_annual, true)}</p>
              </div>
              <div>
                <p className="text-xs text-gray-400">Joined</p>
                <p className="font-semibold text-gray-900 text-sm mt-0.5">{formatDate(emp.date_of_joining)}</p>
              </div>
              <div>
                <p className="text-xs text-gray-400">Avg Rating</p>
                <p className="font-semibold text-gray-900 text-sm mt-0.5 flex items-center gap-1">
                  {avgRating ? <><Star size={12} className="text-amber-400 fill-amber-400" />{avgRating}/5</> : '—'}
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-400">Total Leave</p>
                <p className="font-semibold text-gray-900 text-sm mt-0.5">{totalLeaveDays} days</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Left col */}
        <div className="space-y-5">
          <Section title="Contact" icon={Mail}>
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-sm">
                <Mail size={13} className="text-gray-400" />
                <a href={`mailto:${emp.email}`} className="text-brand-600 hover:underline truncate">{emp.email}</a>
              </div>
              {emp.phone && <div className="flex items-center gap-2 text-sm">
                <Phone size={13} className="text-gray-400" />
                <span className="text-gray-700">{emp.phone}</span>
              </div>}
              {emp.address_city && <div className="flex items-center gap-2 text-sm">
                <MapPin size={13} className="text-gray-400" />
                <span className="text-gray-700">{emp.address_city}, {emp.address_state}</span>
              </div>}
            </div>
          </Section>

          <Section title="Personal" icon={Calendar}>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Date of Birth" value={formatDate(emp.dob)} />
              <Field label="Gender" value={emp.gender} />
              <Field label="Blood Group" value={emp.blood_group} />
              <Field label="Employment Type" value={emp.employment_type} />
              {emp.probation_end_date && <Field label="Probation Ends" value={formatDate(emp.probation_end_date)} />}
            </div>
          </Section>

          <Section title="Banking" icon={TrendingUp}>
            <div className="space-y-2">
              <Field label="PAN" value={emp.pan_number} />
              <Field label="Bank" value={emp.bank_name} />
              <Field label="IFSC" value={emp.ifsc_code} />
            </div>
          </Section>

          {emp.reportees?.length > 0 && (
            <Section title={`Direct Reports (${emp.reportees.length})`} icon={Users}>
              <div className="space-y-2">
                {emp.reportees.map(r => (
                  <Link key={r.id} to={`/employees/${r.id}`} className="flex items-center gap-2 text-sm text-brand-600 hover:text-brand-700">
                    <div className="w-6 h-6 rounded-full flex items-center justify-center text-white text-xs font-semibold" style={{ background: avatarColor(r.first_name + r.last_name) }}>
                      {getInitials(r.first_name, r.last_name)}
                    </div>
                    <span className="truncate">{r.first_name} {r.last_name}</span>
                    <span className={`ml-auto text-xs px-1.5 py-0.5 rounded-full ${statusBadgeClass(r.employment_status)}`}>{r.employment_status}</span>
                  </Link>
                ))}
              </div>
            </Section>
          )}
        </div>

        {/* Right col */}
        <div className="lg:col-span-2 space-y-5">
          {/* Compensation */}
          <Section title="Compensation" icon={TrendingUp}>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-4">
              <div className="bg-brand-50 rounded-xl p-3">
                <p className="text-xs text-brand-600">Annual CTC</p>
                <p className="font-bold text-brand-800 text-sm mt-1">{formatCurrency(emp.ctc_annual)}</p>
              </div>
              <div className="bg-gray-50 rounded-xl p-3">
                <p className="text-xs text-gray-500">Basic</p>
                <p className="font-semibold text-gray-800 text-sm mt-1">{formatCurrency(emp.basic_salary)}</p>
              </div>
              <div className="bg-gray-50 rounded-xl p-3">
                <p className="text-xs text-gray-500">HRA</p>
                <p className="font-semibold text-gray-800 text-sm mt-1">{formatCurrency(emp.hra)}</p>
              </div>
              <div className="bg-gray-50 rounded-xl p-3">
                <p className="text-xs text-gray-500">Special Allow.</p>
                <p className="font-semibold text-gray-800 text-sm mt-1">{formatCurrency(emp.special_allowance)}</p>
              </div>
            </div>
            {emp.salaryHistory?.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase mb-2">Salary History</p>
                <div className="space-y-1.5">
                  {emp.salaryHistory.map(s => (
                    <div key={s.id} className="flex items-center justify-between text-xs bg-gray-50 px-3 py-2 rounded-lg">
                      <span className="text-gray-500">{formatDate(s.effective_date)}</span>
                      <span className="text-gray-600">{s.reason}</span>
                      <span className="font-semibold text-gray-800">{formatCurrency(s.old_ctc, true)} → {formatCurrency(s.new_ctc, true)}</span>
                      <span className="text-emerald-600 font-bold">+{s.hike_percent}%</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </Section>

          {/* Performance */}
          {emp.reviews?.length > 0 && (
            <Section title="Performance Reviews" icon={Star}>
              <div className="space-y-3">
                {emp.reviews.map(r => (
                  <div key={r.id} className="border border-gray-100 rounded-xl p-4">
                    <div className="flex items-start justify-between mb-2">
                      <div>
                        <p className="font-semibold text-sm text-gray-800">{r.review_period} · {r.review_type}</p>
                        <p className="text-xs text-gray-400 mt-0.5">Reviewed by {r.reviewer_name} on {formatDate(r.review_date)}</p>
                      </div>
                      <div className="flex items-center gap-1">
                        {[1,2,3,4,5].map(n => (
                          <Star key={n} size={13} className={n <= Math.round(r.rating) ? 'text-amber-400 fill-amber-400' : 'text-gray-200 fill-gray-200'} />
                        ))}
                        <span className="text-sm font-bold text-gray-800 ml-1">{r.rating}</span>
                      </div>
                    </div>
                    {r.strengths && <p className="text-xs text-gray-600 mb-1"><span className="font-medium text-emerald-600">Strengths:</span> {r.strengths}</p>}
                    {r.improvement_areas && <p className="text-xs text-gray-600 mb-1"><span className="font-medium text-amber-600">Improve:</span> {r.improvement_areas}</p>}
                    {r.comments && <p className="text-xs text-gray-500 italic">"{r.comments}"</p>}
                    {r.salary_hike_percent && <p className="text-xs text-emerald-600 font-semibold mt-1">Hike: +{r.salary_hike_percent}%</p>}
                  </div>
                ))}
              </div>
            </Section>
          )}

          {/* Leaves */}
          {emp.leaves?.length > 0 && (
            <Section title={`Leave Records (${emp.leaves.length})`} icon={Plane}>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-gray-400 border-b border-gray-100">
                      <th className="text-left pb-2 font-medium">Type</th>
                      <th className="text-left pb-2 font-medium">From</th>
                      <th className="text-left pb-2 font-medium">To</th>
                      <th className="text-right pb-2 font-medium">Days</th>
                      <th className="text-left pb-2 font-medium pl-3">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {emp.leaves.map(l => (
                      <tr key={l.id} className="border-b border-gray-50">
                        <td className="py-1.5 font-medium text-gray-700">{l.leave_type}</td>
                        <td className="py-1.5 text-gray-500">{formatDate(l.start_date)}</td>
                        <td className="py-1.5 text-gray-500">{formatDate(l.end_date)}</td>
                        <td className="py-1.5 text-right font-semibold text-gray-800">{l.days_taken}</td>
                        <td className="py-1.5 pl-3">
                          <span className={`px-2 py-0.5 rounded-full text-xs ${l.status === 'Approved' ? 'bg-emerald-50 text-emerald-700' : l.status === 'Rejected' ? 'bg-rose-50 text-rose-700' : 'bg-amber-50 text-amber-700'}`}>
                            {l.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Section>
          )}

          {/* Skills */}
          {emp.skills && (
            <Section title="Skills" icon={Package}>
              <div className="flex flex-wrap gap-2">
                {emp.skills.split(',').map(s => (
                  <span key={s} className="text-xs bg-brand-50 text-brand-700 border border-brand-100 px-2.5 py-1 rounded-full font-medium">{s.trim()}</span>
                ))}
              </div>
            </Section>
          )}
        </div>
      </div>

      {editing && (
        <EmployeeModal
          employee={emp}
          departments={departments}
          onClose={() => setEditing(false)}
          onSaved={async () => {
            setEditing(false);
            const updated = await api.getEmployee(id);
            setEmp(updated);
          }}
        />
      )}
    </div>
  );
}
