import os, re
from typing import Iterable, Optional
from core.logger import core_log  # <-- event logger
from memory_core.fs import MemoryPaths
from memory_core.state import StateManager
from memory_core.raw_logger import RawLogger
from memory_core.context_builder import ContextBuilder
from memory_core.introspection import IntrospectionEngine
from memory_core.scheduler import SummaryScheduler


class MemoryEngine:
    LEADING_KIND_TAG_RE = re.compile(r"^\s*\[[^\]\r\n]{1,64}\]\s*(?:\r?\n)+", re.UNICODE)
    def __init__(self, root: str = ".", timeutils=None, context_max_chars: int = 12000):
        self.paths = MemoryPaths(root=root)
        self.paths.ensure()
        if timeutils is None:
            raise RuntimeError("MemoryEngine requires a timeutils module instance.")
        self.t = timeutils
        self.state = StateManager(self.paths.state_path)
        self.raw = RawLogger(self.paths.daily_raw_dir)
        self.context_builder = ContextBuilder(self.paths, max_chars=context_max_chars)
        self.introspection = IntrospectionEngine(self.paths, self.state, self.raw, self.t, self.context_builder)
        self.scheduler = SummaryScheduler(self.paths, self.state, self.t)
        self._last_built_context: str = ""

        # ---- context rebuild control ----
        self._context_dirty: bool = True  # build once at startup
        self._last_context_sig = None     # signature of inputs
        self._last_context_build_ms: int = 0
        self._min_rebuild_interval_s: int = 15  # safety throttle (optional)

        core_log("MEMORY_BOOT", root=root, daily_raw_dir=self.paths.daily_raw_dir,
                 summaries_dir=self.paths.summaries_dir, state_path=self.paths.state_path,
                 context_max_chars=int(context_max_chars))

    # -------------------------
    # Time helpers
    # -------------------------
    def _time_str(self) -> str:
        return self.t.local_dt().strftime("%Y-%m-%d %H:%M:%S")

    def date_key(self, dt) -> str:
        return dt.strftime("%Y-%m-%d")

    def today_key(self) -> str:
        return self.date_key(self.t.local_dt())

    def yesterday_key(self) -> str:
        y_ms = self.t.now_ms() - 24 * 60 * 60 * 1000
        return self.date_key(self.t.local_dt_from_ms(y_ms))

    # -------------------------
    # Content sanitization (NO KIND TAGS IN RAW)
    # -------------------------
    def _strip_leading_kind_tag(self, text: str) -> str:
        if not text:
            return ""
        # Remove at most one leading tag block; if you ever nest tags, loop.
        out = text
        for _ in range(2):  # small safety loop; prevents weird double tags
            new = self.LEADING_KIND_TAG_RE.sub("", out, count=1)
            if new == out:
                break
            out = new
        return out

    def _sanitize_for_raw(self, role: str, content: str) -> str:
        """Raw files must remain human/LLM clean. No metadata tags in content."""
        c = (content or "")
        # Strip kind tags for system + assistant (and it's harmless for user too)
        c = self._strip_leading_kind_tag(c)
        return c

    # -------------------------
    # Context rebuild helpers
    # -------------------------
    def _stat_sig(self, path: str):
        """Return a cheap signature for a path (exists, time, size)."""
        try:
            st = os.stat(path)
            return True, int(st.st_mtime), int(st.st_size)
        except OSError:
            return False, 0, 0

    def _dir_sig(self, folder: str, exts=(".md", ".txt", ".json"), limit: int = 50):
        """Signature for a folder: stable list of (name, time, size) for up to `limit` files."""
        if not os.path.isdir(folder):
            return False, ()
        names = []
        try:
            for name in sorted(os.listdir(folder)):
                if not name.lower().endswith(exts):
                    continue
                names.append(name)
        except OSError:
            return False, ()

        # limit to last N by name (works fine if date-based filenames)
        if limit and len(names) > limit:
            names = names[-limit:]

        items = []
        for name in names:
            p = os.path.join(folder, name)
            exists, mtime, size = self._stat_sig(p)
            if exists:
                items.append((name, mtime, size))
        return True, tuple(items)

    def _compute_context_signature(self, today: str, yesterday: str):
        """
        Inputs that affect context:
        - daily raw D0 / D1
        - system prompt folder contents
        - static context folder contents
        - summary dirs signatures (carry selection)
        """
        d0_path = os.path.join(self.paths.daily_raw_dir, f"{today}.json")
        d1_path = os.path.join(self.paths.daily_raw_dir, f"{yesterday}.json")

        sig = (
            ("d0",) + self._stat_sig(d0_path)
            + ("d1",) + self._stat_sig(d1_path)
            + ("system_dir",) + self._dir_sig(self.paths.system_prompt_dir, limit=50)
            + ("context_dir",) + self._dir_sig(self.paths.context_dir, limit=50)
            + ("daily_summaries",) + self._dir_sig(self.paths.daily_summary_dir, exts=(".md", ".txt"), limit=30)
            + ("weekly_summaries",) + self._dir_sig(self.paths.weekly_summary_dir, exts=(".md", ".txt"), limit=12)
            + ("monthly_summaries",) + self._dir_sig(self.paths.monthly_summary_dir, exts=(".md", ".txt"), limit=24)
            + ("yearly_summaries",) + self._dir_sig(self.paths.yearly_summary_dir, exts=(".md", ".txt"), limit=5)
            )
        return sig

    def _mark_context_dirty(self, reason: str = ""):
        self._context_dirty = True
        if reason:
            core_log("CTX_DIRTY", reason=reason)

    def _append_raw(self, date_key: str, role: str, content: str):
        clean = self._sanitize_for_raw(role, content)

        entry = {
            "role": role,
            "time": self._time_str(),
            "content": clean,
            }
        self.raw.append(date_key, entry)

        # Anything appended to raw can affect context (D0/D1)
        self._mark_context_dirty(reason=f"raw_append:{role}")

    def log_user_message(self, chat_id: int, text: str):
        today = self.today_key()
        self._append_raw(today, "user", text or "")
        self.state.set_last_user_message(chat_id, self.t.now_ms(), text or "")

        core_log("MEMORY_LOG_USER", chat_id=chat_id, day=today, chars=len(text or ""),
            raw_path=os.path.join(self.paths.daily_raw_dir, f"{today}.json"))

    def log_assistant_output(self, chat_id: int, text: str, kind: str = "assistant"):
        today = self.today_key()
        content = (text or "").strip()
        self._append_raw(today, "assistant", content)
        core_log("MEMORY_LOG_ASSISTANT", chat_id=chat_id, day=today, kind=kind, chars=len(content),
            raw_path=os.path.join(self.paths.daily_raw_dir, f"{today}.json"))

    def log_system_event(self, chat_id: int, text: str, kind: str):
        today = self.today_key()
        content = (text or "").strip()
        self._append_raw(today, "system", content)
        core_log("MEMORY_LOG_SYSTEM", chat_id=chat_id, day=today, kind=kind, chars=len(content),
                 raw_path=os.path.join(self.paths.daily_raw_dir, f"{today}.json"))

    def build_context_text(self) -> str:
        today = self.today_key()
        yesterday = self.yesterday_key()
        ctx = self.context_builder.build(today_key=today, yesterday_key=yesterday)
        self._last_built_context = ctx or ""
        self._context_dirty = False
        self._last_context_sig = self._compute_context_signature(today, yesterday)
        self._last_context_build_ms = int(self.t.now_ms())

        core_log("MEMORY_BUILD_CONTEXT", today=today, yesterday=yesterday, chars=len(self._last_built_context),
                 d0_path=os.path.join(self.paths.daily_raw_dir, f"{today}.json"),
                 d1_path=os.path.join(self.paths.daily_raw_dir, f"{yesterday}.json"))

        return self._last_built_context

    def get_last_context_text(self) -> str:
        return self._last_built_context or ""

    def tick(self, llm, any_chat_id_for_llm: Optional[int], known_chats: Iterable[int]):
        today = self.today_key()
        yesterday = self.yesterday_key()
        known_list = list(known_chats or [])

        core_log("MEMORY_TICK_START", today=today, yesterday=yesterday, known_chats=len(known_list),
                 any_chat_id_for_llm=any_chat_id_for_llm)

        # 1) Introspection per chat (never sent)
        introspected = 0
        for chat_id in known_list:
            try:
                block = self.introspection.run_if_needed(llm, chat_id, today)
            except Exception as e:
                core_log("MEMORY_INTROSPECTION_FAIL", chat_id=chat_id, error=str(e))
                continue
            if block:
                introspected += 1
                core_log("MEMORY_INTROSPECTION_DONE", chat_id=chat_id, day=today)

        # 2) Scheduled summaries (idempotent)
        created_paths = []
        if any_chat_id_for_llm is not None:
            try:
                created_paths = self.scheduler.run_due_jobs(
                    llm, chat_id_for_llm=any_chat_id_for_llm
                ) or []
            except Exception as e:
                core_log("MEMORY_SUMMARY_FAIL", error=str(e))
                created_paths = []

        for p in created_paths:
            core_log("MEMORY_SUMMARY_CREATED", path=p)
            # summaries affect context carry selection
            self._mark_context_dirty(reason="summary_created")

        # 3) Rebuild context ONLY if needed
        try:
            now_ms = int(self.t.now_ms())
            since_last = (now_ms - int(self._last_context_build_ms or 0)) / 1000.0

            sig_now = self._compute_context_signature(today, yesterday)
            sig_changed = (self._last_context_sig is None) or (sig_now != self._last_context_sig)

            should_rebuild = (self._context_dirty or sig_changed)

            # optional throttle so never rebuild too frequently
            if should_rebuild and since_last < self._min_rebuild_interval_s:
                core_log("CTX_SKIP", reason="throttled", since_last_s=round(since_last, 2),
                         dirty=self._context_dirty, sig_changed=sig_changed)

            elif should_rebuild:
                self.build_context_text()
            else:
                core_log("CTX_SKIP", reason="no_changes", dirty=False, sig_changed=False)

        except Exception as e:
            core_log("MEMORY_BUILD_CONTEXT_FAIL", error=str(e))

        core_log("MEMORY_TICK_END", introspected=introspected, summaries_created=len(created_paths),
                 context_chars=len(self._last_built_context or ""))
        return created_paths
