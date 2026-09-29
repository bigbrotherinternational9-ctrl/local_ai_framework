import sys
from core.medusa_safeguard import MEDUSASafeguardMonitor, ReviewRequest


class MEDUSAConsole:
    """
    Interactive console for MEDUSA safety review and action execution.
    """

    def __init__(self, audit_path: str = "medusa_console_audit.jsonl"):
        self.monitor = MEDUSASafeguardMonitor(
            reviewer=self._terminal_reviewer,
            audit_path=audit_path,
        )
        self.is_running = True

    def _terminal_reviewer(self, request: ReviewRequest) -> tuple[str, str, str]:
        """
        Terminal-based human review interface.
        """
        print("\n" + "=" * 70)
        print("🛡️  MEDUSA SAFETY REVIEW")
        print("=" * 70)
        print(f"\nRequest ID: {request.request_id}")
        print(f"Risk Score: {request.risk_score}/100")
        print(f"Reason: {request.reason}")
        print(f"\nProposed Action:")
        print(f"  Type: {request.proposed_action.get('action_type', 'unknown')}")
        print(f"  Description: {request.proposed_action.get('description', 'N/A')}")
        print(f"\nAction Metadata:")
        for key, value in request.proposed_action.items():
            if key not in ['action_type', 'description']:
                print(f"  {key}: {value}")

        print("\n" + "-" * 70)
        print("Options: [A]pprove, [R]eject, [C]ancel, [V]iew Details")
        print("-" * 70)

        while True:
            choice = input("\n🔐 Your decision: ").strip().upper()

            if choice == "A":
                note = input("Review note (optional): ").strip()
                return "APPROVE", "operator", note or "Approved by operator"

            elif choice == "R":
                note = input("Rejection reason: ").strip()
                return "REJECT", "operator", note or "Rejected by operator"

            elif choice == "C":
                note = input("Cancellation note: ").strip()
                return "CANCEL", "operator", note or "Cancelled by operator"

            elif choice == "V":
                self._print_action_details(request.proposed_action)

            else:
                print("❌ Invalid choice. Please enter A, R, C, or V.")

    @staticmethod
    def _print_action_details(action: dict) -> None:
        """Pretty print full action details."""
        print("\n" + "-" * 70)
        print("��� FULL ACTION DETAILS")
        print("-" * 70)
        for key, value in action.items():
            print(f"  {key:<25} : {value}")
        print("-" * 70)

    def _execute_action(self, action: dict) -> dict:
        """
        Execute the proposed action. This is a placeholder for actual execution.
        """
        action_type = action.get("action_type", "unknown")
        description = action.get("description", "No description")

        print(f"\n✅ Executing: {description}")
        return {
            "completed": True,
            "action_type": action_type,
            "timestamp": MEDUSASafeguardMonitor._timestamp(),
        }

    def _parse_action_input(self, user_input: str) -> dict:
        """
        Parse user input into an action dictionary.
        Format: action_type | description | affects_people | irreversible | external_side_effects | sensitive_data_access
        """
        parts = [p.strip() for p in user_input.split("|")]

        if len(parts) < 2:
            return None

        action_type = parts[0]
        description = parts[1]
        affects_people = parts[2].lower() == "true" if len(parts) > 2 else False
        irreversible = parts[3].lower() == "true" if len(parts) > 3 else False
        external_side_effects = parts[4].lower() == "true" if len(parts) > 4 else False
        sensitive_data_access = parts[5].lower() == "true" if len(parts) > 5 else False

        return {
            "action_type": action_type,
            "description": description,
            "affects_people": affects_people,
            "irreversible": irreversible,
            "external_side_effects": external_side_effects,
            "sensitive_data_access": sensitive_data_access,
        }

    def _print_help(self) -> None:
        """Print help text."""
        print("\n" + "=" * 70)
        print("📖 MEDUSA CONSOLE HELP")
        print("=" * 70)
        print("\nCommands:")
        print("  new       - Create a new action for review")
        print("  status    - Show system status")
        print("  audit     - View recent audit log entries")
        print("  help      - Show this help message")
        print("  exit      - Exit the console")
        print("\nAction Format (for 'new' command):")
        print("  action_type | description | affects_people | irreversible | external_side_effects | sensitive_data_access")
        print("\nExample:")
        print("  local_command | Read configuration file | false | false | false | false")
        print("  system_update | Apply security patch | true | true | false | false")
        print("=" * 70 + "\n")

    def _print_status(self) -> None:
        """Print system status."""
        print("\n" + "=" * 70)
        print("🔍 MEDUSA SYSTEM STATUS")
        print("=" * 70)
        print(f"Project: {self.monitor.params['project_name']}")
        print(f"Policy Version: {self.monitor.params['policy_version']}")
        print(f"Mode: {self.monitor.params['mode']}")
        print(f"Risk Threshold: {self.monitor.params['risk_threshold']}")
        print(f"Monitor Active: {self.monitor.is_active}")
        print(f"Audit Log: {self.monitor.audit_path}")
        print("=" * 70 + "\n")

    def _print_audit_log(self) -> None:
        """Display recent audit log entries."""
        if not self.monitor.audit_path.exists():
            print("\n📋 No audit log entries yet.\n")
            return

        print("\n" + "=" * 70)
        print("📊 RECENT AUDIT LOG")
        print("=" * 70)

        try:
            with self.monitor.audit_path.open("r", encoding="utf-8") as f:
                lines = f.readlines()
                recent = lines[-10:] if len(lines) > 10 else lines

                for idx, line in enumerate(recent, 1):
                    import json
                    event = json.loads(line)
                    print(f"\n[{idx}] Event: {event.get('event', 'unknown')}")
                    print(f"    Timestamp: {event.get('timestamp', 'N/A')}")
                    if "request" in event:
                        req = event["request"]
                        print(f"    Risk Score: {req.get('risk_score', 'N/A')}")
                        print(f"    Status: {req.get('status', 'N/A')}")
        except Exception as e:
            print(f"\n❌ Error reading audit log: {e}")

        print("\n" + "=" * 70 + "\n")

    def run(self) -> None:
        """Main console loop."""
        print("\n" + "=" * 70)
        print("🛡️  MEDUSA SAFETY CONSOLE v1.0")
        print("=" * 70)
        print("Type 'help' for available commands\n")

        while self.is_running:
            try:
                command = input("MEDUSA> ").strip()

                if not command:
                    continue

                if command.lower() == "exit":
                    print("\n👋 Shutting down MEDUSA console. Goodbye!")
                    self.is_running = False
                    break

                elif command.lower() == "help":
                    self._print_help()

                elif command.lower() == "status":
                    self._print_status()

                elif command.lower() == "audit":
                    self._print_audit_log()

                elif command.lower() == "new":
                    print("\n" + "-" * 70)
                    print("Create a new action for review")
                    print("-" * 70)
                    print("Format: action_type | description | affects_people | irreversible | external_side_effects | sensitive_data_access")
                    print("Example: local_command | Run diagnostic | false | false | false | false\n")

                    action_input = input("Action: ").strip()

                    if not action_input:
                        print("❌ No action provided.")
                        continue

                    action = self._parse_action_input(action_input)

                    if action is None:
                        print("❌ Invalid action format. Please use: action_type | description | ...")
                        continue

                    result = self.monitor.process_action(action, execute=self._execute_action)

                    print("\n" + "=" * 70)
                    print("📝 REVIEW RESULT")
                    print("=" * 70)
                    print(f"Status: {result.get('status', 'unknown')}")
                    print(f"Executed: {result.get('executed', False)}")
                    print(f"Risk Score: {result.get('risk_score', 'N/A')}/100")
                    if result.get("request_id"):
                        print(f"Request ID: {result.get('request_id')}")
                    if result.get("reason"):
                        print(f"Reason: {result.get('reason')}")
                    if result.get("result"):
                        print(f"Result: {result.get('result')}")
                    print("=" * 70 + "\n")

                else:
                    print(f"❌ Unknown command: '{command}'. Type 'help' for available commands.")

            except KeyboardInterrupt:
                print("\n\n👋 MEDUSA console interrupted. Goodbye!")
                self.is_running = False
                break

            except Exception as e:
                print(f"\n❌ Error: {e}")
                print("Type 'help' for available commands.\n")


if __name__ == "__main__":
    console = MEDUSAConsole()
    console.run()
