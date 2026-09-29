import sys
from core.engine import LocalAIEngine
from core.memory import LocalMemory


def run_local_development_loop():
    print("====================================================")
    print("🔒 Initializing Data-Center-Free AI Framework...")
    print("====================================================\n")

    memory = LocalMemory(system_prompt="You are a private AI operating entirely on local consumer hardware.")
    ai_engine = LocalAIEngine(model_name="qwen2.5:7b")

    print(f"Ready. Running model: [{ai_engine.model_name}]")
    print("Type 'exit' or 'quit' to stop the framework.\n")

    while True:
        try:
            user_input = input("🧑 Dev / User: ")
            if user_input.strip().lower() in ['exit', 'quit']:
                print("Shutting down local framework securely. Goodbye!")
                break

            if not user_input.strip():
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


if __name__ == "__main__":
    run_local_development_loop()
