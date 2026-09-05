import asyncio
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
SERVER_PATH = Path(__file__).parents[1] / "custom_components" / "pima" / "server.py"
CUSTOM_COMPONENTS = types.ModuleType("custom_components")
CUSTOM_COMPONENTS.__path__ = [str(SERVER_PATH.parents[1])]
PIMA_PACKAGE = types.ModuleType("custom_components.pima")
PIMA_PACKAGE.__path__ = [str(SERVER_PATH.parent)]
sys.modules.setdefault("custom_components", CUSTOM_COMPONENTS)
sys.modules.setdefault("custom_components.pima", PIMA_PACKAGE)
SPEC = importlib.util.spec_from_file_location("custom_components.pima.server", SERVER_PATH)
pima_server = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = pima_server
SPEC.loader.exec_module(pima_server)

JsonFrameBuffer = pima_server.JsonFrameBuffer
PimaCommandError = pima_server.PimaCommandError
PimaServer = pima_server.PimaServer
redact = pima_server._redact
decode_fault = pima_server.decode_fault


def load_fixture(name):
    return [
        json.loads(line)
        for line in (FIXTURES / name).read_text(encoding="utf-8").splitlines()
        if line
    ]


class FakeBus:
    def __init__(self):
        self.events = []

    def async_fire(self, event_type, data):
        self.events.append((event_type, data))


class FakeHass:
    def __init__(self):
        self.bus = FakeBus()

    def async_create_task(self, coroutine):
        coroutine.close()


class FakeWriter:
    def __init__(self):
        self.frames = []
        self.closed = False

    def write(self, data):
        self.frames.append(json.loads(data))

    async def drain(self):
        pass

    def close(self):
        self.closed = True


class FakeReader:
    def __init__(self):
        self.queue = asyncio.Queue()

    async def read(self, size):
        return await self.queue.get()

    def feed(self, data):
        self.queue.put_nowait(data)

    def close(self):
        self.queue.put_nowait(b"")


class FakeListener:
    def __init__(self):
        self.closed = False
        self.waited = False

    def close(self):
        self.closed = True

    async def wait_closed(self):
        self.waited = True


class JsonFrameBufferTests(unittest.TestCase):
    def test_fragmented_and_back_to_back_frames(self):
        frames = load_fixture("specification.jsonl")[:2]
        raw = "noise\x00" + "".join(json.dumps(frame) for frame in frames)
        parser = JsonFrameBuffer()
        self.assertEqual(parser.feed(raw[:31].encode("latin-1")), [])
        self.assertEqual(parser.feed(raw[31:].encode("latin-1")), frames)

    def test_braces_and_escaped_quotes_inside_strings(self):
        parser = JsonFrameBuffer()
        frame = {"frame_type": "NAK", "counter": 1, "DATA": 'bad { "value" }'}
        self.assertEqual(parser.feed(json.dumps(frame).encode()), [frame])

    def test_log_redaction_masks_credentials_and_names_without_mutation(self):
        frame = {
            "frame_type": "DATA",
            "account": "654321",
            "password": "secret",
            "id": 260,
            "parameters": ["Private zone", "Another zone"],
        }
        safe = redact(frame)
        self.assertEqual(safe["account"], "***")
        self.assertEqual(safe["password"], "***")
        self.assertEqual(safe["parameters"], ["***", "***"])
        self.assertEqual(frame["parameters"][0], "Private zone")

    def test_sanitized_bypass_fixture_covers_disabled_and_enabled_results(self):
        frames = load_fixture("sanitized_bypass_confirmation.jsonl")
        read_backs = [
            frame["parameters"][0]
            for frame in frames
            if frame.get("frame_type", "").upper() == "DATA"
            and frame.get("id") == 2150
            and "more" in frame
        ]
        bypass_events = [
            (frame["qualifier"], frame["zone"])
            for frame in frames
            if frame.get("type") == 570
        ]
        self.assertEqual(read_backs, ["0", "1", "0"])
        self.assertEqual(bypass_events, [(1, 8), (3, 8)])


class ServerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.hass = FakeHass()
        self.server = PimaServer(self.hass, 999001, "sanitized", 10006)
        self.server.writer = FakeWriter()
        self.server.connected = True

    async def test_stop_closes_client_and_listener(self):
        listener = FakeListener()
        writer = self.server.writer
        self.server.server = listener

        await self.server.stop()

        self.assertTrue(writer.closed)
        self.assertTrue(listener.closed)
        self.assertTrue(listener.waited)
        self.assertFalse(self.server.connected)
        self.assertIsNone(self.server.writer)
        self.assertIsNone(self.server.server)

    async def test_null_heartbeat_is_acked_and_starts_discovery_once(self):
        null = load_fixture("specification.jsonl")[0]
        await self.server.handle_message(null)
        await self.server.handle_message(null)
        ack_frames = [f for f in self.server.writer.frames if f["frame_type"] == "ACK"]
        requests = [f for f in self.server.writer.frames if f["frame_type"] == "DATA-REQ"]
        self.assertEqual(len(ack_frames), 2)
        self.assertEqual(
            [f["id"] for f in requests], [2310, 2148, 2301, 2301, 2250, 411]
        )
        output_requests = [f for f in requests if f["id"] == 2301]
        self.assertEqual(
            [(f["start_order"], f["stop_order"]) for f in output_requests],
            [(1, 2), (34, 41)],
        )
        heartbeat = [d for n, d in self.hass.bus.events if n == "pima_last_seen"]
        self.assertEqual(len(heartbeat), 2)
        self.assertIsNotNone(heartbeat[-1]["last_heartbeat"])

    def test_fault_values_decode_id_optional_order_and_label(self):
        self.assertEqual(decode_fault("1")["description"], "AC Loss")
        self.assertIsNone(decode_fault("6")["order"])
        expander = decode_fault("309")
        self.assertEqual((expander["fault_id"], expander["order"]), (9, 3))
        self.assertEqual(expander["label"], "Zone Expander Fault #3")
        network = decode_fault("421")
        self.assertEqual((network["fault_id"], network["order"]), (33, 4))
        self.assertEqual(network["label"], "Station Network Communication Fault")
        zone = decode_fault("2B3C")
        self.assertEqual((zone["fault_id"], zone["order"]), (60, 43))
        self.assertEqual(zone["label"], "Zone Tamper Fault #43")

    async def test_active_fault_is_reconciled_on_later_heartbeat(self):
        self.hass.async_create_task = asyncio.create_task
        self.server._init_done = True
        self.server.faults_initialized = True
        self.server.faults = [decode_fault("421")]
        self.server._last_fault_request = 0
        original_delay = pima_server.FAULT_REFRESH_DELAY
        original_interval = pima_server.ACTIVE_FAULT_RECHECK_INTERVAL
        pima_server.FAULT_REFRESH_DELAY = 0
        pima_server.ACTIVE_FAULT_RECHECK_INTERVAL = 0
        try:
            await self.server.handle_message({
                "frame_type": "NULL", "counter": 50, "account": "654321"
            })
            await asyncio.sleep(0.05)
        finally:
            pima_server.FAULT_REFRESH_DELAY = original_delay
            pima_server.ACTIVE_FAULT_RECHECK_INTERVAL = original_interval
        requests = [
            frame for frame in self.server.writer.frames
            if frame.get("frame_type") == "DATA-REQ" and frame.get("id") == 2250
        ]
        self.assertEqual(len(requests), 1)

    async def test_fault_pagination_and_empty_restore(self):
        self.hass.async_create_task = asyncio.create_task
        self.server.process_data({
            "frame_type": "DATA", "id": 2250, "start_order": 1,
            "parameters": ["1", "6", "309"], "more": "yes",
        })
        await asyncio.sleep(0)
        request = self.server.writer.frames[-1]
        self.assertEqual((request["id"], request["start_order"]), (2250, 4))
        self.server.process_data({
            "frame_type": "DATA", "id": 2250, "start_order": 4,
            "parameters": ["2B3C"], "more": "no",
        })
        self.assertTrue(self.server.faults_initialized)
        self.assertEqual(len(self.server.faults), 4)
        update = [d for n, d in self.hass.bus.events if n == "pima_faults_updated"][-1]
        self.assertTrue(update["problem"])
        self.assertIn("Zone Expander Fault #3", update["active_faults"])

        self.server.process_data({
            "frame_type": "DATA", "id": 2250, "start_order": 1,
            "parameters": [], "more": "no",
        })
        self.assertEqual(self.server.faults, [])
        update = [d for n, d in self.hass.bus.events if n == "pima_faults_updated"][-1]
        self.assertFalse(update["problem"])

    def test_bypass_status_updates_zone_attributes(self):
        self.server.installed_zones = 4
        self.server.process_data({
            "frame_type": "DATA", "id": 2150, "start_order": 1,
            "parameters": ["1", "0", "0", "1"], "more": "no",
        })
        self.assertTrue(self.server.zones[1]["manual_bypassed"])
        self.assertFalse(self.server.zones[2]["manual_bypassed"])
        self.assertTrue(self.server.zones[4]["manual_bypassed"])
        updates = [d for n, d in self.hass.bus.events if n == "pima_zone_update"]
        self.assertEqual(len(updates), 4)
        self.assertEqual(
            [d["zone"] for d in updates if d["manual_bypassed"]], [1, 4]
        )

    async def test_bypass_status_paginates_positionally(self):
        self.hass.async_create_task = asyncio.create_task
        self.server.installed_zones = 4
        self.server.process_data({
            "frame_type": "DATA", "id": 2150, "start_order": 1,
            "parameters": ["0", "1"], "more": "yes",
        })
        await asyncio.sleep(0)
        request = self.server.writer.frames[-1]
        self.assertEqual(
            (request["id"], request["start_order"], request["stop_order"]),
            (2150, 3, 4),
        )
        self.server.process_data({
            "frame_type": "DATA", "id": 2150, "start_order": 3,
            "parameters": ["1", "0"], "more": "no",
        })
        self.assertEqual(
            [self.server.zones[z]["manual_bypassed"] for z in range(1, 5)],
            [False, True, True, False],
        )

    async def test_bypass_command_is_acked_and_read_back(self):
        self.server.installed_zones = 24
        task = asyncio.create_task(self.server.send_zone_bypass(3, True))
        await asyncio.sleep(0)
        command = self.server.writer.frames[0]
        self.assertEqual(command["frame_type"], "DATA")
        self.assertEqual(command["id"], 2150)
        self.assertEqual(command["start_order"], 3)
        self.assertEqual(command["parameters"], ["1"])
        await self.server.handle_message({
            "frame_type": "ACK", "counter": command["counter"]
        })
        await asyncio.sleep(0.05)
        refresh = self.server.writer.frames[-1]
        self.assertEqual(
            (refresh["frame_type"], refresh["id"], refresh["start_order"], refresh["stop_order"]),
            ("DATA-REQ", 2150, 3, 3),
        )
        await self.server.handle_message({
            "frame_type": "DATA", "counter": refresh["counter"], "id": 2150,
            "start_order": 3, "parameters": ["1"], "more": "no",
        })
        await task

    async def test_bypass_acknowledged_but_not_applied_fails(self):
        """ACK is transport acceptance; the 2150 read-back is authoritative."""
        self.server.installed_zones = 24
        task = asyncio.create_task(self.server.send_zone_bypass(8, True))
        await asyncio.sleep(0)
        command = self.server.writer.frames[0]
        await self.server.handle_message({
            "frame_type": "ACK", "counter": command["counter"]
        })
        await asyncio.sleep(0.05)
        refresh = self.server.writer.frames[-1]
        self.assertEqual((refresh["id"], refresh["start_order"]), (2150, 8))
        await self.server.handle_message({
            "frame_type": "DATA", "counter": refresh["counter"], "id": 2150,
            "start_order": 8, "parameters": ["0"], "more": "no",
        })
        with self.assertRaisesRegex(PimaCommandError, "acknowledged but not applied"):
            await task

    async def test_unbypass_command_and_uninstalled_zone_validation(self):
        self.server.installed_zones = 4
        task = asyncio.create_task(self.server.send_zone_bypass(2, False))
        await asyncio.sleep(0)
        command = self.server.writer.frames[0]
        self.assertEqual(command["parameters"], ["0"])
        await self.server.handle_message({
            "frame_type": "ACK", "counter": command["counter"]
        })
        await asyncio.sleep(0.05)
        refresh = self.server.writer.frames[-1]
        self.assertEqual((refresh["id"], refresh["start_order"]), (2150, 2))
        await self.server.handle_message({
            "frame_type": "DATA", "counter": refresh["counter"], "id": 2150,
            "start_order": 2, "parameters": ["0"], "more": "no",
        })
        await task
        with self.assertRaisesRegex(PimaCommandError, "not installed"):
            await self.server.send_zone_bypass(5, True)

    async def test_programming_change_schedules_configuration_refresh(self):
        self.hass.async_create_task = asyncio.create_task
        self.server.connected = True
        original_delay = pima_server.CONFIG_REFRESH_DELAY
        pima_server.CONFIG_REFRESH_DELAY = 0
        try:
            self.server.process_event({
                "frame_type": "event", "counter": 61, "type": 306,
                "qualifier": 1, "zone": 0, "partition": 1,
            })
            await asyncio.sleep(0.12)
        finally:
            pima_server.CONFIG_REFRESH_DELAY = original_delay
        requests = [
            (frame.get("id"), frame.get("start_order"), frame.get("stop_order"))
            for frame in self.server.writer.frames
        ]
        self.assertIn((2310, 1, 16), requests)
        self.assertIn((2148, 1, 1), requests)
        self.assertIn((411, 1, 32), requests)

    async def test_user_names_paginate_decode_and_stay_out_of_logs(self):
        self.hass.async_create_task = asyncio.create_task
        self.server.process_data({
            "frame_type": "DATA", "id": 411, "start_order": 1,
            "parameters": ["Admin", "àáâ"], "more": "yes",
        })
        await asyncio.sleep(0)
        request = self.server.writer.frames[-1]
        self.assertEqual(
            (request["id"], request["start_order"], request["stop_order"]),
            (411, 3, 32),
        )
        self.server.process_data({
            "frame_type": "DATA", "id": 411, "start_order": 3,
            "parameters": ["Guest"], "more": "no",
        })
        self.assertEqual(self.server.users, {1: "Admin", 2: "אבג", 3: "Guest"})
        update = [d for n, d in self.hass.bus.events if n == "pima_users_updated"][-1]
        self.assertEqual(update["count"], 3)
        safe = redact({"id": 411, "parameters": ["Admin", "Guest"]})
        self.assertEqual(safe["parameters"], ["***", "***"])

    def test_arm_user_attribution_and_last_trigger_details(self):
        self.server.users = {2: "Owner"}
        self.server.process_event({
            "type": 401, "qualifier": 3, "zone": 2, "partition": 1
        })
        armed = [d for n, d in self.hass.bus.events if n == "pima_state"][-1]
        self.assertEqual((armed["user"], armed["user_name"]), (2, "Owner"))
        self.assertEqual(armed["action"], "armed")
        self.assertEqual(armed["cid_type"], 401)
        self.assertIn("+00:00", armed["action_at"])

        self.server.process_event({
            "type": 130, "qualifier": 1, "zone": 7, "partition": 1
        })
        triggered = [d for n, d in self.hass.bus.events if n == "pima_state"][-1]
        self.assertEqual(triggered["state"], "triggered")
        self.assertEqual(triggered["last_triggered_zone"], 7)
        self.assertEqual(triggered["last_triggered_partition"], 1)
        self.assertEqual(triggered["last_triggered_user"], 2)
        self.assertEqual(triggered["last_triggered_user_name"], "Owner")
        self.assertIn("+00:00", triggered["last_triggered_at"])

        self.server.process_event({
            "type": 401, "qualifier": 1, "zone": 2, "partition": 1
        })
        disarmed = [d for n, d in self.hass.bus.events if n == "pima_state"][-1]
        self.assertEqual(disarmed["action"], "disarmed")
        self.assertEqual((disarmed["user"], disarmed["user_name"]), (2, "Owner"))
        self.assertEqual(self.server.last_triggered[1]["last_triggered_zone"], 7)

    async def test_replaced_client_disconnect_does_not_drop_active_client(self):
        first_reader, second_reader = FakeReader(), FakeReader()
        first_writer, second_writer = FakeWriter(), FakeWriter()

        first_task = asyncio.create_task(
            self.server.handle_client(first_reader, first_writer)
        )
        await asyncio.sleep(0)
        second_task = asyncio.create_task(
            self.server.handle_client(second_reader, second_writer)
        )
        await asyncio.sleep(0)

        self.assertTrue(first_writer.closed)
        self.assertIs(self.server.writer, second_writer)
        first_reader.close()
        await first_task
        self.assertTrue(self.server.connected)
        self.assertIs(self.server.writer, second_writer)
        disconnected = [d for n, d in self.hass.bus.events if n == "pima_disconnected"]
        self.assertEqual(disconnected, [])

        second_reader.close()
        await second_task
        self.assertFalse(self.server.connected)
        self.assertIsNone(self.server.writer)

    def test_zone_discovery_names_status_and_partition(self):
        frames = load_fixture("sanitized_panel_capture.jsonl")
        for frame in frames[1:5]:
            self.server.process_data(frame)
        self.assertEqual(self.server.installed_zones, 4)
        self.assertEqual(self.server.zones[1]["name"], "Front Door")
        self.assertTrue(self.server.zones[1]["open"])
        self.assertTrue(self.server.zones[2]["open"])
        self.assertTrue(self.server.zones[2]["alarmed"])
        self.assertTrue(self.server.zones[3]["manual_bypassed"])
        self.assertEqual(self.server.partition_states[1], "armed_away")

    def test_multiple_partition_states_are_discovered_and_isolated(self):
        self.server.process_data({
            "frame_type": "DATA", "counter": 20, "id": 2310,
            "start_order": 1, "parameters": ["2", "3", "1", "5"],
            "more": "no",
        })
        self.assertEqual(self.server.existing_partitions, {1, 2, 4})
        self.assertEqual(
            self.server.partition_states,
            {1: "disarmed", 2: "armed_away", 4: "armed_home_2"},
        )
        self.assertEqual(self.server.state, "disarmed")
        updates = [d for n, d in self.hass.bus.events if n == "pima_state"]
        self.assertEqual(
            [(d["partition"], d["state"]) for d in updates],
            [(1, "disarmed"), (2, "armed_away"), (4, "armed_home_2")],
        )

        self.server.process_event({
            "type": 401, "qualifier": 1, "zone": 9, "partition": 2
        })
        self.assertEqual(self.server.partition_states[2], "disarmed")
        self.assertEqual(self.server.partition_states[4], "armed_home_2")
        self.assertEqual(self.server.state, "disarmed")

    def test_alarm_trigger_and_restore_affect_only_event_partition(self):
        self.server.partition_states = {1: "disarmed", 2: "armed_away"}
        self.server.process_event({
            "type": 130, "qualifier": 1, "zone": 7, "partition": 2
        })
        self.assertEqual(self.server.state, "disarmed")
        self.assertEqual(self.server.partition_states[2], "armed_away")
        self.server.process_event({
            "type": 130, "qualifier": 3, "zone": 7, "partition": 2
        })
        states = [d for n, d in self.hass.bus.events if n == "pima_state"]
        self.assertEqual(
            [(d["partition"], d["state"]) for d in states],
            [(2, "triggered"), (2, "armed_away")],
        )

    def test_empty_zone_status_marks_all_discovered_zones_clean(self):
        self.server.installed_zones = 2
        self.server.zones = {
            1: {"open": True, "alarmed": True},
            2: {"open": False, "manual_bypassed": True},
        }
        self.server.process_data({
            "frame_type": "DATA",
            "counter": 3,
            "id": 2149,
            "start_order": 1,
            "parameters": [],
            "more": "no",
        })
        updates = [data for name, data in self.hass.bus.events if name == "pima_zone_update"]
        self.assertEqual(len(updates), 2)
        self.assertFalse(updates[0]["open"])
        self.assertFalse(updates[0]["alarmed"])
        self.assertFalse(updates[1]["manual_bypassed"])

    def test_sanitized_real_capture_discovery_and_pagination(self):
        frames = load_fixture("sanitized_real_panel_capture.jsonl")
        self.assertEqual(frames[0]["frame_type"], "null")
        self.assertIsInstance(frames[0]["account"], str)
        for frame in frames:
            if str(frame.get("frame_type", "")).upper() == "DATA":
                self.server.process_data(frame)
        self.assertEqual(self.server.installed_zones, 24)
        self.assertEqual(self.server.partition_states[1], "disarmed")
        self.assertEqual(self.server.zones[1]["name"], "Zone 01")
        self.assertEqual(self.server.zones[24]["name"], "Zone 24")
        self.assertFalse(self.server.zones[24]["open"])

    async def test_alarm_trigger_restore_and_duplicate_ack(self):
        self.server.partition_states[1] = "armed_away"
        frames = load_fixture("sanitized_panel_capture.jsonl")[5:]
        for frame in frames:
            await self.server.handle_message(frame)
        states = [data for name, data in self.hass.bus.events if name == "pima_state"]
        self.assertEqual([event["state"] for event in states], ["triggered", "armed_away"])
        self.assertEqual(states[0]["zone"], 2)
        self.assertEqual(states[0]["partition"], 1)
        self.assertEqual(len(self.server.writer.frames), 3)  # duplicate was still ACKed

    async def test_real_panel_home_and_key_switch_disarm_events(self):
        frames = load_fixture("sanitized_real_panel_capture.jsonl")
        arm = next(frame for frame in frames if frame.get("type") == 441)
        disarm = next(
            frame
            for frame in frames
            if frame.get("type") == 409 and frame.get("qualifier") == 1
        )
        await self.server.handle_message(arm)
        self.assertEqual(self.server.state, "armed_home_1")
        await self.server.handle_message(disarm)
        self.assertEqual(self.server.state, "disarmed")
        states = [data for name, data in self.hass.bus.events if name == "pima_state"]
        self.assertEqual([event["state"] for event in states], ["armed_home_1", "disarmed"])
        self.assertEqual([event["partition"] for event in states], [1, 1])

    async def test_key_switch_away_arm_event(self):
        await self.server.handle_message({
            "frame_type": "event",
            "counter": 2202,
            "account": "654321",
            "type": 409,
            "qualifier": 3,
            "zone": 19,
            "partition": 1,
        })
        self.assertEqual(self.server.state, "armed_away")

    async def test_remote_arm_event_preserves_authoritative_home_mode(self):
        self.server.process_data({
            "frame_type": "DATA",
            "counter": 12,
            "id": 2310,
            "start_order": 1,
            "parameters": ["4"],
            "more": "no",
        })
        await self.server.handle_message({
            "frame_type": "event",
            "counter": 2356,
            "type": 407,
            "qualifier": 3,
            "zone": 1,
            "partition": 1,
        })
        self.assertEqual(self.server.partition_states[1], "armed_home_1")
        self.assertEqual(self.server.state, "armed_home_1")

    async def test_remote_arm_event_defaults_to_away_without_status(self):
        self.server.partition_states[1] = "disarmed"
        await self.server.handle_message({
            "frame_type": "event",
            "counter": 2356,
            "type": 407,
            "qualifier": 3,
            "zone": 1,
            "partition": 1,
        })
        self.assertEqual(self.server.state, "armed_away")

    async def test_ack_correlates_operation_and_refreshes_partition(self):
        task = asyncio.create_task(self.server.send_operation(12, partition=1))
        await asyncio.sleep(0)
        counter = self.server.writer.frames[0]["counter"]
        await self.server.handle_message({"frame_type": "ACK", "counter": counter})
        await task
        self.assertEqual(self.server.writer.frames[-1]["id"], 2310)

    async def test_home_operation_uses_real_panel_partition_and_order(self):
        task = asyncio.create_task(self.server.send_operation(13, partition=1))
        await asyncio.sleep(0)
        operation = self.server.writer.frames[0]
        self.assertEqual(operation["partition"], 1)
        self.assertEqual(operation["order"], 1)
        await self.server.handle_message({
            "frame_type": "ACK", "counter": operation["counter"]
        })
        await task

    async def test_all_additional_arming_modes_use_expected_operation(self):
        for optype in (14, 15, 16, 43):
            self.server.writer.frames.clear()
            task = asyncio.create_task(self.server.send_operation(optype, partition=2))
            await asyncio.sleep(pima_server.MIN_REQUEST_GAP + 0.1)
            operation = self.server.writer.frames[0]
            self.assertEqual(operation["optype"], optype)
            self.assertEqual(operation["partition"], 2)
            self.assertEqual(operation["order"], 1)
            await self.server.handle_message(
                {"frame_type": "ACK", "counter": operation["counter"]}
            )
            await task
            self.assertEqual(self.server.writer.frames[-1]["id"], 2310)

    async def test_concurrent_requests_claim_unique_counters(self):
        await asyncio.gather(
            self.server._request_zone_status(),
            self.server._request_zone_names(1),
            self.server._request_faults(1),
            self.server._request_user_names(1),
        )
        counters = [frame["counter"] for frame in self.server.writer.frames]
        self.assertEqual(len(counters), 4)
        self.assertEqual(len(set(counters)), 4)

    async def test_fault_initialization_retries_are_bounded(self):
        calls = []

        async def request_faults(start_order=1):
            calls.append(start_order)

        original_delay = pima_server.FAULT_INIT_RETRY_DELAY
        pima_server.FAULT_INIT_RETRY_DELAY = 0
        self.server._request_faults = request_faults
        try:
            await self.server._retry_fault_initialization()
        finally:
            pima_server.FAULT_INIT_RETRY_DELAY = original_delay
        self.assertEqual(calls, [1] * pima_server.FAULT_INIT_RETRIES)

    def test_2301_decodes_siren_and_controlled_output_status(self):
        self.server.process_data({
            "frame_type": "DATA", "id": 2301, "start_order": 1,
            "parameters": ["1", "0"], "more": "no",
        })
        self.server.process_data({
            "frame_type": "DATA", "id": 2301, "start_order": 34,
            "parameters": ["0", "1", "0", "0", "0", "0", "0", "1"],
            "more": "no",
        })
        self.assertEqual(self.server.sirens, {1: True, 2: False})
        self.assertTrue(self.server.outputs[2])
        self.assertTrue(self.server.outputs[8])
        self.assertFalse(self.server.outputs[1])
        siren_updates = [d for n, d in self.hass.bus.events if n == "pima_siren_update"]
        output_updates = [d for n, d in self.hass.bus.events if n == "pima_output_update"]
        self.assertEqual(len(siren_updates), 2)
        self.assertEqual(len(output_updates), 8)

    async def test_output_operation_uses_order_and_refreshes_2301(self):
        task = asyncio.create_task(self.server.send_operation(35, partition=0, order=34))
        await asyncio.sleep(0)
        operation = self.server.writer.frames[0]
        self.assertEqual(operation["optype"], 35)
        self.assertEqual(operation["partition"], 0)
        self.assertEqual(operation["order"], 34)
        await self.server.handle_message(
            {"frame_type": "ACK", "counter": operation["counter"]}
        )
        await task
        refresh = self.server.writer.frames[-1]
        self.assertEqual(refresh["id"], 2301)
        self.assertEqual((refresh["start_order"], refresh["stop_order"]), (34, 41))

    async def test_siren_operation_refreshes_only_siren_range(self):
        task = asyncio.create_task(self.server.send_operation(36, partition=0, order=1))
        await asyncio.sleep(0)
        operation = self.server.writer.frames[0]
        await self.server.handle_message(
            {"frame_type": "ACK", "counter": operation["counter"]}
        )
        await task
        refresh = self.server.writer.frames[-1]
        self.assertEqual((refresh["id"], refresh["start_order"], refresh["stop_order"]), (2301, 1, 2))

    async def test_output_event_updates_physical_state_without_polling(self):
        await self.server.handle_message({
            "frame_type": "EVENT", "counter": 77, "type": 770,
            "qualifier": 1, "zone": 1, "partition": 0,
        })
        self.assertTrue(self.server.physical_outputs[1])
        self.assertTrue(self.server.sirens[1])
        requests = [f for f in self.server.writer.frames if f["frame_type"] == "DATA-REQ"]
        self.assertEqual(requests, [])
        siren = [d for n, d in self.hass.bus.events if n == "pima_siren_update"][-1]
        self.assertEqual(siren, {"siren": 1, "is_on": True})

    async def test_output_event_burst_creates_no_request_storm(self):
        for counter, zone in enumerate((2, 1, 5, 3, 10, 11), start=100):
            await self.server.handle_message({
                "frame_type": "EVENT", "counter": counter, "type": 770,
                "qualifier": 1, "zone": zone, "partition": 1,
            })
        requests = [f for f in self.server.writer.frames if f["frame_type"] == "DATA-REQ"]
        self.assertEqual(requests, [])
        self.assertEqual(set(self.server.physical_outputs), {1, 2, 3, 5, 10, 11})

    async def test_nak_reports_failure(self):
        task = asyncio.create_task(self.server.send_operation(17, partition=1))
        await asyncio.sleep(0)
        counter = self.server.writer.frames[0]["counter"]
        await self.server.handle_message(
            {"frame_type": "NAK", "counter": counter, "DATA": "Wrong User Code"}
        )
        with self.assertRaisesRegex(PimaCommandError, "Wrong User Code"):
            await task

    async def test_lowercase_nak_decodes_hebrew_reason(self):
        task = asyncio.create_task(self.server.send_operation(15, partition=1))
        await asyncio.sleep(0)
        counter = self.server.writer.frames[0]["counter"]
        await self.server.handle_message({
            "frame_type": "NAK", "counter": counter, "data": "÷åã ùâåé"
        })
        with self.assertRaisesRegex(PimaCommandError, "קוד שגוי"):
            await task

    async def test_disconnect_fails_pending_command(self):
        task = asyncio.create_task(self.server.send_operation(17, partition=1))
        await asyncio.sleep(0)
        self.server._fail_pending_commands("Panel disconnected")
        with self.assertRaisesRegex(PimaCommandError, "disconnected"):
            await task

    async def test_command_timeout_reports_failure(self):
        original_timeout = pima_server.COMMAND_TIMEOUT
        pima_server.COMMAND_TIMEOUT = 0.01
        try:
            with self.assertRaisesRegex(PimaCommandError, "timed out"):
                await self.server.send_operation(17, partition=1)
        finally:
            pima_server.COMMAND_TIMEOUT = original_timeout

    def test_counter_rollover(self):
        self.assertEqual(PimaServer._next_counter(9998), 9999)
        self.assertEqual(PimaServer._next_counter(9999), 1)


if __name__ == "__main__":
    unittest.main()
