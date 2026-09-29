import requests
import json
from typing import List, Dict, Any


class LocalAIEngine:
    def __init__(self, model_name: str = "qwen2.5:7b", base_url: str = "http://localhost:11434"):
        self.model_name = model_name
        self.base_url = f"{base_url}/api/chat"

    def generate(self, messages: List[Dict[str, str]], options: Dict[str, Any] = None) -> str:
        """Sends chat history straight to the local hardware layer."""
        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "options": options or {"temperature": 0.7}
        }
        
        try:
            response = requests.post(self.base_url, json=payload, timeout=60)
            response.raise_for_status()
            return response.json().get("message", {}).get("content", "")
        except requests.exceptions.ConnectionError:
            return "Error: Local AI engine not found. Ensure Ollama or your local server is running."
        except Exception as e:
            return f"Inference Error: {str(e)}"
