import logging
import async_timeout
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, CONF_URL, CONF_TOKEN, DEFAULT_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["sensor"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Village Map from a config entry."""
    url = entry.data[CONF_URL]
    token = entry.data.get(CONF_TOKEN)
    
    if url.endswith("/"):
        url = url[:-1]

    session = async_get_clientsession(hass)
    
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    coordinator = VillageMapCoordinator(hass, session, url, headers)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # 1. Сервис обновления
    async def handle_update_object(call: ServiceCall):
        title = call.data.get("title")
        payload = {"title": title}
        if "ha_data" in call.data: payload["ha_data"] = call.data["ha_data"]
        if "attributes" in call.data: payload["attributes"] = call.data["attributes"]
        if call.data.get("replace_attributes"): payload["replace_attributes"] = True
        
        async with session.post(f"{url}/api/ha/update", json=payload, headers=headers) as resp:
            if resp.status != 200: _LOGGER.error("Update failed: %s", await resp.text())
        await coordinator.async_request_refresh()

    # 2. Сервис подтверждения удаления
    async def handle_confirm_delete(call: ServiceCall):
        obj_id = call.data.get("object_id")
        async with session.delete(f"{url}/api/objects/{obj_id}", headers=headers) as resp:
            if resp.status != 200: _LOGGER.error("Delete failed: %s", await resp.text())
        await coordinator.async_request_refresh()

    # 3. Сервис восстановления
    async def handle_restore_object(call: ServiceCall):
        obj_id = call.data.get("object_id")
        async with session.post(f"{url}/api/admin/objects/{obj_id}/restore", headers=headers) as resp:
            if resp.status != 200: _LOGGER.error("Restore failed: %s", await resp.text())
        await coordinator.async_request_refresh()

    # 4. Массовое подтверждение удаления
    async def handle_confirm_all(call: ServiceCall):
        objects = coordinator.data.get("objects", [])
        for obj in objects:
            if obj.get("pending_delete"):
                async with session.delete(f"{url}/api/objects/{obj['id']}", headers=headers) as resp:
                    if resp.status != 200: _LOGGER.error("Mass delete failed for ID %s", obj['id'])
        await coordinator.async_request_refresh()

    # 5. Массовое восстановление
    async def handle_restore_all(call: ServiceCall):
        objects = coordinator.data.get("objects", [])
        for obj in objects:
            if obj.get("pending_delete") or obj.get("is_deleted"):
                async with session.post(f"{url}/api/admin/objects/{obj['id']}/restore", headers=headers) as resp:
                    if resp.status != 200: _LOGGER.error("Mass restore failed for ID %s", obj['id'])
        await coordinator.async_request_refresh()

    # 6. Удобный сервис синхронизации ОДНОГО атрибута
    async def handle_sync_attribute(call: ServiceCall):
        title = call.data.get("title")
        key = call.data.get("attribute_key")
        entity_id = call.data.get("source_entity")
        
        # Получаем текущее значение из HA
        state = hass.states.get(entity_id)
        if not state:
            _LOGGER.error("Entity %s not found", entity_id)
            return
            
        val = state.state
        if val in ["unknown", "unavailable"]: return

        # Отправляем на бэкенд
        payload = {
            "title": title,
            "attributes": {key: val}
        }
        
        async with session.post(f"{url}/api/ha/update", json=payload, headers=headers) as resp:
            if resp.status != 200: _LOGGER.error("Sync failed: %s", await resp.text())
        await coordinator.async_request_refresh()

    hass.services.async_register(DOMAIN, "update_object", handle_update_object)
    hass.services.async_register(DOMAIN, "confirm_delete", handle_confirm_delete)
    hass.services.async_register(DOMAIN, "restore_object", handle_restore_object)
    hass.services.async_register(DOMAIN, "confirm_all_deletions", handle_confirm_all)
    hass.services.async_register(DOMAIN, "restore_all_objects", handle_restore_all)
    hass.services.async_register(DOMAIN, "sync_attribute", handle_sync_attribute)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok

class VillageMapCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the API."""
    def __init__(self, hass, session, url, headers):
        self.url, self.session, self.headers = url, session, headers
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL))

    async def _async_update_data(self):
        try:
            async with async_timeout.timeout(10):
                async with self.session.get(f"{self.url}/api/categories", headers=self.headers) as r1:
                    categories = await r1.json()
                async with self.session.get(f"{self.url}/api/objects", headers=self.headers) as r2:
                    objects = await r2.json()
                return {"categories": categories, "objects": objects}
        except Exception as err:
            raise UpdateFailed(f"Error: {err}")