"""Services for the SwitchBot Cloud integration."""

import base64
from pathlib import Path
from typing import Any

from switchbot_api.commands import ArtFrameCommands
import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv, device_registry as dr

from .const import DOMAIN

SERVICE_UPLOAD_IMAGE = "upload_image"

ATTR_DEVICE_ID = "device_id"
ATTR_IMAGE_URL = "image_url"
ATTR_IMAGE_PATH = "image_path"

_UPLOAD_IMAGE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Exclusive(ATTR_IMAGE_URL, "image_source"): cv.url,
        vol.Exclusive(ATTR_IMAGE_PATH, "image_source"): cv.string,
    }
)

_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
}


def _async_get_api_device_id_for_ha_device_id(
    hass: HomeAssistant, ha_device_id: str
) -> tuple[Any, str]:
    """Return the config entry and API device_id for a HA device registry ID."""
    from . import SwitchbotCloudConfigEntry

    device_registry = dr.async_get(hass)
    if not (device_entry := device_registry.async_get(ha_device_id)):
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="device_not_found",
            translation_placeholders={"device_id": ha_device_id},
        )

    entries = [
        hass.config_entries.async_get_entry(entry_id)
        for entry_id in device_entry.config_entries
    ]
    switchbot_entries = [
        entry
        for entry in entries
        if entry is not None
        and entry.domain == DOMAIN
        and entry.state is ConfigEntryState.LOADED
    ]
    if not switchbot_entries:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="device_not_found",
            translation_placeholders={"device_id": ha_device_id},
        )

    entry: SwitchbotCloudConfigEntry = switchbot_entries[0]

    # Extract API device_id from device identifiers
    api_device_id = None
    for identifier in device_entry.identifiers:
        if identifier[0] == DOMAIN:
            api_device_id = identifier[1]
            break

    if api_device_id is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="device_not_found",
            translation_placeholders={"device_id": ha_device_id},
        )

    # Verify it's an AI Art Frame
    data = entry.runtime_data
    for device, _coordinator in data.devices.images:
        if device.device_id == api_device_id:
            if device.device_type != "AI Art Frame":
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="invalid_device",
                    translation_placeholders={"device_id": ha_device_id},
                )
            return entry, api_device_id

    for device, _coordinator in data.devices.buttons:
        if device.device_id == api_device_id:
            if device.device_type != "AI Art Frame":
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="invalid_device",
                    translation_placeholders={"device_id": ha_device_id},
                )
            return entry, api_device_id

    raise ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key="invalid_device",
        translation_placeholders={"device_id": ha_device_id},
    )


def _encode_image_to_base64(image_path: str) -> str:
    """Read an image file and encode it as a base64 data URI."""
    path = Path(image_path)
    if not path.exists():
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="file_not_found",
            translation_placeholders={"image_path": image_path},
        )

    mime_type = _MIME_TYPES.get(path.suffix.lower(), "image/jpeg")
    image_bytes = path.read_bytes()
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


async def async_upload_image(call: ServiceCall) -> None:
    """Upload an image to a SwitchBot AI Art Frame."""
    ha_device_id: str = call.data[ATTR_DEVICE_ID]
    image_url = call.data.get(ATTR_IMAGE_URL)
    image_path = call.data.get(ATTR_IMAGE_PATH)

    entry, api_device_id = _async_get_api_device_id_for_ha_device_id(
        call.hass, ha_device_id
    )
    api = entry.runtime_data.api

    if image_url is not None:
        parameters: dict[str, Any] = {"imageUrl": image_url}
    elif image_path is not None:
        image_base64 = await call.hass.async_add_executor_job(
            _encode_image_to_base64, image_path
        )
        parameters = {"imageBase64": image_base64}
    else:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="no_image_source",
        )

    try:
        await api.send_command(
            api_device_id,
            ArtFrameCommands.UPLOAD.value,
            "command",
            parameters,
        )
    except Exception as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="upload_failed",
            translation_placeholders={"error": str(err)},
        ) from err


def async_setup_services(hass: HomeAssistant) -> None:
    """Set up the services for the SwitchBot Cloud integration."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_UPLOAD_IMAGE,
        async_upload_image,
        schema=_UPLOAD_IMAGE_SCHEMA,
    )


def async_unload_services(hass: HomeAssistant) -> None:
    """Unload the services for the SwitchBot Cloud integration."""
    hass.services.async_remove(DOMAIN, SERVICE_UPLOAD_IMAGE)
