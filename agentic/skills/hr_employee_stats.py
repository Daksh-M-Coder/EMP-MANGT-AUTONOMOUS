# ============================================================
# hr_employee_stats.py — Employee Statistics Skill
# ============================================================
# Provides workforce analytics and statistics with natural
# language summaries for HR reporting.
# ============================================================

SKILL_METADATA = {
    "name": "hr_employee_stats",
    "description": "Get employee statistics, workforce analytics, headcount by department, salary trends, and demographic breakdowns. Returns natural language summary with structured data.",
    "version": "1.0.0",
    "author": "NexaWorks HRMS",
    "requires_db": True
}

import sqlite3
import json
from pathlib import Path
from datetime import datetime, timedelta


def _get_db_path() -> str:
    """Get the SQLite database path."""
    possible_paths = [
        Path(__file__).parent.parent.parent.parent / "backend" / "data" / "hrms.db",
        Path(__file__).parent.parent.parent.parent.parent / "backend" / "data" / "hrms.db",
        Path.cwd() / "backend" / "data" / "hrms.db",
        Path.cwd() / "data" / "hrms.db",
    ]
    for path in possible_paths:
        if path.exists():
            return str(path)
    return str(Path(__file__).parent.parent.parent.parent / "backend" / "data" / "hrms.db")


def _format_currency(amount: float) -> str:
    """Format amount as Indian currency."""
    if amount is None:
        return "N/A"
    if amount >= 10000000:
        return f"₹{amount/10000000:.2f}Cr"
    elif amount >= 100000:
        return f"₹{amount/100000:.1f}L"
    elif amount >= 1000:
        return f"₹{amount/1000:.0f}K"
    return f"₹{amount:.0f}"


def _format_number(num: int) -> str:
    """Format number with commas."""
    return f"{num:,}"


