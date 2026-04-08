# ============================================================
# hr_employee_search.py — Employee Search Skill
# ============================================================
# Search employees by name, department, role, or any criteria.
# Returns natural language summary + structured data.
# ============================================================

SKILL_METADATA = {
    "name": "hr_employee_search",
    "description": "Search employees by name, department, role, status, salary range, or any combination. Returns formatted results with natural language summary.",
    "version": "1.0.0",
    "author": "NexaWorks HRMS",
    "requires_db": True
}

import sqlite3
import json
from pathlib import Path


def _get_db_path() -> str:
    """Get the SQLite database path."""
    # Try to find the backend database
    possible_paths = [
        Path(__file__).parent.parent.parent.parent / "backend" / "data" / "hrms.db",
        Path(__file__).parent.parent.parent.parent.parent / "backend" / "data" / "hrms.db",
        Path.cwd() / "backend" / "data" / "hrms.db",
        Path.cwd() / "data" / "hrms.db",
    ]
    for path in possible_paths:
        if path.exists():
            return str(path)
    # Default fallback
    return str(Path(__file__).parent.parent.parent.parent / "backend" / "data" / "hrms.db")


def _format_currency(amount: float) -> str:
    """Format amount as Indian currency."""
    if amount >= 100000:
        return f"₹{amount/100000:.1f}L"
    elif amount >= 1000:
        return f"₹{amount/1000:.0f}K"
    return f"₹{amount:.0f}"


def _build_query(filters: dict) -> tuple[str, list]:
    """Build SQL query based on filters."""
    base_query = """
        SELECT 
            e.id,
            e.employee_id,
            e.first_name || ' ' || e.last_name as full_name,
            e.email,
            e.phone,
            e.designation,
            e.level,
            e.employment_type,
            e.employment_status,
            e.date_of_joining,
            e.work_location,
            e.ctc_annual,
            d.name as department_name,
            m.first_name || ' ' || m.last_name as manager_name
        FROM employees e
        LEFT JOIN departments d ON e.department_id = d.id
        LEFT JOIN employees m ON e.reporting_manager_id = m.id
        WHERE 1=1
    """
    
    conditions = []
    params = []
    
    # Name search (partial match)
    if filters.get("name"):
        conditions.append("(e.first_name LIKE ? OR e.last_name LIKE ?)")
        name_pattern = f"%{filters['name']}%"
        params.extend([name_pattern, name_pattern])
    
    # Department
    if filters.get("department"):
        conditions.append("(d.name LIKE ? OR e.department_id = ?)")
        params.extend([f"%{filters['department']}%", filters.get("department_id", 0)])
    
    # Designation/Role
    if filters.get("role") or filters.get("designation"):
        role = filters.get("role") or filters.get("designation")
        conditions.append("e.designation LIKE ?")
        params.append(f"%{role}%")
    
    # Employment status
    if filters.get("status"):
        conditions.append("e.employment_status = ?")
        params.append(filters["status"])
    
    # Work location
    if filters.get("location"):
        conditions.append("e.work_location LIKE ?")
        params.append(f"%{filters['location']}%")
    
    # Level (L1-L7)
    if filters.get("level"):
        conditions.append("e.level = ?")
        params.append(filters["level"])
    
    # Salary range
    if filters.get("min_salary"):
        conditions.append("e.ctc_annual >= ?")
        params.append(float(filters["min_salary"]))
    
    if filters.get("max_salary"):
        conditions.append("e.ctc_annual <= ?")
        params.append(float(filters["max_salary"]))
    
    # Employment type
    if filters.get("employment_type"):
        conditions.append("e.employment_type = ?")
        params.append(filters["employment_type"])
    
    # Exclude terminated by default unless explicitly requested
    if not filters.get("include_terminated"):
        conditions.append("e.employment_status != 'Terminated'")
    
    # Date range - joined after
    if filters.get("joined_after"):
        conditions.append("e.date_of_joining >= ?")
        params.append(filters["joined_after"])
    
    # Date range - joined before
    if filters.get("joined_before"):
        conditions.append("e.date_of_joining <= ?")
        params.append(filters["joined_before"])
    
    # Manager name search
    if filters.get("manager"):
        conditions.append("(m.first_name LIKE ? OR m.last_name LIKE ?)")
        manager_pattern = f"%{filters['manager']}%"
        params.extend([manager_pattern, manager_pattern])
    
    # Skills search
    if filters.get("skills"):
        conditions.append("e.skills LIKE ?")
        params.append(f"%{filters['skills']}%")
    
    if conditions:
        base_query += " AND " + " AND ".join(conditions)
    
    base_query += " ORDER BY e.first_name ASC"
    
    # Limit results (default 50)
    limit = int(filters.get("limit", 50))
    base_query += f" LIMIT {limit}"
    
    return base_query, params


