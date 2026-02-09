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
    """Set up the Village Map sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    # Храним ID сущностей, которые МЫ УЖЕ СОЗДАЛИ в этом сеансе работы HA
    added_unique_ids = set()

    async def async_update_entities():
        new_entities = []
        if not coordinator.data: return

        # 1. Сенсор модерации
        mod_uid = f"vmap_moderation_queue" # Стабильный ID без привязки к entry_id
        if mod_uid not in added_unique_ids:
            new_entities.append(VillageMapModerationSensor(coordinator, mod_uid))
            added_unique_ids.add(mod_uid)

        # 2. Сенсоры категорий (групповые)
        if "categories" in coordinator.data:
            for cat in coordinator.data["categories"]:
                cat_uid = f"vmap_cat_{cat['slug']}"
                if cat_uid not in added_unique_ids:
                    new_entities.append(VillageMapCategorySensor(coordinator, cat, cat_uid))
                    added_unique_ids.add(cat_uid)

        # 3. Индивидуальные сенсоры для атрибутов объектов
        if "objects" in coordinator.data:
            for obj in coordinator.data["objects"]:
                attrs = obj.get("attributes") or {}
                
                # Создаем сенсоры для всех атрибутов (кроме системных)
                for key, value in attrs.items():
                    if key in ["ha_expose", "editable_for_users"]: continue
                    
                    # Стабильный ID: префикс + ID объекта + ключ атрибута
                    obj_uid = f"vmap_obj_{obj['id']}_{key}"
                    if obj_uid not in added_unique_ids:
                        new_entities.append(VillageMapObjectAttributeSensor(coordinator, obj, key, obj_uid))
                        added_unique_ids.add(obj_uid)
        
        if new_entities:
            async_add_entities(new_entities)

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
        
        ui_config = obj.get("ui_config") or {}
        friendly_name = ui_config.get(attr_key, attr_key.replace('_', ' ').capitalize())
        
        title = obj.get("title") or f"ID {self.obj_id}"
        self._attr_name = friendly_name
        
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"vmap_obj_{self.obj_id}")},
            name=f"Карта: {title}",
            manufacturer="Village Map",
            model=obj.get("category_slug")
        )

    @property
    def native_value(self):
        if not self.coordinator.data or "objects" not in self.coordinator.data:
            return None
        for obj in self.coordinator.data["objects"]:
            if obj.get("id") == self.obj_id:
                val = (obj.get("attributes") or {}).get(self.attr_key)
                if val is None or val == "": return 0.0
                return val
        return None

    @property
    def native_unit_of_measurement(self):
        # Если ключ содержит temp, вольт или %, ставим красивые единицы
        key = self.attr_key.lower()
        if "temp" in key or "град" in key: return "°C"
        if "faza" in key or "phase" in key or "volt" in key: return "V"
        if "perc" in key or "%" in key: return "%"
        return None
