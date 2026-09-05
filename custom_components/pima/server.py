import asyncio
import json
import logging
from datetime import datetime, UTC

from .faults import decode_fault


_LOGGER = logging.getLogger(__name__)

COMMAND_TIMEOUT = 10
FAULT_REFRESH_DELAY = 0.5
FAULT_INIT_RETRY_DELAY = 2
FAULT_INIT_RETRIES = 3
MIN_REQUEST_GAP = 0.03
CONFIG_REFRESH_DELAY = 5
ACTIVE_FAULT_RECHECK_INTERVAL = 60
FAULT_EVENT_TYPES = {
    137, 143, 144, 145, 301, 302, 305, 312, 321, 322,
    338, 342, 344, 350, 351, 381, 384,
}


class JsonFrameBuffer:
    """Extract complete JSON objects from an arbitrary TCP byte stream."""

    def __init__(self):
        self._buffer = ""

    def feed(self, data: bytes) -> list[dict]:
        """Return all complete frames in data, retaining any partial frame."""
        self._buffer += data.decode("latin-1").replace("\x00", "")
        frames = []

        while True:
            start = self._buffer.find("{")
            if start == -1:
                self._buffer = ""
                break
            if start:
                self._buffer = self._buffer[start:]

            depth = 0
            in_string = False
            escape = False
            end = None
            for index, char in enumerate(self._buffer):
                if in_string:
                    if escape:
                        escape = False
                    elif char == "\\":
                        escape = True
                    elif char == '"':
                        in_string = False
                elif char == '"':
                    in_string = True
                elif char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        end = index + 1
                        break

            if end is None:
                break

            raw = self._buffer[:end]
            self._buffer = self._buffer[end:]
            frames.append(json.loads(raw))

        return frames


class PimaCommandError(Exception):
    """Raised when the panel rejects or cannot complete a command."""


def _redact(msg: dict) -> dict:
    """Return a log-safe copy of a protocol message."""
    redacted = dict(msg)
    if "password" in redacted:
        redacted["password"] = "***"
    if "account" in redacted:
        redacted["account"] = "***"
    if redacted.get("id") in (260, 411) and "parameters" in redacted:
        redacted["parameters"] = ["***"] * len(redacted["parameters"])
    return redacted


def _decode_hebrew(s: str) -> str:
    """Re-decode a latin-1 string as Windows-1255 to recover Hebrew characters."""
    try:
        return s.encode("latin-1").decode("windows-1255")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


