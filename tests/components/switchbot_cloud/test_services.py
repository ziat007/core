"""Test for the switchbot_cloud upload_image service."""

from pathlib import Path
from unittest.mock import patch

import pytest
from switchbot_api import Device
from switchbot_api.commands import ArtFrameCommands

from homeassistant.components.switchbot_cloud import DOMAIN
from homeassistant.components.switchbot_cloud.const import ENTRY_TITLE
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_API_KEY, CONF_API_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr

from tests.common import MockConfigEntry


@pytest.fixture
def art_frame_device() -> Device:
    """Return a mock AI Art Frame device."""
    return Device(
        version="V1.0",
        deviceId="AA:BB:CC:DD:EE:FF",
        deviceName="AI Art Frame 1",
        deviceType="AI Art Frame",
        hubDeviceId="test-hub-id",
    )


async def _setup_art_frame(
    hass: HomeAssistant, device: Device
) -> tuple[MockConfigEntry, str]:
    """Set up the integration with an AI Art Frame and return (entry, ha_device_id)."""
    with (
        patch.object(
            "homeassistant.components.switchbot_cloud.SwitchBotAPI",
            "list_devices",
            return_value=[device],
        ),
        patch.object(
            "homeassistant.components.switchbot_cloud.SwitchBotAPI",
            "get_status",
            return_value={"deviceType": "AI Art Frame"},
        ),
        patch.object(
            "homeassistant.components.switchbot_cloud.SwitchBotAPI",
            "setup_webhook",
            return_value={"statusCode": 100, "body": {}},
        ),
        patch.object(
            "homeassistant.components.switchbot_cloud.SwitchBotAPI",
            "get_webook_configuration",
            return_value={"statusCode": 100, "body": {}},
        ),
    ):
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_API_TOKEN: "test-token", CONF_API_KEY: "test-api-key"},
            entry_id="test-entry-id",
            unique_id="test-unique-id",
            title=ENTRY_TITLE,
        )
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED

    device_registry = dr.async_get(hass)
    devices = dr.async_entries_for_config_entry(device_registry, entry.entry_id)
    ha_device_id = devices[0].id

    return entry, ha_device_id


async def test_upload_image_with_url(
    hass: HomeAssistant,
    art_frame_device: Device,
) -> None:
    """Test uploading an image via URL."""
    entry, ha_device_id = await _setup_art_frame(hass, art_frame_device)

    with patch.object(
        "homeassistant.components.switchbot_cloud.SwitchBotAPI",
        "send_command",
    ) as mock_send_command:
        await hass.services.async_call(
            DOMAIN,
            "upload_image",
            {
                "device_id": ha_device_id,
                "image_url": "https://example.com/image.png",
            },
            blocking=True,
        )
        mock_send_command.assert_called_once_with(
            "AA:BB:CC:DD:EE:FF",
            ArtFrameCommands.UPLOAD.value,
            "command",
            {"imageUrl": "https://example.com/image.png"},
        )


async def test_upload_image_with_local_file(
    hass: HomeAssistant,
    art_frame_device: Device,
    tmp_path: Path,
) -> None:
    """Test uploading an image from a local file."""
    entry, ha_device_id = await _setup_art_frame(hass, art_frame_device)

    # Create a test image file
    test_image = tmp_path / "test.png"
    test_image.write_bytes(b"\x89PNG\r\n\x1a\nfake image data")

    with patch.object(
        "homeassistant.components.switchbot_cloud.SwitchBotAPI",
        "send_command",
    ) as mock_send_command:
        await hass.services.async_call(
            DOMAIN,
            "upload_image",
            {
                "device_id": ha_device_id,
                "image_path": str(test_image),
            },
            blocking=True,
        )
        mock_send_command.assert_called_once()
        call_args = mock_send_command.call_args
        assert call_args[0][0] == "AA:BB:CC:DD:EE:FF"
        assert call_args[0][1] == ArtFrameCommands.UPLOAD.value
        assert call_args[0][2] == "command"
        parameters = call_args[0][3]
        assert "imageBase64" in parameters
        assert parameters["imageBase64"].startswith("data:image/png;base64,")


async def test_upload_image_device_not_found(
    hass: HomeAssistant,
    art_frame_device: Device,
) -> None:
    """Test error when device is not found."""
    await _setup_art_frame(hass, art_frame_device)

    with pytest.raises(ServiceValidationError, match="not found"):
        await hass.services.async_call(
            DOMAIN,
            "upload_image",
            {
                "device_id": "non-existent-device-id",
                "image_url": "https://example.com/image.png",
            },
            blocking=True,
        )


async def test_upload_image_no_source(
    hass: HomeAssistant,
    art_frame_device: Device,
) -> None:
    """Test error when neither image_url nor image_path is provided."""
    entry, ha_device_id = await _setup_art_frame(hass, art_frame_device)

    with pytest.raises(ServiceValidationError, match="image_url or image_path"):
        await hass.services.async_call(
            DOMAIN,
            "upload_image",
            {
                "device_id": ha_device_id,
            },
            blocking=True,
        )


async def test_upload_image_file_not_found(
    hass: HomeAssistant,
    art_frame_device: Device,
) -> None:
    """Test error when local file doesn't exist."""
    entry, ha_device_id = await _setup_art_frame(hass, art_frame_device)

    with pytest.raises(ServiceValidationError, match="not found"):
        await hass.services.async_call(
            DOMAIN,
            "upload_image",
            {
                "device_id": ha_device_id,
                "image_path": "/nonexistent/path/image.png",
            },
            blocking=True,
        )


async def test_upload_image_service_removed_on_unload(
    hass: HomeAssistant,
    art_frame_device: Device,
) -> None:
    """Test that the service is removed when the last entry is unloaded."""
    entry, ha_device_id = await _setup_art_frame(hass, art_frame_device)

    # Service should exist
    assert hass.services.has_service(DOMAIN, "upload_image")

    # Unload the entry
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    # Service should be removed
    assert not hass.services.has_service(DOMAIN, "upload_image")
