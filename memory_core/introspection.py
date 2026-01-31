class IntrospectionEngine:
    """Generates a private introspection output and logs ONLY the output into daily JSON."""
    def __init__(self, timeutils):
        self.t = timeutils

    def should_introspect(self, state: dict, silence_ms: int = 3600_000) -> bool:
        last_inbound = int(state.get("last_inbound_ms", 0))
        if last_inbound <= 0:
            return False
        
        last_introspection = int(state.get("last_introspection_ms", 0))
        if last_introspection > last_inbound:
            # Already introspected since the last user message
            return False

        now_ms = int(self.t.now_ms())
        delta = now_ms - last_inbound
        eligible = delta >= int(silence_ms)
        return eligible

    def build_block(self) -> str:
        now_str = self.t.local_dt().strftime("%H:%M:%S")
        lines = (
            f"Time: {now_str}\n"
            "This is a private internal reflection generated during silence.\n"
            "Not normal chat. No greeting. No questions. No process explanation.\n"
            "Keep it concise: 6-10 lines max.\n"
            "\n"
            "Write three short sections with headers exactly:\n"
            "UNRESOLVED:\n"
            "TONE:\n"
            "NEXT:\n"
            )
        return lines
