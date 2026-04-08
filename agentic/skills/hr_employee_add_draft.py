# ============================================================
# hr_employee_add_draft.py — Employee Add Draft Skill
# ============================================================
# Creates an employee draft for HR review before actual insertion.
# NEVER writes directly to database - always creates draft for approval.
# ============================================================

SKILL_METADATA = {
    "name": "hr_employee_add_draft",
    "description": "Extract employee information from natural language and create a draft for HR review. Validates data and generates human-readable summary. Does NOT write to database directly.",
    "version": "1.0.0",
    "author": "NexaWorks HRMS",
    "requires_db": False
}

import re
import json
from datetime import datetime, timedelta
from typing import Optional


# Valid options for enum fields
VALID_DEPARTMENTS = [
    "Engineering", "Product", "Design", "Marketing", "Sales", 
    "HR", "Finance", "Operations", "Legal", "Support", "IT"
]

VALID_DESIGNATIONS = [
    "Software Engineer", "Senior Software Engineer", "Lead Engineer", "Engineering Manager",
    "Product Manager", "Senior Product Manager", "Director of Product",
    "Designer", "Senior Designer", "Lead Designer", "Design Manager",
    "Marketing Manager", "Content Writer", "SEO Specialist",
    "Sales Representative", "Account Executive", "Sales Manager",
    "HR Manager", "HR Executive", "Recruiter", "Talent Acquisition Specialist",
    "Finance Manager", "Accountant", "Financial Analyst",
    "Operations Manager", "Operations Executive",
    "Legal Counsel", "Compliance Officer",
    "Support Engineer", "Customer Success Manager",
    "IT Administrator", "System Administrator", "DevOps Engineer"
]

VALID_LEVELS = ["L1", "L2", "L3", "L4", "L5", "L6", "L7"]

VALID_EMPLOYMENT_TYPES = ["Full-time", "Contract", "Intern"]

VALID_EMPLOYMENT_STATUS = ["Active", "Probation", "On Leave"]

VALID_WORK_LOCATIONS = ["Bengaluru", "Mumbai", "Hyderabad", "Pune", "Remote", "Chennai", "Delhi"]

VALID_GENDERS = ["Male", "Female", "Other", "Prefer not to say"]


# Email validation regex
EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

# Phone validation (Indian format)
PHONE_REGEX = re.compile(r'^[\+]?[0-9\s\-\(\)]{10,15}$')


def _validate_email(email: str) -> tuple[bool, Optional[str]]:
    """Validate email format."""
    if not email:
        return False, "Email is required"
    email = email.strip().lower()
    if not EMAIL_REGEX.match(email):
        return False, f"Invalid email format: {email}"
    return True, email


def _validate_phone(phone: str) -> tuple[bool, Optional[str]]:
    """Validate phone number."""
    if not phone:
        return True, None  # Phone is optional
    phone = phone.strip()
    if not PHONE_REGEX.match(phone):
        return False, f"Invalid phone format: {phone}"
    return True, phone


def _validate_date(date_str: str, field_name: str = "date") -> tuple[bool, Optional[str]]:
    """Validate date string (YYYY-MM-DD format)."""
    if not date_str:
        return False, f"{field_name} is required"
    
    # Try to parse
    formats = ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y"]
    for fmt in formats:
        try:
            parsed = datetime.strptime(date_str.strip(), fmt)
            # Return in standard format
            return True, parsed.strftime("%Y-%m-%d")
        except ValueError:
            continue
    
    return False, f"Invalid {field_name} format: {date_str}. Use YYYY-MM-DD"


