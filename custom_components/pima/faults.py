"""PIMA Force fault decoding from protocol Appendix E."""

FAULT_DESCRIPTIONS = {
    1: "AC Loss", 2: "Low Battery", 3: "Panel Tamper 1 Open",
    4: "Panel Tamper 2 Open", 5: "Panel Auxiliary Voltage Fault",
    6: "PSTN Fault - DC", 7: "PSTN Fault - Dial Tone",
    8: "Panel Low DC Fault", 9: "Zone Expander Fault",
    10: "Zone Expander Tamper Open", 11: "Zone Expander Voltage Fault",
    12: "Zone Expander AC Fault", 13: "Zone Expander Low Battery",
    14: "Zone Expander Auxiliary Voltage Fault", 15: "Local Expander Fault",
    16: "Local Expander Voltage Fault", 17: "Local Expander Auxiliary Voltage Fault",
    18: "Output Expander Fault", 19: "Output Expander Tamper Open",
    20: "Output Expander Voltage Fault", 21: "Output Expander AC Fault",
    22: "Output Expander Low Battery", 23: "Output Expander Auxiliary Voltage Fault",
    24: "Keypad Fault", 25: "Keypad Tamper Open", 26: "Keypad Voltage Fault",
    27: "Wireless Receiver Fault", 28: "Wireless Receiver Tamper Open",
    29: "Wireless Receiver Voltage Fault", 30: "Station PSTN Communication Fault",
    31: "Station GPRS Fault", 32: "Station GSM Voice Communication Fault",
    33: "Station Network Communication Fault", 34: "Reserved Fault 34",
    35: "Contact PSTN Communication Fault", 36: "Contact GSM Voice Communication Fault",
    37: "Reserved Fault 37", 38: "Contact SMS Communication Fault",
    39: "GSM Transmitter Fault", 40: "GSM Link 1 Fault", 41: "GSM Link 2 Fault",
    42: "GSM SIM 1 Fault", 43: "GSM SIM 2 Fault", 44: "GSM Boot 1 Fault",
    45: "GSM Boot 2 Fault", 46: "GSM Registration 1 Fault",
    47: "GSM Registration 2 Fault", 48: "GPRS Registration 1 Fault",
    49: "GPRS Registration 2 Fault", 50: "GSM No SIM 1 Fault",
    51: "GSM No SIM 2 Fault", 52: "GSM SIM PIN Code 1 Fault",
    53: "GSM SIM PIN Code 2 Fault", 54: "GSM SIM Lock 1 Fault",
    55: "GSM SIM Lock 2 Fault", 56: "GSM Module Fault", 57: "Network Fault",
    58: "Network Invalid MAC Fault", 59: "Wireless Receiver Jamming Fault",
    60: "Zone Tamper Fault", 61: "Anti-Mask Alarm Fault",
    62: "Wireless Zone Loss Fault", 63: "Wireless Zone Fire Loss Fault",
    64: "Wireless Zone Low Battery Fault", 65: "Wireless Zone Anti-Mask Fault",
    66: "Invalid Code Alarm", 67: "External Siren Fault",
    68: "Internal Siren Fault", 69: "Time Not Set Fault",
    70: "Wireless Zone End of Life Fault", 71: "Wireless Zone Low Sensitivity Fault",
    72: "Wireless Zone Clean Me Fault", 73: "Wireless Zone Power Fault",
    74: "Wireless Zone AC Fault", 75: "Wireless Zone Trouble Fault",
    76: "Wireless Portable Unit Low Battery Fault", 77: "Wireless Siren Loss Fault",
    78: "Wireless Siren Low Battery Fault", 79: "Wireless Siren Tamper Fault",
    80: "Wireless Repeater Loss Fault", 81: "Wireless Repeater Low Battery Fault",
    82: "Wireless Repeater Tamper Fault", 83: "Wireless Repeater Jamming Fault",
    84: "Wireless Repeater AC Fault", 85: "Wireless GAS 1 Fault",
    86: "Wireless GAS 2 Fault", 87: "Wireless GAS 3 Fault",
    88: "Wireless GAS 4 Fault", 89: "Zone Expander Genuine Fault",
    90: "Wireless Receiver Genuine Fault", 91: "Output Expander Genuine Fault",
    92: "Keypad Genuine Fault", 93: "Local Expander Genuine Fault",
    94: "Reserved Fault 94", 95: "Wireless Arming Station Loss Fault",
    96: "Wireless Arming Station Low Battery Fault",
    97: "Wireless Arming Station Tamper Fault",
    98: "Wireless Arming Station Not Enrolled Fault",
}

# For communication fault IDs, the high byte identifies the transport path
# already named by the description (PSTN/GPRS/GSM/network), not a numbered
# physical device. Retain it as raw diagnostic order but do not append "#N".
FAULT_ORDER_IN_DESCRIPTION = set(range(30, 39))


def decode_fault(raw):
    """Decode one B3B2|B1B0 hexadecimal fault value."""
    text = str(raw).strip()
    value = int(text, 16)
    fault_id = value & 0xFF
    order = (value >> 8) & 0xFF
    description = FAULT_DESCRIPTIONS.get(fault_id, f"Unknown Fault {fault_id}")
    label = (
        f"{description} #{order}"
        if order and fault_id not in FAULT_ORDER_IN_DESCRIPTION
        else description
    )
    return {
        "raw": text.upper(),
        "fault_id": fault_id,
        "order": order or None,
        "description": description,
        "label": label,
    }
