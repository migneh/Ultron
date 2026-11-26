"""One approved Home Assistant light request; no discovery or bundled security.

Operator provisioning and authenticated HA semantics remain trusted. HTTPS IP
restriction removes DNS/proxy/redirect routing but is not a network sandbox.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from ultron.core import file_safety
from ultron.core import operation_policy as policy
from ultron.paths import PROJECT_ROOT

CONFIG = PROJECT_ROOT / "config" / "api_keys.json"
_ENTITY = re.compile(r"light\.[a-z0-9_]{1,100}\Z")


def _config():
    path = file_safety.checked(CONFIG, lambda _: True)
    before = file_safety.fingerprint(path)
    if path.stat().st_size > 65536:
        raise ValueError("Configuration too large")
    with path.open("rb") as stream:
        raw = stream.read(65537)
    if len(raw) > 65536 or hashlib.sha256(raw).hexdigest() != before[-1] or file_safety.fingerprint(path) != before:
        raise ValueError("Configuration changed")
    data = json.loads(raw)
    url, token, entities = (data.get(key) for key in (
        "home_assistant_url", "home_assistant_token", "home_assistant_light_entities"))
    if not isinstance(url, str) or len(url) > 200 or any(ord(c) <= 32 for c in url):
        raise ValueError("Invalid controller")
    parts = urlsplit(url)
    ip = ipaddress.IPv4Address(parts.hostname)
    if (parts.scheme != "https" or parts.username or parts.password or parts.query or parts.fragment
            or parts.path not in ("", "/") or not any(ip in net for net in (
                ipaddress.IPv4Network("10.0.0.0/8"), ipaddress.IPv4Network("172.16.0.0/12"),
                ipaddress.IPv4Network("192.168.0.0/16")))):
        raise ValueError("Requires HTTPS RFC1918 IPv4 controller")
    port = 443 if parts.port is None else parts.port
    if not 1 <= port <= 65535:
        raise ValueError("Invalid controller port")
    endpoint = f"https://{ip}:{port}"
    if not isinstance(token, str) or not 16 <= len(token) <= 4096 or any(ord(c) < 33 or ord(c) > 126 for c in token):
        raise ValueError("Invalid token")
    if (not isinstance(entities, list) or not 1 <= len(entities) <= 32
            or any(not isinstance(e, str) or not _ENTITY.fullmatch(e) or e in {"light.all", "light.none"} for e in entities)
            or len(set(entities)) != len(entities)):
        raise ValueError("Provision explicit lights")
    return endpoint, token, tuple(entities), hashlib.sha256(raw).hexdigest()


def _validate(entity, service, settings, allowlist):
    if not isinstance(entity, str) or entity not in allowlist or service not in ("turn_on", "turn_off"):
        raise ValueError("Explicit provisioned entity and deterministic service required")
    if not isinstance(settings, dict) or set(settings) - {"rgb_color", "brightness", "color_temp"}:
        raise ValueError("Unsupported settings")
    if service == "turn_off" and settings:
        raise ValueError("Off has no settings")
    for key in ("brightness", "color_temp"):
        if key in settings and (type(settings[key]) is not int or not (1 <= settings[key] <= (255 if key == "brightness" else 500))):
            raise ValueError("Invalid light setting")
    if "rgb_color" in settings:
        rgb = settings["rgb_color"]
        if not isinstance(rgb, list) or len(rgb) != 3 or any(type(n) is not int or not 0 <= n <= 255 for n in rgb):
            raise ValueError("Invalid RGB")


def _execute(plan):
    policy.consume(plan)
    payload = plan.payload()
    endpoint, token, entities, fingerprint = _config()
    if endpoint != payload["endpoint"] or fingerprint != payload["config_digest"]:
        return "Controller configuration changed; nothing sent. Create a fresh preview."
    _validate(payload["entity"], payload["service"], payload["settings"], entities)
    import requests
    try:
        with requests.Session() as session:
            session.trust_env = False
            # Default adapter has no retries. No response body consumption.
            with session.post(endpoint + "/api/services/light/" + payload["service"],
                              json={"entity_id": payload["entity"], **payload["settings"]},
                              headers={"Authorization": "Bearer " + token}, timeout=(3, 4),
                              allow_redirects=False, stream=True, verify=True) as response:
                code = response.status_code
                if code in (200, 201):
                    return "Home Assistant accepted one lighting request; device state not verified. No retry."
                return "Home Assistant did not report acceptance; physical outcome unverified. No redirect/retry."
    except Exception:
        return "Lighting request failed or outcome unknown; check the device. Do not retry automatically."


def request(entity, service, settings=None):
    try:
        endpoint, _token, entities, digest = _config()
        settings = json.loads(json.dumps({} if settings is None else settings, allow_nan=False))
        _validate(entity, service, settings, entities)
        plan = policy.prepare("iot.single_light", (endpoint, entity), {
            "endpoint": endpoint, "entity": entity, "service": service,
            "settings": settings, "config_digest": digest})
        visible = {k: v for k, v in plan.payload().items() if k != "config_digest"}
        return policy.request(plan, title="Change one explicitly provisioned HA light",
                              detail=json.dumps(visible) + "\nMay affect physical safety, linked automations or group members. "
                              "Operator must verify this entity is a safe light, not a group/appliance. "
                              "One request; acceptance is not physical verification. No camera, lock, alerts, scan or rollback.",
                              execute=_execute)
    except Exception:
        return "Lighting unavailable or invalid: require explicit allowlisted light, deterministic on/off and provisioned HTTPS private IPv4 controller with trusted certificate; no successful change confirmed; nothing queued."
