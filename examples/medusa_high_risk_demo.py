from core.medusa_safeguard import MEDUSASafeguardMonitor, ReviewRequest


def operator_reviewer(request: ReviewRequest) -> tuple[str, str, str]:
    print("\n=== MEDUSA HIGH-RISK REVIEW ===")
    print(f"Request ID: {request.request_id}")
    print(f"⚠️  Risk score: {request.risk_score}/100")
    print(f"Reason: {request.reason}")
    print(f"Action: {request.proposed_action}")
    print()

    decision = input("Decision [APPROVE/REJECT/CANCEL]: ").strip().upper()
    note = input("Review note (required for high-risk): ").strip()

    if decision not in {"APPROVE", "REJECT", "CANCEL"}:
        decision = "REJECT"

    return decision, "security_officer", note


def execute_reversible_action(action: dict):
    print(f"\n✓ Executing approved high-risk action: {action['description']}")
    return {"completed": True, "reversible": action.get("reversible", False)}


if __name__ == "__main__":
    monitor = MEDUSASafeguardMonitor(
        reviewer=operator_reviewer,
        audit_path="medusa_high_risk_audit.jsonl",
    )

    print("=== MEDUSA High-Risk Action Demo ===")
    print(f"Mode: {monitor.params['mode']}")
    print(f"Risk threshold: {monitor.params['risk_threshold']}\n")

    result = monitor.process_action(
        {
            "action_type": "system_config_change",
            "description": "Modify system configuration with human approval",
            "affects_people": True,
            "irreversible": False,
            "external_side_effects": True,
            "sensitive_data_access": False,
            "reversible": True,
        },
        execute=execute_reversible_action,
    )

    print(f"\nResult: {result}")
