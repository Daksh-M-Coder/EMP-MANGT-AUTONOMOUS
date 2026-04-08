import { getDb } from '../db/database.js';

export const DB_TOOL_DEFINITION = {
  name: 'query_employee_database',
  description: `Execute a READ-ONLY SQL query against the HRMS SQLite database.
  
  Tables available:
  - employees: id, employee_id, first_name, last_name, email, phone, dob, gender, blood_group, department_id, designation, level(L1-L7), employment_type, employment_status(Active/On Leave/Probation/Resigned/Terminated), date_of_joining, date_of_leaving, probation_end_date, reporting_manager_id, work_location(Bengaluru/Mumbai/Hyderabad/Remote/Pune), ctc_annual, basic_salary, hra, special_allowance, pf_contribution, pan_number, address_city, address_state, address_pincode, skills, created_at
  - departments: id, name, head_employee_id, budget_inr, location
  - leave_records: id, employee_id, leave_type(Casual/Sick/Earned/LOP/Maternity/Paternity/Comp Off), start_date, end_date, days_taken, status(Approved/Pending/Rejected), reason, approved_by
  - performance_reviews: id, employee_id, review_period, review_type(Annual/Mid-Year/Probation/PIP), rating(1-5), reviewer_id, strengths, improvement_areas, comments, salary_hike_percent, review_date
  - salary_history: id, employee_id, effective_date, old_ctc, new_ctc, hike_percent, reason, approved_by
  - assets_assigned: id, employee_id, asset_type, asset_tag, brand_model, assigned_date, returned_date, condition
  
  Use JOINs freely. Use e.first_name || ' ' || e.last_name for full names. CTC values are in INR (annual). Only SELECT queries allowed.`,
  input_schema: {
    type: 'object',
    properties: {
      sql: {
        type: 'string',
        description: 'The SELECT SQL query to execute. Must be read-only.'
      },
      description: {
        type: 'string',
        description: 'Brief human-readable description of what this query does'
      }
    },
    required: ['sql', 'description']
  }
};

export function runDbTool(input) {
  const { sql } = input;
  
  // Safety: only allow SELECT
  const normalized = sql.trim().toUpperCase();
  if (!normalized.startsWith('SELECT') && !normalized.startsWith('WITH')) {
    return { error: 'Only SELECT queries are allowed for safety.' };
  }
  
  try {
    const db = getDb();
    const rows = db.prepare(sql).all();
    return {
      success: true,
      row_count: rows.length,
      data: rows.slice(0, 100) // cap at 100 rows
    };
  } catch (err) {
    return { error: err.message, sql };
  }
}
