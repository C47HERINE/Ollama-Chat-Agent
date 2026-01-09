import core.timeutils as t

def meta_header():
    dt = t.local_dt()
    date_str = dt.strftime("%Y-%m-%d")
    time_str = dt.strftime("%H:%M")
    tod = t.time_of_day_label(dt.hour)
    wk = t.weekday_label()
    return (
        f"Meta: Local date {date_str}, local time {time_str}, {tod}, {wk}.\n"
        "Instruction: Be natural, conversational, and context-aware.\n"
    )

def build_prompt(kind):
    meta = meta_header()

    if kind == "addon":
        return (
            meta +
            "Task: Write ONE short add-on message.\n"
            "Rules: Keep it casual, natural. Do not sound formal. Do not over-explain.\n"
            "Avoid starting a new topic unless it's a light continuation.\n"
        )

    if kind == "starter":
        return (
            meta +
            "Task: Start a fresh conversation with ONE short message.\n"
            "Rules: Do NOT reference old details unless explicitly relevant. Do not act like you're continuing yesterday.\n"
            "Make it sound like a normal person starting a new thread.\n"
        )

    return meta + "Task: Write ONE short friendly message.\n"