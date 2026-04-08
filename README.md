# NexaWorks HRMS — Intelligent Employee Management System

> **Think Tony Stark's EDITH/FRIDAY, but for HR.** An AI-powered HR management platform that understands natural language queries and executes complex workforce operations — search, analyze, manage, and optimize your entire employee ecosystem through conversational intelligence.

---

## 🎯 The Core Problem

**Traditional HR systems are rigid, menu-driven, and require navigating through dozens of screens to perform simple operations.** HR professionals waste hours:
- Manually filtering through employee records across multiple views
- Writing complex reports and dashboards from scratch
- Cross-referencing data between payroll, performance, leaves, and departments
- Answering repetitive stakeholder queries about headcount, budgets, and attrition
- Performing bulk operations through tedious form-based interfaces

## 💡 Our Solution

**A conversational HR intelligence platform that transforms how organizations manage their workforce.** Instead of clicking through menus, HR teams simply *ask* — and the system understands, reasons, and acts.

### How It Works
```
Natural Language Query → AI Reasoning Engine → Database Tool Execution → Intelligent Response
     "Show me all engineers          ↓              ↓                          ↓
      in Bangalore with              ↓    Queries live SQLite         "Found 34 engineers
      CTC > 15L and rating           ↓    database with SQL           in Bangalore. 12 have
      >= 4.0"                        ↓    and analyzes results        CTC > 15L, 8 have
                                                                        rating >= 4.0..."
```

### The EDITH/FRIDAY Analogy
Just like Tony Stark's AI assistants understood context, executed commands, and provided intelligent insights:
- **Context-Aware**: Understands follow-up questions and maintains conversation state
- **Tool-Using**: Executes real database operations (SELECT, JOIN, aggregate functions)
- **Reasoning**: Thinks through multi-step queries before acting (ReAct pattern)
- **Proactive**: Flags anomalies (excessive leaves, missing reviews, attrition risks)
- **Precision**: Every claim backed by actual data — zero hallucination

---

## 🚀 System Capabilities

### 🤖 AI-Powered HR Assistant (NexaBot)
**Your conversational interface to the entire workforce database.**
- Natural language queries over live SQLite database
- Multi-turn conversations with context retention
- Real SQL execution — no fabricated data
- Supports complex operations: headcount analysis, payroll calculations, performance tracking, leave patterns, attrition risk assessment
- Shows number of DB queries executed per response (transparency)

### 📊 Real-Time Analytics Dashboard
- Live headcount, payroll, and diversity metrics
- Department-wise workforce distribution
- Location-based analytics
- Recent joiners feed

### 👥 Employee Lifecycle Management
- **Search & Filter**: By name, ID, email, designation, department, location, status
- **Full Profiles**: 30+ fields including personal info, compensation, skills, reporting hierarchy
- **Performance Tracking**: Review history with star ratings and feedback
- **Leave Management**: Leave records and pattern analysis
- **Compensation History**: Salary revision timeline with hike percentages
- **CRUD Operations**: Add, edit, view, and terminate employees

### 🏢 Department Intelligence
- Headcount and budget allocation per department
- Location distribution
- Direct drill-down to filtered employee lists

---

## 🛠️ Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Frontend** | React 18 + Vite + Tailwind CSS | Modern UI with hot reload |
| **Backend** | Node.js + Express (ESM) | RESTful API server |
| **Database** | SQLite via `better-sqlite3` | Zero-config embedded database |
| **AI Engine** | Claude API (`claude-sonnet-4-20250514`) | Natural language understanding + tool use |
| **AI Pattern** | ReAct (Reason + Act) | Multi-step reasoning with live tool execution |
| **UI Library** | Lucide React + React Markdown | Icons and formatted AI responses |
| **Fonts** | Syne (display) + Instrument Sans (body) | Professional typography |

---

## 📁 Project Architecture

