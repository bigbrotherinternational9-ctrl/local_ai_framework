# 🔒 Local AI Framework

A privacy-focused, zero-data-center AI framework for local LLM inference using Ollama.

## 🧱 Architectural Blueprint

```
local_ai_framework/
│
├── core/
│ ├── __init__.py
│ ├── engine.py # Manages local LLM inference lifecycle
│ └── memory.py # Handles zero-data-center local context tracking
│
├── tools/
│ ├── __init__.py
│ └── local_sys.py # Local execution tools (file I/O, sensors, etc.)
│
├── main.py # App entry point and developer loop
└── requirements.txt # Local dependencies
```

## 📋 Dependencies

This framework uses standard HTTP requests to communicate with your locally hosted server, meaning it has an incredibly light footprint.

- `requests==2.32.3` - HTTP client for communicating with local Ollama server
- `pydantic==2.8.2` - Data validation

## ⚙️ Core Components

### 1. The Local Engine (`core/engine.py`)

This component abstracts the local inference engine. It targets a locally hosted model instance (e.g., Llama3, Mistral, or Qwen2.5) via [Ollama's Local API Endpoint](https://github.com/ollama/ollama/blob/main/docs/api.md).

**Features:**
- Direct chat history streaming to local hardware
- Temperature and inference parameter control
- Graceful error handling for connection failures

### 2. Local Context & Memory (`core/memory.py`)

Instead of shipping state to a cloud database, history stays in volatile local memory or an encrypted file layer.

**Features:**
- Session-based conversation history
- System prompt configuration
- Memory clearing for privacy
- Full context retrieval for inference

### 3. Local Execution & Sensors (`tools/local_sys.py`)

Mobile sensor integration with explicit permission handling. Supports:
- Android magnetometer access via Plyer
- Desktop simulation mode
- Runtime permission requests
- Local telemetry logging

### 4. Main Development Loop (`main.py`)

Interactive terminal chat interface that never accesses the open internet.

## 🚀 Setup and Local Execution Guide

### Prerequisites

1. **Install a Local Runtime Engine**: Download and set up [Ollama](https://ollama.ai)

2. **Pull a Model Object Locally**: Open your machine's system terminal and fetch a compact model optimized for personal hardware:

```bash
ollama pull qwen2.5:7b
```

3. **Verify Local Service Availability**: Check that the runtime engine is running locally on port 11434:

```bash
curl http://localhost:11434/api/tags
```

### Running the Framework

1. **Install dependencies**:

```bash
pip install -r requirements.txt
```

2. **Launch the framework**:

```bash
python main.py
```

3. **Start chatting**: Type your queries and interact with the local AI model in real-time.

## 📱 Mobile Integration

For Android devices with Buildozer compilation:

```python
from tools.local_sys import MobileEMFScanner

scanner = MobileEMFScanner()
scanner.check_and_request_permissions()
scanner.record_ambient_emf(duration_seconds=5)
```

## 🔐 Privacy & Security

- ✅ **Zero Cloud**: All inference runs locally on your hardware
- ✅ **No Data Shipping**: Conversation history never leaves your device
- ✅ **Local Storage**: All logs and telemetry stored in sandboxed local directories
- ✅ **Permission-Based**: Explicit user authorization for sensor access

## 🎯 Use Cases

- 🧑‍💻 Local development assistance
- 📝 Private document analysis
- 🔬 Local data processing
- 📱 Mobile sensor integration
- 🛡️ Confidential AI research

## 📄 License

This project is open source and available for personal and commercial use.
