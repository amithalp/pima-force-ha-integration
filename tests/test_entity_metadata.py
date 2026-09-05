import importlib
import asyncio
import json
import sys
import types
import unittest
from datetime import UTC, datetime
from enum import IntFlag
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).parents[1]
PIMA_PATH = ROOT / "custom_components" / "pima"


def _module(name, **attributes):
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


class _Entity:
    async def async_added_to_hass(self):
        pass


class _AlarmFeatures(IntFlag):
    ARM_AWAY = 1
    ARM_HOME = 2
    ARM_NIGHT = 4


class _SirenFeatures(IntFlag):
    TURN_ON = 1
    TURN_OFF = 2


homeassistant = _module("homeassistant")
components = _module("homeassistant.components")
helpers = _module("homeassistant.helpers")
homeassistant.components = components
homeassistant.helpers = helpers

alarm = _module(
    "homeassistant.components.alarm_control_panel",
    AlarmControlPanelEntity=_Entity,
    AlarmControlPanelEntityFeature=_AlarmFeatures,
    AlarmControlPanelState=SimpleNamespace(
        DISARMED="disarmed",
        TRIGGERED="triggered",
        ARMED_AWAY="armed_away",
        ARMED_HOME="armed_home",
        ARMED_NIGHT="armed_night",
    ),
    CodeFormat=SimpleNamespace(NUMBER="number"),
)
binary_sensor = _module(
    "homeassistant.components.binary_sensor",
    BinarySensorDeviceClass=SimpleNamespace(
        CONNECTIVITY="connectivity", OPENING="opening", PROBLEM="problem"
    ),
    BinarySensorEntity=_Entity,
)
sensor = _module(
    "homeassistant.components.sensor",
    RestoreSensor=_Entity,
    SensorDeviceClass=SimpleNamespace(TIMESTAMP="timestamp"),
    SensorEntity=_Entity,
)
switch = _module("homeassistant.components.switch", SwitchEntity=_Entity)
button = _module("homeassistant.components.button", ButtonEntity=_Entity)
siren = _module(
    "homeassistant.components.siren",
    SirenEntity=_Entity,
    SirenEntityFeature=_SirenFeatures,
)
components.alarm_control_panel = alarm
components.binary_sensor = binary_sensor
components.sensor = sensor
components.switch = switch
components.button = button
components.siren = siren


def _redact_data(value, keys):
    if isinstance(value, dict):
        return {
            key: "REDACTED" if key in keys else _redact_data(item, keys)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_data(item, keys) for item in value]
    return value


diagnostics_component = _module(
    "homeassistant.components.diagnostics", async_redact_data=_redact_data
)
components.diagnostics = diagnostics_component

entity_registry = _module("homeassistant.helpers.entity_registry", async_get=lambda hass: None)
helpers.entity_registry = entity_registry
entity = _module(
    "homeassistant.helpers.entity",
    EntityCategory=SimpleNamespace(CONFIG="config", DIAGNOSTIC="diagnostic"),
)
helpers.entity = entity

custom_components = sys.modules.setdefault(
    "custom_components", types.ModuleType("custom_components")
)
custom_components.__path__ = [str(PIMA_PATH.parent)]
pima_package = sys.modules.setdefault(
    "custom_components.pima", types.ModuleType("custom_components.pima")
)
pima_package.__path__ = [str(PIMA_PATH)]

alarm_module = importlib.import_module("custom_components.pima.alarm_control_panel")
binary_module = importlib.import_module("custom_components.pima.binary_sensor")
sensor_module = importlib.import_module("custom_components.pima.sensor")
switch_module = importlib.import_module("custom_components.pima.switch")
button_module = importlib.import_module("custom_components.pima.button")
siren_module = importlib.import_module("custom_components.pima.siren")
diagnostics_module = importlib.import_module("custom_components.pima.diagnostics")


