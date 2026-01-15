import os

import memory_core.helpers as helpers


def _read_folder(folder: str) -> str:
    if not os.path.isdir(folder):
        return ""
    parts = []
    for name in sorted(os.listdir(folder)):
        p = os.path.join(folder, name)
        if os.path.isfile(p) and name.lower().endswith((".md", ".txt")):
            txt = helpers.read_text(p).strip()
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

    def update_low_priority(self, path) -> None:
        import core.weather as weather

        weather_injector = weather.WeatherInjector()
        weather_txt = weather_injector.weather_updater()
        if weather_txt and weather_txt.strip():
            helpers.write_text(path, weather_txt)
        low_text = helpers.read_text(path).strip()
        self.cache.set_section("low", "", low_text)

    def update_l0(self, l0_items: list) -> None:
        txt = helpers.render_chat_as_text(l0_items)
        self.cache.set_section("l0", "CONVERSATION (L0)", txt)

    def update_levels(self, st: dict) -> None:
        def join_files(paths_list):
            out = []
            for p in paths_list or []:
                t = helpers.read_text(p).strip()
                if t:
                    out.append(t)
            return "\n\n".join(out).strip()

        master_txt = helpers.read_text(self.paths.master_path()).strip()
        self.cache.set_section("l4", "MASTER (L4)", master_txt)
        self.cache.set_section("l3", "SUMMARIES (L3)", join_files(st.get("l3_active", [])))
        self.cache.set_section("l2", "SUMMARIES (L2)", join_files(st.get("l2_active", [])))
        self.cache.set_section("l1", "SUMMARIES (L1)", join_files(st.get("l1_active", [])))
