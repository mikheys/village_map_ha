from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Village Map sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    # Реестр сущностей для очистки старых записей
    entity_registry = er.async_get(hass)
    
    # Храним ID активных сущностей, чтобы знать, что удалять
    active_unique_ids = set()

    async def async_update_entities():
        new_entities = []
        if not coordinator.data: return

        # 1. Сенсор модерации
        mod_uid = f"{entry.entry_id}_moderation"
        active_unique_ids.add(mod_uid)
        if not entity_registry.async_get_entity_id("sensor", DOMAIN, mod_uid):
            new_entities.append(VillageMapModerationSensor(coordinator, mod_uid))

        # 2. Сенсоры категорий (групповые)
        if "categories" in coordinator.data:
            for cat in coordinator.data["categories"]:
                cat_uid = f"{entry.entry_id}_cat_{cat['slug']}"
                active_unique_ids.add(cat_uid)
                if not entity_registry.async_get_entity_id("sensor", DOMAIN, cat_uid):
                    new_entities.append(VillageMapCategorySensor(coordinator, cat, cat_uid))

        # 3. Индивидуальные сенсоры для атрибутов объектов
        if "objects" in coordinator.data:
            for obj in coordinator.data["objects"]:
                attrs = obj.get("attributes") or {}
                ui_config = obj.get("ui_config") or {}
                
                # Создаем сенсоры для всех атрибутов (кроме системных)
                for key, value in attrs.items():
                    if key in ["ha_expose", "editable_for_users"]: continue
                    
                    obj_uid = f"{entry.entry_id}_obj_{obj['id']}_{key}"
                    active_unique_ids.add(obj_uid)
                    
                    if not entity_registry.async_get_entity_id("sensor", DOMAIN, obj_uid):
                        new_entities.append(VillageMapObjectAttributeSensor(coordinator, obj, key, obj_uid))
        
        if new_entities:
            async_add_entities(new_entities)

        # Очистка: удаляем сущности, которых больше нет в данных
        # (в этом прототипе просто логируем или можно расширить логику удаления)

    coordinator.async_add_listener(async_update_entities)
    await async_update_entities()

class VillageMapModerationSensor(CoordinatorEntity, SensorEntity):
    """Сенсор очереди модерации."""
    def __init__(self, coordinator, unique_id):
        super().__init__(coordinator)
        self._attr_name = "Village Map: Модерация"
        self._attr_unique_id = unique_id
        self._attr_icon = "mdi:shield-search"

    @property
    def native_value(self):
        return len([obj for obj in self.coordinator.data.get("objects", []) if obj.get("pending_delete")])

    @property
    def extra_state_attributes(self):
        pending = [obj for obj in self.coordinator.data.get("objects", []) if obj.get("pending_delete")]
        return {"object_list": pending}

class VillageMapCategorySensor(CoordinatorEntity, SensorEntity):
    """Групповой сенсор категории."""
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
    """Сенсор конкретного атрибута объекта (например, Напряжение фазы А)."""
    def __init__(self, coordinator, obj, attr_key, unique_id):
        super().__init__(coordinator)
        self.obj_id = obj.get("id")
        self.attr_key = attr_key
        self._attr_unique_id = unique_id
        
        # Берем красивое имя из ui_config или используем ключ
        ui_config = obj.get("ui_config") or {}
        friendly_name = ui_config.get(attr_key, attr_key.replace('_', ' ').capitalize())
        
        title = obj.get("title") or f"ID {self.obj_id}"
        self._attr_name = friendly_name
        
        # Привязка к устройству (одно устройство на одну метку карты)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"vmap_obj_{self.obj_id}")},
            name=f"Карта: {title}",
            manufacturer="Village Map",
            model=obj.get("category_slug"),
            suggested_area=obj.get("category_slug")
        )

    @property
    def native_value(self):
        for obj in self.coordinator.data.get("objects", []):
            if obj.get("id") == self.obj_id:
                val = (obj.get("attributes") or {}).get(self.attr_key)
                # Пытаемся превратить в число для графиков, если возможно
                try:
                    if isinstance(val, str):
                        # Убираем " В", " °C" и прочее для перевода в число
                        clean_val = val.split(' ')[0].replace(',', '.')
                        return float(clean_val)
                    return val
                except:
                    return val
        return None

    @property
    def native_unit_of_measurement(self):
        # Авто-определение единиц измерения для красоты
        for obj in self.coordinator.data.get("objects", []):
            if obj.get("id") == self.obj_id:
                val = (obj.get("attributes") or {}).get(self.attr_key)
                if isinstance(val, str):
                    if " В" in val or " V" in val: return "V"
                    if "°C" in val: return "°C"
                    if " %" in val: return "%"
        return None
