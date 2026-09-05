DOMAIN = "pima"

PANEL_MANUFACTURER = "PIMA Electronic Systems"
PANEL_MODEL = "Force"
PANEL_NAME = "PIMA Force Alarm Panel"


def panel_device_info(account):
    """Return stable Home Assistant device-registry information for the panel."""
    return {
        "identifiers": {(DOMAIN, str(account))},
        "manufacturer": PANEL_MANUFACTURER,
        "model": PANEL_MODEL,
        "name": PANEL_NAME,
    }

DEFAULT_PORT = 10006

OPTYPE_ARM_AWAY = 12
OPTYPE_ARM_HOME1 = 13
OPTYPE_ARM_HOME2 = 14
OPTYPE_ARM_HOME3 = 15
OPTYPE_ARM_HOME4 = 16
OPTYPE_DISARM = 17
OPTYPE_OUTPUT_ON = 35
OPTYPE_OUTPUT_OFF = 36
OPTYPE_SHABBAT = 43

ARMING_SERVICES = {
    "arm_home_1": OPTYPE_ARM_HOME1,
    "arm_home_2": OPTYPE_ARM_HOME2,
    "arm_home_3": OPTYPE_ARM_HOME3,
    "arm_home_4": OPTYPE_ARM_HOME4,
    "arm_shabbat": OPTYPE_SHABBAT,
}
