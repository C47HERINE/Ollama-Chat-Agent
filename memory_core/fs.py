import os

class MemoryPaths:
    """Filesystem layout for persistent memory/state."""
    def __init__(self, root="."):
        self.root = root
        self.user_dir = os.path.join(root, "user")
        self.system_prompt_dir = os.path.join(self.user_dir, "system_prompt")
        self.context_dir = os.path.join(self.user_dir, "context")
        self.conversations_dir = os.path.join(self.user_dir, "conversations")
        self.daily_raw_dir = os.path.join(self.conversations_dir, "daily_raw")
        self.summaries_dir = os.path.join(self.user_dir, "summaries")
        self.daily_summary_dir = os.path.join(self.summaries_dir, "daily")
        self.weekly_summary_dir = os.path.join(self.summaries_dir, "weekly")
        self.monthly_summary_dir = os.path.join(self.summaries_dir, "monthly")
        self.yearly_summary_dir = os.path.join(self.summaries_dir, "yearly")
        self.state_dir = os.path.join(self.user_dir, "state")
        self.state_path = os.path.join(self.state_dir, "state.json")

    def ensure(self):
        """Create all required directories."""
        dirs = [
            self.user_dir,
            self.system_prompt_dir,
            self.context_dir,
            self.conversations_dir,
            self.daily_raw_dir,
            self.summaries_dir,
            self.daily_summary_dir,
            self.weekly_summary_dir,
            self.monthly_summary_dir,
            self.yearly_summary_dir,
            self.state_dir,
        ]
        for d in dirs:
            os.makedirs(d, exist_ok=True)