from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Village Map sensors with stable IDs."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    # Список уже добавленных в текущем сеансе уникальных ID
    added_entities = set()

    async def async_update_entities():
        if not coordinator.data: return
        new_to_add = []

        # 1. Очередь модерации
        m_uid = f"{DOMAIN}_moderation_queue_stable"
        if m_uid not in added_entities:
            new_to_add.append(VillageMapModerationSensor(coordinator, m_uid))
            added_entities.add(m_uid)

        # 2. Категории
        for cat in coordinator.data.get("categories", []):
            c_uid = f"{DOMAIN}_cat_{cat['slug']}"
            if c_uid not in added_entities:
                new_to_add.append(VillageMapCategorySensor(coordinator, cat, c_uid))
                added_entities.add(c_uid)

        # 3. Атрибуты объектов (Напряжения, температуры и т.д.)
        for obj in coordinator.data.get("objects", []):
            obj_id = obj.get("id")
            attrs = obj.get("attributes") or {}
            for key in attrs:
                if key in ["ha_expose", "editable_for_users"]: continue
                
                # ВЕЧНЫЙ ID: не зависит от сессии или переустановки
                o_uid = f"{DOMAIN}_obj_{obj_id}_{key}"
                if o_uid not in added_entities:
                    new_to_add.append(VillageMapObjectAttributeSensor(coordinator, obj, key, o_uid))
                    added_entities.add(o_uid)

        if new_to_add:
            async_add_entities(new_to_add)

    coordinator.async_add_listener(async_update_entities)
    await async_update_entities()

class VillageMapModerationSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, unique_id):
        super().__init__(coordinator)
        self._attr_name = "Village Map: Модерация"
        self._attr_unique_id = unique_id
        self._attr_icon = "mdi:shield-search"

    @property
    def native_value(self):
        return len([obj for obj in self.coordinator.data.get("objects", []) if obj.get("pending_delete")])

class VillageMapCategorySensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, category, unique_id):
        super().__init__(coordinator)
        self._category = category
        self._attr_name = f"Village Map: {category['name']}"
        self._attr_unique_id = unique_id
        self._attr_icon = f"mdi:{category.get('icon', 'map-marker')}"

    @property
    def native_value(self):
        cat_slug = self._category.get("slug")
        return len([obj for obj in self.coordinator.data.get("objects", []) if obj.get("category_slug") == cat_slug])

class VillageMapObjectAttributeSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, obj, attr_key, unique_id):
        super().__init__(coordinator)
        self.obj_id = obj.get("id")
        self.attr_key = attr_key
        self._attr_unique_id = unique_id
        
        # Настройка устройства (группировка)
        title = obj.get("title") or f"ID {self.obj_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"vmap_obj_{self.obj_id}")},
            name=f"Карта: {title}",
            manufacturer="Village Map",
            model=obj.get("category_slug")
        )

    @property
    def name(self):
        # Динамически берем имя из ui_config карты
        for obj in self.coordinator.data.get("objects", []):
            if obj.get("id") == self.obj_id:
                ui_config = obj.get("ui_config") or {}
                return ui_config.get(self.attr_key, self.attr_key.replace('_', ' ').capitalize())
        return self.attr_key

    @property
    def native_value(self):
        if not self.coordinator.data or "objects" not in self.coordinator.data: return None
        for obj in self.coordinator.data["objects"]:
            if obj.get("id") == self.obj_id:
                return (obj.get("attributes") or {}).get(self.attr_key)
        return None

    @property
    def native_unit_of_measurement(self):
        key = self.attr_key.lower()
        if "temp" in key or "град" in key: return "°C"
        if "faza" in key or "phase" in key or "volt" in key: return "V"
        if "perc" in key or "%" in key: return "%"
        return None