from memory_core.helpers import read_json, write_json, write_text

class ContextCache:
    """
    Store sections in JSON and render to plain text for injection/review.
    """
    def __init__(self, cache_path: str, out_txt_path: str, sep_line: str):
        self.cache_path = cache_path
        self.out_txt_path = out_txt_path
        self.sep_line = sep_line

    def load(self) -> dict:
        d = read_json(self.cache_path, default={})
        if not isinstance(d, dict):
            d = {}
        d.setdefault("sections", {})
        return d

    def save(self, d: dict) -> None:
        write_json(self.cache_path, d)

    def set_section(self, section_id: str, title: str, text: str) -> None:
        d = self.load()
        d["sections"][section_id] = {"title": title, "text": (text or "").strip()}
        self.save(d)

    def render(self, order: list) -> str:
        d = self.load()
        sections = d.get("sections", {}) if isinstance(d.get("sections", {}), dict) else {}

        parts = []
        for sid in order:
            sec = sections.get(sid)
            if not sec:
                continue
            title = (sec.get("title") or "").strip()
            text = (sec.get("text") or "").strip()
            if not text:
                continue
            parts.append(f"## {title}\n{text}\n{self.sep_line}\n")

        out = "\n".join(parts).strip()
        write_text(self.out_txt_path, out)
        return out