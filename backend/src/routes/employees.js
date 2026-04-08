import { Router } from 'express';
import { getDb } from '../db/database.js';

const router = Router();

// GET all employees with dept name
router.get('/', (req, res) => {
  const db = getDb();
  const { dept, status, location, search, page = 1, limit = 20 } = req.query;
  
  let where = [];
  let params = [];
  
  if (dept) { where.push('d.name = ?'); params.push(dept); }
  if (status) { where.push('e.employment_status = ?'); params.push(status); }
  if (location) { where.push('e.work_location = ?'); params.push(location); }
  if (search) {
    where.push(`(e.first_name LIKE ? OR e.last_name LIKE ? OR e.employee_id LIKE ? OR e.email LIKE ? OR e.designation LIKE ?)`);
    const s = `%${search}%`;
    params.push(s, s, s, s, s);
  }

  const whereClause = where.length ? `WHERE ${where.join(' AND ')}` : '';
  const offset = (parseInt(page) - 1) * parseInt(limit);

  const total = db.prepare(`
    SELECT COUNT(*) as count FROM employees e 
    LEFT JOIN departments d ON e.department_id = d.id
    ${whereClause}
  `).get(...params)?.count || 0;

  const employees = db.prepare(`
    SELECT e.*, d.name as department_name,
           m.first_name || ' ' || m.last_name as manager_name
    FROM employees e
    LEFT JOIN departments d ON e.department_id = d.id
    LEFT JOIN employees m ON e.reporting_manager_id = m.id
    ${whereClause}
    ORDER BY e.first_name ASC
    LIMIT ? OFFSET ?
  `).all(...params, parseInt(limit), offset);

  res.json({ employees, total, page: parseInt(page), limit: parseInt(limit), pages: Math.ceil(total / parseInt(limit)) });
});

// GET single employee full detail
router.get('/:id', (req, res) => {
  const db = getDb();
  const emp = db.prepare(`
    SELECT e.*, d.name as department_name,
           m.first_name || ' ' || m.last_name as manager_name,
           m.designation as manager_designation
    FROM employees e
    LEFT JOIN departments d ON e.department_id = d.id
    LEFT JOIN employees m ON e.reporting_manager_id = m.id
    WHERE e.id = ?
  `).get(req.params.id);

  if (!emp) return res.status(404).json({ error: 'Employee not found' });

  const leaves = db.prepare(`SELECT * FROM leave_records WHERE employee_id = ? ORDER BY start_date DESC LIMIT 20`).all(req.params.id);
  const reviews = db.prepare(`
    SELECT pr.*, r.first_name || ' ' || r.last_name as reviewer_name
    FROM performance_reviews pr
    LEFT JOIN employees r ON pr.reviewer_id = r.id
    WHERE pr.employee_id = ? ORDER BY review_date DESC
  `).all(req.params.id);
  const salaryHistory = db.prepare(`SELECT * FROM salary_history WHERE employee_id = ? ORDER BY effective_date DESC`).all(req.params.id);
  const assets = db.prepare(`SELECT * FROM assets_assigned WHERE employee_id = ?`).all(req.params.id);
  const reportees = db.prepare(`
    SELECT id, employee_id, first_name, last_name, designation, employment_status
    FROM employees WHERE reporting_manager_id = ?
  `).all(req.params.id);

  res.json({ ...emp, leaves, reviews, salaryHistory, assets, reportees });
});

