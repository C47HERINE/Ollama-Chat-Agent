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
        d = read_json(self.cache_path)
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

    def get_section_text(self, section_id: str) -> str:
        d = self.load()
        sec = (d.get("sections") or {}).get(section_id) or {}
        return (sec.get("text") or "").strip()

    def render_string(self, order: list) -> str:
        """Render sections in `order` to a single string (no file write)."""
        d = self.load()
        sections = d.get("sections", {}) if isinstance(d.get("sections", {}), dict) else {}

        parts = []
        for section in order:
            sec = sections.get(section)
            if not sec:
                continue
            title = (sec.get("title") or "").strip()
            text = (sec.get("text") or "").strip()
            if not text:
                continue
            parts.append(f"## {title}\n{text}\n{self.sep_line}\n")

        return "\n".join(parts).strip()

    def render(self, order: list) -> str:
        """Render + write to out_txt_path (your current behavior)."""
        out = self.render_string(order)
        write_text(self.out_txt_path, out)
        return out