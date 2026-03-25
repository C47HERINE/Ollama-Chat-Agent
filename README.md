![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Ollama](https://img.shields.io/badge/Ollama-local%20LLM-black)
![ChromaDB](https://img.shields.io/badge/ChromaDB-vector%20memory-ff69b4)
![Memory](https://img.shields.io/badge/memory-compaction%20%2B%20embedding-critical)
![Status](https://img.shields.io/badge/status-active%20development-orange)
![License](https://img.shields.io/badge/license-MIT-green)

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

## Memory System

The memory pipeline is append-only for raw chat and immutable for summaries. 

### L0: active + archive raw chat

- Active messages are appended to `l0_active.json`.
- When compaction triggers, the oldest chunk is moved to archive storage (`l0_archive.json`), never deleted.
- Roles (`user`, `assistant`, `system`) are preserved with message content and kind metadata.

### L1: semantic diary + bullets + principles

- A chunk of L0 messages is summarized into one L1 JSON file.
- L1 includes:
  - `diary` (narrative summary),
  - `bullets` (indexable memory points),
  - `core_principles` (stable behavior constraints inferred from interaction context).
- Each L1 file is immutable once written.

### Master profile updates

- Every new L1 can trigger a master-profile update.
- The updater merges:
  - existing master memory,
  - new L1 diary information,
  - `core_principles` from that L1 entry.
- This keeps long-term identity/persona constraints alive as raw history grows.

### Retrieval + prompt construction

For each generation, prompt construction includes:

- System prompt files,
- user profile/context files,
- master profile,
- recent L1 summaries,
- retrieved archived L1 summaries (vector search),
- weather/context injector output (low-priority block),
- current conversation window.

#### How vector retrieval works

Retrieval is vector-based and runs locally through Ollama + ChromaDB:

1) During L0 → L1 compaction, each L1 `bullet` is embedded with Ollama's `embeddingGemma` model and stored in ChromaDB.  
2) At inference time, the retrieval query is built from recent conversation turns plus the current user input, then embedded with the same model.  
3) ChromaDB returns the nearest bullet vectors.  
4) Results are grouped by `source_file` (the L1 summary id), and a majority-vote step selects top L1 files.  
5) Those top L1 summaries are injected into the prompt as archived memory context.

---

### Bounded context

Context is capped using token-aware budgeting:

- hard context limit from config,
- safety buffer reserved,
- optional blocks are trimmed proportionally when needed,
- must-have blocks (system/persona/current conversation) stay prioritized.

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

## Install & Run

### Prerequisites

- Python 3.10+
- A Telegram bot token from BotFather
- Local Ollama running (default: `http://localhost:11434`)
- Pulled model available locally (for example: `ollama pull gemma3:12b`)

### 1) Clone and enter the project

```bash
git clone https://github.com/C47HERINE/Ollama-Chat-Agent.git
cd Ollama-Chat-Agent
```

### 2) Create and activate a virtual environment

Windows (PowerShell):

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

Windows (cmd):

```bat
python -m venv .venv
.venv\Scripts\activate
```

Linux/macOS:

```bash
python -m venv .venv
source .venv/bin/activate
```

### 3) Install dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install chatterbox-tts --no-deps
```

### 4) Configure environment variables

Copy `.env.example` to `.env` and set values:

```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=gemma3:12b

VOICE_PROMPT_WAV=path/to/voice.wav
VOICE_EXAGGERATION=0.5
VOICE_CFG_WEIGHT=0.5
TEMPERATURE=0.8
```

### 5) Start the agent

```bash
python main.py
```

### Windows quick path

If you prefer scripts:

1) `install.bat`  
2) `run.bat`

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
