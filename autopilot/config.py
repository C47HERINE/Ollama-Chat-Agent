def default_settings():
    return {
        "state_dir": "./autopilot/agent_state",
        "tick_every_seconds": 30,
        "jitter_min_ms": 10 * 1000,
        "jitter_max_ms": 2 * 60 * 1000,
        "addon_min_seconds": 30,
        "addon_max_seconds": 10 * 60,
        "cap_min": 1,
        "cap_max": 2,
        "quiet_start_hour": 23,
        "quiet_end_hour": 7,
        "reengage_min_hours": 4,
        "reengage_max_hours": 24,
        "addon_max_pending_inbound": 2,
        "addon_cooldown_minutes": 2,
        "addon_post_send_cooldown_minutes": 2,
        "starter_post_send_cooldown_minutes": 180,
    }
