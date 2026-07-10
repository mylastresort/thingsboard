"""Tool for grounding the agent in the actual current date/time.

LLMs will happily invent a "current time" from context or training data
(e.g. assuming a date mentioned earlier in the conversation, or defaulting
to their training cutoff). This tool exists so the root agent never has to
guess: it calls out to the host clock and gets back an unambiguous,
explicitly-labeled answer.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def get_current_datetime(iana_timezone: str = "UTC") -> dict:
    """Returns the real current date and time. Call this before doing any
    calculation that depends on "now" (e.g. "last 24 hours", "this week",
    "since yesterday") — never assume or infer the current date from
    conversation context.

    Args:
        iana_timezone: IANA timezone name, e.g. "UTC", "Africa/Casablanca",
            "America/New_York". Defaults to "UTC".

    Returns:
        dict with:
            iso_utc: current time in UTC, ISO 8601 (e.g.
                "2026-07-10T14:32:05.123456+00:00")
            iso_local: current time in the requested timezone, ISO 8601
            timezone: the timezone name that was actually used
            unix_ms: current time as Unix epoch milliseconds (int) — use
                this directly for ThingsBoard getTimeseries startTs/endTs
            human_readable: e.g. "Friday, July 10, 2026, 14:32 UTC"
    """
    now_utc = datetime.now(timezone.utc)

    try:
        tz = ZoneInfo(iana_timezone)
        resolved_tz_name = iana_timezone
    except Exception:
        tz = timezone.utc
        resolved_tz_name = "UTC"

    now_local = now_utc.astimezone(tz)

    return {
        "iso_utc": now_utc.isoformat(),
        "iso_local": now_local.isoformat(),
        "timezone": resolved_tz_name,
        "unix_ms": int(now_utc.timestamp() * 1000),
        "human_readable": now_local.strftime("%A, %B %d, %Y, %H:%M %Z"),
    }
