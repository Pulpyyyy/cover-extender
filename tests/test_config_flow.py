"""Tests for CoverExtenderConfigFlow."""
from __future__ import annotations

import pytest
import yaml

from custom_components.cover_extender.config_flow import CoverExtenderConfigFlow


class TestConfigFlowUserStep:

    async def _flow(self, hass):
        flow = CoverExtenderConfigFlow()
        flow.hass = hass
        return flow

    async def test_no_input_returns_form(self, hass):
        flow = await self._flow(hass)
        result = await flow.async_step_user()
        assert result["type"] == "form"
        assert result["errors"] == {}

    async def test_file_not_found_error(self, hass):
        flow = await self._flow(hass)
        result = await flow.async_step_user({"source": "/nonexistent/file.yaml"})
        assert result["type"] == "form"
        assert result["errors"]["source"] == "file_not_found"

    async def test_yaml_invalid_error(self, hass, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("[\n", encoding="utf-8")
        flow = await self._flow(hass)
        result = await flow.async_step_user({"source": str(bad)})
        assert result["type"] == "form"
        assert result["errors"]["source"] == "yaml_invalid"

    async def test_no_covers_found_error(self, hass, tmp_path):
        f = tmp_path / "empty.yaml"
        f.write_text(yaml.dump({"not_a_cover": "value"}), encoding="utf-8")
        flow = await self._flow(hass)
        result = await flow.async_step_user({"source": str(f)})
        assert result["type"] == "form"
        assert result["errors"]["source"] == "no_covers_found"

    async def test_valid_config_creates_entry(self, hass, tmp_path):
        f = tmp_path / "covers.yaml"
        f.write_text(yaml.dump({"cover.test": {"modes": {"Day": 40}}}), encoding="utf-8")
        flow = await self._flow(hass)
        result = await flow.async_step_user({"source": str(f)})
        assert result["type"] == "create_entry"
        assert result["title"] == "Cover Extender"
        assert result["data"]["source"] == str(f)

    async def test_import_step_creates_entry(self, hass, tmp_path):
        f = tmp_path / "covers.yaml"
        f.write_text(yaml.dump({"cover.test": {}}), encoding="utf-8")
        flow = await self._flow(hass)
        result = await flow.async_step_import({"source": str(f)})
        assert result["type"] == "create_entry"
