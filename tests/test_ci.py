import importlib
import json
import pathlib
import sys
import types


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _install_stub_modules(monkeypatch):
    dotenv_mod = types.ModuleType("dotenv")
    dotenv_mod.load_dotenv = lambda: None
    monkeypatch.setitem(sys.modules, "dotenv", dotenv_mod)

    requests_mod = types.ModuleType("requests")

    class RequestException(Exception):
        pass

    requests_mod.exceptions = types.SimpleNamespace(RequestException=RequestException)
    requests_mod.get = lambda *args, **kwargs: None
    requests_mod.post = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "requests", requests_mod)

    chromadb_mod = types.ModuleType("chromadb")

    class DummyCollection:
        def __init__(self):
            self.items = []

        def upsert(self, **kwargs):
            self.items.append(kwargs)

        def query(self, **kwargs):
            return {"ids": [[]], "metadatas": [[]]}

        def get(self, **kwargs):
            return {"ids": []}

        def count(self):
            return 0

    class DummyClient:
        def __init__(self, path):
            self.path = path
            self.collection = DummyCollection()

        def get_or_create_collection(self, name):
            return self.collection

        def delete_collection(self, name):
            return None

    chromadb_mod.PersistentClient = DummyClient
    monkeypatch.setitem(sys.modules, "chromadb", chromadb_mod)

    tiktoken_mod = types.ModuleType("tiktoken")

    class DummyEncoding:
        def encode(self, text):
            return list(text.encode("utf-8"))

    tiktoken_mod.get_encoding = lambda name: DummyEncoding()
    monkeypatch.setitem(sys.modules, "tiktoken", tiktoken_mod)

    torch_mod = types.ModuleType("torch")
    torch_mod.cuda = types.SimpleNamespace(is_available=lambda: False)
    monkeypatch.setitem(sys.modules, "torch", torch_mod)

    numpy_mod = types.ModuleType("numpy")
    numpy_mod.transpose = lambda arr, axes: arr
    monkeypatch.setitem(sys.modules, "numpy", numpy_mod)


def test_telegram_get_updates_advances_offset_for_non_text_updates(monkeypatch):
    _install_stub_modules(monkeypatch)
    telegram_bot = importlib.import_module("core.telegram_bot")

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "result": [
                    {"update_id": 10, "message": {"chat": {"id": 1}, "photo": [{}]}},
                    {"update_id": 11, "message": {"chat": {"id": 2}, "text": "hi", "from": {"first_name": "A"}}},
                ]
            }

    monkeypatch.setattr(telegram_bot.requests, "get", lambda *args, **kwargs: DummyResponse())
    monkeypatch.setattr(telegram_bot.time, "sleep", lambda *_args, **_kwargs: None)

    bot = telegram_bot.TelegramBot("token")
    updates = list(bot.get_updates())

    assert updates == [(2, "hi", "A")]
    assert bot.offset == 12


def test_validate_startup_config_requires_expected_settings(monkeypatch, tmp_path):
    _install_stub_modules(monkeypatch)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "memory_config.json").write_text(json.dumps({"retrieval": {}}), encoding="utf-8")
    (tmp_path / "config" / "prompts.json").write_text(json.dumps({"introspection_prompt": "think"}), encoding="utf-8")

    app_runtime = importlib.import_module("app_runtime")
    config = app_runtime.validate_startup_config(
        {
            "TELEGRAM_BOT_TOKEN": "123:abc",
            "OLLAMA_HOST": "http://localhost:11434/",
            "OLLAMA_MODEL": "gemma3:12b",
        }
    )

    assert config["ollama_host"] == "http://localhost:11434"
    assert config["ollama_model"] == "gemma3:12b"

    try:
        app_runtime.validate_startup_config({"OLLAMA_HOST": "bad-url", "OLLAMA_MODEL": ""})
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("validate_startup_config should fail for invalid config")

    assert "TELEGRAM_BOT_TOKEN" in message
    assert "OLLAMA_HOST must be a valid http(s) URL" in message


def test_run_startup_healthchecks_calls_all_dependencies(monkeypatch):
    _install_stub_modules(monkeypatch)
    app_runtime = importlib.import_module("app_runtime")

    class DummyTelegram:
        def healthcheck(self):
            return {"status": "ok"}

    class DummyOllama:
        def healthcheck(self):
            return {"models": [{"name": "gemma3:12b"}]}

    class DummyVectorManager:
        def __init__(self, collection_name):
            self.collection_name = collection_name

        def healthcheck(self):
            return {"status": "ok", "collection": self.collection_name}

    class DummyWeather:
        def healthcheck(self):
            return {"status": "skipped"}

    monkeypatch.setattr(app_runtime, "VectorManager", DummyVectorManager)
    monkeypatch.setattr(app_runtime, "WeatherInjector", DummyWeather)

    checks = app_runtime.run_startup_healthchecks({"telegram": DummyTelegram(), "ollama": DummyOllama()})

    assert checks["telegram"]["status"] == "ok"
    assert checks["vector_db"]["collection"] == "startup_healthcheck"
    assert checks["weather"]["status"] == "skipped"


