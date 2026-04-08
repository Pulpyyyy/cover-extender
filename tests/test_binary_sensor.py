import pytest

@pytest.mark.asyncio
async def test_binary_sensor_async_setup_entry(hass, mock_config_entry):
    from custom_components.cover_extender.binary_sensor import async_setup_entry

    entities = []

    def async_add_entities(new_entities):
        entities.extend(new_entities)

    result = await async_setup_entry(hass, mock_config_entry, async_add_entities)

    assert result is True
    assert entities  # au moins une entité créée
