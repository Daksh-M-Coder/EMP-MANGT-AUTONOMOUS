# ============================================================
# skills/fraud_risk_scorer.py — Example Domain Skill
# ============================================================
# This skill demonstrates how to adapt the system to a
# specific domain (fraud detection) by writing a skill.
#
# To use in a different project, replace this with your
# domain logic. The interface (SKILL_METADATA + run()) never
# changes — only the internal logic does.
# ============================================================

SKILL_METADATA = {
    "name":        "fraud_risk_scorer",
    "description": "Scores a transaction's fraud risk based on heuristic rules.",
    "version":     "1.0.0",
    "author":      "Universal Agent System",
}


def run(input: dict) -> dict:
    """
    Compute a heuristic fraud risk score for a transaction.

    Input:
        {
          "amount":        float,   # Transaction amount in USD
          "country":       str,     # ISO country code (e.g. "US", "NG")
          "account_age_days": int,  # How old the account is
          "hour_of_day":   int,     # 0-23, hour of transaction
          "is_new_device": bool     # Whether device is new/unrecognized
        }

    Output:
        {
          "success":     bool,
          "result": {
            "risk_score":  float,   # 0.0 (safe) to 1.0 (high risk)
            "risk_level":  str,     # "low" | "medium" | "high" | "critical"
            "flags":       list[str], # Triggered risk flags
            "recommended_action": str
          },
          "error": None
        }
    """
    amount           = float(input.get("amount", 0))
    country          = str(input.get("country", "US")).upper()
    account_age_days = int(input.get("account_age_days", 365))
    hour             = int(input.get("hour_of_day", 12))
    is_new_device    = bool(input.get("is_new_device", False))

    score = 0.0
    flags = []

    # Rule 1: Large transaction
    if amount > 10000:
        score += 0.3
        flags.append(f"large_transaction (${amount:,.0f})")
    elif amount > 5000:
        score += 0.15
        flags.append(f"elevated_amount (${amount:,.0f})")

    # Rule 2: High-risk countries (simplified list)
    HIGH_RISK_COUNTRIES = {"NG", "GH", "CI", "CM", "KE", "TZ"}
    if country in HIGH_RISK_COUNTRIES:
        score += 0.25
        flags.append(f"high_risk_country ({country})")

    # Rule 3: New account
    if account_age_days < 7:
        score += 0.35
        flags.append(f"very_new_account ({account_age_days} days)")
    elif account_age_days < 30:
        score += 0.2
        flags.append(f"new_account ({account_age_days} days)")

    # Rule 4: Unusual hours (2am-5am)
    if 2 <= hour <= 5:
        score += 0.15
        flags.append(f"unusual_hours ({hour:02d}:00)")

    # Rule 5: New device
    if is_new_device:
        score += 0.1
        flags.append("new_unrecognized_device")

    # Cap at 1.0
    score = min(score, 1.0)

    # Determine risk level
    if score >= 0.8:
        risk_level = "critical"
        action     = "BLOCK transaction immediately. Require manual review."
    elif score >= 0.6:
        risk_level = "high"
        action     = "Flag for review. Send OTP verification. Delay transfer 24h."
    elif score >= 0.35:
        risk_level = "medium"
        action     = "Monitor closely. Log for pattern analysis."
    else:
        risk_level = "low"
        action     = "Allow transaction. No action required."

    return {
        "success": True,
        "result": {
            "risk_score":         round(score, 3),
            "risk_level":         risk_level,
            "flags":              flags,
            "recommended_action": action,
        },
        "error": None,
    }
