import json, os, re
from dataclasses import dataclass
from typing import List

date_raw_re = re.compile(r"^(\d{4}-\d{2}-\d{2})\.json$")
date_md_re = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")
week_re = re.compile(r"^(\d{4})-(\d{2})\.md$")
month_re = re.compile(r"^(\d{4})-(\d{2})\.md$")
year_re = re.compile(r"^(\d{4})\.md$")

@dataclass
class SummaryFile:
    path: str
    key: str

def list_daily_raw(daily_raw_dir: str) -> List[SummaryFile]:
    out: List[SummaryFile] = []
    if not os.path.isdir(daily_raw_dir):
        return out
    for name in os.listdir(daily_raw_dir):
        m = date_raw_re.match(name)
        if not m:
            continue
        key = m.group(1)
        out.append(SummaryFile(os.path.join(daily_raw_dir, name), key))
    out.sort(key=lambda x: x.key)
    return out

def list_daily_summaries(daily_dir: str) -> List[SummaryFile]:
    out: List[SummaryFile] = []
    if not os.path.isdir(daily_dir):
        return out
    for name in os.listdir(daily_dir):
        m = date_md_re.match(name)
        if not m:
            continue
        key = m.group(1)
        out.append(SummaryFile(os.path.join(daily_dir, name), key))
    out.sort(key=lambda x: x.key)
    return out

def list_weekly_summaries(weekly_dir: str) -> List[SummaryFile]:
    out: List[SummaryFile] = []
    if not os.path.isdir(weekly_dir):
        return out
    for name in os.listdir(weekly_dir):
        m = week_re.match(name)
        if not m:
            continue
        key = f"{m.group(1)}-{m.group(2)}"
        out.append(SummaryFile(os.path.join(weekly_dir, name), key))
    out.sort(key=lambda x: x.key)
    return out

def list_monthly_summaries(monthly_dir: str) -> List[SummaryFile]:
    out: List[SummaryFile] = []
    if not os.path.isdir(monthly_dir):
        return out
    for name in os.listdir(monthly_dir):
        m = month_re.match(name)
        if not m:
            continue
        key = f"{m.group(1)}-{m.group(2)}"
        out.append(SummaryFile(os.path.join(monthly_dir, name), key))
    out.sort(key=lambda x: x.key)
    return out

def list_yearly_summaries(yearly_dir: str) -> List[SummaryFile]:
    out: List[SummaryFile] = []
    if not os.path.isdir(yearly_dir):
        return out
    for name in os.listdir(yearly_dir):
        m = year_re.match(name)
        if not m:
            continue
        key = m.group(1)
        out.append(SummaryFile(os.path.join(yearly_dir, name), key))
    out.sort(key=lambda x: x.key)
    return out

def read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return ""

def read_conversation_tail(path: str, max_messages: int = 60, max_chars: int = 8000) -> str:
    """Read the tail of a daily conversation JSON file"""
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return ""
    except Exception:
        return ""
    tail = data[-max_messages:] if len(data) > max_messages else data
    lines: List[str] = []
    for m in tail:
        if not isinstance(m, dict):
            continue
        role = (m.get("role") or "").strip()
        time_s = (m.get("time") or "").strip()
        content = m.get("content")
        if content is None:
            content = ""
        content = str(content).strip()
        if not role or not content:
            continue
        if time_s:
            lines.append(f"[{time_s}] {role}: {content}")
        else:
            lines.append(f"{role}: {content}")
    text = "\n".join(lines).strip()
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]