```
EMPLOYEE DATA MGT SYS/
├── backend/
│   ├── src/
│   │   ├── index.js              # Express server + API routing
│   │   ├── db/
│   │   │   ├── database.js       # SQLite schema initialization
│   │   │   └── seed.js           # 100 Indian employees seed script
│   │   ├── routes/
│   │   │   ├── employees.js      # Employee CRUD + stats endpoints
│   │   │   └── ai.js             # AI chat endpoint
│   │   ├── ai/
│   │   │   └── agent.js          # ReAct agent loop with tool use
│   │   └── tools/
│   │       └── dbTool.js         # Database query tool definition
│   ├── data/                     # SQLite database storage
│   └── .env                      # API keys and configuration
│
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Dashboard.jsx     # Analytics dashboard
│   │   │   ├── Employees.jsx     # Employee directory
│   │   │   ├── EmployeeDetail.jsx # Full employee profiles
│   │   │   ├── AIAssistant.jsx   # NexaBot chat interface
│   │   │   └── Departments.jsx   # Department intelligence
│   │   ├── components/
│   │   │   ├── layout/Sidebar.jsx
│   │   │   └── employees/EmployeeModal.jsx
│   │   └── lib/
│   │       ├── api.js            # API client
│   │       └── utils.js          # Formatters and helpers
│   └── vite.config.js            # Vite + proxy configuration
│
└── agentic/                      # Advanced LangGraph agentic system (optional)
    ├── planner.py                # Query planning agent
    ├── executor.py               # Tool execution agent
    ├── reflector.py              # Response quality checker
    ├── memory/                   # Multi-layer memory system
    └── skills/                   # Pluggable domain skills
```

---

## ⚡ Quick Start

