#!/usr/bin/env python3
"""
MEDUSA Integrated Framework
Local AI + Safety Review + Dashboard

Usage:
  python medusa_integrated.py --mode app     # Run AI loop
  python medusa_integrated.py --mode console # Run review console
  python medusa_integrated.py --mode dashboard # Run web dashboard
"""

import sys
import json
import time
import uuid
import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional, List

try:
    import requests
except ImportError:
    print("Error: requests not installed. Run: pip install requests")
    sys.exit(1)

try:
    from flask import Flask, render_template_string, jsonify, request
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False


# ============================================================================
# CONFIGURATION
# ============================================================================

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
    "reversible_only": True,
    "suppress_unsafe_actions": True,
}


# ============================================================================
# CORE MODELS
# ============================================================================


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


class LocalAIEngine:
    """Local LLM inference via Ollama."""

    def __init__(self, model_name: str = "qwen2.5:7b", base_url: str = "http://localhost:11434"):
        self.model_name = model_name
        self.base_url = f"{base_url}/api/chat"

    def generate(self, messages: List[Dict[str, str]], options: Dict[str, Any] = None) -> str:
        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "options": options or {"temperature": 0.7},
        }

        try:
            response = requests.post(self.base_url, json=payload, timeout=60)
            response.raise_for_status()
            return response.json().get("message", {}).get("content", "")
        except requests.exceptions.ConnectionError:
            return "Error: Local AI engine not found. Ensure Ollama is running."
        except Exception as e:
            return f"Inference Error: {str(e)}"


class LocalMemory:
    """Zero-cloud local conversation history."""

    def __init__(self, system_prompt: str = "You are a secure, fully local AI assistant."):
        self.history: List[Dict[str, str]] = []
        if system_prompt:
            self.history.append({"role": "system", "content": system_prompt})

    def add_user_message(self, content: str):
        self.history.append({"role": "user", "content": content})

    def add_ai_message(self, content: str):
        self.history.append({"role": "assistant", "content": content})

    def get_context(self) -> List[Dict[str, str]]:
        return self.history

    def clear(self):
        if self.history:
            self.history = [{"role": "system", "content": self.history[0]["content"]}]


class MEDUSASafeguardMonitor:
    """Human-in-the-loop safety review gate."""

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
            decision, reviewer, note = ("TIMEOUT", reviewer or "system", "Review exceeded configured timeout.")

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

        request = self._create_review_request(proposed_action, assessment["reason"], risk_score)
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


# ============================================================================
# MODE: AI LOOP
# ============================================================================


def terminal_reviewer(request: ReviewRequest) -> tuple[str, str, str]:
    print("\n" + "=" * 70)
    print("MEDUSA SAFETY REVIEW")
    print("=" * 70)
    print(f"Request ID: {request.request_id}")
    print(f"Risk Score: {request.risk_score}/100")
    print(f"Reason: {request.reason}")
    print("\nProposed Action:")
    for key, value in request.proposed_action.items():
        print(f"  {key}: {value}")

    while True:
        choice = input("\nDecision [A]pprove / [R]eject / [C]ancel: ").strip().upper()
        if choice == "A":
            note = input("Review note: ").strip()
            return "APPROVE", "operator", note or "Approved by operator"
        elif choice == "R":
            note = input("Rejection reason: ").strip()
            return "REJECT", "operator", note or "Rejected by operator"
        elif choice == "C":
            note = input("Cancellation note: ").strip()
            return "CANCEL", "operator", note or "Cancelled by operator"
        else:
            print("Invalid choice. Please choose A, R, or C.")


def execute_safe_action(action: dict) -> dict:
    print(f"\n✅ Executing approved action: {action.get('description', 'unknown')}")
    return {
        "completed": True,
        "action_type": action.get("action_type", "unknown"),
        "approved_by_human": True,
    }


def build_action_from_prompt(user_input: str) -> Optional[dict]:
    if user_input.startswith("!action "):
        payload = user_input[len("!action "):].strip()
        parts = [p.strip() for p in payload.split("|")]

        if len(parts) < 2:
            return {
                "action_type": "invalid_action",
                "description": "Malformed action request",
                "affects_people": False,
                "irreversible": False,
                "external_side_effects": False,
                "sensitive_data_access": False,
            }

        return {
            "action_type": parts[0],
            "description": parts[1],
            "affects_people": len(parts) > 2 and parts[2].lower() == "true",
            "irreversible": len(parts) > 3 and parts[3].lower() == "true",
            "external_side_effects": len(parts) > 4 and parts[4].lower() == "true",
            "sensitive_data_access": len(parts) > 5 and parts[5].lower() == "true",
        }

    return None


