import { Router } from 'express';
import { runAIAgent } from '../ai/agent.js';
import { getDb } from '../db/database.js';

const router = Router();

// ── AI Chat with Agent ──────────────────────────────────────
router.post('/chat', async (req, res) => {
  const { message, history = [], session_id } = req.body;
  
  if (!message?.trim()) {
    return res.status(400).json({ error: 'Message is required' });
  }

  try {
    const result = await runAIAgent(message, history, session_id);
    res.json(result);
  } catch (err) {
    console.error('AI Agent error:', err);
    res.status(500).json({ error: err.message || 'AI agent failed' });
  }
});

// ── Create Employee Draft ─────────────────────────────────
router.post('/draft', async (req, res) => {
  const { draft_data, proposed_by = 'system' } = req.body;
  
  if (!draft_data || typeof draft_data !== 'object') {
    return res.status(400).json({ error: 'draft_data is required' });
  }

  try {
    const db = getDb();
    const draft_id = `DRAFT-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    
    const result = db.prepare(`
      INSERT INTO employee_drafts (draft_id, draft_data, proposed_by, status)
      VALUES (?, ?, ?, 'pending')
    `).run(draft_id, JSON.stringify(draft_data), proposed_by);
    
    res.json({
      success: true,
      draft_id: draft_id,
      id: result.lastInsertRowid,
      status: 'pending',
      message: 'Employee draft created and pending HR review'
    });
  } catch (err) {
    console.error('Draft creation error:', err);
    res.status(500).json({ error: err.message });
  }
});

// ── List Employee Drafts ───────────────────────────────────
router.get('/drafts', (req, res) => {
  const { status = 'pending' } = req.query;
  
  try {
    const db = getDb();
    const drafts = db.prepare(`
      SELECT 
        id,
        draft_id,
        draft_data,
        proposed_by,
        proposed_at,
        status,
        reviewed_by,
        reviewed_at,
        review_notes,
        final_employee_id
      FROM employee_drafts
      WHERE status = ?
      ORDER BY proposed_at DESC
    `).all(status);
    
    // Parse draft_data JSON
    const parsedDrafts = drafts.map(d => ({
      ...d,
      draft_data: JSON.parse(d.draft_data)
    }));
    
    res.json({
      success: true,
      drafts: parsedDrafts,
      count: parsedDrafts.length
    });
  } catch (err) {
    console.error('Draft list error:', err);
    res.status(500).json({ error: err.message });
  }
});

// ── Get Single Draft ────────────────────────────────────────
router.get('/draft/:id', (req, res) => {
  try {
    const db = getDb();
    const draft = db.prepare(`
      SELECT * FROM employee_drafts 
      WHERE draft_id = ? OR id = ?
    `).get(req.params.id, req.params.id);
    
    if (!draft) {
      return res.status(404).json({ error: 'Draft not found' });
    }
    
    res.json({
      success: true,
      draft: {
        ...draft,
        draft_data: JSON.parse(draft.draft_data)
      }
    });
  } catch (err) {
    console.error('Draft fetch error:', err);
    res.status(500).json({ error: err.message });
  }
});

// ── Approve Draft & Create Employee ───────────────────────────
router.post('/draft/:id/approve', async (req, res) => {
  const { reviewed_by = 'hr_admin', review_notes = '' } = req.body;
  
  try {
    const db = getDb();
    
    // Get the draft
    const draft = db.prepare(`
      SELECT * FROM employee_drafts 
      WHERE draft_id = ? OR id = ?
    `).get(req.params.id, req.params.id);
    
    if (!draft) {
      return res.status(404).json({ error: 'Draft not found' });
    }
    
    if (draft.status !== 'pending') {
      return res.status(400).json({ error: `Draft is already ${draft.status}` });
    }
    
    const draftData = JSON.parse(draft.draft_data);
    
    // Find department ID
    let deptId = draftData.department_id;
    if (!deptId && draftData.department) {
      const dept = db.prepare('SELECT id FROM departments WHERE name = ?').get(draftData.department);
      if (dept) deptId = dept.id;
    }
    
    // Find manager ID
    let managerId = draftData.reporting_manager_id;
    if (!managerId && draftData.manager_name) {
      const parts = draftData.manager_name.split(' ');
      const manager = db.prepare(`
        SELECT id FROM employees 
        WHERE first_name = ? AND last_name = ?
      `).get(parts[0], parts.slice(1).join(' '));
      if (manager) managerId = manager.id;
    }
    
    // Calculate salary breakdown from CTC
    const ctc = draftData.ctc_annual || 0;
    const basic = Math.round(ctc * 0.4);  // 40% basic
    const hra = Math.round(basic * 0.5);  // 50% of basic as HRA
    const special = ctc - basic - hra - Math.round(ctc * 0.048);  // Remaining - PF
    const pf = Math.round(basic * 0.12);  // 12% of basic as PF
    
    // Insert employee
    const result = db.prepare(`
      INSERT INTO employees (
        employee_id, first_name, last_name, email, phone, designation,
        department_id, level, employment_type, employment_status,
        date_of_joining, probation_end_date, work_location, reporting_manager_id,
        ctc_annual, basic_salary, hra, special_allowance, pf_contribution,
        skills, gender, dob
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).run(
      draftData.employee_id || `EMP${Date.now().toString().slice(-6)}`,
      draftData.first_name,
      draftData.last_name,
      draftData.email,
      draftData.phone || null,
      draftData.designation,
      deptId || null,
      draftData.level || 'L1',
      draftData.employment_type || 'Full-Time',
      'Active',
      draftData.date_of_joining || new Date().toISOString().split('T')[0],
      draftData.probation_end_date || null,
      draftData.work_location || 'Bengaluru',
      managerId || null,
      ctc || null,
      basic || null,
      hra || null,
      special > 0 ? special : 0,
      pf || null,
      draftData.skills || null,
      draftData.gender || null,
      draftData.dob || null
    );
    
    const employeeId = result.lastInsertRowid;
    
    // Update draft status
    db.prepare(`
      UPDATE employee_drafts 
      SET status = 'approved', 
          reviewed_by = ?, 
          reviewed_at = datetime('now'),
          review_notes = ?,
          final_employee_id = ?,
          updated_at = datetime('now')
      WHERE id = ?
    `).run(reviewed_by, review_notes, employeeId, draft.id);
    
    res.json({
      success: true,
      message: 'Employee created successfully',
      employee_id: employeeId,
      draft_id: draft.draft_id,
      employee: {
        id: employeeId,
        first_name: draftData.first_name,
        last_name: draftData.last_name,
        email: draftData.email,
        designation: draftData.designation
      }
    });
    
  } catch (err) {
    console.error('Draft approval error:', err);
    res.status(500).json({ error: err.message });
  }
});