### Prerequisites
- **Node.js 18+** (ESM support required)
- **Anthropic API Key** ([Get one here](https://console.anthropic.com))

### 1️⃣ Backend Setup

```bash
cd backend
npm install
npm run seed              # Initialize database with 100 employees
npm run dev               # Start server on http://localhost:3001
```

**Configure API Key:**
```bash
# Create backend/.env
ANTHROPIC_API_KEY=sk-ant-your-key-here
PORT=3001
```

### 2️⃣ Frontend Setup

```bash
cd frontend
npm install
npm run dev               # Start dev server on http://localhost:5173
```

**Access the application:** http://localhost:5173

---

## 🧠 How the AI Agent Works

### The ReAct Pattern (Reason + Act)

```
User Query: "Who are the top performers in Engineering with CTC > 20L?"
    ↓
[REASON] Claude analyzes: Need to JOIN employees + performance_reviews + departments
    ↓
[ACT] Calls query_employee_database tool with SQL:
      SELECT e.name, e.ctc, r.rating 
      FROM employees e 
      JOIN performance_reviews r ON e.id = r.employee_id
      JOIN departments d ON e.department_id = d.id
      WHERE d.name = 'Engineering' AND e.ctc > 2000000 AND r.rating >= 4.0
    ↓
[OBSERVE] Gets real results from SQLite (12 employees found)
    ↓
[REASON] Analyzes results, decides data is sufficient
    ↓
[RESPOND] Returns formatted answer with employee table and insights
```

### Example Queries NexaBot Handles

**Headcount & Organization:**
- "How many engineers do we have across Bengaluru and Hyderabad?"
- "Show me the reporting structure for the Product team"
- "Which departments have grown the most this year?"

**Compensation & Payroll:**
- "What is the total payroll for the Engineering department?"
- "Who got hikes above 15% in the last appraisal cycle?"
- "Show me salary distribution by level (L1-L7)"

**Performance Management:**
- "Who are the top performers from FY2024-25?"
- "Which employees need performance improvement plans?"
- "Average performance rating by department"

**Leave & Attendance:**
- "Who has taken more than 10 days leave in 2025?"
- "Which employees are currently on leave?"
- "Leave usage patterns by department"

**Employee Intelligence:**
- "Give me a full employment history for EMP022"
- "Show me all L5+ engineers with their CTCs"
- "Who is on probation and when does each probation end?"

**Attrition & Risk:**
- "Who has resigned in the last quarter?"
- "Which employees are attrition risks based on performance and tenure?"
- "Probation completion dates for this month"

---

## 🔌 API Reference

### Employee Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/employees` | List employees (pagination + filters) |
| GET | `/api/employees/:id` | Full employee details + leaves + reviews |
| POST | `/api/employees` | Create new employee |
| PUT | `/api/employees/:id` | Update employee record |
| DELETE | `/api/employees/:id` | Soft delete (mark as Terminated) |
| GET | `/api/employees/meta/stats` | Dashboard statistics |
| GET | `/api/employees/meta/departments` | Department list with headcount |

### AI Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/ai/chat` | Send query, get AI response with tool usage |
| GET | `/api/ai/suggestions` | Get starter question suggestions |

---

## 🗄️ Database Schema

**6 Relational Tables:**

| Table | Records | Purpose |
|---|---|---|
| `employees` | 100 | Core employee data (30+ fields: personal, work, compensation) |
| `departments` | 10 | Department metadata with budget and location |
| `leave_records` | 40+ | Leave entries with types and durations |
| `performance_reviews` | 27 | Review ratings, feedback, and appraisal cycles |
| `salary_history` | Variable | Salary revisions with hike percentages |
| `assets_assigned` | Variable | Laptop, phone, and asset tracking |

**Pre-seeded Organization: NexaWorks IT Solutions**
- **HQ**: Bengaluru
- **Offices**: Mumbai, Hyderabad, Pune
- **10 Departments**: Engineering, Product, QA, DevOps, Data Science, HR, Finance, Sales, Customer Success, Legal
- **100 Employees**: L1 (Interns) → L7 (VP/C-Suite)
- **Realistic Data**: Indian names, PAN numbers, market-competitive salaries, authentic designations

---

## 🎨 User Interface Features

### Dashboard
- Real-time headcount, total payroll, gender diversity metrics
- Department-wise workforce visualization
- Location distribution breakdown
- Recent joiners activity feed

### Employee Directory
- Full-text search (name, ID, email, designation)
- Multi-filter support (department, status, location)
- Paginated results (15 per page)
- Click-through to comprehensive profiles

### Employee Profile View
- Complete personal and professional information
- Compensation history with hike timeline visualization
- Performance reviews with star ratings
- Leave records table
- Skills and competencies tags
- Direct reports hierarchy

### AI Assistant Interface
- Conversational chat UI
- Natural language processing for HR queries
- Real-time DB query execution transparency
- Multi-turn conversation support
- 8 starter question prompts for onboarding
- Markdown-formatted responses with tables

### Department Cards
- Visual cards for all 10 departments
- Headcount and budget display
- Office location indicators
- Direct navigation to filtered employee lists

---

## 🔒 Security & Best Practices

- **API Key Protection**: Anthropic key stored in `.env`, never committed
- **Soft Deletes**: Employees marked as "Terminated" instead of hard deletion
- **SQL Injection Prevention**: Tool-based query execution with validation
- **CORS Configuration**: Controlled cross-origin access
- **Environment Isolation**: Separate `.env` files for different environments

---

## 🧪 Advanced: LangGraph Agentic System (Optional)

The project includes an advanced **multi-agent system** built with LangGraph for complex workflows:

- **Planner**: Breaks down complex queries into executable steps
- **Executor**: Runs tools and skills with iterative reasoning
- **Reflector**: Validates output quality and decides next actions
- **Memory System**: Episodic, vector, entity, and working memory layers
- **Pluggable Skills**: Drop-in Python skill files for domain-specific operations

**Use Case**: Extend NexaBot with advanced capabilities like resume parsing, job matching, fraud detection, or predictive analytics.

```bash
cd agentic
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8000
```

---

## 📈 Future Roadmap

- [ ] **Predictive Analytics**: Attrition risk scoring, performance forecasting
- [ ] **Automated Workflows**: Onboarding, offboarding, appraisal cycle automation
- [ ] **Advanced AI Tools**: Document generation (offer letters, PIP notices)
- [ ] **Multi-Tenant Support**: Multiple organizations in single instance
- [ ] **Real-Time Notifications**: Slack/Email alerts for HR events
- [ ] **Advanced RBAC**: Role-based access control with permission levels
- [ ] **Audit Logging**: Complete change history for compliance
- [ ] **Integration APIs**: Payroll systems, background verification, ATS

---

## 📄 License

Internal use — NexaWorks IT Solutions

---

**Built with precision. Powered by AI. Designed for HR teams who demand more.** 🚀
