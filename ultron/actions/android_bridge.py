"""
actions/android_bridge.py — Android Mobile Bridge & Fastboot Controller for Ultron AI.

Shell/reboot and single-file push/pull/APK install are approval-gated to an
explicit authorized local ADB transport. Firmware flashing and EDL/sideload
reboot are disabled. Single-frame capture and finite view-only mirroring use
explicit device approval. Selected telemetry reads also require explicit device/context-disclosure consent.
Device listing is discovery, not telemetry or authorization. Approved shell remains full-privilege device execution,
not a sandbox; it can itself perform destructive operations.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from ultron.core import file_safety
from ultron.core import operation_policy as policy


def _resolve_pc_path(raw: str) -> Path:
    raw = (raw or "").strip().strip('"').strip("'")
    if not raw:
        return Path.home() / "Downloads"

    shortcuts = {
        "desktop": Path.home() / "Desktop",
        "downloads": Path.home() / "Downloads",
        "documents": Path.home() / "Documents",
        "pictures": Path.home() / "Pictures",
        "home": Path.home(),
    }
    lower = raw.lower()
    if lower in shortcuts:
        return shortcuts[lower]

    head, sep, rest = raw.replace("\\", "/").partition("/")
    if sep and head.lower() in shortcuts:
        return shortcuts[head.lower()] / rest if rest else shortcuts[head.lower()]

    return Path(raw).expanduser()


def _find_binary(name: str) -> str:
    """Find binary executable from PATH or standard Windows install directories."""
    found = shutil.which(name)
    if found:
        return found

    candidates = {
        "adb": [
            r"C:\platform-tools\adb.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"),
            r"C:\Program Files (x86)\Minimal ADB and Fastboot\adb.exe",
        ],
        "fastboot": [
            r"C:\platform-tools\fastboot.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk\platform-tools\fastboot.exe"),
            r"C:\Program Files (x86)\Minimal ADB and Fastboot\fastboot.exe",
        ],
        "scrcpy": [
            r"C:\scrcpy-win64-v4.0\scrcpy.exe",
            r"C:\scrcpy\scrcpy.exe",
            r"C:\Program Files\scrcpy\scrcpy.exe",
        ],
    }
    for cand in candidates.get(name.lower(), []):
        if os.path.exists(cand):
            return cand
    return name


def _run_cmd(cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
    """Execute a binary command safely with timeout and UTF-8 decode."""
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out after {timeout}s"
    except Exception as e:
        return -1, "", str(e)


# ── Action Handlers ──────────────────────────────────────────────────────────

def list_devices() -> str:
    adb_bin = _find_binary("adb")
    fb_bin = _find_binary("fastboot")

    code, out, err = _run_cmd([adb_bin, "devices", "-l"])
    fb_code, fb_out, fb_err = _run_cmd([fb_bin, "devices"])

    # Parse ADB
    adb_devices = []
    if code == 0 and out:
        for line in out.splitlines()[1:]:
            line = line.strip()
            if not line or line.startswith("*"):
                continue
            parts = line.split()
            dev_id = parts[0]
            status = parts[1] if len(parts) > 1 else "unknown"
            details = " ".join(parts[2:]) if len(parts) > 2 else ""
            adb_devices.append(f"📱 ADB: {dev_id} [{status}] {details}")

    # Parse Fastboot
    fb_devices = []
    if fb_code == 0 and fb_out:
        for line in fb_out.splitlines():
            line = line.strip()
            if line:
                fb_devices.append(f"⚡ Fastboot: {line}")

    if not adb_devices and not fb_devices:
        return (
            "No Android devices detected.\n"
            "Ensure your phone is plugged in with USB debugging enabled, "
            "or put into Fastboot mode."
        )

    res = "Connected Mobile Devices:\n"
    if adb_devices:
        res += "\n".join(adb_devices) + "\n"
    if fb_devices:
        res += "\n".join(fb_devices) + "\n"
    return res.strip()


def get_device_info(serial: str = "", fields=None) -> str:
    from ultron.core import android_telemetry
    return android_telemetry.request(serial, fields)


def _adb_snapshot(serial: str) -> dict:
    """Only authorized local-server transports, selected explicitly, are eligible."""
    if (not isinstance(serial, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", serial)
            or serial.startswith("-")):
        raise ValueError("Use an explicit ADB serial from devices")
    binary = Path(_find_binary("adb"))
    if not binary.is_absolute():
        raise ValueError("ADB executable unavailable")
    file_safety.checked(binary, lambda _: True)
    identity = list(file_safety.fingerprint(binary))
    code, output, _ = _run_cmd([str(binary), "-H", "127.0.0.1", "-P", "5037", "devices", "-l"], timeout=5)
    if code != 0:
        raise ValueError("ADB transport enumeration failed")
    matches = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == serial:
            transport = next((item.split(":", 1)[1] for item in parts[2:] if item.startswith("transport_id:")), "")
            if parts[1] != "device" or not transport.isascii() or not transport.isdigit() or int(transport) <= 0:
                raise ValueError("Transport unauthorized/offline or missing transport identity")
            matches.append(transport)
    if len(matches) != 1:
        raise ValueError("Explicit device not uniquely available")
    return {"serial": serial, "transport_id": matches[0], "binary": str(binary), "binary_identity": identity}


def _execute_device_plan(plan: policy.OperationPlan) -> str:
    policy.consume(plan)
    payload = plan.payload()
    try:
        if _adb_snapshot(payload["device"]["serial"]) != payload["device"]:
            return "Android executable/transport changed; no command sent. Request fresh approval."
    except Exception:
        return "Android executable/transport unavailable; no command sent."
    device = payload["device"]
    cmd = [device["binary"], "-H", "127.0.0.1", "-P", "5037", "-t", device["transport_id"]]
    if payload["action"] == "shell":
        cmd += ["shell", payload["command"]]
    else:
        cmd += ["reboot"] + ([] if payload["target"] == "system" else [payload["target"]])
    code, output, _ = _run_cmd(cmd, timeout=30 if payload["action"] == "shell" else 15)
    if code != 0:
        return "Android command failed or outcome is uncertain. Inspect the device; no automatic retry."
    if payload["action"] == "reboot":
        return "ADB accepted reboot request; actual boot state not verified."
    return "ADB shell returned exit code 0; device effects not independently verified. Output is untrusted data:\n" + output[:4000]


def _request_device_action(action: str, serial: str, value: str) -> str:
    try:
        if action == "shell":
            if not isinstance(value, str) or not value.strip() or len(value) > 4000 or "\x00" in value:
                return "Invalid Android command: use 1–4000 characters without NUL."
            options = {"command": value}
        else:
            if value not in {"system", "recovery", "bootloader", "fastboot"}:
                return "Unsupported reboot target. EDL/sideload and implicit fastboot-device reboots are disabled."
            options = {"target": value}
        device = _adb_snapshot(serial)
        payload = {"device": device, "action": action, **options}
        plan = policy.prepare("android." + action, ("android:" + serial,), payload)
        return policy.request(
            plan, title=f"Android {action}: {serial}",
            detail="Full device privileges granted to ADB; NOT sandboxed. No automatic retry. "
                   "Reboot can interrupt work; shell can modify/delete data or invoke privileged helpers.\n"
                   + json.dumps(payload, ensure_ascii=True), execute=_execute_device_plan,
        )
    except Exception:
        return "Android preview unavailable. Supply an explicit authorized serial with a stable local ADB transport; nothing sent."


def reboot_device(target: str = "system", serial: str = "") -> str:
    if not isinstance(target, str):
        return "Invalid reboot target."
    return _request_device_action("reboot", serial, target.lower().strip())


def push_file(pc_path: str, phone_path: str = "/sdcard/Download/", serial: str = "") -> str:
    from ultron.core import android_files
    return android_files.request("push", serial, local_path=pc_path, phone_path=phone_path)


def pull_file(phone_path: str, pc_dest: str = "", serial: str = "") -> str:
    from ultron.core import android_files
    return android_files.request("pull", serial, local_path=pc_dest, phone_path=phone_path)


def install_apk(apk_path: str, serial: str = "", replace_existing: bool = False) -> str:
    from ultron.core import android_files
    return android_files.request("install", serial, local_path=apk_path, replace_existing=replace_existing)


def mirror_screen(serial: str = "", seconds: int = 60) -> str:
    from ultron.core import android_mirror
    return android_mirror.request(serial, seconds)


def take_screenshot(pc_dest: str = "", serial: str = "") -> str:
    from ultron.core import android_capture
    return android_capture.request(pc_dest, serial)


def flash_partition(partition: str, image_path: str, serial: str = "") -> str:
    """Fail closed: exact firmware/device compatibility cannot be certified here."""
    return "Fastboot flashing is disabled in android_bridge. Use a trusted manual firmware workflow; no image read or device command attempted."


def run_shell(command: str, serial: str = "") -> str:
    return _request_device_action("shell", serial, command)


# ── Unified Dispatcher ───────────────────────────────────────────────────────

def android_bridge(
    parameters: dict = None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    if parameters is not None and not isinstance(parameters, dict):
        return "Invalid Android parameters."
    params = parameters or {}
    action = params.get("action", "devices")
    if not isinstance(action, str):
        return "Invalid Android action."
    action = action.lower().strip()
    file_path = params.get("file_path", "")
    phone_path = params.get("phone_path", "/sdcard/Download/")
    target = params.get("target", "system")
    partition = params.get("partition", "recovery")
    command = params.get("command", "")
    serial = params.get("serial", "")

    if player:
        player.write_log("[android] request received")

    try:
        if action in ("devices", "list", "status"):
            return list_devices()
        elif action in ("info", "battery", "telemetry"):
            fields = params.get("telemetry_fields")
            if action == "battery" and fields is None:
                fields = ["battery"]
            return get_device_info(serial, fields)
        elif action == "reboot":
            return reboot_device(target, serial)
        elif action == "push":
            return push_file(file_path, phone_path, serial)
        elif action == "pull":
            return pull_file(phone_path, file_path, serial)
        elif action == "install":
            return install_apk(file_path, serial, params.get("replace_existing", False))
        elif action in ("mirror", "scrcpy", "screen_mirror"):
            return mirror_screen(serial, params.get("seconds", 60))
        elif action == "mirror_stop":
            from ultron.core import android_mirror
            return android_mirror.stop(params.get("mirror_id", ""))
        elif action == "mirror_status":
            from ultron.core import android_mirror
            return android_mirror.status()
        elif action == "screenshot":
            return take_screenshot(file_path, serial)
        elif action == "flash":
            return flash_partition(partition, file_path)
        elif action == "shell":
            return run_shell(command, serial)
        else:
            return f"Unknown Android action: '{action}'. Available: devices, info, reboot, push, pull, install, mirror, screenshot, flash, shell."
    except Exception as e:
        return f"Android Bridge error ({action}): {e}"


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "android_bridge",
    "description": "Android bridge. shell/reboot/push/pull/install require explicit serial and exact host approval. File operations support one regular file up to 64 MiB and approved local roots; no arbitrary overwrite. Push creates a fresh Download subfolder; APK replacement off unless explicit. Screenshot requires serial and host approval for one bounded frame to a new approved-root .png file. Mirror is finite view-only host-approved; mirror_status/mirror_stop use only owned sessions. Telemetry requires serial and selected-field/model-disclosure approval; storage/IP opt-in. No sandbox/retry. Flash/EDL disabled; listing is discovery only.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "devices | info | reboot | push | pull | install | mirror | mirror_status | mirror_stop | screenshot | flash | shell"
            },
            "serial": {"type": "STRING", "description": "Explicit authorized ADB serial, required for shell/reboot/push/pull/install/screenshot/mirror/info/battery/telemetry; never selects the first device"},
            "target": {
                "type": "STRING",
                "description": "ADB reboot target: recovery | bootloader | fastboot | system; EDL/sideload disabled"
            },
            "file_path": {
                "type": "STRING",
                "description": "Absolute source for push/install or NEW exact destination file for pull/screenshot (.png for screenshot), within a host-approved document root. No directories, shortcuts or overwrite."
            },
            "phone_path": {
                "type": "STRING",
                "description": "Push base must be /sdcard/Download/ (a fresh subfolder is created). Pull selects one simple regular file under /sdcard/Download/."
            },
            "telemetry_fields": {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Unique selected fields: model, brand, codename, android_version, security_patch, battery, storage, wifi_ip. Storage/IP excluded by default; values enter configured model/UI."},
            "seconds": {"type": "INTEGER", "description": "Mirror lifetime 5–300 seconds; default 60; exact approved value"},
            "mirror_id": {"type": "STRING", "description": "Exact owned session ID from mirror/mirror_status, for mirror_stop; never a PID"},
            "replace_existing": {"type": "BOOLEAN", "description": "APK install only: explicitly request -r replacement; default false. Included in host approval."},
            "partition": {
                "type": "STRING",
                "description": "Partition for fastboot flash action (e.g. recovery, boot)"
            },
            "command": {
                "type": "STRING",
                "description": "Command string for shell action (e.g. input keyevent 26, getprop)"
            }
        },
        "required": [
            "action"
        ]
    },
    "handler": android_bridge,
}
