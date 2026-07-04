"""Test fixtures for cover_extender.

The tested modules (shade, helpers, schemas) are pure logic but import
homeassistant at module level. Home Assistant does not install on Windows
(missing wheels), so when the real package is absent, minimal stubs of the
few HA symbols actually used are injected into sys.modules BEFORE importing
the component. On an environment with homeassistant installed (e.g. Linux
CI), the stubs are skipped and the real modules are used — the tests are
identical in both cases.
"""
from __future__ import annotations

import sys
import types
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Make `custom_components.cover_extender` importable from the repo root,
# WITHOUT executing its __init__.py (it pulls the whole integration:
# coordinator, config_flow, HA config_entries…). The tested submodules
# (shade, helpers, schemas) are imported directly under an empty package.
_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT))

_cc = types.ModuleType("custom_components")
_cc.__path__ = [str(_REPO_ROOT / "custom_components")]
sys.modules.setdefault("custom_components", _cc)

_pkg = types.ModuleType("custom_components.cover_extender")
_pkg.__path__ = [str(_REPO_ROOT / "custom_components" / "cover_extender")]
sys.modules.setdefault("custom_components.cover_extender", _pkg)

try:
    import homeassistant  # noqa: F401
except ImportError:
    import voluptuous as vol

    def _module(name: str) -> types.ModuleType:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
        return mod

    # homeassistant / homeassistant.core
    ha = _module("homeassistant")
    core = _module("homeassistant.core")

    class HomeAssistant:  # minimal type placeholder
        pass

    core.HomeAssistant = HomeAssistant
    core.callback = lambda func: func
    ha.core = core

    # homeassistant.util.dt
    util = _module("homeassistant.util")
    dt = _module("homeassistant.util.dt")
    dt.utcnow = lambda: datetime.now(timezone.utc)
    util.dt = dt
    ha.util = util

    # homeassistant.helpers.{entity_registry, translation, config_validation}
    helpers_mod = _module("homeassistant.helpers")

    er = _module("homeassistant.helpers.entity_registry")
    er.EVENT_ENTITY_REGISTRY_UPDATED = "entity_registry_updated"
    er.async_get = lambda hass: getattr(hass, "entity_registry", None)

    translation = _module("homeassistant.helpers.translation")

    async def _async_get_translations(hass, language, category, integrations):
        return {}

    translation.async_get_translations = _async_get_translations

    cv = _module("homeassistant.helpers.config_validation")

    def _entity_id(value):
        if isinstance(value, str) and "." in value:
            return value.lower()
        raise vol.Invalid(f"invalid entity id: {value}")

    cv.entity_id = _entity_id
    cv.entity_ids = lambda v: [_entity_id(x) for x in ([v] if isinstance(v, str) else v)]
    cv.boolean = vol.Boolean()
    cv.string = vol.Coerce(str)
    cv.ensure_list = lambda v: v if isinstance(v, list) else [v]

    helpers_mod.entity_registry = er
    helpers_mod.translation = translation
    helpers_mod.config_validation = cv
    ha.helpers = helpers_mod


# ── Lightweight fakes shared by the tests ─────────────────────────────────────

class FakeState:
    """Minimal stand-in for homeassistant.core.State."""

    def __init__(self, state: str, attributes: dict | None = None):
        self.state = state
        self.attributes = attributes or {}


class FakeStates:
    def __init__(self):
        self._states: dict[str, FakeState] = {}

    def set(self, entity_id: str, state: str, attributes: dict | None = None):
        self._states[entity_id] = FakeState(state, attributes)

    def get(self, entity_id: str):
        return self._states.get(entity_id)

    def is_state(self, entity_id: str, state: str) -> bool:
        st = self._states.get(entity_id)
        return st is not None and st.state == state


class FakeRegistryEntry:
    def __init__(self, entity_id: str, uid: str, platform: str = "test"):
        self.entity_id = entity_id
        self.id = uid
        self.platform = platform


class FakeEntityRegistry:
    """Registry fake resolving by entity_id or immutable id (like HA's)."""

    def __init__(self):
        self._by_entity_id: dict[str, FakeRegistryEntry] = {}
        self._by_uid: dict[str, FakeRegistryEntry] = {}
        # (domain, platform, unique_id) -> entity_id
        self._unique_ids: dict[tuple[str, str, str], str] = {}

    def register(self, entity_id: str, uid: str, platform: str = "test") -> FakeRegistryEntry:
        entry = FakeRegistryEntry(entity_id, uid, platform)
        self._by_entity_id[entity_id] = entry
        self._by_uid[uid] = entry
        return entry

    def register_unique_id(self, domain: str, platform: str, unique_id: str, entity_id: str):
        self._unique_ids[(domain, platform, unique_id)] = entity_id

    def async_get(self, entity_id_or_uuid: str):
        return self._by_entity_id.get(entity_id_or_uuid) or self._by_uid.get(entity_id_or_uuid)

    def async_get_entity_id(self, domain: str, platform: str, unique_id: str):
        return self._unique_ids.get((domain, platform, unique_id))


class FakeHass:
    def __init__(self):
        self.states = FakeStates()
        self.data: dict = {}
        self.entity_registry = FakeEntityRegistry()


@pytest.fixture
def hass():
    return FakeHass()
