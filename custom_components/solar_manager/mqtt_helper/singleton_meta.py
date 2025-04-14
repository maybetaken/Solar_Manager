"""Thread-safe Singleton metaclass.

Solar Manager or solar_manager © 2025 by @maybetaken is
licensed under Creative Commons
Attribution-NonCommercial-NoDerivatives 4.0 International.
"""

import threading


class SingletonMeta(type):
    """Thread-safe Singleton metaclass."""

    _instances = {}
    _lock: threading.Lock = threading.Lock()

    def __call__(cls, *args, **kwargs):
        """Create or return the singleton instance."""
        with cls._lock:
            if cls not in cls._instances:
                instance = super().__call__(*args, **kwargs)
                cls._instances[cls] = instance
        return cls._instances[cls]
