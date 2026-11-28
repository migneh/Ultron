"""Scoped approved HA lighting. Bundled security and LAN discovery disabled."""
from __future__ import annotations

from ultron.core import iot_lighting

THEME_PRESETS = {
    "crimson": {
        "rgb_color": [255, 0, 0],
        "brightness": 255,
        "label": "Crimson Red Alert (Perimeter Breach / Tactical War Room)",
    },
    "cyan": {
        "rgb_color": [0, 220, 255],
        "brightness": 210,
        "label": "Cyber Matrix Cyan (Deep Code Development)",
    },
    "matrix": {
        "rgb_color": [0, 255, 120],
        "brightness": 190,
        "label": "Matrix Emerald (Cyber Sentinel Protocol)",
    },
    "amber": {
        "color_temp": 370,
        "brightness": 120,
        "label": "Warm Amber (Relaxation & Deep Focus)",
    },
    "daylight": {
        "color_temp": 153,
        "brightness": 255,
        "label": "6500K Crisp Daylight (High Productivity Overdrive)",
    },
    "stealth": {
        "state": "off",
        "label": "Stealth Blackout (All Luminaires Extinguished)",
    },
}


DISABLED = "Bundled lockdown/surveillance and network discovery disabled; no device, camera, workstation lock or alert action attempted."


def _call_ha_service(domain, service, service_data=None):
    """Legacy raw/broadcast service helper fails closed, including workspace callers."""
    return False


def set_room_theme(theme_name, entity_id=None):
    if not isinstance(theme_name, str) or theme_name not in THEME_PRESETS:
        return "Unknown theme; no successful change confirmed."
    preset = THEME_PRESETS[theme_name]
    settings = {k: v for k, v in preset.items() if k in {"rgb_color", "brightness", "color_temp"}}
    return iot_lighting.request(entity_id, "turn_off" if preset.get("state") == "off" else "turn_on", settings)


def toggle_smart_device(entity_id, state=None):
    if state not in ("on", "off"):
        return "Explicit on/off required; toggle disabled. No successful change confirmed; nothing queued."
    return iot_lighting.request(entity_id, "turn_on" if state == "on" else "turn_off")


def execute_focus_mode(entity_id=None):
    return set_room_theme("amber", entity_id) + " Android DND: unsupported; no change attempted."


def execute_lockdown_protocol():
    return DISABLED


def discover_smart_hubs():
    return "Network discovery disabled; no probe sent. Lighting requires operator provisioning."


def iot_overlord(parameters, player=None, **kwargs):
    if not isinstance(parameters, dict) or not isinstance(parameters.get("action", "status"), str):
        return "Invalid IoT request."
    action = parameters.get("action", "status").strip().lower()
    entity = parameters.get("entity_id")
    if action in ("theme", "atmosphere", "color", "lights"):
        return set_room_theme(parameters.get("theme", parameters.get("mode", "cyan")), entity)
    if action in ("focus", "focus_mode", "study", "work"):
        return execute_focus_mode(entity)
    if action in ("toggle", "switch", "control", "turn_on", "turn_off"):
        state = {"turn_on": "on", "turn_off": "off"}.get(action, parameters.get("state"))
        return toggle_smart_device(entity, state)
    if action in ("lockdown", "lock", "red_alert"):
        return DISABLED
    if action in ("discover", "scan"):
        return discover_smart_hubs()
    return "IoT lighting adapter available only with explicit operator provisioning and per-request host approval; no discovery or state query performed."


TOOL = {
    "name": "iot_overlord",
    "description": "Host-approved single provisioned Home Assistant light on/off or fixed theme; explicit entity required. No toggle, all/group defaults, switches, discovery, lockdown or surveillance. HTTP acceptance does not verify physical effect. Requires HTTPS private IPv4 controller with trusted certificate and operator light allowlist.",
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "theme | focus_mode | turn_on | turn_off | status"},
        "theme": {"type": "STRING", "description": "crimson | cyan | matrix | amber | daylight | stealth"},
        "entity_id": {"type": "STRING", "description": "Explicit operator-allowlisted light entity; no implicit all target"},
        "state": {"type": "STRING", "description": "Explicit on/off for control; no toggle"}
    }, "required": ["action"]},
    "handler": iot_overlord,
}
