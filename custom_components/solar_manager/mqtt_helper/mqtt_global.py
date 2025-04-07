"""Global access point for MQTTManager."""

from .mqtt_manager import MQTTManager


class MQTTManagerSingleton:
    """Singleton for managing the MQTTManager instance."""

    _instance: MQTTManager | None = None

    @classmethod
    def get_instance(cls) -> MQTTManager:
        """Get or create the MQTTManager instance."""
        if cls._instance is None:
            # You can modify these parameters as needed
            cls._instance = MQTTManager(
                broker="192.168.31.71", port=1883, username=None, password=None
            )
        return cls._instance


def get_mqtt_manager() -> MQTTManager:
    """Get the global MQTTManager instance."""
    return MQTTManagerSingleton.get_instance()
