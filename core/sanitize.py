import re

# remove role labels at the start of a line: "assistant: ...", "user: ...", "system: ..."
_ROLE_PREFIX = re.compile(r"^\s*(assistant|user|system)\s*:\s*", re.IGNORECASE)

def strip_role_prefixes(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    lines = []
    for line in t.splitlines():
        lines.append(_ROLE_PREFIX.sub("", line))
    t2 = "\n".join(lines).strip()

    # if model double-prefixed, strip once more at very start
    t2 = _ROLE_PREFIX.sub("", t2).strip()
    return t2