class EntityMetadataTests(unittest.TestCase):
    def setUp(self):
        self.server = SimpleNamespace(
            account=999001,
            connected=True,
            faults=[],
            faults_initialized=True,
            existing_partitions={1},
            installed_zones=1,
            last_heartbeat=None,
            last_seen=None,
            last_triggered={},
            outputs={number: False for number in range(1, 9)},
            partition_states={1: "disarmed"},
            port=5001,
            sirens={1: False, 2: False},
            zones={1: {"name": "Front Door", "open": False}},
            users={9: "Smart Home"},
        )

    def test_all_entity_types_belong_to_one_panel_device(self):
        entities = [
            alarm_module.PimaAlarmControlPanel(self.server, 1),
            binary_module.PimaZoneBinarySensor(self.server, 1),
            binary_module.PimaPanelTroubleBinarySensor(self.server),
            binary_module.PimaPanelConnectivityBinarySensor(self.server),
            sensor_module.PimaDiagnosticSensor(
                self.server, "last_seen", None
            ),
            switch_module.PimaOutputSwitch(self.server, 1),
            switch_module.PimaZoneBypassSwitch(self.server, 1),
            button_module.PimaArmingButton(self.server, "arm_home_3", 15),
            siren_module.PimaSiren(self.server, 1),
        ]
        expected_identifier = {("pima", "999001")}
        for entity in entities:
            self.assertEqual(entity._attr_device_info["identifiers"], expected_identifier)
            self.assertEqual(entity._attr_device_info["manufacturer"], "PIMA Electronic Systems")
            self.assertEqual(entity._attr_device_info["model"], "Force")
            self.assertEqual(entity._attr_device_info["name"], "PIMA Force Alarm Panel")

    def test_existing_unique_ids_remain_stable(self):
        self.assertEqual(
            alarm_module.PimaAlarmControlPanel(self.server, 1)._attr_unique_id,
            "pima_alarm",
        )
        self.assertEqual(
            alarm_module.PimaAlarmControlPanel(self.server, 2)._attr_unique_id,
            "pima_alarm_partition_2",
        )
        self.assertEqual(
            binary_module.PimaZoneBinarySensor(self.server, 1)._attr_unique_id,
            "pima_zone_1",
        )
        self.assertEqual(
            binary_module.PimaPanelTroubleBinarySensor(self.server)._attr_unique_id,
            "pima_panel_trouble",
        )
        self.assertEqual(
            binary_module.PimaPanelConnectivityBinarySensor(
                self.server
            )._attr_unique_id,
            "pima_panel_connected",
        )
        self.assertEqual(
            sensor_module.PimaDiagnosticSensor(
                self.server, "last_seen", None
            )._attr_unique_id,
            "pima_last_seen",
        )
        self.assertEqual(
            sensor_module.PimaDiagnosticSensor(
                self.server, "last_armed_by", None, restore=True
            )._attr_unique_id,
            "pima_last_armed_by",
        )
        self.assertEqual(
            sensor_module.PimaDiagnosticSensor(
                self.server, "last_disarmed_by", None, restore=True
            )._attr_unique_id,
            "pima_last_disarmed_by",
        )
        self.assertEqual(
            switch_module.PimaOutputSwitch(self.server, 1)._attr_unique_id,
            "pima_output_1",
        )
        self.assertEqual(
            switch_module.PimaZoneBypassSwitch(self.server, 1)._attr_unique_id,
            "pima_zone_1_bypass",
        )
        self.assertEqual(
            button_module.PimaArmingButton(
                self.server, "arm_home_3", 15
            )._attr_unique_id,
            "pima_arm_home_3",
        )
        self.assertEqual(
            button_module.PimaArmingButton(
                self.server, "arm_home_3", 15, partition=2
            )._attr_unique_id,
            "pima_arm_home_3_partition_2",
        )
        self.assertEqual(
            siren_module.PimaSiren(self.server, 1)._attr_unique_id,
            "pima_siren_1",
        )

    def test_zone_uses_generic_opening_device_class(self):
        zone = binary_module.PimaZoneBinarySensor(self.server, 1)
        self.assertEqual(zone._attr_device_class, "opening")
        self.assertEqual(zone._attr_unique_id, "pima_zone_1")

    def test_panel_controls_use_device_relative_names(self):
        alarm = alarm_module.PimaAlarmControlPanel(self.server, 1)
        partition = alarm_module.PimaAlarmControlPanel(self.server, 2)
        external = siren_module.PimaSiren(self.server, 1)
        output = switch_module.PimaOutputSwitch(self.server, 1)

        self.assertTrue(alarm._attr_has_entity_name)
        self.assertIsNone(alarm._attr_name)
        self.assertEqual(partition._attr_name, "Partition 2")
        self.assertEqual(external._attr_name, "External siren")
        self.assertEqual(output._attr_name, "Output 1")
        self.assertNotIn(
            "PIMA",
            " ".join(
                name
                for name in (
                    partition._attr_name,
                    external._attr_name,
                    output._attr_name,
                )
                if name
            ),
        )

    def test_home_assistant_controls_call_standard_server_commands(self):
        calls = []

        async def send_operation(operation, **data):
            calls.append(("operation", operation, data))

        async def send_zone_bypass(zone, bypassed):
            calls.append(("bypass", zone, bypassed))

        self.server.send_operation = send_operation
        self.server.send_zone_bypass = send_zone_bypass

        async def exercise():
            await button_module.PimaArmingButton(
                self.server, "arm_home_3", 15
            ).async_press()
            bypass = switch_module.PimaZoneBypassSwitch(self.server, 1)
            await bypass.async_turn_on()
            await bypass.async_turn_off()

        asyncio.run(exercise())
        self.assertEqual(
            calls,
            [
                ("operation", 15, {"partition": 1}),
                ("bypass", 1, True),
                ("bypass", 1, False),
            ],
        )
        self.assertFalse(
            switch_module.PimaZoneBypassSwitch(
                self.server, 1
            )._attr_entity_registry_enabled_default
        )

    def test_panel_diagnostics_use_translated_entity_names(self):
        entities = {
            binary_module.PimaPanelTroubleBinarySensor(self.server): "panel_trouble",
            binary_module.PimaPanelConnectivityBinarySensor(
                self.server
            ): "panel_connection",
            sensor_module.PimaDiagnosticSensor(
                self.server, "last_seen", None
            ): "last_seen",
        }
        for entity, translation_key in entities.items():
            self.assertTrue(entity._attr_has_entity_name)
            self.assertEqual(entity._attr_translation_key, translation_key)

    def test_entity_translation_keys_exist_in_english_and_hebrew(self):
        expected = {
            "button": {
                "arm_home_1",
                "arm_home_2",
                "arm_home_3",
                "arm_home_4",
                "arm_shabbat",
            },
            "binary_sensor": {"panel_connection", "panel_trouble"},
            "sensor": {
                "fault_count",
                "last_seen",
                "last_heartbeat",
                "last_triggered_zone",
                "last_triggered_partition",
                "last_triggered_user",
                "last_triggered_at",
                "last_armed_by",
                "last_armed_at",
                "last_disarmed_by",
                "last_disarmed_at",
                "last_system_action",
            },
        }
        for filename in ("en.json", "he.json"):
            translation = json.loads(
                (PIMA_PATH / "translations" / filename).read_text(encoding="utf-8")
            )
            for platform, keys in expected.items():
                self.assertEqual(set(translation["entity"][platform]), keys)

    def test_diagnostic_timestamp_is_a_timezone_aware_datetime(self):
        value = sensor_module._as_datetime("2026-09-02T16:35:11.943100+00:00")
        self.assertEqual(value, datetime(2026, 9, 2, 16, 35, 11, 943100, UTC))

    def test_latest_trigger_and_user_name_are_selected(self):
        triggers = {
            1: {
                "last_triggered_at": "2026-09-01T10:00:00+00:00",
                "last_triggered_user": 1,
            },
            2: {
                "last_triggered_at": "2026-09-02T10:00:00+00:00",
                "last_triggered_user": 9,
                "last_triggered_user_name": "Smart Home",
            },
        }
        latest = sensor_module._latest_trigger(triggers)
        self.assertEqual(latest["last_triggered_user"], 9)
        self.assertEqual(sensor_module._trigger_user(latest), "Smart Home")

    def test_trigger_labels_are_human_readable(self):
        self.assertEqual(sensor_module._zone_label(self.server, 1), "Front Door")
        self.assertEqual(sensor_module._zone_label(self.server, 7), "Zone 7")
        self.assertEqual(sensor_module._partition_label(1), "Partition 1")
        self.assertEqual(
            sensor_module._system_action_label("armed_home_2"), "Armed Home 2"
        )
        self.assertEqual(sensor_module._system_action_label("disarmed"), "Disarmed")

    def test_last_trigger_sensor_restores_native_value_and_number(self):
        async def exercise():
            entity = sensor_module.PimaDiagnosticSensor(
                self.server,
                "last_triggered_zone",
                None,
                restore=True,
            )

            async def get_sensor_data():
                return SimpleNamespace(native_value="Front Door")

            async def get_last_state():
                return SimpleNamespace(attributes={"zone": 1})

            entity.async_get_last_sensor_data = get_sensor_data
            entity.async_get_last_state = get_last_state
            await entity.async_added_to_hass()
            return entity

        restored = asyncio.run(exercise())
        self.assertEqual(restored._attr_native_value, "Front Door")
        self.assertEqual(restored._attr_extra_state_attributes, {"zone": 1})
        self.assertTrue(restored._attr_available)

    def test_diagnostics_redact_credentials_and_names(self):
        entry = SimpleNamespace(
            data={"account": 999001, "password": "secret", "port": 5001},
            runtime_data=self.server,
        )
        result = asyncio.run(
            diagnostics_module.async_get_config_entry_diagnostics(None, entry)
        )
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("secret", serialized)
        self.assertNotIn("Front Door", serialized)
        self.assertNotIn("Smart Home", serialized)
        self.assertEqual(result["panel"]["user_count"], 1)


if __name__ == "__main__":
    unittest.main()
