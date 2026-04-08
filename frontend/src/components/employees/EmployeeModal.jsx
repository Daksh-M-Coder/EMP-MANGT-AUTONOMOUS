import React, { useState } from 'react';
import { X } from 'lucide-react';
import { api } from '../../lib/api';

const LEVELS = ['L1','L2','L3','L4','L5','L6','L7'];
const TYPES = ['Full-Time','Part-Time','Contract','Intern'];
const STATUSES = ['Active','Probation','On Leave','Resigned','Terminated'];
const LOCATIONS = ['Bengaluru','Mumbai','Hyderabad','Pune','Remote'];
const GENDERS = ['Male','Female','Other'];
const BLOOD_GROUPS = ['A+','A-','B+','B-','AB+','AB-','O+','O-'];

export default function EmployeeModal({ employee, departments, onClose, onSaved }) {
  const isEdit = !!employee;
  const [form, setForm] = useState(employee ? {
    first_name: employee.first_name || '',
    last_name: employee.last_name || '',
    email: employee.email || '',
    phone: employee.phone || '',
    dob: employee.dob || '',
    gender: employee.gender || '',
    blood_group: employee.blood_group || '',
    department_id: employee.department_id || '',
    designation: employee.designation || '',
    level: employee.level || '',
    employment_type: employee.employment_type || 'Full-Time',
    employment_status: employee.employment_status || 'Active',
    date_of_joining: employee.date_of_joining || '',
    probation_end_date: employee.probation_end_date || '',
    work_location: employee.work_location || '',
    ctc_annual: employee.ctc_annual || '',
    basic_salary: employee.basic_salary || '',
    hra: employee.hra || '',
    special_allowance: employee.special_allowance || '',
    pf_contribution: employee.pf_contribution || '',
    pan_number: employee.pan_number || '',
    address_city: employee.address_city || '',
    address_state: employee.address_state || '',
    address_pincode: employee.address_pincode || '',
    skills: employee.skills || '',
    reporting_manager_id: employee.reporting_manager_id || '',
    employee_id: employee.employee_id || '',
  } : {
    first_name: '', last_name: '', email: '', phone: '', dob: '', gender: 'Male', blood_group: '',
    department_id: '', designation: '', level: 'L3', employment_type: 'Full-Time',
    employment_status: 'Probation', date_of_joining: new Date().toISOString().split('T')[0],
    probation_end_date: '', work_location: 'Bengaluru', ctc_annual: '', basic_salary: '',
    hra: '', special_allowance: '', pf_contribution: '', pan_number: '',
    address_city: '', address_state: '', address_pincode: '', skills: '',
    reporting_manager_id: '', employee_id: '',
  });

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [tab, setTab] = useState('basic');

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    try {
      if (isEdit) await api.updateEmployee(employee.id, form);
      else await api.createEmployee(form);
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const tabs = [
    { id: 'basic', label: 'Basic Info' },
    { id: 'work', label: 'Work Details' },
    { id: 'comp', label: 'Compensation' },
    { id: 'personal', label: 'Personal' },
  ];

  const F = ({ label, children, required }) => (
    <div>
      <label className="block text-xs font-medium text-gray-600 mb-1">{label}{required && <span className="text-rose-500 ml-0.5">*</span>}</label>
      {children}
    </div>
  );

  return (
    <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col animate-fade-in">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <h2 className="font-display font-bold text-gray-900">{isEdit ? `Edit: ${employee.first_name} ${employee.last_name}` : 'Add New Employee'}</h2>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100 transition-colors"><X size={16} /></button>
        </div>

        {/* Tabs */}
        <div className="flex gap-0 border-b border-gray-100 px-6">
          {tabs.map(t => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`text-xs font-medium py-3 px-3 border-b-2 transition-colors ${tab === t.id ? 'border-brand-500 text-brand-600' : 'border-transparent text-gray-500 hover:text-gray-700'}`}>
              {t.label}
            </button>
          ))}
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto px-6 py-4">
          {tab === 'basic' && (
            <div className="grid grid-cols-2 gap-4">
              <F label="First Name" required><input value={form.first_name} onChange={e => set('first_name', e.target.value)} className="input-base" required /></F>
              <F label="Last Name" required><input value={form.last_name} onChange={e => set('last_name', e.target.value)} className="input-base" required /></F>
              <F label="Employee ID"  required={!isEdit}><input value={form.employee_id} onChange={e => set('employee_id', e.target.value)} className="input-base" placeholder="EMP101" /></F>
              <F label="Email" required><input type="email" value={form.email} onChange={e => set('email', e.target.value)} className="input-base" required /></F>
              <F label="Phone"><input value={form.phone} onChange={e => set('phone', e.target.value)} className="input-base" placeholder="9XXXXXXXXX" /></F>
              <F label="Gender">
                <select value={form.gender} onChange={e => set('gender', e.target.value)} className="input-base">
                  <option value="">Select</option>
                  {GENDERS.map(g => <option key={g}>{g}</option>)}
                </select>
              </F>
              <F label="Date of Birth"><input type="date" value={form.dob} onChange={e => set('dob', e.target.value)} className="input-base" /></F>
              <F label="Blood Group">
                <select value={form.blood_group} onChange={e => set('blood_group', e.target.value)} className="input-base">
                  <option value="">Select</option>
                  {BLOOD_GROUPS.map(g => <option key={g}>{g}</option>)}
                </select>
              </F>
            </div>
          )}

          {tab === 'work' && (
            <div className="grid grid-cols-2 gap-4">
              <F label="Designation" required><input value={form.designation} onChange={e => set('designation', e.target.value)} className="input-base" required placeholder="Software Engineer" /></F>
              <F label="Department">
                <select value={form.department_id} onChange={e => set('department_id', e.target.value)} className="input-base">
                  <option value="">Select Department</option>
                  {departments.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
                </select>
              </F>
              <F label="Level">
                <select value={form.level} onChange={e => set('level', e.target.value)} className="input-base">
                  {LEVELS.map(l => <option key={l}>{l}</option>)}
                </select>
              </F>
              <F label="Employment Type">
                <select value={form.employment_type} onChange={e => set('employment_type', e.target.value)} className="input-base">
                  {TYPES.map(t => <option key={t}>{t}</option>)}
                </select>
              </F>
              <F label="Status">
                <select value={form.employment_status} onChange={e => set('employment_status', e.target.value)} className="input-base">
                  {STATUSES.map(s => <option key={s}>{s}</option>)}
                </select>
              </F>
              <F label="Work Location">
                <select value={form.work_location} onChange={e => set('work_location', e.target.value)} className="input-base">
                  <option value="">Select</option>
                  {LOCATIONS.map(l => <option key={l}>{l}</option>)}
                </select>
              </F>
              <F label="Date of Joining" required><input type="date" value={form.date_of_joining} onChange={e => set('date_of_joining', e.target.value)} className="input-base" required /></F>
              <F label="Probation End Date"><input type="date" value={form.probation_end_date} onChange={e => set('probation_end_date', e.target.value)} className="input-base" /></F>
              <div className="col-span-2">
                <F label="Skills (comma-separated)"><input value={form.skills} onChange={e => set('skills', e.target.value)} className="input-base" placeholder="Python, React, AWS" /></F>
              </div>
            </div>
          )}

          {tab === 'comp' && (
            <div className="grid grid-cols-2 gap-4">
              <F label="Annual CTC (₹)"><input type="number" value={form.ctc_annual} onChange={e => set('ctc_annual', e.target.value)} className="input-base" placeholder="1500000" /></F>
              <F label="Basic Salary (₹)"><input type="number" value={form.basic_salary} onChange={e => set('basic_salary', e.target.value)} className="input-base" /></F>
              <F label="HRA (₹)"><input type="number" value={form.hra} onChange={e => set('hra', e.target.value)} className="input-base" /></F>
              <F label="Special Allowance (₹)"><input type="number" value={form.special_allowance} onChange={e => set('special_allowance', e.target.value)} className="input-base" /></F>
              <F label="PF Contribution (₹)"><input type="number" value={form.pf_contribution} onChange={e => set('pf_contribution', e.target.value)} className="input-base" /></F>
              <F label="PAN Number"><input value={form.pan_number} onChange={e => set('pan_number', e.target.value)} className="input-base font-mono" placeholder="ABCDE1234F" /></F>
            </div>
          )}

          {tab === 'personal' && (
            <div className="grid grid-cols-2 gap-4">
              <F label="City"><input value={form.address_city} onChange={e => set('address_city', e.target.value)} className="input-base" /></F>
              <F label="State"><input value={form.address_state} onChange={e => set('address_state', e.target.value)} className="input-base" /></F>
              <F label="Pincode"><input value={form.address_pincode} onChange={e => set('address_pincode', e.target.value)} className="input-base" /></F>
            </div>
          )}

          {error && <p className="mt-4 text-xs text-rose-600 bg-rose-50 border border-rose-200 rounded-lg px-3 py-2">{error}</p>}
        </form>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-gray-100 flex justify-end gap-3">
          <button type="button" onClick={onClose} className="btn-secondary">Cancel</button>
          <button onClick={handleSubmit} disabled={saving} className="btn-primary">
            {saving ? 'Saving…' : isEdit ? 'Save Changes' : 'Add Employee'}
          </button>
        </div>
      </div>
    </div>
  );
}
