from typing import List, Dict


class LocalMemory:
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
        # Clears memory context instantly from RAM
        self.history = [{"role": "system", "content": self.history[0]["content"]}]
