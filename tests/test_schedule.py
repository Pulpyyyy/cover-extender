"""Tests for the morning / evening schedule curve (schedule.py, pure)."""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone

import pytest

from custom_components.cover_extender import schedule as sch
from custom_components.cover_extender.schedule import Settings, SunYear, build_curve

YEAR = 2026
SUMMER = range(88, 298)   # roughly the European summer time days


def _paris_sunset() -> SunYear:
    """A Paris-like sunset: 15:55 UTC in December, 19:58 UTC in June, and the
    clock one hour ahead of UTC in winter, two in summer."""
    ref = [0.0] + [
        1077 + 122 * math.cos(2 * math.pi * (j - 172) / sch.P_YEAR) for j in range(1, sch.DAYS + 1)
    ]
    off = [0] + [120 if j in SUMMER else 60 for j in range(1, sch.DAYS + 1)]
    return SunYear(ref=ref, off=off)


SUN = _paris_sunset()


def test_sun_year_extremes():
    assert SUN.jp == 172 and SUN.jt in (354, 355)
    assert SUN.dst_gap == 60   # summer max day vs winter min day


def test_fixed_time_is_the_same_legal_time_every_day():
    curve = build_curve(SUN, Settings(hi=20 * 60, lo=20 * 60))
    assert curve.error is None
    assert all(abs(curve.points[j] - 1200) < 1e-9 for j in range(1, sch.DAYS + 1))


def test_curve_reaches_max_and_min_on_the_extreme_days():
    s = Settings(hi=22 * 60, lo=16 * 60 + 30)
    curve = build_curve(SUN, s)
    assert abs(curve.points[SUN.jp] - s.hi) < 1e-6
    assert abs(curve.points[SUN.jt] - s.lo) < 1e-6
    # Everything in between stays between them.
    assert all(s.lo - 1 <= curve.points[j] <= s.hi + 1 for j in range(1, sch.DAYS + 1))


def test_crossing_lands_on_the_sunset_that_day():
    day = 76   # 17 March
    s = Settings(hi=22 * 60 + 5, lo=16 * 60 + 28, cross_spring=day)
    curve = build_curve(SUN, s)
    assert curve.ignored == {}
    assert abs(curve.points[day] - SUN.local(day)) < 1


def test_crossings_on_the_same_half_keep_only_the_first():
    s = Settings(hi=22 * 60, lo=16 * 60 + 30, cross_spring=70, cross_autumn=80)
    assert build_curve(SUN, s).ignored == {"autumn": "same_half"}


def test_crossing_where_the_sun_is_outside_min_max_is_ignored():
    # Min and max both before the earliest sunset: the curve cannot cross it.
    s = Settings(hi=15 * 60, lo=14 * 60, cross_spring=76)
    assert build_curve(SUN, s).ignored == {"spring": "out_of_range"}


def test_floor_and_ceiling_clamp_in_legal_time():
    s = Settings(hi=22 * 60, lo=16 * 60, floor=17 * 60, ceiling=21 * 60 + 30)
    curve = build_curve(SUN, s)
    assert min(curve.points[1:]) >= 17 * 60 - 1e-9
    assert max(curve.points[1:]) <= 21 * 60 + 30 + 1e-9


def test_min_after_max_has_no_curve():
    curve = build_curve(SUN, Settings(hi=16 * 60, lo=20 * 60))
    assert curve.points is None and curve.error == "schedule_min_after_max"


@pytest.mark.parametrize("cfg, error", [
    ({"type": "fixed", "time": "20:30"}, None),
    ({"type": "curve", "max": "22:05", "min": "16:28", "cross_spring": "03-17", "cross_autumn": None}, None),
    ({"type": "curve", "max": "16:00", "min": "20:00"}, "schedule_min_after_max"),
    ({"type": "fixed", "time": "25:00"}, "schedule_invalid"),
    ({"type": "curve", "max": "22:00", "min": "16:00", "cross_spring": "13-40"}, "schedule_invalid"),
    ({"type": "fixed", "time": "20:00", "not_before": "21:00", "not_after": "20:00"}, "schedule_floor_after_ceiling"),
    ({"type": "weekly"}, "schedule_invalid"),
    ("20:00", "schedule_invalid"),
])
def test_validate_settings(cfg, error):
    assert sch.validate_settings(cfg) == error


