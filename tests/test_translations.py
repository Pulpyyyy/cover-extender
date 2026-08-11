"""Validate translation files against the real hassfest schema.

Loads the vendored snapshot of script/hassfest/translations.py (see
tests/hassfest_translations.py) and runs its gen_strings_schema against
strings.json and translations/fr.json - the same validation the hassfest
CI action applies. Catching schema violations here avoids discovering
them one by one in CI.

Works in both test environments (see conftest.py): with the real
homeassistant package (Linux CI) the real config_validation helpers are
used; with the stubs (local Windows) faithful re-implementations of the
few cv functions the schema needs are attached to the stub module.
"""
from __future__ import annotations

import json
import re
import types
from pathlib import Path

import pytest
import voluptuous as vol
from voluptuous.humanize import humanize_error

_REPO_ROOT = Path(__file__).parent.parent
_COMPONENT = _REPO_ROOT / "custom_components" / "cover_extender"
_VENDORED = Path(__file__).parent / "hassfest_translations.py"

_TRANSLATION_FILES = ("strings.json", "translations/fr.json")


def _ensure_cv_functions() -> None:
    """Attach the cv helpers the hassfest schema needs to the stub module.

    No-op when the real homeassistant package is installed.
    """
    import homeassistant.helpers.config_validation as cv

    if hasattr(cv, "string_with_no_html"):
        return

    html_re = re.compile(r"<[a-z][\s\S]*>", re.IGNORECASE)
    slug_re = re.compile(r"^[a-z0-9_]+$")

    def string_with_no_html(value):
        if not isinstance(value, str):
            raise vol.Invalid("expected string")
        if html_re.search(value):
            raise vol.Invalid("the string should not contain HTML")
        return value

    def slug(value):
        if not isinstance(value, str) or not slug_re.match(value):
            raise vol.Invalid(f"invalid slug {value}")
        return value

    def schema_with_slug_keys(value_schema, *, slug_validator=slug):
        schema = vol.Schema({str: value_schema})

        def verify(value):
            if not isinstance(value, dict):
                raise vol.Invalid("expected dictionary")
            for key in value:
                slug_validator(key)
            return schema(value)

        return verify

    def has_at_least_one_key(*keys):
        def validate(obj):
            if not isinstance(obj, dict):
                raise vol.Invalid("expected dictionary")
            if not any(k in obj for k in keys):
                raise vol.Invalid(f"must contain at least one of {', '.join(keys)}")
            return obj

        return validate

    cv.string_with_no_html = string_with_no_html
    cv.slug = slug
    cv.underscore_slug = slug
    cv.schema_with_slug_keys = schema_with_slug_keys
    cv.has_at_least_one_key = has_at_least_one_key


def _load_hassfest_translations() -> types.ModuleType:
    """Load the vendored validator with HA-internal imports patched out."""
    _ensure_cv_functions()

    source = _VENDORED.read_text(encoding="utf-8")
    source = source.replace(
        "from homeassistant.helpers.issue_registry import FRONTEND_HANDLED_ISSUES",
        "try:\n"
        "    from homeassistant.helpers.issue_registry import FRONTEND_HANDLED_ISSUES\n"
        "except ImportError:\n"
        "    FRONTEND_HANDLED_ISSUES = {}",
    )
    # upload is only used by validate(), which these tests never call
    source = source.replace("from script.translations import upload", "upload = None")
    source = source.replace(
        "from .model import Config, Integration, IntegrationType",
        "class IntegrationType:\n"
        "    HELPER = 'helper'\n"
        "\n"
        "\n"
        "class Config:\n"
        "    pass\n"
        "\n"
        "\n"
        "class Integration:\n"
        "    pass",
    )
    module = types.ModuleType("hassfest_translations_vendored")
    exec(compile(source, str(_VENDORED), "exec"), module.__dict__)
    return module


@pytest.fixture(scope="module")
def strings_schema():
    module = _load_hassfest_translations()
    config = module.Config()
    config.specific_integrations = [_COMPONENT]
    integration = module.Integration()
    integration.domain = "cover_extender"
    integration.name = "Cover Extender"
    integration.integration_type = "integration"
    integration.core = False  # custom integration, like in CI
    return module.gen_strings_schema(config, integration)


@pytest.mark.parametrize("filename", _TRANSLATION_FILES)
def test_translation_file_passes_hassfest_schema(strings_schema, filename):
    data = json.loads((_COMPONENT / filename).read_text(encoding="utf-8"))
    try:
        strings_schema(data)
    except vol.Invalid as err:
        pytest.fail(f"{filename}: {humanize_error(data, err)}")


def test_translation_files_have_same_keys():
    """fr.json must translate exactly the keys defined in strings.json."""

    def key_paths(node: dict, prefix: str = "") -> set[str]:
        paths: set[str] = set()
        for key, value in node.items():
            path = f"{prefix}/{key}"
            paths.add(path)
            if isinstance(value, dict):
                paths |= key_paths(value, path)
        return paths

    strings, fr = (
        json.loads((_COMPONENT / name).read_text(encoding="utf-8"))
        for name in _TRANSLATION_FILES
    )
    missing_in_fr = key_paths(strings) - key_paths(fr)
    extra_in_fr = key_paths(fr) - key_paths(strings)
    assert not missing_in_fr, f"keys missing in fr.json: {sorted(missing_in_fr)}"
    assert not extra_in_fr, f"keys in fr.json absent from strings.json: {sorted(extra_in_fr)}"


# Top-level keys accepted by hassfest's icons schema (script/hassfest/icons.py).
# Notably absent: "config_subentries" — the frontend has no lookup for subentry
# section icons either, so they never render. An icons.json holding them fails
# hassfest outright, which is what happened between 2026-07-21 and 2026-08-12.
# This integration is subentries-only, leaving no valid content for the file,
# so it ships none; this test guards against it coming back.
_ICONS_ALLOWED_KEYS = frozenset({
    "conditions", "config", "entity", "entity_component",
    "issues", "options", "services", "triggers",
})


def test_icons_file_has_no_unsupported_keys():
    """If an icons.json reappears, keep it within the hassfest schema."""
    icons_file = _COMPONENT / "icons.json"
    if not icons_file.exists():
        pytest.skip("no icons.json shipped")
    unsupported = set(json.loads(icons_file.read_text(encoding="utf-8")))
    unsupported -= _ICONS_ALLOWED_KEYS
    assert not unsupported, (
        f"icons.json holds keys hassfest rejects: {sorted(unsupported)}. "
        f"Allowed: {sorted(_ICONS_ALLOWED_KEYS)}"
    )
