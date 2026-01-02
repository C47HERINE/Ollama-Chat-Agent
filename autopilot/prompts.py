from .timeutils import local_time, time_of_day_label, weekday_label

def meta_header():
    lt = local_time()
    date_str = f"{lt.tm_year:04d}-{lt.tm_mon:02d}-{lt.tm_mday:02d}"
    time_str = f"{lt.tm_hour:02d}:{lt.tm_min:02d}"
    tod = time_of_day_label(lt.tm_hour)
    wk = weekday_label()
    return (
        f"Meta: Local date {date_str}, local time {time_str}, {tod}, {wk}.\n"
        "Instruction: Be natural, conversational, and context-aware.\n"
    )

def build_prompt(kind):
    meta = meta_header()

    if kind == "addon":
        return (
            meta +
            "Task: Write ONE short add-on message as if you just remembered something.\n"
            "Rules: Keep it casual, natural. Do not sound formal. Do not over-explain.\n"
            "Avoid starting a whole new topic unless it's a light continuation.\n"
        )

    if kind == "starter":
        return (
            meta +
            "Task: Start a fresh conversation with ONE short message.\n"
            "Rules: Do NOT reference old details unless explicitly relevant. Do not act like you're continuing yesterday.\n"
            "Make it sound like a normal person starting a new thread.\n"
        )

    return meta + "Task: Write ONE short friendly message.\n"