def test_parse_settings_round_trip():
    s = sch.parse_settings({
        "type": "curve", "max": "22:05", "min": "16:28",
        "cross_spring": "03-17", "cross_autumn": "11-22", "not_before": "07:15", "not_after": None,
    }, YEAR)
    assert (s.hi, s.lo, s.floor, s.ceiling) == (1325, 988, 435, None)
    assert sch.day_to_mmdd(s.cross_spring, YEAR) == "03-17"
    assert sch.day_to_mmdd(s.cross_autumn, YEAR) == "11-22"


def test_event_at_gives_an_aware_local_datetime():
    curve = build_curve(SUN, Settings(hi=20 * 60 + 30, lo=20 * 60 + 30))
    tz = timezone(timedelta(hours=2))
    when = sch.event_at(curve, date(YEAR, 7, 1), tz)
    assert when == datetime(YEAR, 7, 1, 20, 30, tzinfo=tz)


# ── Catching up at startup ────────────────────────────────────────────────────

TZ = timezone(timedelta(hours=2))
TODAY = date(YEAR, 10, 6)
OPENING = datetime(YEAR, 10, 6, 7, 45, tzinfo=TZ)
CLOSING = datetime(YEAR, 10, 6, 20, 5, tzinfo=TZ)


@pytest.mark.parametrize("now, last, expected", [
    # Down through the evening closing: catch it up.
    (datetime(YEAR, 10, 6, 21, 0, tzinfo=TZ), {"morning": "2026-10-06", "evening": "2026-10-05"}, "evening"),
    # Evening already applied today: nothing.
    (datetime(YEAR, 10, 6, 21, 0, tzinfo=TZ), {"morning": "2026-10-06", "evening": "2026-10-06"}, None),
    # Down through the morning only: catch the morning up.
    (datetime(YEAR, 10, 6, 9, 0, tzinfo=TZ), {"morning": "2026-10-05", "evening": "2026-10-05"}, "morning"),
    # Both missed: only the latest one.
    (datetime(YEAR, 10, 6, 22, 0, tzinfo=TZ), {"morning": "2026-10-05", "evening": "2026-10-05"}, "evening"),
    # Before the morning: nothing to catch up.
    (datetime(YEAR, 10, 6, 6, 0, tzinfo=TZ), {"morning": "2026-10-05", "evening": "2026-10-05"}, None),
    # Never ran (fresh install): nothing, whatever the time.
    (datetime(YEAR, 10, 6, 22, 0, tzinfo=TZ), {}, None),
])
def test_missed_event(now, last, expected):
    assert sch.missed_event(now, OPENING, CLOSING, last, TODAY) == expected


# ── The Home Assistant side ───────────────────────────────────────────────────

def test_ha_sun_year_reads_the_sun_day_by_day():
    def sunset(event, day):
        assert event == "sunset"
        return datetime(day.year, day.month, day.day, 18, 0, tzinfo=timezone.utc)

    sun = sch.ha_sun_year(sunset, YEAR, "sunset", timezone(timedelta(hours=1)))
    assert sun.ref[1] == 18 * 60 and sun.ref[sch.DAYS] == 18 * 60
    assert sun.off[100] == 60


def test_ha_sun_year_gives_up_where_the_sun_does_not_set():
    assert sch.ha_sun_year(lambda e, d: None, YEAR, "sunset", timezone.utc) is None


@pytest.mark.parametrize("kind", sch.KINDS)
def test_defaults_are_valid_and_build_a_curve(kind):
    assert sch.validate_settings(sch.DEFAULTS[kind]) is None
    curve = build_curve(SUN, sch.parse_settings(sch.DEFAULTS[kind], YEAR))
    assert curve.error is None and curve.points is not None


@pytest.mark.parametrize("value, expected", [
    ("Night", "Night"),
    ("", None),
    (None, None),
    ({"position": 0}, {"position": 0, "force": False}),
    ({"position": 100, "force": True}, {"position": 100, "force": True}),
])
def test_parse_action(value, expected):
    assert sch.parse_action(value) == expected


@pytest.mark.parametrize("position", [101, -5, "40", None, False])
def test_parse_action_refuses_a_position_it_cannot_read(position):
    with pytest.raises(ValueError):
        sch.parse_action({"position": position})