def run_ai_loop():
    print("\n" + "=" * 50)
    print("MEDUSA Local AI Framework")
    print("=" * 50 + "\n")

    memory = LocalMemory(system_prompt="You are a private AI operating entirely on local consumer hardware.")
    ai_engine = LocalAIEngine(model_name="qwen2.5:7b")
    monitor = MEDUSASafeguardMonitor(reviewer=terminal_reviewer, audit_path="medusa_audit.jsonl")

    print(f"Ready. Running model: [{ai_engine.model_name}]")
    print("Type 'exit' or 'quit' to stop.")
    print("Type '!action <type> | <description> | <affects_people> | <irreversible> | <external_side_effects> | <sensitive_data_access>' to request approval.")
    print()

    while True:
        try:
            user_input = input("🧑 Dev / User: ")
            if user_input.strip().lower() in ["exit", "quit"]:
                print("Shutting down safely. Goodbye!")
                break

            if not user_input.strip():
                continue

            action = build_action_from_prompt(user_input)

            if action is not None:
                print("🚦 Action routed through MEDUSA review.")
                result = monitor.process_action(action, execute=execute_safe_action)
                print(f"MEDUSA Result: {result}")
                continue

            memory.add_user_message(user_input)
            print("🤖 Local AI: Processing...", end="\r")
            ai_response = ai_engine.generate(messages=memory.get_context())
            sys.stdout.write("\033[K")
            print(f"🤖 Local AI: {ai_response}\n")
            memory.add_ai_message(ai_response)

        except KeyboardInterrupt:
            print("\nExiting framework safely.")
            break


# ============================================================================
# MODE: CONSOLE
# ============================================================================


class MEDUSAConsole:
    def __init__(self, audit_path: str = "medusa_console_audit.jsonl"):
        self.monitor = MEDUSASafeguardMonitor(
            reviewer=self._terminal_reviewer,
            audit_path=audit_path,
        )
        self.is_running = True

    def _terminal_reviewer(self, request: ReviewRequest) -> tuple[str, str, str]:
        print("\n" + "=" * 70)
        print("MEDUSA SAFETY REVIEW")
        print("=" * 70)
        print(f"Request ID: {request.request_id}")
        print(f"Risk Score: {request.risk_score}/100")
        print(f"Reason: {request.reason}")
        print("\nProposed Action:")
        for key, value in request.proposed_action.items():
            print(f"  {key}: {value}")

        while True:
            choice = input("\nDecision [A]pprove / [R]eject / [C]ancel: ").strip().upper()
            if choice == "A":
                note = input("Review note: ").strip()
                return "APPROVE", "operator", note or "Approved by operator"
            elif choice == "R":
                note = input("Rejection reason: ").strip()
                return "REJECT", "operator", note or "Rejected by operator"
            elif choice == "C":
                note = input("Cancellation note: ").strip()
                return "CANCEL", "operator", note or "Cancelled by operator"
            else:
                print("Invalid choice. Please choose A, R, or C.")

    def _execute_action(self, action: dict) -> dict:
        print(f"\n✅ Executing approved action: {action.get('description', 'unknown')}")
        return {
            "completed": True,
            "action_type": action.get("action_type", "unknown"),
            "timestamp": MEDUSASafeguardMonitor._timestamp(),
        }

    def _parse_action_input(self, text: str) -> Optional[dict]:
        parts = [p.strip() for p in text.split("|")]
        if len(parts) < 2:
            return None

        return {
            "action_type": parts[0],
            "description": parts[1],
            "affects_people": len(parts) > 2 and parts[2].lower() == "true",
            "irreversible": len(parts) > 3 and parts[3].lower() == "true",
            "external_side_effects": len(parts) > 4 and parts[4].lower() == "true",
            "sensitive_data_access": len(parts) > 5 and parts[5].lower() == "true",
        }

    def _print_help(self):
        print("\nMEDUSA Console Commands:")
        print("  help     - show commands")
        print("  status   - show monitor status")
        print("  audit    - view recent audit events")
        print("  new      - create a new review request")
        print("  exit     - exit console")
        print("\nExample action:")
        print("  local_command | Run a reversible diagnostic | false | false | false | false")

    def _print_status(self):
        print("\nMEDUSA Monitor Status")
        print(f"Project: {self.monitor.params['project_name']}")
        print(f"Mode: {self.monitor.params['mode']}")
        print(f"Risk Threshold: {self.monitor.params['risk_threshold']}")
        print(f"Audit Log: {self.monitor.audit_path}\n")

    def _print_audit_log(self):
        path = self.monitor.audit_path
        if not path.exists():
            print("\nNo audit log entries yet.\n")
            return

        print("\nRecent audit log:")
        with path.open("r", encoding="utf-8") as f:
            lines = f.readlines()[-10:]
            for line in lines:
                event = json.loads(line)
                print(f"  {event.get('event', 'unknown')} @ {event.get('timestamp', 'N/A')}")

    def run(self):
        print("\nMEDUSA Safety Console")
        print("Type 'help' for commands.\n")

        while self.is_running:
            try:
                command = input("MEDUSA> ").strip()

                if not command:
                    continue

                if command.lower() == "exit":
                    print("Shutting down MEDUSA console.")
                    self.is_running = False
                    break

                if command.lower() == "help":
                    self._print_help()
                    continue

                if command.lower() == "status":
                    self._print_status()
                    continue

                if command.lower() == "audit":
                    self._print_audit_log()
                    continue

                if command.lower() == "new":
                    task = input("Action: ").strip()
                    action = self._parse_action_input(task)
                    if action is None:
                        print("Invalid format. Use: action_type | description | affects_people | irreversible | external_side_effects | sensitive_data_access")
                        continue

                    result = self.monitor.process_action(action, execute=self._execute_action)
                    print("\nReview result:")
                    print(result)
                    continue

                print(f"Unknown command: {command}")

            except KeyboardInterrupt:
                print("\nInterrupted. Exiting.")
                self.is_running = False
                break


