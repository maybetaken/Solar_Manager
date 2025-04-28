"""Unified device configuration for Solar Manager.

Solar Manager or solar_manager © 2025 by @maybetaken is
licensed under Creative Commons
Attribution-NonCommercial-NoDerivatives 4.0 International.
"""

from custom_components.solar_manager.plugins.MakeSkyBlue import MakeSkyBlueDevice

# Unified device configuration
DEVICE_CONFIG = {
    "MakeSkyBlue": {
        "protocol": "makeskyblue",
        "device_class": MakeSkyBlueDevice,
    },
    # "ChintMeter": {
    #     "protocol": "chintmeter",
    #     "device_class": None,
    # },
    # "REVO": {
    #     "protocol": "revo",
    #     "device_class": None,
    # },
}

# Derived lists and mappings
SUPPORTED_MODELS = list(DEVICE_CONFIG.keys())
PROTOCOL_MAP = {model: config["protocol"] for model, config in DEVICE_CONFIG.items()}
DEVICE_CLASS_MAP = {
    model: config["device_class"]
    for model, config in DEVICE_CONFIG.items()
    if config["device_class"] is not None
}