def _extract_from_natural_language(text: str) -> dict:
    """Extract employee fields from natural language text."""
    extracted = {}
    text_lower = text.lower()
    
    # Name extraction patterns
    name_patterns = [
        r'(?:name is|called|named)\s+([A-Za-z\s]+?)(?:\s+(?:with|having|email|phone)|$|\.\s)',
        r'(?:add|create|hire)\s+([A-Za-z\s]+?)(?:\s+(?:as|to|with|email)|$|\.\s)',
        r'^([A-Za-z]+(?:\s+[A-Za-z]+)+)(?:\s+with|$)',
    ]
    for pattern in name_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            if len(name) > 2 and len(name) < 50:
                parts = name.split()
                if len(parts) >= 2:
                    extracted["first_name"] = parts[0]
                    extracted["last_name"] = " ".join(parts[1:])
                else:
                    extracted["first_name"] = name
                break
    
    # Email extraction
    email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text)
    if email_match:
        extracted["email"] = email_match.group(0).lower()
    
    # Phone extraction
    phone_patterns = [
        r'(?:phone|contact|mobile|call)\s*(?:is|:)?\s*([\+\d\s\-\(\)]{10,20})',
        r'(?:\+|91)?[\s\-]?[789]\d{9}',
    ]
    for pattern in phone_patterns:
        match = re.search(pattern, text)
        if match:
            phone = re.sub(r'\s+', '', match.group(0))
            if len(phone) >= 10:
                extracted["phone"] = phone
                break
    
    # Department extraction
    for dept in VALID_DEPARTMENTS:
        if dept.lower() in text_lower:
            extracted["department"] = dept
            break
    
    # Designation extraction
    for desig in VALID_DESIGNATIONS:
        if desig.lower() in text_lower:
            extracted["designation"] = desig
            break
    
    # If no exact designation match, try role keywords
    if "designation" not in extracted:
        role_keywords = {
            "engineer": "Software Engineer",
            "developer": "Software Engineer",
            "manager": "Engineering Manager",
            "designer": "Designer",
            "analyst": "Financial Analyst",
            "recruiter": "Recruiter",
            "sales": "Sales Representative",
            "marketing": "Marketing Manager",
            "writer": "Content Writer",
        }
        for keyword, default_role in role_keywords.items():
            if keyword in text_lower:
                extracted["designation"] = default_role
                break
    
    # Level extraction (L1-L7)
    level_match = re.search(r'\b(L[1-7])\b', text, re.IGNORECASE)
    if level_match:
        extracted["level"] = level_match.group(1).upper()
    
    # Employment type
    if "contract" in text_lower:
        extracted["employment_type"] = "Contract"
    elif "intern" in text_lower:
        extracted["employment_type"] = "Intern"
    else:
        extracted["employment_type"] = "Full-time"
    
    # Work location
    for loc in VALID_WORK_LOCATIONS:
        if loc.lower() in text_lower:
            extracted["work_location"] = loc
            break
    
    # Salary/CTC extraction
    salary_patterns = [
        r'(?:ctc|salary|package)(?:\s+(?:is|of|:))?\s*(?:₹|Rs\.?|INR)?\s*([\d,\.]+)\s*(?:L|lakh|lakhs)?',
        r'(?:₹|Rs\.?|INR)?\s*([\d,\.]+)\s*(?:L|lakh|lakhs)?(?:\s+(?:ctc|salary|package))?',
    ]
    for pattern in salary_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            amount_str = match.group(1).replace(',', '')
            try:
                amount = float(amount_str)
                # If amount is small, assume it's in lakhs
                if amount < 100000:
                    amount = amount * 100000
                extracted["ctc_annual"] = round(amount, 2)
                break
            except ValueError:
                pass
    
    # Date of joining extraction
    date_patterns = [
        r'(?:joining|join|start)(?:\s+(?:date|on))?(?:\s+(?:is|:))?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
        r'(?:from|on|starting)\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
    ]
    for pattern in date_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            is_valid, date_str = _validate_date(match.group(1), "date of joining")
            if is_valid:
                extracted["date_of_joining"] = date_str
                break
    
    # If no date, default to today
    if "date_of_joining" not in extracted:
        extracted["date_of_joining"] = datetime.now().strftime("%Y-%m-%d")
    
    # Skills extraction (comma-separated after "skills" keyword)
    skills_match = re.search(r'(?:skills?|knows?|expertise)(?:\s+(?:include|are|:|in))?\s*([A-Za-z0-9\s,#\.]+?)(?:\.|$|\n)', text, re.IGNORECASE)
    if skills_match:
        skills_text = skills_match.group(1)
        # Clean up and split
        skills = [s.strip() for s in re.split(r'[,#]', skills_text) if s.strip()]
        if skills:
            extracted["skills"] = ", ".join(skills)
    
    return extracted


def _validate_draft(draft: dict) -> list[str]:
    """Validate the draft and return list of issues."""
    issues = []
    
    # Required fields
    required = ["first_name", "email", "designation", "department", "date_of_joining"]
    for field in required:
        if not draft.get(field):
            issues.append(f"Missing required field: {field}")
    
    # Validate email if present
    if draft.get("email"):
        is_valid, result = _validate_email(draft["email"])
        if not is_valid:
            issues.append(result)
        else:
            draft["email"] = result  # Use normalized email
    
    # Validate phone if present
    if draft.get("phone"):
        is_valid, result = _validate_phone(draft["phone"])
        if not is_valid:
            issues.append(result)
    
    # Validate department
    if draft.get("department") and draft["department"] not in VALID_DEPARTMENTS:
        issues.append(f"Unknown department: {draft['department']}. Valid: {', '.join(VALID_DEPARTMENTS)}")
    
    # Validate level
    if draft.get("level") and draft["level"] not in VALID_LEVELS:
        issues.append(f"Invalid level: {draft['level']}. Valid: {', '.join(VALID_LEVELS)}")
    
    # Validate employment type
    if draft.get("employment_type") and draft["employment_type"] not in VALID_EMPLOYMENT_TYPES:
        issues.append(f"Invalid employment type: {draft['employment_type']}")
    
    # Validate work location
    if draft.get("work_location") and draft["work_location"] not in VALID_WORK_LOCATIONS:
        issues.append(f"Unknown location: {draft['work_location']}. Valid: {', '.join(VALID_WORK_LOCATIONS)}")
    
    return issues


