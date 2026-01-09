from memory_core.helpers import read_json

class PromptLibrary:
    """
    Load prompts.json and format templates.
    """
    def __init__(self, prompts_json_path: str):
        data = read_json(prompts_json_path, default={})
        self.templates = (data.get("templates") or {}) if isinstance(data, dict) else {}
        self.limits = (data.get("limits") or {}) if isinstance(data, dict) else {}

    def format(self, name: str, **kwargs) -> str:
        tpl = self.templates.get(name, "")
        return tpl.format(**kwargs)