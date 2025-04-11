"""Global access point for MQTTManager."""

from homeassistant.core import HomeAssistant

from .mqtt_manager import MQTTManager


class MQTTManagerSingleton:
    """Singleton for managing the MQTTManager instance."""

    _instance: MQTTManager | None = None

    @classmethod
    def get_instance(cls, hass: HomeAssistant) -> MQTTManager:
        """Get or create the MQTTManager instance."""
        if cls._instance is None:
            cls._instance = MQTTManager(hass)
        return cls._instance


def get_mqtt_manager(hass: HomeAssistant) -> MQTTManager:
    """Get the global MQTTManager instance."""
    return MQTTManagerSingleton.get_instance(hass)