def _generate_summary(results: list, filters: dict, total_count: int) -> str:
    """Generate natural language summary of search results."""
    if not results:
        return "No employees found matching your criteria."
    
    count = len(results)
    shown = f"Showing {count} employee{'s' if count > 1 else ''}"
    if total_count > count:
        shown += f" (out of {total_count} total matches)"
    
    # Build criteria description
    criteria = []
    if filters.get("name"):
        criteria.append(f"name containing '{filters['name']}'")
    if filters.get("department"):
        criteria.append(f"department '{filters['department']}'")
    if filters.get("role") or filters.get("designation"):
        criteria.append(f"role '{filters.get('role') or filters.get('designation')}'")
    if filters.get("status"):
        criteria.append(f"status '{filters['status']}'")
    if filters.get("location"):
        criteria.append(f"location '{filters['location']}'")
    if filters.get("level"):
        criteria.append(f"level {filters['level']}")
    if filters.get("min_salary") and filters.get("max_salary"):
        criteria.append(f"salary between {_format_currency(float(filters['min_salary']))} and {_format_currency(float(filters['max_salary']))}")
    elif filters.get("min_salary"):
        criteria.append(f"salary above {_format_currency(float(filters['min_salary']))}")
    elif filters.get("max_salary"):
        criteria.append(f"salary below {_format_currency(float(filters['max_salary']))}")
    
    if criteria:
        criteria_str = ", ".join(criteria)
        summary = f"Found {shown} matching {criteria_str}."
    else:
        summary = f"Found {shown} in the system."
    
    # Add quick stats
    if count > 0:
        statuses = {}
        locations = {}
        for emp in results:
            status = emp.get("employment_status", "Unknown")
            location = emp.get("work_location", "Unknown")
            statuses[status] = statuses.get(status, 0) + 1
            locations[location] = locations.get(location, 0) + 1
        
        stats_parts = []
        if len(statuses) > 1:
            status_summary = ", ".join([f"{v} {k}" for k, v in statuses.items()])
            stats_parts.append(f"Status: {status_summary}")
        
        if len(locations) > 1:
            location_summary = ", ".join([f"{v} in {k}" for k, v in locations.items()])
            stats_parts.append(f"Locations: {location_summary}")
        
        if stats_parts:
            summary += "\n" + " | ".join(stats_parts)
    
    return summary


def run(input: dict) -> dict:
    """
    Execute employee search with given filters.
    
    Args:
        input: Dictionary with search filters:
            - name: Partial name match
            - department: Department name
            - role/designation: Job title
            - status: Active/On Leave/Probation/Resigned/Terminated
            - location: Work location
            - level: L1-L7
            - min_salary: Minimum annual CTC
            - max_salary: Maximum annual CTC
            - employment_type: Full-time/Contract/Intern
            - joined_after: Date (YYYY-MM-DD)
            - joined_before: Date (YYYY-MM-DD)
            - manager: Manager name
            - skills: Skill keywords
            - include_terminated: True/False (default False)
            - limit: Max results (default 50)
    
    Returns:
        Dictionary with:
            - success: True/False
            - summary: Natural language description
            - employees: List of employee records
            - count: Number of results
            - total_matches: Total matching (if limited)
    """
    try:
        db_path = _get_db_path()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        
        # Build and execute query
        query, params = _build_query(input)
        cursor = conn.execute(query, params)
        rows = cursor.fetchall()
        
        # Convert to list of dicts
        employees = [dict(row) for row in rows]
        
        # Get total count (for "showing X of Y")
        total_matches = len(employees)
        if len(employees) >= int(input.get("limit", 50)):
            # Might be more, get total
            count_query = query.replace("SELECT e.id", "SELECT COUNT(*) as c").split("ORDER BY")[0]
            count_cursor = conn.execute(count_query, params)
            total_matches = count_cursor.fetchone()["c"]
        
        conn.close()
        
        # Format currency for display
        for emp in employees:
            if emp.get("ctc_annual"):
                emp["ctc_formatted"] = _format_currency(emp["ctc_annual"])
        
        # Generate natural language summary
        summary = _generate_summary(employees, input, total_matches)
        
        return {
            "success": True,
            "summary": summary,
            "employees": employees,
            "count": len(employees),
            "total_matches": total_matches
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "summary": f"Error searching employees: {str(e)}"
        }


# For testing directly
if __name__ == "__main__":
    # Test search by name
    result = run({"name": "Arjun"})
    print(json.dumps(result, indent=2, default=str))
