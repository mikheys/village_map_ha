import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, CONF_URL, CONF_TOKEN

class VillageMapConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Village Map."""
    
    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            # Проверяем соединение
            valid = await self._test_connection(user_input[CONF_URL], user_input.get(CONF_TOKEN))
            if valid:
                return self.async_create_entry(
                    title="Village Map", 
                    data=user_input
                )
            else:
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_URL, default="http://localhost:8000"): str,
                vol.Optional(CONF_TOKEN): str,
            }),
            errors=errors,
        )

    async def _test_connection(self, url, token):
        """Test connection to the API."""
        session = async_get_clientsession(self.hass)
        try:
            if url.endswith("/"):
                url = url[:-1]
            
            headers = {}
            if token:
                headers["Authorization"] = f"Bearer {token}"
                
            async with session.get(f"{url}/api/auth/status", headers=headers, timeout=10) as response:
                return response.status == 200
        except Exception:
            return False