def _generate_employee_id() -> str:
    """Generate a new employee ID."""
    # Format: EMP + timestamp-based number
    now = datetime.now()
    return f"EMP{now.strftime('%y%m')}{now.strftime('%d%H%M')[2:]}"


def _generate_summary(draft: dict, issues: list, is_complete: bool) -> str:
    """Generate human-readable summary of the draft."""
    lines = []
    
    name = f"{draft.get('first_name', '')} {draft.get('last_name', '')}".strip() or "Unknown"
    lines.append(f"Employee Draft: {name}")
    lines.append("=" * 40)
    
    # Key details
    details = []
    if draft.get("designation"):
        details.append(f"Role: {draft['designation']}")
    if draft.get("department"):
        details.append(f"Department: {draft['department']}")
    if draft.get("level"):
        details.append(f"Level: {draft['level']}")
    if draft.get("work_location"):
        details.append(f"Location: {draft['work_location']}")
    if draft.get("employment_type"):
        details.append(f"Type: {draft['employment_type']}")
    if draft.get("date_of_joining"):
        details.append(f"Joining: {draft['date_of_joining']}")
    
    if details:
        lines.append(" | ".join(details))
    
    # Contact
    contact = []
    if draft.get("email"):
        contact.append(f"Email: {draft['email']}")
    if draft.get("phone"):
        contact.append(f"Phone: {draft['phone']}")
    if contact:
        lines.append(" | ".join(contact))
    
    # Salary
    if draft.get("ctc_annual"):
        ctc_lakhs = draft["ctc_annual"] / 100000
        lines.append(f"CTC: ₹{ctc_lakhs:.2f}L per annum")
    
    # Skills
    if draft.get("skills"):
        lines.append(f"Skills: {draft['skills']}")
    
    # Status
    lines.append("")
    if is_complete:
        lines.append("✓ Draft is complete and ready for HR review.")
    else:
        lines.append(f"⚠ Draft incomplete - {len(issues)} issue(s) to resolve:")
        for issue in issues[:5]:  # Show first 5 issues
            lines.append(f"  - {issue}")
        if len(issues) > 5:
            lines.append(f"  ... and {len(issues) - 5} more")
    
    return "\n".join(lines)


def run(input: dict) -> dict:
    """
    Create an employee draft from extracted information.
    
    Args:
        input: Dictionary containing either:
            - raw_query: Natural language description of employee to add
            OR explicit fields:
            - first_name, last_name, email, phone, designation, department,
              level, employment_type, work_location, ctc_annual,
              date_of_joining, skills, etc.
    
    Returns:
        Dictionary with:
            - success: True (draft created, may have issues)
            - draft: The employee draft object with all extracted/derived fields
            - is_complete: True if all required fields present and valid
            - issues: List of validation issues (if any)
            - summary: Human-readable description of the draft
            - status: "pending_review" (always)
    """
    try:
        # Start with any explicit fields
        draft = {}
        for key in ["first_name", "last_name", "email", "phone", "designation", 
                    "department", "level", "employment_type", "employment_status",
                    "work_location", "ctc_annual", "date_of_joining", 
                    "probation_end_date", "gender", "dob", "skills", "address_city"]:
            if key in input and input[key] is not None:
                draft[key] = input[key]
        
        # Extract from natural language if raw_query provided
        if "raw_query" in input and input["raw_query"]:
            extracted = _extract_from_natural_language(input["raw_query"])
            # Merge: explicit fields take priority
            for key, value in extracted.items():
                if key not in draft or not draft[key]:
                    draft[key] = value
        
        # Generate employee ID
        draft["employee_id"] = _generate_employee_id()
        
        # Set defaults
        if "employment_status" not in draft:
            draft["employment_status"] = "Active"
        if "probation_end_date" not in draft and draft.get("date_of_joining"):
            # Default 6 months probation
            try:
                join_date = datetime.strptime(draft["date_of_joining"], "%Y-%m-%d")
                probation_end = join_date + timedelta(days=180)
                draft["probation_end_date"] = probation_end.strftime("%Y-%m-%d")
            except:
                pass
        
        # Validate
        issues = _validate_draft(draft)
        is_complete = len(issues) == 0
        
        # Generate summary
        summary = _generate_summary(draft, issues, is_complete)
        
        return {
            "success": True,
            "draft": draft,
            "is_complete": is_complete,
            "issues": issues,
            "summary": summary,
            "status": "pending_review",
            "message": "Employee draft created successfully. Review required before saving to database."
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "summary": f"Error creating employee draft: {str(e)}"
        }


# For testing
if __name__ == "__main__":
    # Test with natural language
    test_input = {
        "raw_query": "Add a new employee called John Doe with email john@company.com. He's a Software Engineer in Engineering department, level L3, joining on 2024-03-15 with CTC of 15 lakhs. Location is Bengaluru. Skills: Python, React, Node.js"
    }
    result = run(test_input)
    print(json.dumps(result, indent=2, default=str))
