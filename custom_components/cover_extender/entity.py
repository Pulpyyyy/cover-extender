"""Where a cover's helper entities live, and what they are called.

Each helper is attached to the device of the cover it serves, so it shows on
that device's page next to the cover itself. It is linked through
``Entity.device_entry`` rather than ``device_info``: the latter would add this
integration's config entry to a device another integration owns, and
"Cover Extender never takes ownership of your covers" covers their devices too.

A cover without a device (a template cover, a YAML cover without unique_id)
has nowhere to host its helpers; they go to the integration's own hub device
instead, named after the cover so that six "CX lock" can still be told apart.
"""
from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.device import async_entity_id_to_device
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, HUB_IDENTIFIER
from .helpers import HELPER_NAMES, cover_object_id, helper_entity_id


def hub_device_info() -> DeviceInfo:
    """The integration's own device, for helpers that belong to no cover."""
    return DeviceInfo(identifiers={(DOMAIN, HUB_IDENTIFIER)})


def attach_cover_helper(
    entity: Entity, hass: HomeAssistant, cover_entity_id: str, kind: str
) -> None:
    """Set the suggested entity_id, the name and the device of a cover helper.

    Must run before the entity is added: the platform reads the device when it
    registers the entity. The entity_id is only a suggestion; a helper already
    in the registry keeps the id it has there.
    """
    entity.entity_id = helper_entity_id(kind, cover_entity_id)
    if device := async_entity_id_to_device(hass, cover_entity_id):
        entity.device_entry = device
        entity._attr_has_entity_name = True
        entity._attr_name = HELPER_NAMES[kind]
    else:
        entity._attr_device_info = hub_device_info()
        entity._attr_has_entity_name = False
        entity._attr_name = f"{cover_object_id(cover_entity_id)} {HELPER_NAMES[kind]}"
