import os

from memory_core.helpers import read_json, write_json


class StateStore:
    """
    Load/save the per-chat state.json (persistent).
    """

    def __init__(self, state_path: str):
        self.state_path = state_path

    def ensure_exists(self) -> None:
        if os.path.exists(self.state_path):
            return
        self.save({
            "l1_active": [],
            "l2_active": [],
            "l3_active": [],
            "jobs": [],
            "ephemeral": {}
        })

    def load(self) -> dict:
        state = read_json(self.state_path)
        if not isinstance(state, dict):
            state = {}
        state.setdefault("l1_active", [])
        state.setdefault("l2_active", [])
        state.setdefault("l3_active", [])
        state.setdefault("jobs", [])
        state.setdefault("ephemeral", {})
        return state

    def save(self, st: dict) -> None:
        write_json(self.state_path, st)