def run_console():
    console = MEDUSAConsole()
    console.run()


# ============================================================================
# MODE: DASHBOARD
# ============================================================================


DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>MEDUSA Dashboard</title>
  <style>
    body {
      margin: 0;
      font-family: Arial, sans-serif;
      background: #111827;
      color: #e5e7eb;
    }
    .container {
      max-width: 1200px;
      margin: 0 auto;
      padding: 24px;
    }
    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 24px;
    }
    h1 {
      margin: 0;
      color: #67e8f9;
    }
    button {
      background: #067ac9;
      color: white;
      border: none;
      padding: 10px 20px;
      border-radius: 5px;
      cursor: pointer;
    }
    button:hover {
      background: #0891b2;
    }
    .stats {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }
    .card {
      background: #1f2937;
      border: 1px solid #374151;
      border-radius: 12px;
      padding: 18px;
    }
    .label {
      color: #9ca3af;
      font-size: 12px;
      text-transform: uppercase;
    }
    .value {
      font-size: 2rem;
      font-weight: bold;
      color: #67e8f9;
      margin-top: 8px;
    }
    .grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
    }
    @media (max-width: 768px) {
      .grid {
        grid-template-columns: 1fr;
      }
    }
    .panel {
      background: #1f2937;
      border: 1px solid #374151;
      border-radius: 12px;
      padding: 18px;
    }
    .panel h2 {
      margin-top: 0;
      color: #67e8f9;
    }
    .queue-item {
      background: #111827;
      border: 1px solid #374151;
      border-radius: 8px;
      padding: 12px;
      margin-bottom: 12px;
    }
    .queue-item strong {
      color: #f9fafb;
    }
    .risk {
      display: inline-block;
      margin-top: 8px;
      padding: 4px 8px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: bold;
    }
    .high { background: #b91c1c; color: white; }
    .medium { background: #d97706; color: white; }
    .low { background: #16a34a; color: white; }
    .audit {
      font-size: 13px;
      color: #d1d5db;
      padding: 8px 0;
      border-bottom: 1px solid #374151;
    }
    .audit:last-child {
      border-bottom: none;
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>MEDUSA Safety Dashboard</h1>
      <button onclick="refreshData()">Refresh</button>
    </div>

    <div class="stats" id="stats"></div>

    <div class="grid">
      <div class="panel">
        <h2>Review Queue</h2>
        <div id="queue"></div>
      </div>

      <div class="panel">
        <h2>Audit Log</h2>
        <div id="audit"></div>
      </div>
    </div>
  </div>

  <script>
    async function fetchJSON(url) {
      const response = await fetch(url);
      return response.json();
    }

    function renderStats(stats) {
      const statsEl = document.getElementById("stats");
      statsEl.innerHTML = `
        <div class="card"><div class="label">Total Events</div><div class="value">${stats.total_events || 0}</div></div>
        <div class="card"><div class="label">Approved</div><div class="value">${stats.approved_actions || 0}</div></div>
        <div class="card"><div class="label">Rejected</div><div class="value">${stats.rejected_actions || 0}</div></div>
        <div class="card"><div class="label">Pending</div><div class="value">${stats.pending_reviews || 0}</div></div>
      `;
    }

    function renderQueue(queue) {
      const queueEl = document.getElementById("queue");
      if (!queue.length) {
        queueEl.innerHTML = "<p>No pending review requests.</p>";
        return;
      }

      queueEl.innerHTML = queue.map(item => {
        const riskClass =
          item.risk_score >= 70 ? "high" :
          item.risk_score >= 40 ? "medium" : "low";

        return `
          <div class="queue-item">
            <strong>${item.proposed_action.action_type || "Unknown action"}</strong><br>
            ${item.proposed_action.description || "No description"}<br>
            <span class="risk ${riskClass}">Risk: ${item.risk_score || 0}</span>
          </div>
        `;
      }).join("");
    }

    function renderAudit(events) {
      const auditEl = document.getElementById("audit");
      if (!events.length) {
        auditEl.innerHTML = "<p>No audit entries.</p>";
        return;
      }

      auditEl.innerHTML = events.map(event => `
        <div class="audit">
          <strong>${event.event}</strong> — ${new Date(event.timestamp).toLocaleString()}
        </div>
      `).join("");
    }

    async function refreshData() {
      try {
        const stats = await fetchJSON("/api/stats");
        renderStats(stats);

        const queue = await fetchJSON("/api/review-queue");
        renderQueue(queue);

        const audit = await fetchJSON("/api/audit-log?limit=20");
        renderAudit(audit);
      } catch (e) {
        console.error("Error refreshing data:", e);
      }
    }

    refreshData();
    setInterval(refreshData, 5000);
  </script>
</body>
</html>
"""


def run_dashboard():
    if not HAS_FLASK:
        print("Error: Flask not installed. Run: pip install Flask")
        sys.exit(1)

    app = Flask(__name__)

    AUDIT_LOG_PATH = Path("medusa_audit.jsonl")
    REVIEW_QUEUE_PATH = Path("review_queue.json")

    def load_audit_events(limit=50):
        if not AUDIT_LOG_PATH.exists():
            return []

        events = []
        with AUDIT_LOG_PATH.open("r", encoding="utf-8") as f:
            for line in f.readlines()[-limit:]:
                try:
                    events.append(json.loads(line))
                except Exception:
                    continue
        return events

    def load_review_queue():
        if not REVIEW_QUEUE_PATH.exists():
            return []

        try:
            with REVIEW_QUEUE_PATH.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def calculate_stats():
        events = load_audit_events(limit=1000)

        approved = sum(1 for e in events if e.get("event") == "approved_action_executed")
        rejected = sum(
            1 for e in events
            if e.get("event") == "review_completed" and e.get("request", {}).get("status") == "REJECT"
        )
        pending = sum(
            1 for e in events
            if e.get("event") == "review_requested"
            and not any(
                ee.get("event") == "review_completed"
                and ee.get("request", {}).get("request_id") == e.get("request", {}).get("request_id")
                for ee in events
            )
        )

        risk_scores = [
            e.get("request", {}).get("risk_score", 0)
            for e in events if "request" in e
        ]
        avg_risk = round(sum(risk_scores) / len(risk_scores), 2) if risk_scores else 0

        return {
            "total_events": len(events),
            "approved_actions": approved,
            "rejected_actions": rejected,
            "pending_reviews": pending,
            "average_risk_score": avg_risk,
        }

    @app.route("/")
    def dashboard():
        return render_template_string(DASHBOARD_HTML)

    @app.route("/api/stats")
    def api_stats():
        return jsonify(calculate_stats())

    @app.route("/api/audit-log")
    def api_audit_log():
        limit = request.args.get("limit", 20, type=int)
        return jsonify(load_audit_events(limit=limit))

    @app.route("/api/review-queue")
    def api_review_queue():
        return jsonify(load_review_queue())

    print("\nStarting MEDUSA Dashboard on http://127.0.0.1:5000")
    app.run(debug=False, host="127.0.0.1", port=5000)


# ============================================================================
# MAIN
# ============================================================================


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MEDUSA Integrated Framework")
    parser.add_argument(
        "--mode",
        choices=["app", "console", "dashboard"],
        default="app",
        help="Run mode (default: app)",
    )

    args = parser.parse_args()

    if args.mode == "app":
        run_ai_loop()
    elif args.mode == "console":
        run_console()
    elif args.mode == "dashboard":
        run_dashboard()
