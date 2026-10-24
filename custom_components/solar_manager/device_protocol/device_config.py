"""Unified device configuration for Solar Manager.

Copyright 2025-2026 maybetaken

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

from custom_components.solar_manager.plugins.DDSU666 import ChintDDSU666
from custom_components.solar_manager.plugins.JkBMS import JkBms
from custom_components.solar_manager.plugins.MakeSkyBlue import MakeSkyBlueDevice
from custom_components.solar_manager.plugins.MakeSkyBlueMppt import MakeSkyBlueMppt
from custom_components.solar_manager.plugins.Megarevo import Megarevo
from custom_components.solar_manager.plugins.PZemV04 import PZemV04
from custom_components.solar_manager.plugins.Sungrey import SungreyDevice
from custom_components.solar_manager.plugins.Switches import SwitchesDevice

# Unified device configuration
DEVICE_CONFIG = {
    "MakeSkyBlue": {
        "protocol": "makeskyblue",
        "device_class": MakeSkyBlueDevice,
    },
    "MakeSkyBlue MPPT": {
        "protocol": "makeskybluemppt",
        "device_class": MakeSkyBlueMppt,
    },
    "JK BMS": {
        "protocol": "jkbms",
        "device_class": JkBms,
    },
    "DDSU666": {
        "protocol": "ddsu666",
        "device_class": ChintDDSU666,
    },
    "Megarevo": {
        "protocol": "megarevo",
        "device_class": Megarevo,
    },
    "Sungrey": {
        "protocol": "sungrey",
        "device_class": SungreyDevice,
    },
    "PZEMV04": {
        "protocol": "pzem_v04",
        "device_class": PZemV04,
    },
    "Switches": {
        "protocol": "switches",
        "device_class": SwitchesDevice,
    },
}

# Derived lists and mappings
SUPPORTED_MODELS = list(DEVICE_CONFIG.keys())
PROTOCOL_MAP = {model: config["protocol"] for model, config in DEVICE_CONFIG.items()}
DEVICE_CLASS_MAP = {
    model: config["device_class"]
    for model, config in DEVICE_CONFIG.items()
    if config["device_class"] is not None
}
