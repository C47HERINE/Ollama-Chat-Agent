import os
import traceback
from .helpers import read_json, write_json


class StateStore:
    def __init__(self, path):
        self.path = path


    def ensure_exists(self):
        if not os.path.exists(self.path):
            write_json(self.path, {"jobs": []})


    def load(self) -> dict:
        try:
            data = read_json(self.path)
            if not isinstance(data, dict):
                self.ensure_exists()
                return {"jobs": []}
            return data
        except Exception as e:
            print(e, traceback.format_exc())
            return {"jobs": []}


    def save(self, state: dict):
        if not isinstance(state, dict):
            raise ValueError("State must be a dictionary.")
        write_json(self.path, state)
