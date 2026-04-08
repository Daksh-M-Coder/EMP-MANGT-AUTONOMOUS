import Database from 'better-sqlite3';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DB_PATH = path.join(__dirname, '../../data/hrms.db');

let db;

export function getDb() {
  if (!db) {
    db = new Database(DB_PATH);
    db.pragma('journal_mode = WAL');
    db.pragma('foreign_keys = ON');
    initSchema();
  }
  return db;
}

function initSchema() {
  db.exec(`
    CREATE TABLE IF NOT EXISTS departments (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL UNIQUE,
      head_employee_id INTEGER,
      budget_inr INTEGER,
      location TEXT,
      created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS employees (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      employee_id TEXT NOT NULL UNIQUE,
      first_name TEXT NOT NULL,
      last_name TEXT NOT NULL,
      email TEXT NOT NULL UNIQUE,
      phone TEXT,
      dob TEXT,
      gender TEXT CHECK(gender IN ('Male','Female','Other')),
      blood_group TEXT,
      department_id INTEGER REFERENCES departments(id),
      designation TEXT NOT NULL,
      level TEXT CHECK(level IN ('L1','L2','L3','L4','L5','L6','L7')),
      employment_type TEXT CHECK(employment_type IN ('Full-Time','Part-Time','Contract','Intern')),
      employment_status TEXT CHECK(employment_status IN ('Active','On Leave','Probation','Resigned','Terminated')) DEFAULT 'Active',
      date_of_joining TEXT NOT NULL,
      date_of_leaving TEXT,
      probation_end_date TEXT,
      reporting_manager_id INTEGER REFERENCES employees(id),
      work_location TEXT CHECK(work_location IN ('Bengaluru','Mumbai','Hyderabad','Remote','Pune')),
      ctc_annual INTEGER,
      basic_salary INTEGER,
      hra INTEGER,
      special_allowance INTEGER,
      pf_contribution INTEGER,
      pan_number TEXT,
      aadhar_number TEXT,
      bank_account TEXT,
      bank_name TEXT,
      ifsc_code TEXT,
      address_line1 TEXT,
      address_city TEXT,
      address_state TEXT,
      address_pincode TEXT,
      emergency_contact_name TEXT,
      emergency_contact_relation TEXT,
      emergency_contact_phone TEXT,
      skills TEXT,
      linkedin_url TEXT,
      profile_photo_url TEXT,
      created_at TEXT DEFAULT (datetime('now')),
      updated_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS leave_records (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      employee_id INTEGER NOT NULL REFERENCES employees(id),
      leave_type TEXT CHECK(leave_type IN ('Casual','Sick','Earned','LOP','Maternity','Paternity','Comp Off')),
      start_date TEXT NOT NULL,
      end_date TEXT NOT NULL,
      days_taken REAL NOT NULL,
      status TEXT CHECK(status IN ('Approved','Pending','Rejected')) DEFAULT 'Approved',
      reason TEXT,
      approved_by INTEGER REFERENCES employees(id),
      created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS performance_reviews (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      employee_id INTEGER NOT NULL REFERENCES employees(id),
      review_period TEXT NOT NULL,
      review_type TEXT CHECK(review_type IN ('Annual','Mid-Year','Probation','PIP')),
      rating REAL CHECK(rating BETWEEN 1 AND 5),
      reviewer_id INTEGER REFERENCES employees(id),
      goals_set TEXT,
      goals_achieved TEXT,
      strengths TEXT,
      improvement_areas TEXT,
      comments TEXT,
      salary_hike_percent REAL,
      review_date TEXT NOT NULL,
      created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS salary_history (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      employee_id INTEGER NOT NULL REFERENCES employees(id),
      effective_date TEXT NOT NULL,
      old_ctc INTEGER,
      new_ctc INTEGER,
      hike_percent REAL,
      reason TEXT CHECK(reason IN ('Annual Appraisal','Promotion','Market Correction','Joining','Contract Renewal')),
      approved_by INTEGER REFERENCES employees(id),
      created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS assets_assigned (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      employee_id INTEGER NOT NULL REFERENCES employees(id),
      asset_type TEXT CHECK(asset_type IN ('Laptop','Mobile','Access Card','Monitor','Headset','Keyboard & Mouse')),
      asset_tag TEXT,
      brand_model TEXT,
      assigned_date TEXT,
      returned_date TEXT,
      condition TEXT CHECK(condition IN ('Good','Fair','Damaged')),
      notes TEXT
    );

    CREATE TABLE IF NOT EXISTS employee_drafts (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      draft_id TEXT NOT NULL UNIQUE,
      draft_data TEXT NOT NULL,
      proposed_by TEXT,
      proposed_at TEXT DEFAULT (datetime('now')),
      status TEXT CHECK(status IN ('pending', 'approved', 'rejected')) DEFAULT 'pending',
      reviewed_by TEXT,
      reviewed_at TEXT,
      review_notes TEXT,
      final_employee_id INTEGER REFERENCES employees(id),
      created_at TEXT DEFAULT (datetime('now')),
      updated_at TEXT DEFAULT (datetime('now'))
    );

    CREATE INDEX IF NOT EXISTS idx_employees_dept ON employees(department_id);
    CREATE INDEX IF NOT EXISTS idx_employees_status ON employees(employment_status);
    CREATE INDEX IF NOT EXISTS idx_leaves_employee ON leave_records(employee_id);
    CREATE INDEX IF NOT EXISTS idx_reviews_employee ON performance_reviews(employee_id);
    CREATE INDEX IF NOT EXISTS idx_drafts_status ON employee_drafts(status);
  `);
}