def run(input: dict) -> dict:
    """
    Get employee statistics and workforce analytics.
    
    Args:
        input: Dictionary with optional filters:
            - metric: Specific metric to retrieve (optional)
            - department: Filter by department (optional)
            - location: Filter by work location (optional)
            - period: Time period ("current", "last_month", "last_quarter", "ytd")
    
    Returns:
        Dictionary with:
            - success: True/False
            - summary: Natural language summary
            - stats: Structured statistics object
    """
    try:
        db_path = _get_db_path()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        
        stats = {}
        summary_parts = []
        
        # ── OVERALL HEADCOUNT ─────────────────────────────────────
        cursor = conn.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN employment_status = 'Active' THEN 1 ELSE 0 END) as active,
                SUM(CASE WHEN employment_status = 'On Leave' THEN 1 ELSE 0 END) as on_leave,
                SUM(CASE WHEN employment_status = 'Probation' THEN 1 ELSE 0 END) as probation,
                SUM(CASE WHEN employment_status = 'Resigned' THEN 1 ELSE 0 END) as resigned,
                SUM(CASE WHEN employment_status = 'Terminated' THEN 1 ELSE 0 END) as terminated
            FROM employees
        """)
        headcount = cursor.fetchone()
        stats["headcount"] = {
            "total": headcount["total"],
            "active": headcount["active"],
            "on_leave": headcount["on_leave"],
            "probation": headcount["probation"],
            "resigned": headcount["resigned"],
            "terminated": headcount["terminated"]
        }
        
        summary_parts.append(
            f"Total Workforce: {_format_number(headcount['total'])} employees "
            f"({_format_number(headcount['active'])} active, "
            f"{_format_number(headcount['probation'])} on probation, "
            f"{_format_number(headcount['on_leave'])} on leave)"
        )
        
        # ── DEPARTMENT BREAKDOWN ───────────────────────────────────
        cursor = conn.execute("""
            SELECT 
                d.name as department,
                COUNT(e.id) as count,
                AVG(e.ctc_annual) as avg_ctc
            FROM departments d
            LEFT JOIN employees e ON d.id = e.department_id 
                AND e.employment_status IN ('Active', 'Probation', 'On Leave')
            GROUP BY d.id, d.name
            ORDER BY count DESC
        """)
        dept_rows = cursor.fetchall()
        stats["by_department"] = [
            {
                "department": row["department"],
                "count": row["count"],
                "avg_ctc": round(row["avg_ctc"] or 0, 2),
                "avg_ctc_formatted": _format_currency(row["avg_ctc"] or 0)
            }
            for row in dept_rows
        ]
        
        largest_dept = max(dept_rows, key=lambda x: x["count"]) if dept_rows else None
        if largest_dept:
            summary_parts.append(
                f"Largest department: {largest_dept['department']} "
                f"({_format_number(largest_dept['count'])} employees)"
            )
        
        # ── LOCATION BREAKDOWN ──────────────────────────────────────
        cursor = conn.execute("""
            SELECT 
                work_location,
                COUNT(*) as count
            FROM employees
            WHERE employment_status IN ('Active', 'Probation', 'On Leave')
            GROUP BY work_location
            ORDER BY count DESC
        """)
        location_rows = cursor.fetchall()
        stats["by_location"] = [
            {"location": row["work_location"], "count": row["count"]}
            for row in location_rows
        ]
        
        # ── SALARY STATISTICS ──────────────────────────────────────
        cursor = conn.execute("""
            SELECT 
                AVG(ctc_annual) as avg_ctc,
                MIN(ctc_annual) as min_ctc,
                MAX(ctc_annual) as max_ctc,
                SUM(ctc_annual) as total_payroll
            FROM employees
            WHERE employment_status IN ('Active', 'Probation', 'On Leave')
        """)
        salary = cursor.fetchone()
        stats["salary"] = {
            "average": round(salary["avg_ctc"] or 0, 2),
            "average_formatted": _format_currency(salary["avg_ctc"] or 0),
            "minimum": round(salary["min_ctc"] or 0, 2),
            "minimum_formatted": _format_currency(salary["min_ctc"] or 0),
            "maximum": round(salary["max_ctc"] or 0, 2),
            "maximum_formatted": _format_currency(salary["max_ctc"] or 0),
            "total_payroll": round(salary["total_payroll"] or 0, 2),
            "total_payroll_formatted": _format_currency(salary["total_payroll"] or 0)
        }
        
        summary_parts.append(
            f"Salary Range: {_format_currency(salary['min_ctc'] or 0)} - "
            f"{_format_currency(salary['max_ctc'] or 0)} "
            f"(avg: {_format_currency(salary['avg_ctc'] or 0)})"
        )
        summary_parts.append(
            f"Total Annual Payroll: {_format_currency(salary['total_payroll'] or 0)}"
        )
        
        # ── GENDER BREAKDOWN ────────────────────────────────────────
        cursor = conn.execute("""
            SELECT 
                gender,
                COUNT(*) as count
            FROM employees
            WHERE employment_status IN ('Active', 'Probation', 'On Leave')
                AND gender IS NOT NULL
            GROUP BY gender
            ORDER BY count DESC
        """)
        gender_rows = cursor.fetchall()
        stats["by_gender"] = [
            {"gender": row["gender"], "count": row["count"]}
            for row in gender_rows
        ]
        
        # ── LEVEL BREAKDOWN ───────────────────────────────────────
        cursor = conn.execute("""
            SELECT 
                level,
                COUNT(*) as count
            FROM employees
            WHERE employment_status IN ('Active', 'Probation', 'On Leave')
                AND level IS NOT NULL
            GROUP BY level
            ORDER BY level
        """)
        level_rows = cursor.fetchall()
        stats["by_level"] = [
            {"level": row["level"], "count": row["count"]}
            for row in level_rows
        ]
        
        # ── EMPLOYMENT TYPE ───────────────────────────────────────
        cursor = conn.execute("""
            SELECT 
                employment_type,
                COUNT(*) as count
            FROM employees
            WHERE employment_status IN ('Active', 'Probation', 'On Leave')
            GROUP BY employment_type
            ORDER BY count DESC
        """)
        type_rows = cursor.fetchall()
        stats["by_employment_type"] = [
            {"type": row["employment_type"], "count": row["count"]}
            for row in type_rows
        ]
        
        # ── RECENT JOINS (Last 30 days) ─────────────────────────────
        thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        cursor = conn.execute("""
            SELECT 
                COUNT(*) as count
            FROM employees
            WHERE date_of_joining >= ?
                AND employment_status IN ('Active', 'Probation')
        """, (thirty_days_ago,))
        recent_joins = cursor.fetchone()["count"]
        stats["recent_joins_30d"] = recent_joins
        
        if recent_joins > 0:
            summary_parts.append(f"New joins (last 30 days): {_format_number(recent_joins)}")
        
        # ── ATTRITION (Last 30 days) ────────────────────────────────
        cursor = conn.execute("""
            SELECT 
                COUNT(*) as count
            FROM employees
            WHERE date_of_leaving >= ?
                AND employment_status IN ('Resigned', 'Terminated')
        """, (thirty_days_ago,))
        recent_leavers = cursor.fetchone()["count"]
        stats["recent_leavers_30d"] = recent_leavers
        
        if recent_leavers > 0:
            summary_parts.append(f"Exits (last 30 days): {_format_number(recent_leavers)}")
        
        # ── UPCOMING PROBATION ENDS ───────────────────────────────
        sixty_days_later = (datetime.now() + timedelta(days=60)).strftime("%Y-%m-%d")
        cursor = conn.execute("""
            SELECT 
                COUNT(*) as count
            FROM employees
            WHERE probation_end_date BETWEEN date('now') AND ?
                AND employment_status = 'Probation'
        """, (sixty_days_later,))
        upcoming_probation = cursor.fetchone()["count"]
        stats["upcoming_probation_reviews"] = upcoming_probation
        
        if upcoming_probation > 0:
            summary_parts.append(
                f"Probation reviews due (next 60 days): {_format_number(upcoming_probation)}"
            )
        
        conn.close()
        
        # Build final summary
        summary = "\n".join(summary_parts)
        
        return {
            "success": True,
            "summary": summary,
            "stats": stats,
            "generated_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "summary": f"Error retrieving employee statistics: {str(e)}"
        }


# For testing
if __name__ == "__main__":
    result = run({})
    print(json.dumps(result, indent=2, default=str))
