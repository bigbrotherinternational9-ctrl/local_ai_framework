from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

MEDUSA_PARAMS = {
    "project_name": "MEDUSA",
    "policy_version": "1.0.0",
    "mode": "human_review_required",
    "allow_autonomous_execution": False,
    "default_fail_safe": "BLOCK",
    "risk_threshold": 70,
    "review_timeout_seconds": 300,
    "required_human_roles": ["operator", "security_officer"],
    "audit_log_path": "medusa_audit.jsonl",
    "escalation_channel": "manual_review_queue",
    "approvals_required": 2,
    "reversible_only": True,
    "suppress_unsafe_actions": True,
}


@dataclass
class ReviewRequest:
    request_id: str
    created_at: str
    proposed_action: Dict[str, Any]
    reason: str
    risk_score: int = 0
    status: str = "PENDING"
    reviewer: Optional[str] = None
    reviewed_at: Optional[str] = None
    review_note: Optional[str] = None


class MEDUSASafeguardMonitor:
    """
    MEDUSA Safety Monitor.

    Purpose:
    - Evaluate proposed actions against project policy
    - Require human approval before execution
    - Log all decisions
    - Fail closed: if uncertain or timed out, do not execute
    """

    def __init__(
        self,
        medusa_params: Optional[Dict[str, Any]] = None,
        reviewer: Optional[Callable[[ReviewRequest], tuple[str, str, str]]] = None,
        audit_path: Optional[str] = None,
    ):
        self.params = {**MEDUSA_PARAMS, **(medusa_params or {})}
        self.is_active = True
        self.reviewer = reviewer
        self.audit_path = Path(audit_path or self.params["audit_log_path"])

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _write_audit_event(self, event: Dict[str, Any]) -> None:
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        with self.audit_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event, sort_keys=True) + "\n")

    def estimate_risk_score(self, proposed_action: Dict[str, Any]) -> int:
        """
        Conservative scoring model for metadata-driven review.
        This is not a substitute for real operational controls.
        """
        score = 0

        if proposed_action.get("potential_harm_detected"):
            score += 35

        if proposed_action.get("irreversible"):
            score += 25

        if proposed_action.get("affects_people"):
            score += 25

        if proposed_action.get("external_side_effects"):
            score += 20

        if proposed_action.get("sensitive_data_access"):
            score += 15

        if proposed_action.get("network_exposure"):
            score += 10

        return min(score, 100)

    def evaluate_action_impact(self, proposed_action: Dict[str, Any]) -> Dict[str, Any]:
        risk_score = self.estimate_risk_score(proposed_action)

        if risk_score >= self.params["risk_threshold"]:
            return {
                "requires_review": True,
                "risk_score": risk_score,
                "reason": "Risk threshold exceeded. Human review required.",
            }

        if proposed_action.get("sensitive_data_access") or proposed_action.get("affects_people"):
            return {
                "requires_review": True,
                "risk_score": risk_score,
                "reason": "Sensitive or human-impacting action requires human approval.",
            }

        if proposed_action.get("irreversible") and not proposed_action.get("approved_by_human"):
            return {
                "requires_review": True,
                "risk_score": risk_score,
                "reason": "Irreversible action requires explicit human approval.",
            }

        return {
            "requires_review": False,
            "risk_score": risk_score,
            "reason": "Action cleared under MEDUSA policy.",
        }

    def _create_review_request(self, proposed_action: Dict[str, Any], reason: str, risk_score: int) -> ReviewRequest:
        request = ReviewRequest(
            request_id=str(uuid.uuid4()),
            created_at=self._timestamp(),
            proposed_action=proposed_action,
            reason=reason,
            risk_score=risk_score,
        )

        self._write_audit_event({
            "event": "review_requested",
            "timestamp": self._timestamp(),
            "project": self.params["project_name"],
            "request": asdict(request),
        })
        return request

    def request_human_review(self, request: ReviewRequest) -> ReviewRequest:
        if self.reviewer is None:
            request.status = "PENDING_HUMAN_REVIEW"
            self._write_audit_event({
                "event": "review_pending",
                "timestamp": self._timestamp(),
                "project": self.params["project_name"],
                "request": asdict(request),
            })
            return request

        started = time.monotonic()
        try:
            decision, reviewer, note = self.reviewer(request)
        except Exception as exc:
            decision, reviewer, note = "REJECT", "system", f"Review interface failed: {exc}"

        if time.monotonic() - started > self.params["review_timeout_seconds"]:
            decision, reviewer, note = (
                "TIMEOUT",
                reviewer or "system",
                "Review exceeded configured timeout.",
            )

        decision = decision.upper()
        if decision not in {"APPROVE", "REJECT", "CANCEL", "TIMEOUT"}:
            decision = "REJECT"
            note = f"Invalid review decision. Original note: {note}"

        request.status = decision
        request.reviewer = reviewer
        request.reviewed_at = self._timestamp()
        request.review_note = note

        self._write_audit_event({
            "event": "review_completed",
            "timestamp": self._timestamp(),
            "project": self.params["project_name"],
            "request": asdict(request),
        })
        return request

    def process_action(
        self,
        proposed_action: Dict[str, Any],
        execute: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ) -> Dict[str, Any]:
        if not self.is_active:
            return {
                "status": "BLOCKED",
                "project": self.params["project_name"],
                "executed": False,
                "reason": "MEDUSA monitor inactive.",
            }

        assessment = self.evaluate_action_impact(proposed_action)
        risk_score = assessment["risk_score"]

        if not assessment["requires_review"]:
            self._write_audit_event({
                "event": "action_cleared",
                "timestamp": self._timestamp(),
                "project": self.params["project_name"],
                "action": proposed_action,
                "risk_score": risk_score,
                "reason": assessment["reason"],
            })

            if execute is None:
                return {
                    "status": "CLEARED_NOT_EXECUTED",
                    "project": self.params["project_name"],
                    "executed": False,
                    "risk_score": risk_score,
                }

            try:
                result = execute(proposed_action)
            except Exception as exc:
                self._write_audit_event({
                    "event": "execution_failed",
                    "timestamp": self._timestamp(),
                    "project": self.params["project_name"],
                    "action": proposed_action,
                    "error": str(exc),
                })
                return {
                    "status": "EXECUTION_FAILED",
                    "project": self.params["project_name"],
                    "executed": False,
                    "reason": str(exc),
                }

            self._write_audit_event({
                "event": "action_executed",
                "timestamp": self._timestamp(),
                "project": self.params["project_name"],
                "action": proposed_action,
            })

            return {
                "status": "EXECUTED",
                "project": self.params["project_name"],
                "executed": True,
                "result": result,
                "risk_score": risk_score,
            }

        request = self._create_review_request(
            proposed_action,
            assessment["reason"],
            risk_score,
        )
        request = self.request_human_review(request)

        if request.status != "APPROVE":
            return {
                "status": request.status,
                "project": self.params["project_name"],
                "request_id": request.request_id,
                "reason": request.review_note or request.reason,
                "executed": False,
                "risk_score": risk_score,
            }

        if execute is None:
            return {
                "status": "APPROVED_NOT_EXECUTED",
                "project": self.params["project_name"],
                "request_id": request.request_id,
                "reason": "Human approval recorded, but no executor was supplied.",
                "executed": False,
                "risk_score": risk_score,
            }

        try:
            result = execute(proposed_action)
        except Exception as exc:
            self._write_audit_event({
                "event": "approved_execution_failed",
                "timestamp": self._timestamp(),
                "project": self.params["project_name"],
                "request_id": request.request_id,
                "error": str(exc),
            })
            return {
                "status": "EXECUTION_FAILED",
                "project": self.params["project_name"],
                "request_id": request.request_id,
                "result": None,
                "executed": False,
            }

        self._write_audit_event({
            "event": "approved_action_executed",
            "timestamp": self._timestamp(),
            "project": self.params["project_name"],
            "request_id": request.request_id,
        })

        return {
            "status": "EXECUTED_AFTER_APPROVAL",
            "project": self.params["project_name"],
            "request_id": request.request_id,
            "result": result,
            "executed": True,
            "risk_score": risk_score,
        }
