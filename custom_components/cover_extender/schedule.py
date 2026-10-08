"""Morning and evening schedules: one annual curve per event.

Pure: the caller supplies, for each day of the year (1..365), the time of the
sun event (sunrise for the morning, sunset for the evening) in UTC minutes and
the local time-zone offset in minutes. Nothing here imports Home Assistant,
so the whole computation is tested as is; ha_sun_year below is the one place
that asks Home Assistant for the sun.

The curve, per schedule:
- it reaches its max time on the day the sun event is the latest, its min
  time on the day it is the earliest, and joins them by two half-sines in
  SOLAR time (UTC), so it follows the sun rather than the clock change;
- a spring or autumn crossing bends the half that holds it so that, that day,
  the schedule falls exactly on the sun event;
- a floor ("not before") and a ceiling ("not after") clamp it, in LEGAL time;
- max == min means a fixed time all year, in legal time.

Same maths as the "Horaires des volets" mock-up, now the single source of
truth: the panel only draws what the preview command returns.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, tzinfo
from typing import Any

DAYS = 365
P_YEAR = 365.2425
MARCH_EQUINOX = 79          # day of the year, used to tell spring from autumn
KINDS = ("morning", "evening")
SUN_EVENT = {"morning": "sunrise", "evening": "sunset"}
# What a schedule starts from when it is switched on in the panel: a curve
# that follows the sun between sensible bounds, never before 07:00 in the
# morning, nor after 22:30 in the evening.
DEFAULTS = {
    "morning": {"type": "curve", "max": "08:30", "min": "06:30", "cross_spring": None,
                "cross_autumn": None, "not_before": "07:00", "not_after": None},
    "evening": {"type": "curve", "max": "22:00", "min": "17:30", "cross_spring": None,
                "cross_autumn": None, "not_before": None, "not_after": "22:30"},
}

_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_MMDD = re.compile(r"^(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")


# ── Settings ──────────────────────────────────────────────────────────────────

@dataclass
class Settings:
    """One schedule, in minutes of the local day and days of the year."""

    hi: int                         # max time (legal), minutes
    lo: int                         # min time (legal), minutes
    cross_spring: int | None = None  # day of the year, or None
    cross_autumn: int | None = None
    floor: int | None = None        # "not before" (legal), minutes
    ceiling: int | None = None      # "not after" (legal), minutes

    @property
    def fixed(self) -> bool:
        return self.hi == self.lo


def hm_to_minutes(value: str) -> int:
    match = _HHMM.match(str(value))
    if not match:
        raise ValueError(value)
    return int(match.group(1)) * 60 + int(match.group(2))


def minutes_to_hm(minutes: float) -> str:
    m = int(round(minutes)) % 1440
    return f"{m // 60:02d}:{m % 60:02d}"


def mmdd_to_day(value: str, year: int) -> int:
    """'03-17' → its day of the year (1..365; 29 February folds onto 28)."""
    match = _MMDD.match(str(value))
    if not match:
        raise ValueError(value)
    month, day = int(match.group(1)), int(match.group(2))
    if month == 2 and day == 29:
        day = 28
    return min(date(year, month, day).timetuple().tm_yday, DAYS)


def day_to_mmdd(day: int, year: int) -> str:
    return (date(year, 1, 1) + timedelta(days=day - 1)).strftime("%m-%d")


def parse_action(value: Any) -> str | dict[str, Any] | None:
    """A cover's morning or evening action: a mode name, a position, or None.

    A position is {"position": 0..100, "force": bool}: forced, it moves a
    locked cover too; otherwise a locked cover keeps it in memory. Anything
    else that is not a mode name reads as no action. Raises ValueError on a
    position that cannot be read, for the panel to refuse it.
    """
    if isinstance(value, dict):
        pos = value.get("position")
        if isinstance(pos, bool) or not isinstance(pos, int) or not 0 <= pos <= 100:
            raise ValueError(pos)
        return {"position": pos, "force": bool(value.get("force", False))}
    return value if isinstance(value, str) and value else None


def validate_settings(cfg: Any) -> str | None:
    """Shape of one stored schedule; an error code, or None.

    Stored shape: {"type": "fixed", "time": "HH:MM"} or {"type": "curve",
    "max", "min" ("HH:MM"), "cross_spring", "cross_autumn" ("MM-DD" or
    null)}, plus "not_before" / "not_after" ("HH:MM" or null) for both.
    """
    if not isinstance(cfg, dict):
        return "schedule_invalid"
    try:
        if cfg.get("type") == "fixed":
            hm_to_minutes(cfg.get("time"))
        elif cfg.get("type") == "curve":
            hi, lo = hm_to_minutes(cfg.get("max")), hm_to_minutes(cfg.get("min"))
            if lo > hi:
                return "schedule_min_after_max"
            for key in ("cross_spring", "cross_autumn"):
                if cfg.get(key) is not None:
                    mmdd_to_day(cfg[key], 2001)
        else:
            return "schedule_invalid"
        floor = cfg.get("not_before")
        ceiling = cfg.get("not_after")
        if floor is not None:
            floor = hm_to_minutes(floor)
        if ceiling is not None:
            ceiling = hm_to_minutes(ceiling)
    except (TypeError, ValueError):
        return "schedule_invalid"
    if floor is not None and ceiling is not None and floor >= ceiling:
        return "schedule_floor_after_ceiling"
    return None


def parse_settings(cfg: dict[str, Any], year: int) -> Settings:
    """Stored shape → Settings. The shape must have passed validate_settings."""
    if cfg.get("type") == "fixed":
        hi = lo = hm_to_minutes(cfg["time"])
        spring = autumn = None
    else:
        hi, lo = hm_to_minutes(cfg["max"]), hm_to_minutes(cfg["min"])
        spring = mmdd_to_day(cfg["cross_spring"], year) if cfg.get("cross_spring") else None
        autumn = mmdd_to_day(cfg["cross_autumn"], year) if cfg.get("cross_autumn") else None
    return Settings(
        hi=hi, lo=lo, cross_spring=spring, cross_autumn=autumn,
        floor=hm_to_minutes(cfg["not_before"]) if cfg.get("not_before") else None,
        ceiling=hm_to_minutes(cfg["not_after"]) if cfg.get("not_after") else None,
    )


# ── The sun over a year ───────────────────────────────────────────────────────

@dataclass
class SunYear:
    """A sun event and the time-zone offset, for days 1..365 (index 0 unused)."""

    ref: list[float]       # UTC minutes of the sun event
    off: list[int]         # local offset, minutes
    jp: int = field(init=False)     # day the event is the latest
    jt: int = field(init=False)     # day the event is the earliest
    l1: float = field(init=False)   # length of the rising half, days

    def __post_init__(self) -> None:
        days = range(1, DAYS + 1)
        self.jp = max(days, key=lambda j: self.ref[j])
        self.jt = min(days, key=lambda j: self.ref[j])
        self.l1 = (self.jp - self.jt) % P_YEAR

    def local(self, j: int) -> float:
        return self.ref[j] + self.off[j]

    @property
    def dst_gap(self) -> int:
        """Minutes the clock shifts between the min day and the max day.

        Between a fixed time and a curve, max and min must be at least this
        far apart: closer, the clock change would turn the curve upside down
        in solar time and push it under the min in winter.
        """
        return max(0, self.off[self.jp] - self.off[self.jt])


def _frac(sun: SunYear, j: float) -> tuple[bool, float]:
    """Which half day *j* is on (rising toward the max day or not), and how far."""
    k = (j - sun.jt) % P_YEAR
    if k < sun.l1:
        return True, k / sun.l1
    return False, (P_YEAR - k) / (P_YEAR - sun.l1)


# ── The curve ─────────────────────────────────────────────────────────────────

@dataclass
class Curve:
    """Local minutes of the schedule for days 1..365 (index 0 unused), or the
    reason there is none, plus the crossings that had to be ignored."""

    points: list[float] | None
    error: str | None = None
    ignored: dict[str, str] = field(default_factory=dict)   # "spring"/"autumn" → reason


def build_curve(sun: SunYear, s: Settings) -> Curve:
    """The schedule for every day of the year."""
    if s.fixed:
        pu = pd = 1.0
        hi_u = lo_u = 0.0
    else:
        if s.lo > s.hi:
            return Curve(points=None, error="schedule_min_after_max")
        hi_u = s.hi - sun.off[sun.jp]
        lo_u = s.lo - sun.off[sun.jt]
        pu = pd = 1.0
        used: set[bool] = set()
        ignored: dict[str, str] = {}
        for name, day in (("spring", s.cross_spring), ("autumn", s.cross_autumn)):
            if day is None:
                continue
            up, f = _frac(sun, day)
            q = (sun.ref[day] - lo_u) / (hi_u - lo_u) if hi_u != lo_u else -1
            if not 0 < q < 1:
                ignored[name] = "out_of_range"   # the sun is not between min and max that day
                continue
            if up in used:
                ignored[name] = "same_half"      # both crossings on the same half
                continue
            used.add(up)
            try:
                p = math.log(math.acos(1 - 2 * q) / math.pi) / math.log(f)
            except (ValueError, ZeroDivisionError):
                p = float("nan")
            if not 0.15 < p < 6:
                ignored[name] = "too_steep"      # would bend the curve too much
                continue
            if up:
                pu = p
            else:
                pd = p

    points: list[float] = [0.0] * (DAYS + 1)
    for j in range(1, DAYS + 1):
        if s.fixed:
            m = s.hi - sun.off[j]
        else:
            up, f = _frac(sun, j)
            m = lo_u + (hi_u - lo_u) * (1 - math.cos(math.pi * f ** (pu if up else pd))) / 2
        if s.floor is not None:
            m = max(m, s.floor - sun.off[j])
        if s.ceiling is not None:
            m = min(m, s.ceiling - sun.off[j])
        points[j] = m + sun.off[j]
    return Curve(points=points, ignored={} if s.fixed else ignored)


def day_of_year(day: date) -> int:
    return min(day.timetuple().tm_yday, DAYS)


def event_at(curve: Curve, day: date, tz: tzinfo) -> datetime | None:
    """The schedule on *day*, as an aware datetime in *tz*."""
    if curve.points is None:
        return None
    minutes = int(round(curve.points[day_of_year(day)]))
    midnight = datetime(day.year, day.month, day.day, tzinfo=tz)
    return midnight + timedelta(minutes=minutes)


def missed_event(
    now: datetime, opening: datetime | None, closing: datetime | None,
    last_applied: dict[str, str], today: date,
) -> str | None:
    """The one schedule to catch up at startup, if any.

    Only the latest event of the day that has passed, only when it has not
    run today, and only when the schedule has run at least once before (a
    first start, or the first start of a new install, catches nothing up:
    no cover should move just because the integration was installed late in
    the evening).
    """
    if not last_applied:
        return None
    stamp = today.isoformat()
    if closing is not None and now >= closing:
        return "evening" if last_applied.get("evening") != stamp else None
    if opening is not None and now >= opening:
        return "morning" if last_applied.get("morning") != stamp else None
    return None


# ── Home Assistant side ───────────────────────────────────────────────────────

def ha_sun_year(sun_event_at: Any, year: int, event: str, tz: tzinfo) -> SunYear | None:
    """The sun for every day of *year*, from a callable (event, date) → aware
    UTC datetime, typically homeassistant.helpers.sun.get_astral_event_date.

    None where the sun does not rise or set on some day (polar latitudes):
    no curve can follow it there.
    """
    ref: list[float] = [0.0] * (DAYS + 1)
    off: list[int] = [0] * (DAYS + 1)
    start = date(year, 1, 1)
    for j in range(1, DAYS + 1):
        day = start + timedelta(days=j - 1)
        when = sun_event_at(event, day)
        if when is None:
            return None
        utc_midnight = datetime(day.year, day.month, day.day, tzinfo=when.tzinfo)
        ref[j] = (when - utc_midnight).total_seconds() / 60
        noon = datetime(day.year, day.month, day.day, 12, tzinfo=tz)
        off[j] = int(noon.utcoffset().total_seconds() // 60)
    return SunYear(ref=ref, off=off)
