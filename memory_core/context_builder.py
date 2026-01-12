import os
from memory_core.helpers import read_text, render_chat_as_text

def _read_folder(folder: str) -> str:
    if not os.path.isdir(folder):
        return ""
    parts = []
    for name in sorted(os.listdir(folder)):
        p = os.path.join(folder, name)
        if os.path.isfile(p) and name.lower().endswith((".md", ".txt")):
            txt = read_text(p).strip()
            if txt:
                parts.append(txt)
    return "\n\n".join(parts).strip()

class ContextBuilder:
    """
    Update cache sections from filesystem/state (no job logic).
    """
    def __init__(self, paths, cache):
        self.paths = paths
        self.cache = cache

    def get_system_prompt(self) -> str:
        sys_txt = _read_folder(self.paths.system_dir)
        return sys_txt.strip()

    def update_user_context(self) -> None:
        ctx_txt = _read_folder(self.paths.user_context_dir)
        self.cache.set_section("user_context", "USER CONTEXT", ctx_txt)

    def update_low_priority(self, low_text: str) -> None:
        # weather/introspection later; keep empty or a small block
        self.cache.set_section("low", "LOW PRIORITY", (low_text or "").strip())

    def update_l0(self, l0_items: list) -> None:
        txt = render_chat_as_text(l0_items)
        self.cache.set_section("l0", "CONVERSATION (L0)", txt)

    def update_levels(self, st: dict) -> None:
        def join_files(paths_list):
            out = []
            for p in paths_list or []:
                t = read_text(p).strip()
                if t:
                    out.append(t)
            return "\n\n".join(out).strip()

        master_txt = read_text(self.paths.master_path()).strip()
        self.cache.set_section("l4", "MASTER (L4)", master_txt)

        self.cache.set_section("l3", "SUMMARIES (L3)", join_files(st.get("l3_active", [])))
        self.cache.set_section("l2", "SUMMARIES (L2)", join_files(st.get("l2_active", [])))
        self.cache.set_section("l1", "SUMMARIES (L1)", join_files(st.get("l1_active", [])))