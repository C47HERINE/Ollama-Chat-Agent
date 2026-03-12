import json

from memory_core.paths import MemoryPaths
from memory_core.prompt_builder import PromptBuilder


class DummyVM:
    def __init__(self, ids):
        self.ids = ids

    def search_and_vote(self, query, top_n_files=3):
        return self.ids


class DummyWeather:
    def weather_updater(self):
        return ""


def _write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def test_prompt_builder_deduplicates_archived_and_recent(tmp_path):
    paths = MemoryPaths(str(tmp_path), 123)
    paths.ensure()

    _write_json(paths.master_path(), {})
    _write_json(
        paths.l0_active_path(),
        [{"role": "user", "content": "hello"}],
    )

    _write_json(
        paths.l1_dir + "/l1_1.json",
        {"id": "l1_1", "timestamp": "1", "diary": "first", "core_principles": []},
    )
    _write_json(
        paths.l1_dir + "/l1_2.json",
        {"id": "l1_2", "timestamp": "2", "diary": "second", "core_principles": []},
    )

    config = {
        "retrieval": {
            "max_context_tokens": 4000,
            "safety_buffer_tokens": 100,
            "recent_l1_count": 2,
            "archived_l1_count": 2,
        }
    }
    builder = PromptBuilder(paths, DummyVM(["l1_1"]), config)
    builder.weather_injector = DummyWeather()

    prompt = builder.build_prompt("query", [{"role": "user", "content": "hi"}])

    assert prompt.count("### Entry ID: l1_1") == 1
    assert "### Entry ID: l1_2" in prompt


def test_prompt_builder_truncates_optional_context_when_budget_exhausted(tmp_path):
    paths = MemoryPaths(str(tmp_path), 456)
    paths.ensure()

    _write_json(paths.master_path(), {"bio": "x" * 4000})
    _write_json(
        paths.l1_dir + "/l1_1.json",
        {"id": "l1_1", "timestamp": "1", "diary": "first", "core_principles": []},
    )

    config = {
        "retrieval": {
            "max_context_tokens": 128,
            "safety_buffer_tokens": 0,
            "recent_l1_count": 1,
            "archived_l1_count": 1,
        }
    }
    builder = PromptBuilder(paths, DummyVM(["l1_1"]), config)
    builder.weather_injector = DummyWeather()

    prompt = builder.build_prompt("query", [{"role": "user", "content": "hi"}])

    assert "... [TRUNCATED]" in prompt
