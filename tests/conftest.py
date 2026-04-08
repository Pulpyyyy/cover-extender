from types import SimpleNamespace
from homeassistant.core import HomeAssistant

def make_hass(
    hass: HomeAssistant,
    *,
    sun_azi: float | None = None,
    sun_ele: float | None = None,
    sun_ok: bool = True,
    cover_pos: int | None = None,
    minutes_since_move: int | None = None,
):
    """Factory used by test_shade.py to prepare a hass with sun + cover state."""

    # ── Fake sun entity ──────────────────────────────────────
    if sun_ok:
        hass.states.async_set(
            "sun.sun",
            "above_horizon",
            {
                "azimuth": sun_azi,
                "elevation": sun_ele,
            },
        )
    else:
        hass.states.async_set("sun.sun", "unavailable")

    # ── Fake cover entity ────────────────────────────────────
    if cover_pos is not None:
        attrs = {"current_position": cover_pos}
        if minutes_since_move is not None:
            attrs["last_changed"] = hass.loop.time() - (minutes_since_move * 60)

        hass.states.async_set("cover.test", "open", attrs)

    return hass
