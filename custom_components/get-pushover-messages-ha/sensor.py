import logging
import aiohttp
import asyncio
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
SCAN_INTERVAL = timedelta(seconds=8)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the Pushover sensor."""
    secret = entry.data.get(CONF_SECRET)
    device_id = entry.data.get(CONF_DEVICE_ID)

    if not secret or not device_id:
        _LOGGER.error("Missing secret or device ID. Integration not set up correctly.")
        return

    coordinator = PushoverDataUpdateCoordinator(hass, secret, device_id)
    await coordinator.async_refresh()

    async_add_entities([PushoverLastMessageSensor(coordinator)], True)

class PushoverDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Pushover data from API."""

    def __init__(self, hass, secret, device_id):
        super().__init__(
            hass,
            _LOGGER,
            name="Pushover Messages",
            update_interval=SCAN_INTERVAL,
        )
        self.secret = secret
        self.device_id = device_id

    async def _async_update_data(self):
        """Fetch data from Pushover API and process messages."""
        async with aiohttp.ClientSession() as session:
            try:
                response = await session.get(
                    API_MESSAGES_URL,
                    params={"secret": self.secret, "device_id": self.device_id}
                )
                if response.status == 200:
                    data = await response.json()
                    messages = data.get("messages", [])

                    if not messages:
                        return self.data if self.data else []

                    # Sort messages by date to find the absolute latest
                    sorted_messages = sorted(messages, key=lambda msg: msg.get("date", 0), reverse=True)
                    highest_id = str(max(msg.get("id", 0) for msg in messages))

                    # Logic: Delete from server immediately after fetching
                    # to keep the inbox clean.
                    await asyncio.sleep(1)
                    await self._delete_messages(session, highest_id)

                    return sorted_messages

                else:
                    _LOGGER.error("Error fetching messages: %s", response.status)
            except aiohttp.ClientError as e:
                _LOGGER.error("Error connecting to Pushover: %s", str(e))
        return self.data if self.data else []

    async def _delete_messages(self, session, highest_message_id):
        """Delete messages from the Pushover server up to highest_message_id."""
        delete_url = DELETE_MESSAGES_URL.format(self.device_id)
        payload = {"secret": self.secret, "message": highest_message_id}
        try:
            async with session.post(delete_url, data=payload) as response:
                if response.status == 200:
                    _LOGGER.info("Successfully cleared Pushover inbox up to ID %s", highest_message_id)
        except aiohttp.ClientError as e:
            _LOGGER.error("Error clearing Pushover inbox: %s", str(e))

class PushoverLastMessageSensor(CoordinatorEntity, Entity):
    """Sensor that stores the latest message and a history of the last 10."""

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "Latest Pushover Message"
        self._attr_unique_id = f"pushover_{coordinator.device_id}"
        self._history = []  # Internal list to store last 10 unique messages

    @property
    def state(self):
        """Return the text of the latest unique message."""
        new_messages = self.coordinator.data
        if not new_messages or not isinstance(new_messages, list):
            return self._history[0]["message"] if self._history else "No messages"

        # Check the newest messages from the poll
        for msg in reversed(new_messages):  # Process oldest to newest
            msg_id = msg.get("id")
            # If ID is not in our recent history, add it
            if not any(h.get("id") == msg_id for h in self._history):
                self._history.insert(0, {
                    "id": msg_id,
                    "message": msg.get("message"),
                    "title": msg.get("title", "No Title"),
                    "date": msg.get("date"),
                    "app": msg.get("app")
                })

        # Trim history to last 10 items
        self._history = self._history[:10]
        
        return self._history[0]["message"] if self._history else "No messages"

    @property
    def extra_state_attributes(self):
        """Return the history and metadata of the current message."""
        if not self._history:
            return {}

        latest = self._history[0]
        return {
            "recent_messages": self._history,
            "title": latest.get("title"),
            "id": latest.get("id"),
            "app": latest.get("app"),
            "history_count": len(self._history)
        }

    async def async_update(self):
        """Manual refresh logic."""
        await self.coordinator.async_request_refresh()
