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
        # Initialize with only the fields needed for the new architecture
        self.save({"l1_active": [], "jobs": [], "ephemeral": {}})

    def load(self) -> dict:
        state = read_json(self.state_path)
        if not isinstance(state, dict):
            state = {}
        
        # Ensure required fields exist
        state.setdefault("l1_active", [])
        state.setdefault("jobs", [])
        state.setdefault("ephemeral", {})
        
        # Clean up obsolete fields if they exist in the file
        for key in ["l2_active", "l3_active"]:
            if key in state:
                del state[key]

        return state

    def save(self, st: dict) -> None:
        write_json(self.state_path, st)
