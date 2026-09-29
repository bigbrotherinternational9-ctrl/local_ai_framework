from core.medusa_safeguard import MEDUSASafeguardMonitor, ReviewRequest


def operator_reviewer(request: ReviewRequest) -> tuple[str, str, str]:
    print("\n=== MEDUSA HUMAN REVIEW ===")
    print(f"Request ID: {request.request_id}")
    print(f"Risk score: {request.risk_score}")
    print(f"Reason: {request.reason}")
    print(f"Action: {request.proposed_action}")
    print()

    decision = input("Decision [APPROVE/REJECT/CANCEL]: ").strip().upper()
    note = input("Review note: ").strip()

    if decision not in {"APPROVE", "REJECT", "CANCEL"}:
        decision = "REJECT"

    return decision, "operator", note


def execute_safe_action(action: dict):
    # This is a placeholder for a tightly scoped function.
    print(f"\n✓ Executing approved MEDUSA action: {action['description']}")
    return {"completed": True, "approved_by_human": True}


if __name__ == "__main__":
    monitor = MEDUSASafeguardMonitor(
        reviewer=operator_reviewer,
        audit_path="medusa_audit.jsonl",
    )

    print("=== MEDUSA Safety Monitor Demo ===")
    print(f"Mode: {monitor.params['mode']}")
    print(f"Risk threshold: {monitor.params['risk_threshold']}")
    print(f"Audit log: {monitor.audit_path}\n")

    result = monitor.process_action(
        {
            "action_type": "local_diagnostic",
            "description": "Run a reversible maintenance check",
            "affects_people": False,
            "irreversible": False,
            "external_side_effects": False,
            "sensitive_data_access": False,
        },
        execute=execute_safe_action,
    )

    print(f"\nResult: {result}")
