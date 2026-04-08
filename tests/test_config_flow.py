import pytest

@pytest.mark.asyncio
async def test_config_flow_user_step(hass):
    from custom_components.cover_extender.config_flow import CoverExtenderConfigFlow

    flow = CoverExtenderConfigFlow()
    flow.hass = hass

    result = await flow.async_step_user()

    assert result["type"] == "form"