// ── Reject Draft ─────────────────────────────────────────────
router.post('/draft/:id/reject', (req, res) => {
  const { reviewed_by = 'hr_admin', review_notes = '' } = req.body;
  
  try {
    const db = getDb();
    
    const draft = db.prepare(`
      SELECT * FROM employee_drafts 
      WHERE draft_id = ? OR id = ?
    `).get(req.params.id, req.params.id);
    
    if (!draft) {
      return res.status(404).json({ error: 'Draft not found' });
    }
    
    if (draft.status !== 'pending') {
      return res.status(400).json({ error: `Draft is already ${draft.status}` });
    }
    
    db.prepare(`
      UPDATE employee_drafts 
      SET status = 'rejected', 
          reviewed_by = ?, 
          reviewed_at = datetime('now'),
          review_notes = ?,
          updated_at = datetime('now')
      WHERE id = ?
    `).run(reviewed_by, review_notes, draft.id);
    
    res.json({
      success: true,
      message: 'Draft rejected',
      draft_id: draft.draft_id
    });
    
  } catch (err) {
    console.error('Draft rejection error:', err);
    res.status(500).json({ error: err.message });
  }
});

// ── Draft Stats ───────────────────────────────────────────────
router.get('/drafts/stats', (req, res) => {
  try {
    const db = getDb();
    const stats = db.prepare(`
      SELECT 
        SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
        SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) as approved,
        SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) as rejected,
        COUNT(*) as total
      FROM employee_drafts
    `).get();
    
    res.json({
      success: true,
      stats: {
        pending: stats.pending || 0,
        approved: stats.approved || 0,
        rejected: stats.rejected || 0,
        total: stats.total || 0
      }
    });
  } catch (err) {
    console.error('Draft stats error:', err);
    res.status(500).json({ error: err.message });
  }
});

// ── Suggested Questions ──────────────────────────────────────
router.get('/suggestions', (req, res) => {
  res.json([
    "How many employees do we have across all departments?",
    "Who are the top performers from the last performance review cycle?",
    "Which employees are currently on probation and when does it end?",
    "Show me all employees in Engineering with CTC above ₹20 lakhs",
    "Who has taken the most leave in 2025 so far?",
    "What is the average salary by department?",
    "Which employees haven't had a performance review in the last year?",
    "Show me headcount breakdown by location",
    "Who are the direct reports of Arjun Mehta?",
    "What is our total annual payroll cost?",
    "Which department has the highest average CTC?",
    "List all employees who joined in the last 6 months",
    "Who are the employees currently on leave?",
    "Show attrition — who has resigned and when?",
    "Give me a full profile of employee EMP022",
    "Add a new Software Engineer in the Engineering department",
    "What is our gender diversity ratio?",
  ]);
});

export default router;
