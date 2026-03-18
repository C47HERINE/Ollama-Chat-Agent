import os
import logging
import traceback
from .helpers import read_json, write_json

logger = logging.getLogger(__name__)

class StateStore:
    def __init__(self, path):
        self.path = path

    def ensure_exists(self):
        try:
            if not os.path.exists(self.path):
                write_json(self.path, {"jobs": []})
        except Exception as e:
            logger.error(f"Failed to ensure state file exists at {self.path}: {e}")
            logger.error(traceback.format_exc())

    def load(self) -> dict:
        try:
            data = read_json(self.path)
            if not isinstance(data, dict):
                logger.warning(f"State file at {self.path} is not a dict, re-initializing.")
                self.ensure_exists()
                return {"jobs": []}
            return data
        except Exception as e:
            logger.error(f"Failed to load state from {self.path}: {e}")
            logger.error(traceback.format_exc())
            return {"jobs": []} # Return a default state on failure

    def save(self, state: dict):
        try:
            if not isinstance(state, dict):
                raise ValueError("State must be a dictionary.")
            write_json(self.path, state)
        except Exception as e:
            logger.error(f"Failed to save state to {self.path}: {e}")
            logger.error(traceback.format_exc())
