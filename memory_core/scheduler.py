import os, re
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple
from memory_core.summarizer import Summarizer


DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.(json|md)$")


def _parse_date_from_filename(name: str) -> Optional[date]:
    m = DATE_RE.match(name.strip())
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d").date()
    except Exception:
        return None


def _date_key(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def _start_of_week(d: date) -> date:
    # Monday start, Sunday end
    return d - timedelta(days=d.weekday())


def _end_of_week(d: date) -> date:
    return _start_of_week(d) + timedelta(days=6)


def _ym(d: date) -> Tuple[int, int]:
    return d.year, d.month


class SummaryScheduler:
    """
    New behavior:
    - Never summarizes yesterday. Daily starts at day-before-yesterday.
    - Backfills missing summaries based on what's present in daily_raw.
    - Plans all tasks first, then executes only eligible ones.
    - Weekly runs on Thursdays and only generates LAST WEEK (not current week).
    - Monthly/yearly follow same "completed period only" pattern.
    - Adds startup integrity check to fill missing summaries immediately.
    """

    def __init__(self, paths, state, timeutils):
        self.paths = paths
        self.state = state
        self.t = timeutils
        self.summarizer = Summarizer(paths, timeutils)

    # -------------------------
    # Directory scanners
    # -------------------------
    def _list_raw_days(self) -> List[date]:
        out: List[date] = []
        if not os.path.isdir(self.paths.daily_raw_dir):
            return out
        for name in os.listdir(self.paths.daily_raw_dir):
            d = _parse_date_from_filename(name)
            if d and name.lower().endswith(".json"):
                out.append(d)
        out.sort()
        return out

    def _list_daily_summaries(self) -> List[date]:
        out: List[date] = []
        if not os.path.isdir(self.paths.daily_summary_dir):
            return out
        for name in os.listdir(self.paths.daily_summary_dir):
            d = _parse_date_from_filename(name)
            if d and name.lower().endswith(".md"):
                out.append(d)
        out.sort()
        return out

    def _daily_out_path(self, d: date) -> str:
        return os.path.join(self.paths.daily_summary_dir, f"{_date_key(d)}.md")

    def _daily_raw_path(self, d: date) -> str:
        return os.path.join(self.paths.daily_raw_dir, f"{_date_key(d)}.json")

    def _weekly_out_path(self, start_d: date, end_d: date) -> str:
        # explicit boundaries to avoid ambiguity / duplicates
        return os.path.join(self.paths.weekly_summary_dir, f"{_date_key(start_d)}_to_{_date_key(end_d)}.md")

    def _monthly_out_path(self, y: int, m: int) -> str:
        return os.path.join(self.paths.monthly_summary_dir, f"{y:04d}-{m:02d}.md")

    def _yearly_out_path(self, y: int) -> str:
        return os.path.join(self.paths.yearly_summary_dir, f"{y:04d}.md")

    # -------------------------
    # Planning logic
    # -------------------------
    def _plan_daily_tasks(self, today: date) -> List[Dict]:
        """
        Daily creation rule:
        - For every daily_raw day that is <= day-before-yesterday,
          create daily summary if missing.
        - Never create for yesterday or today.
        """
        tasks: List[Dict] = []
        raw_days = self._list_raw_days()

        cutoff = today - timedelta(days=2)  # day-before-yesterday is allowed; yesterday is not
        for d in raw_days:
            if d > cutoff:
                continue

            raw_path = self._daily_raw_path(d)
            out_path = self._daily_out_path(d)

            if not os.path.exists(raw_path):
                continue

            if os.path.exists(out_path):
                tasks.append({
                    "type": "daily",
                    "eligible": False,
                    "reason": "already_exists",
                    "day": _date_key(d),
                    "raw_path": raw_path,
                    "out_path": out_path,
                })
                continue

            tasks.append({
                "type": "daily",
                "eligible": True,
                "reason": "missing_daily_summary",
                "day": _date_key(d),
                "raw_path": raw_path,
                "out_path": out_path,
            })

        return tasks

    def _plan_weekly_task(self, today: date, weekday: int) -> Dict:
        """
        Weekly rule:
        - Run on Thursdays.
        - Only generate LAST WEEK (not current week).
        - Generate if:
            - weekly file for that range does not exist
            - AND at least one daily summary exists inside that week (so input exists)
        """
        # Thursday = 3 (Mon=0)
        if weekday != 3:
            return {"type": "weekly", "eligible": False, "reason": "not_thursday"}

        start_this_week = _start_of_week(today)
        last_week_end = start_this_week - timedelta(days=1)
        last_week_start = _start_of_week(last_week_end)

        out_path = self._weekly_out_path(last_week_start, last_week_end)
        if os.path.exists(out_path):
            return {
                "type": "weekly",
                "eligible": False,
                "reason": "already_exists",
                "start": _date_key(last_week_start),
                "end": _date_key(last_week_end),
                "out_path": out_path,
            }

        # Inputs: daily summaries within last week
        daily_days = set(self._list_daily_summaries())
        daily_paths: List[str] = []
        d = last_week_start
        while d <= last_week_end:
            if d in daily_days:
                daily_paths.append(self._daily_out_path(d))
            d += timedelta(days=1)

        if not daily_paths:
            return {
                "type": "weekly",
                "eligible": False,
                "reason": "no_daily_inputs",
                "start": _date_key(last_week_start),
                "end": _date_key(last_week_end),
                "out_path": out_path,
            }

        return {
            "type": "weekly",
            "eligible": True,
            "reason": "missing_weekly_summary",
            "start": _date_key(last_week_start),
            "end": _date_key(last_week_end),
            "out_path": out_path,
            "daily_paths": daily_paths,
        }

    def _plan_monthly_task(self, today: date, weekday: int) -> Dict:
        """
        Monthly rule:
        - Run on Thursdays.
        - Only generate LAST MONTH (not current month).
        - Generate if monthly summary missing and there are daily summaries for that month.
        """
        if weekday != 3:
            return {"type": "monthly", "eligible": False, "reason": "not_thursday"}

        first_this_month = today.replace(day=1)
        last_month_end = first_this_month - timedelta(days=1)
        y, m = _ym(last_month_end)

        out_path = self._monthly_out_path(y, m)
        if os.path.exists(out_path):
            return {"type": "monthly", "eligible": False, "reason": "already_exists", "year": y, "month": m, "out_path": out_path}

        daily_days = set(self._list_daily_summaries())
        daily_paths: List[str] = []
        d = last_month_end.replace(day=1)
        while d.month == m:
            if d in daily_days:
                daily_paths.append(self._daily_out_path(d))
            d += timedelta(days=1)

        if not daily_paths:
            return {"type": "monthly", "eligible": False, "reason": "no_daily_inputs", "year": y, "month": m, "out_path": out_path}

        return {"type": "monthly", "eligible": True, "reason": "missing_monthly_summary", "year": y, "month": m, "out_path": out_path, "daily_paths": daily_paths}

    def _plan_yearly_task(self, today: date, weekday: int) -> Dict:
        """
        Yearly rule:
        - Run on Thursdays.
        - Only generate LAST YEAR (not current year).
        - Generate if yearly summary missing and there are monthly summaries for that year.
        """
        if weekday != 3:
            return {"type": "yearly", "eligible": False, "reason": "not_thursday"}

        last_year = today.year - 1
        out_path = self._yearly_out_path(last_year)
        if os.path.exists(out_path):
            return {"type": "yearly", "eligible": False, "reason": "already_exists", "year": last_year, "out_path": out_path}

        # monthly inputs: YYYY-MM.md
        monthly_paths: List[str] = []
        if os.path.isdir(self.paths.monthly_summary_dir):
            for name in sorted(os.listdir(self.paths.monthly_summary_dir)):
                if name.startswith(f"{last_year:04d}-") and name.lower().endswith(".md"):
                    monthly_paths.append(os.path.join(self.paths.monthly_summary_dir, name))

        if not monthly_paths:
            return {"type": "yearly", "eligible": False, "reason": "no_monthly_inputs", "year": last_year, "out_path": out_path}

        return {"type": "yearly", "eligible": True, "reason": "missing_yearly_summary", "year": last_year, "out_path": out_path, "monthly_paths": monthly_paths}

    def build_plan(self) -> Dict[str, List[Dict]]:
        """
        Build a full plan (all tasks) based on current date/time, without executing.
        """
        dt = self.t.local_dt()
        today = dt.date()
        hhmm = (dt.hour, dt.minute)
        weekday = dt.weekday()

        plan: Dict[str, List[Dict]] = {"daily": [], "weekly": [], "monthly": [], "yearly": []}

        # Daily tasks are allowed ONLY at/after 03:00 during scheduled runs,
        # but integrity checker can override.
        plan["daily"] = self._plan_daily_tasks(today)

        # Higher-level tasks planned always, but only eligible on Thursdays.
        plan["weekly"] = [self._plan_weekly_task(today, weekday)]
        plan["monthly"] = [self._plan_monthly_task(today, weekday)]
        plan["yearly"] = [self._plan_yearly_task(today, weekday)]

        return plan

    # -------------------------
    # Execution
    # -------------------------
    def _execute_task(self, llm, chat_id_for_llm: int, task: Dict) -> Optional[str]:
        ttype = task.get("type")

        if not task.get("eligible"):
            return None

        if ttype == "daily":
            day_key = task["day"]
            raw_path = task["raw_path"]
            out_path = task["out_path"]
            return self.summarizer.daily(llm, chat_id_for_llm, day_key, raw_path, out_path)

        if ttype == "weekly":
            # requires summarizer.weekly_range(...)
            return self.summarizer.weekly_range(
                llm,
                chat_id_for_llm,
                task["start"],
                task["end"],
                task["daily_paths"],
                task["out_path"],
            )

        if ttype == "monthly":
            # requires summarizer.monthly_range(...)
            return self.summarizer.monthly_range(
                llm,
                chat_id_for_llm,
                int(task["year"]),
                int(task["month"]),
                task["daily_paths"],
                task["out_path"],
            )

        if ttype == "yearly":
            # requires summarizer.yearly_range(...)
            return self.summarizer.yearly_range(
                llm,
                chat_id_for_llm,
                int(task["year"]),
                task["monthly_paths"],
                task["out_path"],
            )

        return None

    def run_due_jobs(self, llm, chat_id_for_llm: int) -> List[str]:
        """
        Scheduled run:
        - At/after 03:00 → allow DAILY execution.
        - At/after 03:30/03:45/04:00 is no longer needed because we run weekly/monthly/yearly on Thursdays only,
          and these don't need minute precision now. (You can re-add gates if you want.)
        """
        created: List[str] = []
        dt = self.t.local_dt()
        hhmm = (dt.hour, dt.minute)
        plan = self.build_plan()

        # Time gate: daily only after 03:00
        allow_daily = hhmm >= (3, 0)

        # Execute daily tasks (if allowed)
        for task in plan["daily"]:
            if not allow_daily:
                continue
            p = self._execute_task(llm, chat_id_for_llm, task)
            if p:
                created.append(p)

        # Execute weekly/monthly/yearly tasks (only if eligible=true; they self-enforce Thursday)
        for bucket in ("weekly", "monthly", "yearly"):
            for task in plan[bucket]:
                p = self._execute_task(llm, chat_id_for_llm, task)
                if p:
                    created.append(p)
        return created