🤖 Autonomous Chat Agent (Telegram + Ollama)

An experimental autonomous conversational agent built in Python, designed to behave like a real person texting over time.

The agent:
- Replies to Telegram messages using a local Ollama LLM
- Maintains per-chat memory
- Injects system prompts and external context automatically
- Can initiate messages on its own based on timing, rules, and randomness
- Is built with modular, extensible architecture for future features

This project is intentionally designed as a portfolio piece, emphasizing system design, state management, and AI-agent logic rather than just prompt engineering.

--------------------------------------------------

KEY FEATURES

Conversational Memory
- Per-chat conversation history stored locally
- Memory persists across restarts
- Resettable per chat

Autonomous Behavior (AutoPilot)
- Sends natural “add-on” messages shortly after replies
- Re-engages conversations after long silence (4–24h)
- Respects quiet hours
- Uses soft randomness (human-like unpredictability)
- Per-message randomized caps to avoid spammy behavior

Modular Agent Design
Separated concerns:
- Telegram I/O
- LLM interaction (Ollama)
- Agent policy & timing
- Persistent state
- Prompts & context

This makes the project easy to extend with new capabilities.

--------------------------------------------------

PROJECT STRUCTURE

chat-agent/
├── main.py                     Application entry point
├── telegram_bot.py             Telegram API interface
├── ollama_chat.py              Ollama LLM wrapper + memory
├── autopilot/                  Autonomous agent logic
│   ├── autopilot.py
│   ├── policy.py
│   ├── config.py
│   ├── store.py
│   ├── timeutils.py
│   └── prompts.py
├── ollama_system_prompt/       System prompt files (auto-loaded)
├── ollama_context/             External context files (auto-loaded)
├── ollama_state/               Conversation memory
├── agent_state/                Agent timing / state
├── .env.example                Environment variable template
└── README.txt

--------------------------------------------------

ENVIRONMENT VARIABLES

Create a .env file:

TELEGRAM_BOT_TOKEN=your_telegram_bot_token
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=gemma3:12b

An example file is provided as .env.example.

--------------------------------------------------

GETTING STARTED

Requirements
- Python 3.10+
- Telegram Bot Token
- Local Ollama installation
- A supported Ollama model pulled (for example: gemma3:12b)

Install dependencies
pip install -r requirements.txt

Run the agent
python main.py
or
start.bat

--------------------------------------------------

TELEGRAM COMMANDS

/start   Basic greeting
/pause   Disable autonomous messages
/resume  Re-enable autonomous messages
/reset   Clear conversation + agent state
/status  Show internal agent status

--------------------------------------------------

SYSTEM PROMPTS AND CONTEXT

The agent automatically injects all .txt and .md files found in:
- ollama_system_prompt/
- ollama_context/

These files are reloaded every message, allowing you to:
- Update personality
- Add memories
- Inject external knowledge

No restart required. Conversation memory is preserved.

--------------------------------------------------

DESIGN PHILOSOPHY

This project prioritizes:
- Stateful agents
- Human-like behavior
- Predictable rules combined with randomness
- Clear separation of concerns
- Extensibility over clever hacks

It is intentionally not a thin wrapper around an LLM.

--------------------------------------------------

PLANNED / POSSIBLE EXTENSIONS

- Web scraping (weather, events, daily summaries)
- Long-term memory summarization
- Voice memos (text-to-speech)
- Multi-platform support (Telegram, Messenger, SMS)
- Scheduled background world updates
- Emotion and tone tracking
- Daily and weekly conversation summaries

--------------------------------------------------

NOTES

- This project uses local models only
- Conversation and state files are intentionally excluded from Git
- Secrets are handled via environment variables

--------------------------------------------------

LICENSE

MIT — free to explore, learn, and adapt.
