import logging
import aiohttp
from datetime import timedelta
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from .const import DOMAIN, CONF_SECRET, CONF_DEVICE_ID

_LOGGER = logging.getLogger(__name__)

API_MESSAGES_URL = "https://api.pushover.net/1/messages.json"
DELETE_MESSAGES_URL = "https://api.pushover.net/1/devices/{}/update_highest_message.json"
SCAN_INTERVAL = timedelta(seconds=25)  # Set to poll every 25 seconds

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the Pushover sensor."""
    secret = entry.data.get(CONF_SECRET)
    device_id = entry.data.get(CONF_DEVICE_ID)

    if not secret or not device_id:
        _LOGGER.error("Missing secret or device ID. Integration not set up correctly.")
        return

    coordinator = PushoverDataUpdateCoordinator(hass, secret, device_id)

    # Schedule the first data refresh after setting up entities
    await coordinator.async_refresh()

    async_add_entities([PushoverLastMessageSensor(coordinator)], True)

class PushoverDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Pushover data from API."""

    def __init__(self, hass, secret, device_id):
        """Initialize the data update coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Pushover Messages",
            update_interval=SCAN_INTERVAL,
        )
        self.secret = secret
        self.device_id = device_id

    async def _async_update_data(self):
        """Fetch data from Pushover API and delete after processing."""
        async with aiohttp.ClientSession() as session:
            try:
                response = await session.get(
                    API_MESSAGES_URL,
                    params={"secret": self.secret, "device_id": self.device_id}
                )
                if response.status == 200:
                    data = await response.json()
                    _LOGGER.debug("Full Pushover response: %s", data)

                    messages = data.get("messages", [])

                    if not messages:
                        # _LOGGER.warning("No new messages found from Pushover.")
                        return None

                    # Get the latest message by sorting messages based on 'date'
                    latest_message = max(messages, key=lambda msg: msg.get("date", 0))
                    _LOGGER.info("Latest Pushover message received: %s", latest_message["message"])

                    # Delete messages after processing
                    await self._delete_messages(session, latest_message["id"])

                    return latest_message

                else:
                    error_text = await response.text()
                    _LOGGER.error("Error fetching messages: %s - %s", response.status, error_text)
            except aiohttp.ClientError as e:
                _LOGGER.error("Error connecting to Pushover: %s", str(e))
        return None

    async def _delete_messages(self, session, highest_message_id):
        """Delete messages from the Pushover server."""
        delete_url = DELETE_MESSAGES_URL.format(self.device_id)
        payload = {"secret": self.secret, "message": highest_message_id}

        try:
            response = await session.post(delete_url, data=payload)
            if response.status == 200:
                delete_response = await response.json()
                if delete_response.get("status") == 1:
                    _LOGGER.info("Successfully deleted messages up to ID %s", highest_message_id)
                else:
                    _LOGGER.error("Failed to delete messages: %s", delete_response)
            else:
                _LOGGER.error("Error deleting messages: %s", response.status)
        except aiohttp.ClientError as e:
            _LOGGER.error("Error connecting to Pushover for deletion: %s", str(e))

class PushoverLastMessageSensor(CoordinatorEntity, Entity):
    """Representation of the latest Pushover message sensor."""

    def __init__(self, coordinator):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_name = "Latest Pushover Message"
        self._attr_unique_id = f"pushover_{coordinator.device_id}"
        self._last_message = None  # Store last valid message

    @property
    def state(self):
        """Return the message content of the most recent Pushover message."""
        latest_message = self.coordinator.data
        if latest_message:
            self._last_message = latest_message.get("message", self._last_message)
        return self._last_message or "No messages received yet"

    @property
    def extra_state_attributes(self):
        """Return additional attributes of the latest message."""
        latest_message = self.coordinator.data
        if latest_message:
            return {
                "title": latest_message.get("title", "No title"),
                "date": latest_message.get("date"),
                "priority": latest_message.get("priority"),
                "app": latest_message.get("app"),
                "id": latest_message.get("id"),
                "umid": latest_message.get("umid"),
            }
        return {}

    async def async_update(self):
        """Manually trigger an update."""
        await self.coordinator.async_request_refresh()
        _LOGGER.info("Pushover sensor manually updated.")
