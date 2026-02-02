import logging
import traceback
from .helpers import read_json

logger = logging.getLogger(__name__)

class PromptLibrary:
    def __init__(self, path):
        self.path = path
        self.prompts = self._load()

    def _load(self) -> dict:
        try:
            prompts = read_json(self.path)
            if not isinstance(prompts, dict):
                raise ValueError("Prompts file must be a JSON object.")
            return prompts
        except Exception as e:
            logger.error(f"Failed to load prompt library from {self.path}: {e}")
            logger.error(traceback.format_exc())
            return {} # Return empty dict on failure

    def get(self, key: str) -> str:
        try:
            return self.prompts.get(key, "")
        except Exception as e:
            logger.error(f"Failed to get prompt for key '{key}': {e}")
            return ""

    def format(self, key: str, **kwargs) -> str:
        try:
            prompt_template = self.get(key)
            if not prompt_template:
                logger.warning(f"Prompt template for key '{key}' is empty or not found.")
                return ""
            return prompt_template.format(**kwargs)
        except KeyError as e:
            logger.error(f"Missing keyword for prompt '{key}': {e}")
            logger.error(traceback.format_exc())
            return f"ERROR: Prompt formatting failed for key '{key}'. Missing placeholder: {e}"
        except Exception as e:
            logger.error(f"Failed to format prompt for key '{key}': {e}")
            logger.error(traceback.format_exc())
            return f"ERROR: Prompt formatting failed for key '{key}'."
