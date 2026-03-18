[![CI](https://github.com/C47HERINE/Ollama-Chat-Agent/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/C47HERINE/Ollama-Chat-Agent/actions/workflows/ci.yml)
# 🤖 Autonomous Chat Agent (Telegram + Ollama)

An experimental systems-level autonomous chat agent written in Python, designed to behave like a real person texting over time.

This is not a prompt wrapper.  
It is a long-running, stateful agent combining local LLM inference, persistent memory, autonomous scheduling, contextual awareness, and multi-modal output (text + voice).

The focus is on architecture, invariants, and durability, not novelty prompts.

---

## Overview

The agent:

- Replies to Telegram messages using a local Ollama LLM
- Maintains persistent, file-backed memory per chat
- Compresses conversation history into bounded hierarchical memory
- Injects strictly capped context for every inference
- Sends autonomous messages based on silence and timing rules
- Produces text or voice output depending on length or command
- Integrates external environment data via REST APIs
- Runs continuously with no cloud dependencies

This project is designed as a portfolio-grade systems demo, emphasizing stateful agents, context orchestration, deterministic bounds, and long-running stability.

---

## Key Features

### 🧠 Persistent Conversational Memory

- Per-chat raw conversation logs (JSON, append-only)
- Messages are strictly separated by role:
  - User
  - Assistant
  - Internal/system events
- Memory persists across restarts
- Raw logs are never deleted or rewritten
- Conversation memory is excluded from Git

Raw logs are the source of truth for all higher-level memory.

---

### 🧩 Hierarchical Memory Compaction

To prevent unbounded context growth while preserving semantic continuity, the agent uses LLM-driven hierarchical summarization.

Memory levels:

- Level 0 (Raw)  
  Unlimited raw messages on disk

- Level 1 (L1)  
  - Every 60 messages  
  - Last 30 summarized  
  - Strict length cap

- Level 2 (L2)  
  - Triggered at 3 L1 files  
  - Last 2 L1 files summarized

- Level 3 (L3)  
  - Triggered at 3 L2 files  
  - Last 2 L2 files summarized

- Master Memory  
  - Triggered at 3 L3 files  
  - Existing master + last 2 L3 files summarized together  
  - Produces a new master file (compression, not appending)

All summaries are immutable once written.  
No memory file is ever deleted or overwritten.

Compaction is executed as a serialized background process.  
Only one compaction task runs at a time; additional tasks are queued and prioritized via a persistent state file to prevent concurrent writes and runaway processing.

---

### 🧠 Context Injection (Strictly Bounded)

At inference time, the agent injects at most:

- ≤ 60 recent raw messages  
- ≤ 3 L1 summaries  
- ≤ 3 L2 summaries  
- ≤ 3 L3 summaries  
- ≤ 1 master memory  

Each tier has its own length cap.

Context is rebuilt only when memory changes (for example, during compaction), minimizing disk I/O, recomputation, and unnecessary inference overhead.

---

### 🌦️ Environment Awareness

The agent can incorporate background world state (such as weather) by consuming third-party REST APIs.

- External data is fetched via HTTP and parsed from JSON
- Errors are handled explicitly to avoid contaminating conversation flow
- Environment data is injected as system-only context and never surfaced directly unless relevant

This allows the agent to remain context-aware without polluting user-visible messages.

---

### 🤖 Autonomous Behavior (AutoPilot)

- Add-on messages  
  - Short-range follow-ups after a reply if the conversation stalls  
  - Controlled by probability, delay, and per-chat caps

- Conversation starters  
  - Triggered after multiple hours of silence  
  - Always outside quiet hours  
  - Subject to strict cooldowns

AutoPilot is pausable per chat and never fires recursively.  
All autonomous actions are logged internally for traceability.

---

### 🎙️ Voice Output (Local TTS)

- Text is the default output
- Voice output is triggered by:
  - Message length thresholds
  - Explicit /voice command
- Uses Chatterbox TTS (fully local)
- Supports custom voices from ~10s audio samples
- Sentence-aware chunking allows very long voice memos
- Voice generation never alters stored text memory

---

### 🧱 Modular Architecture

Clear separation of responsibilities:

- core/ — Telegram I/O, Ollama calls, TTS routing, environment data retrieval  
- memory_core/ — Logs, memory compaction, summarization, context building, state tracking  
- autopilot/ — Scheduling, policies, cooldowns, autonomous behavior  
- config/ — Declarative configuration and prompt templates  

The system is designed so that operational concerns (memory safety, serialization, error handling) are enforced by structure rather than convention.

---

## Model & Runtime

- LLM: gemma3:12b
- Persona: baked into the model via `ollama create -f Modelfile`  
  External system prompt injection is temporarily disabled due to Ollama behavior
- Context length: < 32k (bounded by design)
- Hardware tested: RTX 5070 Ti
- Observed behavior: fast inference, stable memory, no lag

---

## Environment Variables

Create a `.env` file:

TELEGRAM_BOT_TOKEN=your_telegram_bot_token  
OLLAMA_HOST=http://localhost:11434  
OLLAMA_MODEL=gemma3:12b  

VOICE_PROMPT_WAV=path/to/voice.wav  
VOICE_EXAGGERATION=0.5  
VOICE_CFG_WEIGHT=0.5  
TEMPERATURE=0.8  

An example is provided as `.env.example`.

---

## Getting Started

Requirements:
- Python 3.10+
- Telegram Bot Token
- Local Ollama installation
- Pulled Ollama model (`ollama run gemma3:12b`)

Option A — Windows scripts:

1) install.bat  
2) run.bat  

Option B — Manual install:

1) Activate virtual environment  
   .venv\Scripts\activate

2) Upgrade pip  
   python -m pip install --upgrade pip

3) Install base dependencies  
   python -m pip install -r requirements.txt

4) Install environment variable support  
   python -m pip install python-dotenv

5) Install Chatterbox TTS  
   python -m pip install chatterbox-tts

6) Remove any existing PyTorch installs  
   python -m pip uninstall -y torch torchvision torchaudio

7) Install PyTorch with CUDA 12.8 support  
   python -m pip install ^  
     torch==2.7.1+cu128 ^  
     torchvision==0.22.1+cu128 ^  
     torchaudio==2.7.1+cu128 ^  
     --index-url https://download.pytorch.org/whl/cu128

Run:
python main.py

---

## Telegram Commands

- /start — Basic greeting  
- /pause — Disable autonomous messages  
- /resume — Re-enable autonomous messages  
- /status — Show internal agent status  

---

## Design Philosophy

- Stateful agents over stateless chat
- Deterministic bounds over clever retrieval
- Compression over deletion
- Clear invariants over heuristics
- Local-first execution

This is intentionally not a thin wrapper around an LLM.

---

## Planned / Exploratory Extensions

- Vision support (Telegram image input)
- User voice messages + local STT
- Typing / recording indicators
- Tool usage (model-native or scripted)
- Fully self-hosted model (no Ollama dependency)

---

## License

MIT — free to explore, learn, and adapt.
