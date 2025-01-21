"""Config flow for Pushover integration."""
import logging
import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from .const import DOMAIN, CONF_EMAIL, CONF_PASSWORD, CONF_TWOFA, CONF_SECRET, CONF_DEVICE_ID

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_EMAIL): str,
    vol.Required(CONF_PASSWORD): str,
    vol.Required(CONF_TWOFA): str,
})

API_LOGIN_URL = "https://api.pushover.net/1/users/login.json"
API_REGISTER_URL = "https://api.pushover.net/1/devices.json"


class PushoverConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the configuration flow for Pushover."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            async with aiohttp.ClientSession() as session:
                try:
                    response = await session.post(
                        API_LOGIN_URL,
                        data={
                            "email": user_input[CONF_EMAIL],
                            "password": user_input[CONF_PASSWORD],
                            "twofa": user_input[CONF_TWOFA],
                        }
                    )

                    if response.status == 200:
                        data = await response.json()
                        secret = data.get("secret")

                        if secret:
                            _LOGGER.info("Successfully authenticated with Pushover.")
                            user_input[CONF_SECRET] = secret

                            # Register the device after obtaining the secret
                            device_id = await self._register_device(secret)
                            if device_id:
                                user_input[CONF_DEVICE_ID] = device_id
                                return self.async_create_entry(title="Pushover", data=user_input)
                            else:
                                errors["base"] = "device_registration_failed"
                                _LOGGER.error("Failed to register device with Pushover.")
                        else:
                            errors["base"] = "auth_failed"
                            _LOGGER.error("Pushover authentication failed: %s", data)

                    else:
                        error_text = await response.text()
                        errors["base"] = "auth_failed"
                        _LOGGER.error("Pushover authentication failed with status: %s - %s", response.status, error_text)

                except aiohttp.ClientError as e:
                    _LOGGER.error("Error connecting to Pushover: %s", str(e))
                    errors["base"] = "connection_error"

        return self.async_show_form(step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors)

    async def _register_device(self, secret):
        """Register the device asynchronously with Pushover."""
        async with aiohttp.ClientSession() as session:
            try:
                response = await session.post(
                    API_REGISTER_URL,
                    data={
                        "secret": secret,
                        "name": "home_assistant",  # Customize this to your preference
                        "os": "O"  # Use 'O' for generic OS as per Pushover API
                    }
                )
                if response.status == 200:
                    data = await response.json()
                    device_id = data.get("id")
                    if device_id:
                        _LOGGER.info("Successfully registered device with ID: %s", device_id)
                        return device_id
                else:
                    error_text = await response.text()
                    _LOGGER.error("Failed to register device: %s - %s", response.status, error_text)
            except aiohttp.ClientError as e:
                _LOGGER.error("Device registration failed: %s", str(e))
        return None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Return the options flow handler."""
        return PushoverOptionsFlowHandler(config_entry)


class PushoverOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Pushover options."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options for the integration."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options_schema = vol.Schema({})

        return self.async_show_form(step_id="init", data_schema=options_schema)