class PimaServer:
    def __init__(self, hass, account, password, port):
        self.hass = hass
        self.account = int(account)
        self.password = str(password)
        self.port = int(port)
        self.server = None
        self.writer = None
        self.counter = 1
        self.state = "disarmed"
        self.partition_states = {}
        self.existing_partitions = set()
        self.connected = False
        self.last_seen = None
        self.last_heartbeat = None
        self.zones = {}          # zone_num -> dict with "open", "name", etc.
        self.sirens = {number: False for number in range(1, 3)}
        self.outputs = {number: False for number in range(1, 9)}
        self.physical_outputs = {}
        self.faults = []
        self.faults_initialized = False
        self._fault_page_items = []
        self._bypass_page_values = {}
        self.users = {}
        self.last_user_by_partition = {}
        self.last_triggered = {}
        self.installed_zones = 0
        self._last_panel_counter = None
        self._pending_commands = {}
        self._pending_bypass_confirmations = {}
        self._init_done = False
        self._fault_refresh_task = None
        self._fault_init_retry_task = None
        self._configuration_refresh_task = None
        self._write_lock = asyncio.Lock()
        self._last_request_sent = 0.0
        self._last_fault_request = 0.0

    async def start(self):
        self.server = await asyncio.start_server(
            self.handle_client, "0.0.0.0", self.port
        )
        _LOGGER.info("PIMA server listening on port %s", self.port)

    async def stop(self):
        """Close the panel connection and TCP listener."""
        if self._fault_refresh_task and not self._fault_refresh_task.done():
            self._fault_refresh_task.cancel()
        if self._fault_init_retry_task and not self._fault_init_retry_task.done():
            self._fault_init_retry_task.cancel()
        if self._configuration_refresh_task and not self._configuration_refresh_task.done():
            self._configuration_refresh_task.cancel()
        self._fail_pending_commands("Integration unloaded")
        if self.writer is not None:
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except (AttributeError, OSError):
                pass
            self.writer = None
        self.connected = False
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()
            self.server = None

    async def handle_client(self, reader, writer):
        _LOGGER.info("PIMA client connected")
        previous_writer = self.writer
        self.writer = writer
        if previous_writer is not None and previous_writer is not writer:
            _LOGGER.warning("Replacing an existing PIMA client connection")
            previous_writer.close()
        self.connected = True
        self.last_seen = datetime.now(UTC)
        self._last_panel_counter = None
        self._init_done = False  # DATA-REQs sent only after first null handshake
        self.faults_initialized = False
        if self._configuration_refresh_task and not self._configuration_refresh_task.done():
            self._configuration_refresh_task.cancel()
        self._configuration_refresh_task = None
        self.hass.bus.async_fire(
            "pima_connected", {"last_seen": self.last_seen.isoformat()}
        )

        frame_buffer = JsonFrameBuffer()

        try:
            while True:
                data = await reader.read(4096)
                if not data:
                    break
                if self.writer is not writer:
                    _LOGGER.debug("Ignoring data from replaced PIMA connection")
                    break

                self.last_seen = datetime.now(UTC)
                # Decode as latin-1 (1:1 byte mapping, never fails).
                # Hebrew names from PIMA are Windows-1255; latin-1 preserves
                # the raw bytes through JSON parsing so we can re-decode them
                # correctly per field afterwards.
                try:
                    for msg in frame_buffer.feed(data):
                        _LOGGER.debug("RX: %s", _redact(msg))
                        await self.handle_message(msg, writer=writer)
                except (UnicodeError, json.JSONDecodeError) as e:
                    _LOGGER.error("Parse error: %s", e)

        except Exception as e:
            _LOGGER.exception("PIMA connection error: %s", e)

        finally:
            _LOGGER.info("PIMA client disconnected")
            writer.close()
            if self.writer is writer:
                self.connected = False
                self.writer = None
                self._fail_pending_commands("Panel disconnected")
                self.hass.bus.async_fire("pima_disconnected", {})
            else:
                _LOGGER.debug("Replaced PIMA connection closed; active client retained")

    async def handle_message(self, msg, writer=None):
        frame_type = str(msg.get("frame_type", "")).upper()

        if frame_type == "NULL":
            await self.send_ack(msg, writer=writer)
            self.last_heartbeat = datetime.now(UTC)
            self.hass.bus.async_fire(
                "pima_last_seen",
                {
                    "last_seen": self.last_seen.isoformat() if self.last_seen else None,
                    "last_heartbeat": self.last_heartbeat.isoformat(),
                },
            )
            if not self._init_done:
                self._init_done = True
                _LOGGER.info("PIMA handshake complete — sending initial DATA-REQs")
                await self._send_init_requests()
            elif self.faults and (
                asyncio.get_running_loop().time() - self._last_fault_request
                >= ACTIVE_FAULT_RECHECK_INTERVAL
            ):
                # Restore events can be lost while the panel or network is
                # restarting. Reconcile active faults on a later heartbeat so
                # stale trouble state cannot persist indefinitely.
                self._schedule_fault_refresh()
            return

        if frame_type == "EVENT":
            await self.send_ack(msg, writer=writer)
            counter = int(msg.get("counter", 0))
            if counter == self._last_panel_counter:
                _LOGGER.debug("Ignoring duplicate PIMA event counter=%s", counter)
                return
            self._last_panel_counter = counter
            self.process_event(msg)
            return

        if frame_type == "DATA":
            await self.send_ack(msg, writer=writer)
            self.process_data(msg)
            return

        if frame_type == "ACK":
            _LOGGER.debug("PIMA ACK received: %s", _redact(msg))
            self._resolve_command(msg, None)
            return

        if frame_type == "NAK":
            reason = msg.get("DATA", msg.get("data", "Command rejected"))
            reason = _decode_hebrew(str(reason))
            safe_msg = _redact(msg)
            if "DATA" in safe_msg:
                safe_msg["DATA"] = reason
            if "data" in safe_msg:
                safe_msg["data"] = reason
            _LOGGER.warning("PIMA NAK received: %s", safe_msg)
            self._resolve_command(msg, PimaCommandError(reason))
            return

        _LOGGER.warning("PIMA unknown frame type: %s", _redact(msg))

    async def send_ack(self, msg, writer=None):
        ack = {
            "frame_type": "ACK",
            "counter": int(msg.get("counter", 0)),
            "account": self.account,
            "kc": 1,
        }
        _LOGGER.debug("TX ACK: %s", _redact(ack))
        await self.send(ack, writer=writer)

    async def send(self, payload, writer=None):
        target_writer = writer or self.writer
        if not target_writer:
            _LOGGER.warning("PIMA send skipped — no active connection")
            return

        try:
            async with self._write_lock:
                is_request = str(payload.get("frame_type", "")).upper() != "ACK"
                if is_request:
                    loop = asyncio.get_running_loop()
                    remaining = MIN_REQUEST_GAP - (loop.time() - self._last_request_sent)
                    if remaining > 0:
                        await asyncio.sleep(remaining)
                raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
                _LOGGER.debug("TX RAW: %s", _redact(json.loads(raw)))
                target_writer.write(raw.encode("utf-8"))
                await target_writer.drain()
                if is_request:
                    self._last_request_sent = asyncio.get_running_loop().time()
        except Exception as e:
            _LOGGER.exception("PIMA send failed: %s", e)
            raise PimaCommandError("Failed to send command to panel") from e

    def _zone_event_payload(self, zone_num):
        """Build the full event payload for a zone from current state."""
        info = self.zones.get(zone_num, {})
        return {
            "zone": zone_num,
            "name": info.get("name", f"PIMA Zone {zone_num}"),
            "open": info.get("open", False),
            "manual_bypassed": info.get("manual_bypassed", False),
            "auto_bypassed": info.get("auto_bypassed", False),
            "alarmed": info.get("alarmed", False),
            "armed": info.get("armed", False),
            "supervision_loss": info.get("supervision_loss", False),
            "low_battery": info.get("low_battery", False),
            "short": info.get("short", False),
            "cut_tamper": info.get("cut_tamper", False),
            "soak": info.get("soak", False),
            "chime": info.get("chime", False),
            "anti_mask": info.get("anti_mask", False),
            "duress": info.get("duress", False),
            "fire": info.get("fire", False),
            "medical": info.get("medical", False),
            "panic": info.get("panic", False),
            "last_event": info.get("last_event"),
        }

    def _ensure_zone(self, zone_num):
        """Initialize zone dict if not present."""
        if zone_num not in self.zones:
            self.zones[zone_num] = {"open": False, "name": f"PIMA Zone {zone_num}"}

    def process_event(self, msg):
        t = msg.get("type")
        q = msg.get("qualifier")
        zone = msg.get("zone")
        partition = int(msg.get("partition", 1) or 1)

        if t in FAULT_EVENT_TYPES:
            self._schedule_fault_refresh()

        # CID 306 only says that panel programming changed; it does not
        # identify the setting. Refresh discoverable configuration after a
        # short delay so zone/user names and installed-zone data can settle.
        if t == 306:
            self._schedule_configuration_refresh()
            return

        # ── Arm / Disarm events ──────────────────────────────────────────────
        # CID types:
        #   400 / 401 = local/remote arm-away (q=3) or disarm (q=1)
        #   403       = auto arming (q=3 only)
        #   407       = remote arm/disarm via app/upload (q=3/1)
        #   408       = fast arming (q=3 only → armed_away)
        #   409       = key-switch/arming-zone arm (q=3) or disarm (q=1)
        #   441       = Home-x / Shabbat arming (q=3) or disarm (q=1)
        if t in (400, 401, 403, 407, 408, 409, 441):
            user_number = int(zone) if zone is not None and int(zone) > 0 else None
            user_name = self.users.get(user_number) if user_number else None
            if q == 1:
                new_state = "disarmed"
            elif q == 3:
                if t == 441:
                    new_state = "armed_home_1"   # refined by the subsequent 2310 refresh
                elif t == 407:
                    # Remote-arm CID 407 does not encode the selected arm mode.
                    # Preserve an authoritative Home/Shabbat state already
                    # returned by the post-command 2310 refresh.
                    current = self.partition_states.get(partition)
                    if current and current.startswith("armed_"):
                        new_state = current
                    else:
                        new_state = "armed_away"
                else:
                    new_state = "armed_away"
            else:
                return
            self.partition_states[partition] = new_state
            if q == 3 and user_number:
                self.last_user_by_partition[partition] = {
                    "user": user_number,
                    "user_name": user_name,
                }
            if partition == 1:
                self.state = new_state
            payload = {"state": new_state, "partition": partition}
            payload.update(
                {
                    "action": "disarmed" if q == 1 else "armed",
                    "action_at": datetime.now(UTC).isoformat(),
                    "cid_type": t,
                }
            )
            if user_number:
                payload["user"] = user_number
                if user_name:
                    payload["user_name"] = user_name
            self.hass.bus.async_fire("pima_state", payload)
            return

        # ── Zone open / close (CID 760) ──────────────────────────────────────
        # 760-1-N = zone N open, 760-3-N = zone N closed
        if t == 760 and zone is not None:
            zone_num = int(zone)
            self._ensure_zone(zone_num)
            self.zones[zone_num]["open"] = (q == 1)   # qualifier 1 = event (open), 3 = restore (closed)
            self.zones[zone_num]["last_event"] = t
            self.hass.bus.async_fire("pima_zone_update", self._zone_event_payload(zone_num))
            return

        # ── Burglary / alarm events (CID 130) ────────────────────────────────
        # 130-1-N = alarm on zone N, 130-3-N = restore
        if t == 130 and zone is not None:
            zone_num = int(zone)
            self._ensure_zone(zone_num)
            self.zones[zone_num]["alarmed"] = (q == 1)
            self.zones[zone_num]["last_event"] = t
            self.hass.bus.async_fire("pima_zone_update", self._zone_event_payload(zone_num))
            if q == 1:
                alarm_state = "triggered"
            elif q == 3:
                alarm_state = self.partition_states.get(partition, "disarmed")
            else:
                return
            if partition == 1:
                self.state = alarm_state
            if q == 1:
                armed_by = self.last_user_by_partition.get(partition, {})
                self.last_triggered[partition] = {
                    "last_triggered_zone": zone_num,
                    "last_triggered_partition": partition,
                    "last_triggered_user": armed_by.get("user"),
                    "last_triggered_user_name": armed_by.get("user_name"),
                    "last_triggered_at": datetime.now(UTC).isoformat(),
                }
            trigger_details = self.last_triggered.get(partition, {})
            self.hass.bus.async_fire(
                "pima_state",
                {
                    "state": alarm_state,
                    "partition": partition,
                    "zone": zone_num,
                    "alarm_type": t,
                    **trigger_details,
                },
            )
            return

        # 770 reports authoritative physical output state. Physical output
        # numbering is distinct from controlled-output DATA orders 34..41.
        if t == 770 and zone is not None:
            output_number = int(zone)
            is_on = q == 1
            self.physical_outputs[output_number] = is_on
            self.hass.bus.async_fire(
                "pima_physical_output_update",
                {"output": output_number, "is_on": is_on},
            )
            # Protocol physical outputs 1 and 2 are external/internal sirens.
            if output_number in self.sirens:
                self.sirens[output_number] = is_on
                self.hass.bus.async_fire(
                    "pima_siren_update",
                    {"siren": output_number, "is_on": is_on},
                )
            return

        # ── Zone bypass (CID 570) ────────────────────────────────────────────
        # 570-1-N = bypass zone N, 570-3-N = remove bypass
        if t == 570 and zone is not None:
            zone_num = int(zone)
            self._ensure_zone(zone_num)
            self.zones[zone_num]["manual_bypassed"] = (q == 1)   # q=1 = bypassed, q=3 = restored
            self.zones[zone_num]["last_event"] = t
            self.hass.bus.async_fire("pima_zone_update", self._zone_event_payload(zone_num))
            return

        # ── Wireless zone supervision/battery/tamper ─────────────────────────
        if t == 381 and zone is not None:   # 381 = wireless supervision loss
            zone_num = int(zone)
            self._ensure_zone(zone_num)
            self.zones[zone_num]["supervision_loss"] = (q == 1)
            self.zones[zone_num]["last_event"] = t
            self.hass.bus.async_fire("pima_zone_update", self._zone_event_payload(zone_num))
            return

        if t == 384 and zone is not None:   # 384 = wireless low battery
            zone_num = int(zone)
            self._ensure_zone(zone_num)
            self.zones[zone_num]["low_battery"] = (q == 1)
            self.zones[zone_num]["last_event"] = t
            self.hass.bus.async_fire("pima_zone_update", self._zone_event_payload(zone_num))
            return

        if t == 144 and zone is not None:   # 144 = cut/short (tamper)
            zone_num = int(zone)
            self._ensure_zone(zone_num)
            self.zones[zone_num]["cut_tamper"] = (q == 1)
            self.zones[zone_num]["last_event"] = t
            self.hass.bus.async_fire("pima_zone_update", self._zone_event_payload(zone_num))
            return

        # ── Special zone alarm types ─────────────────────────────────────────
        if t == 110 and zone is not None:   # Fire alarm
            zone_num = int(zone)
            self._ensure_zone(zone_num)
            self.zones[zone_num]["fire"] = (q == 1)
            self.zones[zone_num]["last_event"] = t
            self.hass.bus.async_fire("pima_zone_update", self._zone_event_payload(zone_num))
            return

        if t == 100 and zone is not None:   # Medical alarm
            zone_num = int(zone)
            self._ensure_zone(zone_num)
            self.zones[zone_num]["medical"] = (q == 1)
            self.zones[zone_num]["last_event"] = t
            self.hass.bus.async_fire("pima_zone_update", self._zone_event_payload(zone_num))
            return

        if t in (120, 122) and zone is not None:   # Panic / silent panic
            zone_num = int(zone)
            self._ensure_zone(zone_num)
            self.zones[zone_num]["panic"] = (q == 1)
            self.zones[zone_num]["last_event"] = t
            self.hass.bus.async_fire("pima_zone_update", self._zone_event_payload(zone_num))
            return

        if t == 121 and zone is not None:   # Duress
            zone_num = int(zone)
            self._ensure_zone(zone_num)
            self.zones[zone_num]["duress"] = (q == 1)
            self.zones[zone_num]["last_event"] = t
            self.hass.bus.async_fire("pima_zone_update", self._zone_event_payload(zone_num))
            return

        _LOGGER.debug("Unhandled PIMA event: type=%s qualifier=%s zone=%s", t, q, zone)

    def process_data(self, msg):
        data_id = msg.get("id")
        params = msg.get("parameters", [])
        start_order = int(msg.get("start_order", 1))

        _LOGGER.debug(
            "PIMA DATA received: id=%s start_order=%s parameter_count=%s more=%s",
            data_id, start_order, len(params), msg.get("more", "no"),
        )

        # ── 2310: Partition key status ───────────────────────────────────────
        # Response is one value per partition (start_order = partition index).
        # Values: 1=not exist, 2=disarmed, 3=armed_away, 4=home1,
        #         5=home2, 6=home3, 7=home4, 8=shabbat_on, 9=shabbat_off
        if data_id == 2310 and params:
            state_map = {
                1: None,             # partition does not exist
                2: "disarmed",
                3: "armed_away",
                4: "armed_home_1",
                5: "armed_home_2",
                6: "armed_home_3",
                7: "armed_home_4",
                8: "armed_shabbat",
                9: "armed_shabbat",
            }
            discovered = []
            for i, raw in enumerate(params):
                code = int(raw)
                new_state = state_map.get(code)
                if new_state is not None:
                    partition = start_order + i
                    discovered.append(partition)
                    self.existing_partitions.add(partition)
                    self.partition_states[partition] = new_state
                    if partition == 1:
                        self.state = new_state
                    self.hass.bus.async_fire(
                        "pima_state",
                        {"state": new_state, "partition": partition},
                    )
                else:
                    self.existing_partitions.discard(start_order + i)
                    self.partition_states.pop(start_order + i, None)
            self.hass.bus.async_fire(
                "pima_partitions_updated",
                {"partitions": sorted(self.existing_partitions)},
            )
            return

        # 2301 orders 1..2 are sirens; 34..41 are controlled outputs 1..8.
        if data_id == 2301:
            for i, raw in enumerate(params):
                order = start_order + i
                try:
                    is_on = int(str(raw)) != 0
                except (TypeError, ValueError):
                    _LOGGER.warning("Invalid 2301 value for order %s", order)
                    continue
                if 1 <= order <= 2:
                    self.sirens[order] = is_on
                    self.hass.bus.async_fire(
                        "pima_siren_update", {"siren": order, "is_on": is_on}
                    )
                elif 34 <= order <= 41:
                    output = order - 33
                    self.outputs[output] = is_on
                    self.hass.bus.async_fire(
                        "pima_output_update", {"output": output, "is_on": is_on}
                    )
            return

        # 2250: paginated active faults. Low byte is fault ID; high byte is
        # an optional module/zone order (Appendix E).
        if data_id == 2250:
            if start_order == 1:
                self._fault_page_items = []
            for raw in params:
                try:
                    self._fault_page_items.append(decode_fault(raw))
                except (TypeError, ValueError):
                    _LOGGER.warning("Invalid 2250 fault value: %r", raw)
            if str(msg.get("more", "no")).lower() == "yes":
                if params:
                    self.hass.async_create_task(
                        self._request_faults(start_order + len(params))
                    )
                else:
                    _LOGGER.error("2250 returned more=yes with no parameters")
            else:
                self.faults = list(self._fault_page_items)
                self.faults_initialized = True
                self.hass.bus.async_fire(
                    "pima_faults_updated",
                    {
                        "problem": bool(self.faults),
                        "fault_count": len(self.faults),
                        "active_faults": [fault["label"] for fault in self.faults],
                        "fault_details": list(self.faults),
                    },
                )
                _LOGGER.info("PIMA active faults: %s", len(self.faults))
            return

        # 2150: one positional value per zone ("1" bypassed, "0" normal).
        if data_id == 2150:
            if start_order == 1:
                self._bypass_page_values = {}
            for i, raw in enumerate(params):
                zone_num = start_order + i
                try:
                    bypassed = bool(int(str(raw)))
                except (TypeError, ValueError):
                    _LOGGER.warning("Invalid 2150 value for zone %s: %r", zone_num, raw)
                    continue
                self._bypass_page_values[zone_num] = bypassed
                self._ensure_zone(zone_num)
                self.zones[zone_num]["manual_bypassed"] = bypassed
                confirmation = self._pending_bypass_confirmations.get(zone_num)
                if confirmation:
                    expected, future = confirmation
                    if not future.done():
                        if bypassed == expected:
                            future.set_result(bypassed)
                        else:
                            future.set_exception(PimaCommandError(
                                f"Zone {zone_num} bypass was acknowledged but not "
                                "applied by the panel; the zone may be permanently "
                                "disabled or otherwise unavailable"
                            ))
            if str(msg.get("more", "no")).lower() == "yes":
                if params:
                    next_start = start_order + len(params)
                    self.hass.async_create_task(
                        self._request_bypass_status(next_start, self.installed_zones)
                    )
                else:
                    _LOGGER.error("2150 returned more=yes with no parameters")
            else:
                for zone_num in sorted(self._bypass_page_values):
                    self.hass.bus.async_fire(
                        "pima_zone_update", self._zone_event_payload(zone_num)
                    )
                _LOGGER.info(
                    "PIMA bypassed zones: %s",
                    sum(self._bypass_page_values.values()),
                )
            return

        # 411: paginated user names. Names are sensitive and redacted by
        # _redact before protocol messages are written to DEBUG logs.
        if data_id == 411:
            if start_order == 1:
                self.users = {}
            for i, raw_name in enumerate(params):
                user_number = start_order + i
                name = _decode_hebrew(str(raw_name)).strip()
                if name:
                    self.users[user_number] = name
            if str(msg.get("more", "no")).lower() == "yes":
                if params:
                    self.hass.async_create_task(
                        self._request_user_names(start_order + len(params))
                    )
                else:
                    _LOGGER.error("411 returned more=yes with no parameters")
            else:
                self.hass.bus.async_fire(
                    "pima_users_updated", {"count": len(self.users)}
                )
                _LOGGER.info("PIMA user names loaded: %s", len(self.users))
            return

        # ── 2148: Number of installed zones ──────────────────────────────────
        if data_id == 2148 and params:
            try:
                self.installed_zones = int(params[0])
                _LOGGER.info("Installed zones: %s", self.installed_zones)

                for zone in range(1, self.installed_zones + 1):
                    self._ensure_zone(zone)

                self.hass.bus.async_fire(
                    "pima_zones_initialized",
                    {"count": self.installed_zones},
                )

                # Chain: now request zone status and zone names
                self.hass.async_create_task(self._request_zone_status())
                self.hass.async_create_task(self._request_zone_names())
                self.hass.async_create_task(
                    self._request_bypass_status(1, self.installed_zones)
                )
            except Exception as e:
                _LOGGER.error("Failed parsing installed zones: %s", e)
            return

        # ── 260: Zone names ───────────────────────────────────────────────────
        # Each param is the name for zone (start_order + index).
        if data_id == 260 and params:
            for i, name in enumerate(params):
                zone_num = start_order + i
                self._ensure_zone(zone_num)
                clean_name = _decode_hebrew(name).strip()
                self.zones[zone_num]["name"] = clean_name if clean_name else f"PIMA Zone {zone_num}"
                _LOGGER.debug("Zone %s name updated", zone_num)
            if msg.get("more") == "yes":
                last_zone = start_order + len(params) - 1
                self.hass.async_create_task(
                    self._request_zone_names(start_order=last_zone + 1)
                )
            else:
                # All zone names received — notify binary_sensor to update registry
                self.hass.bus.async_fire("pima_zone_names_updated", {})
            return

        # ── 2149: Zone status ─────────────────────────────────────────────────
        # Each param is a hex string encoding both zone number and status bits:
        #   Format:  B B6 B5 B4 B3 B2 | B1 B0
        #            [status bits]     | [zone number (0-based index)]
        #
        # The zone number occupies the LOW 2 hex digits (1 byte = bits 0..7),
        # and the status bits occupy the remaining HIGH bytes.
        #
        # Example: "80005"  → zone number = 0x05 = 5, status = 0x800 (bit 11 = Open)
        #          "800C"   → zone number = 0x0C = 12, status = 0x80 (bit 7 = Manual Bypassed)
        #          "A0019"  → zone number = 0x19 = 25, status = 0xA00 (bits 9+11 = Alarmed+Open)
        #          "81B"    → zone number = 0x1B = 27, status = 0x8 (bit 3 = Cut/Tamper)
        #
        # Per Appendix C bit definitions:
        #   0: Supervision Loss   8: Auto Bypassed
        #   1: Low Battery        9: Alarmed
        #   2: Short (wired)     10: Armed
        #   3: Cut (Tamper)      11: Open
        #   4: Soak              12: Duress
        #   5: Chime             13: Fire
        #   6: Anti Mask         14: Medical
        #   7: Manual Bypassed   15: Panic
        if data_id == 2149:
            try:
                BIT_SUPERVISION  = 0
                BIT_LOW_BATTERY  = 1
                BIT_SHORT        = 2
                BIT_CUT_TAMPER   = 3
                BIT_SOAK         = 4
                BIT_CHIME        = 5
                BIT_ANTI_MASK    = 6
                BIT_MAN_BYPASS   = 7
                BIT_AUTO_BYPASS  = 8
                BIT_ALARMED      = 9
                BIT_ARMED        = 10
                BIT_OPEN         = 11
                BIT_DURESS       = 12
                BIT_FIRE         = 13
                BIT_MEDICAL      = 14
                BIT_PANIC        = 15

                for raw in params:
                    value = int(str(raw), 16)
                    zone_num = value & 0xFF          # low byte = zone number
                    status   = (value >> 8) & 0xFFFF # high bytes = status bits

                    if zone_num == 0:
                        continue
                    if self.installed_zones and zone_num > self.installed_zones:
                        continue

                    self._ensure_zone(zone_num)
                    z = self.zones[zone_num]

                    def bit(n):
                        return bool(status & (1 << n))

                    z["supervision_loss"] = bit(BIT_SUPERVISION)
                    z["low_battery"]      = bit(BIT_LOW_BATTERY)
                    z["short"]            = bit(BIT_SHORT)
                    z["cut_tamper"]       = bit(BIT_CUT_TAMPER)
                    z["soak"]             = bit(BIT_SOAK)
                    z["chime"]            = bit(BIT_CHIME)
                    z["anti_mask"]        = bit(BIT_ANTI_MASK)
                    z["manual_bypassed"]  = bit(BIT_MAN_BYPASS)
                    z["auto_bypassed"]    = bit(BIT_AUTO_BYPASS)
                    z["alarmed"]          = bit(BIT_ALARMED)
                    z["armed"]            = bit(BIT_ARMED)
                    z["open"]             = bit(BIT_OPEN)
                    z["duress"]           = bit(BIT_DURESS)
                    z["fire"]             = bit(BIT_FIRE)
                    z["medical"]          = bit(BIT_MEDICAL)
                    z["panic"]            = bit(BIT_PANIC)

                    self.hass.bus.async_fire(
                        "pima_zone_update",
                        self._zone_event_payload(zone_num),
                    )
                    _LOGGER.debug(
                        "Zone %s status updated: open=%s alarmed=%s bypassed=%s",
                        zone_num, z["open"], z["alarmed"], z["manual_bypassed"],
                    )

                # Handle pagination ("more":"yes")
                if msg.get("more") == "yes":
                    _LOGGER.debug("2149 has more data — sparse response retained.")
                else:
                    # 2149 is sparse — zones absent from the response are closed with no flags.
                    # Fire a zone_update for them so they become available in HA.
                    updated_zones = set()
                    for raw in params:
                        try:
                            updated_zones.add(int(str(raw), 16) & 0xFF)
                        except Exception:
                            pass

                    for zone_num in range(1, self.installed_zones + 1):
                        if zone_num not in updated_zones:
                            self._ensure_zone(zone_num)
                            # Confirm all flags are False (clean closed state)
                            z = self.zones[zone_num]
                            for flag in ("open", "alarmed", "manual_bypassed", "auto_bypassed",
                                         "supervision_loss", "low_battery", "short", "cut_tamper",
                                         "soak", "chime", "anti_mask", "duress", "fire", "medical", "panic"):
                                z[flag] = False
                            self.hass.bus.async_fire(
                                "pima_zone_update",
                                self._zone_event_payload(zone_num),
                            )

            except Exception as e:
                _LOGGER.error("Failed parsing zone status 2149: %s | params=%s", e, params)
            return

    async def _send_init_requests(self):
        """Send initial DATA-REQs after the panel handshake (first null frame)."""
        try:
            # 2310 = partition key status
            await self.send({
                "frame_type": "DATA-REQ",
                "counter": self._claim_counter(),
                "account": self.account,
                "password": self.password,
                "id": 2310,
                "start_order": 1,
                "stop_order": 16,
            })
            _LOGGER.debug("TX DATA-REQ 2310 (partition status)")

            # 2148 = installed zones count (2149 zone status is chained after this responds)
            await self.send({
                "frame_type": "DATA-REQ",
                "counter": self._claim_counter(),
                "account": self.account,
                "password": self.password,
                "id": 2148,
                "start_order": 1,
                "stop_order": 1,
            })
            _LOGGER.debug("TX DATA-REQ 2148 (installed zones)")

            await self._request_output_status(1, 2)
            await self._request_output_status(34, 41)
            await self._request_faults(1)
            if self._fault_init_retry_task and not self._fault_init_retry_task.done():
                self._fault_init_retry_task.cancel()
            self._fault_init_retry_task = self.hass.async_create_task(
                self._retry_fault_initialization()
            )
            await self._request_user_names(1)

        except Exception as e:
            _LOGGER.exception("Init DATA-REQ send failed: %s", e)

    async def _request_zone_status(self):
        """Request current zone status (sparse — only non-closed zones returned)."""
        _LOGGER.debug("Requesting zone status (2149)")
        await self.send({
            "frame_type": "DATA-REQ",
            "counter": self._claim_counter(),
            "account": self.account,
            "password": self.password,
            "id": 2149,
            "start_order": 1,
        })

    async def _request_zone_names(self, start_order=1):
        """Request zone names from the panel in batches of up to 64."""
        stop_order = min(start_order + 63, self.installed_zones)
        _LOGGER.debug("Requesting zone names %s to %s", start_order, stop_order)
        await self.send({
            "frame_type": "DATA-REQ",
            "counter": self._claim_counter(),
            "account": self.account,
            "password": self.password,
            "id": 260,
            "start_order": start_order,
            "stop_order": stop_order,
        })

    async def send_operation(self, optype, partition=1, order=None):
        if not self.writer:
            raise PimaCommandError("Panel is not connected")

        counter = self._claim_counter()
        payload = {
            "frame_type": "OPERATION",
            "counter": counter,
            "account": self.account,
            "password": self.password,
            "optype": int(optype),
            "opclass": 1,
            "partition": int(partition),
        }

        # Validated FORCE traffic requires order=1 for arming modes. Disarm
        # uses order=0 on the tested firmware.
        # Output operations (35/36) use a specific output number as order.
        if order is not None:
            payload["order"] = int(order)
        elif int(optype) in (12, 13, 14, 15, 16, 43):
            payload["order"] = 1
        elif int(optype) == 17:
            payload["order"] = 0

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._pending_commands[counter] = future
        try:
            await self.send(payload)
            await asyncio.wait_for(future, timeout=COMMAND_TIMEOUT)
            if int(optype) in (12, 13, 14, 15, 16, 17, 43):
                await self._request_partition_status()
            elif int(optype) in (35, 36):
                requested_order = int(order or 0)
                if 1 <= requested_order <= 2:
                    await self._request_output_status(1, 2)
                elif 34 <= requested_order <= 41:
                    await self._request_output_status(34, 41)
        except TimeoutError as err:
            raise PimaCommandError(
                f"Panel command counter {counter} timed out"
            ) from err
        finally:
            self._pending_commands.pop(counter, None)

    async def send_zone_bypass(self, zone, bypassed):
        """Set one zone bypass value and verify the resulting panel state."""
        zone = int(zone)
        if zone < 1 or zone > 144:
            raise PimaCommandError(f"Invalid zone number {zone}")
        if self.installed_zones and zone > self.installed_zones:
            raise PimaCommandError(f"Zone {zone} is not installed")
        if not self.writer:
            raise PimaCommandError("Panel is not connected")

        counter = self._claim_counter()
        payload = {
            "frame_type": "DATA",
            "counter": counter,
            "account": self.account,
            "password": self.password,
            "id": 2150,
            "start_order": zone,
            "parameters": ["1" if bypassed else "0"],
        }
        future = asyncio.get_running_loop().create_future()
        confirmation = asyncio.get_running_loop().create_future()
        self._pending_commands[counter] = future
        self._pending_bypass_confirmations[zone] = (bool(bypassed), confirmation)
        try:
            await self.send(payload)
            await asyncio.wait_for(future, timeout=COMMAND_TIMEOUT)
            await self._request_bypass_status(zone, zone)
            await asyncio.wait_for(confirmation, timeout=COMMAND_TIMEOUT)
        except TimeoutError as err:
            raise PimaCommandError(
                f"Panel bypass command for zone {zone} timed out"
            ) from err
        finally:
            self._pending_commands.pop(counter, None)
            current = self._pending_bypass_confirmations.get(zone)
            if current and current[1] is confirmation:
                self._pending_bypass_confirmations.pop(zone, None)

    def _resolve_command(self, msg, error):
        future = self._pending_commands.get(int(msg.get("counter", 0)))
        if not future or future.done():
            return
        if error:
            future.set_exception(error)
        else:
            future.set_result(msg)

    def _fail_pending_commands(self, reason):
        for future in self._pending_commands.values():
            if not future.done():
                future.set_exception(PimaCommandError(reason))
        for _expected, future in self._pending_bypass_confirmations.values():
            if not future.done():
                future.set_exception(PimaCommandError(reason))

    async def _request_partition_status(self):
        """Refresh authoritative partition state after an arm/disarm command."""
        await self.send({
            "frame_type": "DATA-REQ",
            "counter": self._claim_counter(),
            "account": self.account,
            "password": self.password,
            "id": 2310,
            "start_order": 1,
            "stop_order": 16,
        })

    async def _request_output_status(self, start_order, stop_order):
        """Refresh siren or controlled-output status."""
        await self.send({
            "frame_type": "DATA-REQ",
            "counter": self._claim_counter(),
            "account": self.account,
            "password": self.password,
            "id": 2301,
            "start_order": int(start_order),
            "stop_order": int(stop_order),
        })

    async def _request_faults(self, start_order=1):
        """Request active panel faults starting at the given list index."""
        self._last_fault_request = asyncio.get_running_loop().time()
        await self.send({
            "frame_type": "DATA-REQ",
            "counter": self._claim_counter(),
            "account": self.account,
            "password": self.password,
            "id": 2250,
            "start_order": int(start_order),
        })

    async def async_refresh_faults(self):
        """Request a fresh authoritative active-fault list from the panel."""
        if not self.writer:
            raise PimaCommandError("Panel is not connected")
        await self._request_faults(1)

    async def _request_bypass_status(self, start_order=1, stop_order=None):
        """Request positional bypass state for a zone range."""
        payload = {
            "frame_type": "DATA-REQ",
            "counter": self._claim_counter(),
            "account": self.account,
            "password": self.password,
            "id": 2150,
            "start_order": int(start_order),
        }
        if stop_order is not None:
            payload["stop_order"] = int(stop_order)
        await self.send(payload)

    async def _request_user_names(self, start_order=1):
        """Request PIMA user names in pages, up to the documented 32 users."""
        await self.send({
            "frame_type": "DATA-REQ",
            "counter": self._claim_counter(),
            "account": self.account,
            "password": self.password,
            "id": 411,
            "start_order": int(start_order),
            "stop_order": 32,
        })

    def _schedule_fault_refresh(self):
        """Coalesce fault event bursts into one 2250 refresh."""
        if self._fault_refresh_task and not self._fault_refresh_task.done():
            return
        self._fault_refresh_task = self.hass.async_create_task(
            self._delayed_fault_refresh()
        )

    async def _delayed_fault_refresh(self):
        try:
            await asyncio.sleep(FAULT_REFRESH_DELAY)
            await self._request_faults(1)
        finally:
            self._fault_refresh_task = None

    def _schedule_configuration_refresh(self):
        """Coalesce generic CID 306 events into one safe configuration refresh."""
        if self._configuration_refresh_task and not self._configuration_refresh_task.done():
            return
        self._configuration_refresh_task = self.hass.async_create_task(
            self._delayed_configuration_refresh()
        )

    async def _delayed_configuration_refresh(self):
        try:
            await asyncio.sleep(CONFIG_REFRESH_DELAY)
            if not self.connected:
                return
            _LOGGER.info("PIMA programming changed; refreshing panel configuration")
            await self._request_partition_status()
            await self.send({
                "frame_type": "DATA-REQ",
                "counter": self._claim_counter(),
                "account": self.account,
                "password": self.password,
                "id": 2148,
                "start_order": 1,
                "stop_order": 1,
            })
            await self._request_user_names(1)
        except asyncio.CancelledError:
            return
        except PimaCommandError as err:
            _LOGGER.warning("PIMA configuration refresh failed: %s", err)
        finally:
            self._configuration_refresh_task = None

    async def _retry_fault_initialization(self):
        """Retry read-only fault discovery when startup parsing is rejected."""
        try:
            for attempt in range(1, FAULT_INIT_RETRIES + 1):
                await asyncio.sleep(FAULT_INIT_RETRY_DELAY)
                if self.faults_initialized or not self.connected:
                    return
                _LOGGER.warning(
                    "PIMA fault status not initialized; retrying 2250 (%s/%s)",
                    attempt,
                    FAULT_INIT_RETRIES,
                )
                await self._request_faults(1)
        except asyncio.CancelledError:
            return

    @staticmethod
    def _next_counter(counter):
        counter += 1
        if counter > 9999:
            counter = 1
        return counter

    def _claim_counter(self):
        """Reserve an outbound counter before any coroutine can interleave."""
        counter = self.counter
        self.counter = self._next_counter(counter)
        return counter