def test_autopilot_scheduling_respects_cooldowns(monkeypatch):
    policy = importlib.import_module("autopilot.policy")
    timeutils = importlib.import_module("core.timeutils")

    monkeypatch.setattr(timeutils, "now_ms", lambda: 1_000_000)
    monkeypatch.setattr(timeutils, "local_dt", lambda: types.SimpleNamespace(hour=12))
    monkeypatch.setattr(timeutils, "pseudo_random_range", lambda min_v, max_v: min_v)
    monkeypatch.setattr(timeutils, "jitter_ms", lambda min_v, max_v: min_v)

    state = {
        "paused": False,
        "next_eligible_send_ms": 0,
        "since_user_autonomous_count": 0,
        "since_user_autonomous_cap": 2,
        "scheduled_send_ms": 0,
        "last_outbound_ms": 950_000,
        "pending_inbound_count": 0,
        "last_autonomous_kind": "",
        "last_autonomous_ms": 0,
    }
    config = {
        "quiet_start_hour": 23,
        "quiet_end_hour": 7,
        "addon_max_pending_inbound": 2,
        "addon_min_seconds": 30,
        "addon_max_seconds": 600,
        "addon_cooldown_minutes": 2,
        "jitter_min_ms": 10_000,
        "jitter_max_ms": 20_000,
        "cap_min": 0,
        "cap_max": 2,
        "reengage_min_hours": 4,
        "reengage_max_hours": 24,
        "addon_post_send_cooldown_minutes": 2,
        "starter_post_send_cooldown_minutes": 180,
    }

    assert policy.should_schedule_addon(state, config) is True
    policy.schedule_addon(state, config)
    assert state["scheduled_kind"] == "addon"
    assert state["scheduled_send_ms"] > 1_000_000

    policy.apply_post_send_updates(state, "addon", config)
    assert state["since_user_autonomous_count"] == 1
    assert state["next_eligible_send_ms"] > 1_000_000


def test_memory_compactor_plans_and_runs_l0_jobs(tmp_path):
    helpers = importlib.import_module("memory_core.helpers")
    compactor_mod = importlib.import_module("memory_core.compactor")
    paths_mod = importlib.import_module("memory_core.paths")
    state_mod = importlib.import_module("memory_core.state_store")

    paths = paths_mod.MemoryPaths(root=str(tmp_path), chat_id=123)
    paths.ensure()
    helpers.write_json(paths.l0_active_path(), [{"role": "user", "content": f"m{i}"} for i in range(5)])
    store = state_mod.StateStore(paths.state_path())
    store.ensure_exists()

    class DummySummarizer:
        def l0_to_l1(self, chunk_text):
            return {"diary": "summary", "bullets": ["fact 1", "fact 2"], "core_principles": ["be kind"]}

        def update_master(self, master_data, diary, core_principles):
            return {"bio": diary, "core_principles": core_principles}

    class DummyVectorManager:
        def __init__(self):
            self.calls = []

        def add_to_index(self, bullets, file_id):
            self.calls.append((tuple(bullets), file_id))

    vm = DummyVectorManager()
    compactor = compactor_mod.MemoryCompactor(
        paths=paths,
        state_store=store,
        summarizer=DummySummarizer(),
        vector_manager=vm,
        l0_summary_msgs=2,
        max_level_files=3,
        l0_max_msgs=4,
    )

    state = compactor.plan(store.load(), 5)
    assert state["jobs"][0]["type"] == "COMPACT_L0_TO_L1"
    store.save(state)

    assert compactor.compact_once() is True
    assert len(list((tmp_path / "user" / "chats" / "123" / "l1").glob("l1_*.json"))) == 1
    assert vm.calls


def test_prompt_builder_uses_prompt_templates(monkeypatch, tmp_path):
    _install_stub_modules(monkeypatch)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "prompts.json").write_text(
        json.dumps(
            {
                "l1_diary_system": "sys template",
                "l1_diary_user": "User says {text}",
                "introspection_prompt": "think",
            }
        ),
        encoding="utf-8",
    )

    prompt_builder_mod = importlib.import_module("memory_core.prompt_builder")

    class DummyPaths:
        system_dir = str(tmp_path)
        user_context_dir = str(tmp_path)
        l1_dir = str(tmp_path)

        def personal_context_path(self):
            return str(tmp_path / "missing.txt")

        def master_path(self):
            return str(tmp_path / "missing_master.json")

    class DummyVM:
        def search_and_vote(self, *args, **kwargs):
            return []

    builder = prompt_builder_mod.PromptBuilder(DummyPaths(), DummyVM(), {"retrieval": {}})

    assert builder.get("l1_diary_system") == "sys template"
    assert builder.format("l1_diary_user", text="hello") == "User says hello"
