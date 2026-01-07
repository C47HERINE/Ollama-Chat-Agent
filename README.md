🤖 Autonomous Chat Agent (Telegram + Ollama)

An experimental autonomous conversational agent built in Python, designed to behave like a real person texting over time.

This project is a **systems-level AI agent**, not a prompt toy: it combines local LLM inference, persistent memory, autonomous scheduling, contextual awareness, and multi-modal output (text + voice).

--------------------------------------------------

OVERVIEW

The agent:
- Replies to Telegram messages using a **local Ollama LLM**
- Maintains **persistent, per-chat memory** across restarts
- Builds and injects **prioritized context** automatically
- Generates **autonomous messages** based on time, silence, and rules
- Produces **text or voice messages** depending on content and length
- Runs continuously with low resource usage

The project is intentionally designed as a **portfolio-grade architecture demo**, emphasizing:
- State management
- Context orchestration
- Agent autonomy
- Robust long-running behavior

--------------------------------------------------

KEY FEATURES

🧠 Conversational Memory Engine
- Per-chat daily raw conversation logs (JSON)
- Memory persists across restarts
- Clear separation of:
  - User messages
  - Assistant replies
  - System-only internal events
- Memory drives context, summaries, and autonomy

🧩 Context Builder (Priority-Based)
Context is rebuilt dynamically and injected into the LLM with strict priority:
1. System prompts (personality, rules)
2. Static user context
3. Raw conversation (today + yesterday)
4. Latest carried summaries (daily / weekly / monthly / yearly)

- Context rebuilds only when inputs change
- Signature-based change detection (cheap + efficient)
- Automatic size control (LLM-safe)

🧠 Introspection & Summarization (Internal Only)
- Introspection runs periodically to analyze conversation state
- Reveries and internal thoughts are **never sent to the user**
- Scheduled summaries:
  - Daily
  - Weekly
  - Monthly
  - Yearly
- Summaries are stored separately and selectively reinjected as context

🤖 Autonomous Behavior (AutoPilot)
- Sends natural follow-up messages after replies
- Re-engages conversations after long silence (4–24h)
- Respects quiet hours
- Uses soft randomness for human-like timing
- Cooldown rules prevent spammy behavior
- Fully pausable per chat

🌦️ Background World Injection
- Periodic environment updates (e.g. weather)
- Injected as **system context only**
- Logged internally without polluting conversation flow
- Never directly surfaced unless relevant

🎙️ Voice Routing (Text-to-Speech)
- Automatic voice memo generation for long messages
- `/voice` command forces voice output
- Clean separation between:
  - Raw text (for Telegram)
  - Cleaned text (for TTS)
- Sentence-aware batching for natural speech
- Local TTS inference (no external APIs)

🧱 Modular Architecture
Clear separation of concerns:
- Telegram I/O
- LLM interaction (Ollama)
- Memory engine
- Context builder
- AutoPilot logic
- Voice router
- Background services (weather, scheduling)

Designed for extension without refactors.

--------------------------------------------------

ENVIRONMENT VARIABLES

Create a `.env` file:


TELEGRAM_BOT_TOKEN=your_telegram_bot_token
OLLAMA_HOST=[http://localhost:11434](http://localhost:11434)
OLLAMA_MODEL=gemma3:12b

# Optional (voice)

VOICE_PROMPT_WAV=path/to/voice.wav
VOICE_EXAGGERATION=0.5
VOICE_CFG_WEIGHT=0.5
TEMPERATURE=0.8


An example file is provided as `.env.example`.

--------------------------------------------------

GETTING STARTED

Requirements
- Python 3.10+
- Telegram Bot Token
- Local Ollama installation
- A supported Ollama model pulled (e.g. gemma3:12b)

Install dependencies

pip install -r requirements.txt

Run the agent

python main.py


or on Windows:
run install.bat

launch using:
start.bat


--------------------------------------------------

TELEGRAM COMMANDS

/start    Basic greeting  
/pause    Disable autonomous messages  
/resume   Re-enable autonomous messages  
/status   Show internal agent status  

--------------------------------------------------

SYSTEM PROMPTS & STATIC CONTEXT

The agent automatically loads files from:
- `user/system_prompt/`
- `user/context/`

Supported formats:
- `.json`
- `.md`
- `.txt`

Changes are detected automatically:
- No restart required
- Memory is preserved
- Context rebuilds only when necessary

--------------------------------------------------

DESIGN PHILOSOPHY

This project prioritizes:
- Stateful agents over stateless chat
- Deterministic rules combined with randomness
- Clear internal boundaries
- Long-running stability
- Observability via structured logs
- Extensibility over clever hacks

It is intentionally **not** a thin wrapper around an LLM.

--------------------------------------------------

PLANNED / POSSIBLE EXTENSIONS

- Additional world injectors (events, news, calendars)
- Emotion / tone tracking
- Multi-agent coordination
- Multi-platform support (Messenger, SMS, Web)
- External tool calling
- Memory compression strategies
- UI dashboard for state inspection

--------------------------------------------------

NOTES

- Uses **local models only**
- No cloud dependencies
- Conversation logs and memory files are excluded from Git
- Secrets handled exclusively via environment variables
- Designed to run continuously with minimal CPU usage

--------------------------------------------------

LICENSE

MIT — free to explore, learn, and adapt.