// POST create employee
router.post('/', (req, res) => {
  const db = getDb();
  const e = req.body;
  
  try {
    const result = db.prepare(`
      INSERT INTO employees (
        employee_id, first_name, last_name, email, phone, dob, gender, blood_group,
        department_id, designation, level, employment_type, employment_status,
        date_of_joining, probation_end_date, reporting_manager_id, work_location,
        ctc_annual, basic_salary, hra, special_allowance, pf_contribution,
        pan_number, address_city, address_state, address_pincode,
        emergency_contact_name, emergency_contact_relation, emergency_contact_phone, skills
      ) VALUES (
        @employee_id, @first_name, @last_name, @email, @phone, @dob, @gender, @blood_group,
        @department_id, @designation, @level, @employment_type, @employment_status,
        @date_of_joining, @probation_end_date, @reporting_manager_id, @work_location,
        @ctc_annual, @basic_salary, @hra, @special_allowance, @pf_contribution,
        @pan_number, @address_city, @address_state, @address_pincode,
        @emergency_contact_name, @emergency_contact_relation, @emergency_contact_phone, @skills
      )
    `).run(e);
    res.status(201).json({ id: result.lastInsertRowid, message: 'Employee created successfully' });
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

// PUT update employee
router.put('/:id', (req, res) => {
  const db = getDb();
  const e = req.body;
  const fields = Object.keys(e).filter(k => k !== 'id').map(k => `${k} = @${k}`).join(', ');
  
  try {
    db.prepare(`UPDATE employees SET ${fields}, updated_at = datetime('now') WHERE id = @id`).run({ ...e, id: req.params.id });
    res.json({ message: 'Employee updated successfully' });
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

// DELETE employee (soft delete - mark terminated)
router.delete('/:id', (req, res) => {
  const db = getDb();
  db.prepare(`UPDATE employees SET employment_status = 'Terminated', date_of_leaving = date('now'), updated_at = datetime('now') WHERE id = ?`).run(req.params.id);
  res.json({ message: 'Employee terminated' });
});

// GET departments
router.get('/meta/departments', (req, res) => {
  const db = getDb();
  const depts = db.prepare(`
    SELECT d.*, COUNT(e.id) as headcount
    FROM departments d
    LEFT JOIN employees e ON d.id = e.department_id AND e.employment_status = 'Active'
    GROUP BY d.id ORDER BY d.name
  `).all();
  res.json(depts);
});

// GET stats for dashboard
router.get('/meta/stats', (req, res) => {
  const db = getDb();
  
  const total = db.prepare(`SELECT COUNT(*) as c FROM employees WHERE employment_status != 'Terminated'`).get().c;
  const active = db.prepare(`SELECT COUNT(*) as c FROM employees WHERE employment_status = 'Active'`).get().c;
  const onLeave = db.prepare(`SELECT COUNT(*) as c FROM employees WHERE employment_status = 'On Leave'`).get().c;
  const probation = db.prepare(`SELECT COUNT(*) as c FROM employees WHERE employment_status = 'Probation'`).get().c;
  const resigned = db.prepare(`SELECT COUNT(*) as c FROM employees WHERE employment_status = 'Resigned'`).get().c;
  
  const byDept = db.prepare(`
    SELECT d.name, COUNT(e.id) as count
    FROM departments d LEFT JOIN employees e ON d.id = e.department_id AND e.employment_status = 'Active'
    GROUP BY d.id ORDER BY count DESC
  `).all();
  
  const byLocation = db.prepare(`
    SELECT work_location, COUNT(*) as count FROM employees 
    WHERE employment_status = 'Active' GROUP BY work_location ORDER BY count DESC
  `).all();
  
  const avgCtc = db.prepare(`SELECT AVG(ctc_annual) as avg FROM employees WHERE employment_status = 'Active'`).get().avg;
  const totalPayroll = db.prepare(`SELECT SUM(ctc_annual) as total FROM employees WHERE employment_status = 'Active'`).get().total;
  
  const recentJoiners = db.prepare(`
    SELECT e.id, e.employee_id, e.first_name, e.last_name, e.designation, d.name as department, e.date_of_joining, e.work_location
    FROM employees e LEFT JOIN departments d ON e.department_id = d.id
    WHERE e.employment_status NOT IN ('Terminated')
    ORDER BY e.date_of_joining DESC LIMIT 5
  `).all();

  const byGender = db.prepare(`
    SELECT gender, COUNT(*) as count FROM employees WHERE employment_status = 'Active' GROUP BY gender
  `).all();
  
  res.json({ total, active, onLeave, probation, resigned, byDept, byLocation, avgCtc, totalPayroll, recentJoiners, byGender });
});

export default router;
