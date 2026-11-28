"""
media_controller.py — Universal Media & Audio Controller for Ultron AI.
Control Spotify, YouTube, VLC, browser media, and Windows media players from voice commands.
Auto-discovered by core/action_loader.py.
"""
from __future__ import annotations

import platform
import subprocess

try:
    import pyautogui
    _PYAUTOGUI = True
except Exception:
    # Headless display initialization can fail even when installed.
    _PYAUTOGUI = False

_OS = platform.system()


def _media_key(key: str, count: int = 1) -> str:
    if not _PYAUTOGUI:
        return "Media key unavailable: no usable desktop keyboard backend."
    try:
        for _ in range(count):
            pyautogui.press(key)
        return f"Media key submitted: {key}. Playback/audio state not verified."
    except Exception:
        return "Media key submission failed or is uncertain; audio state not verified."


def media_play_pause() -> str:
    return _media_key("playpause")


def media_next() -> str:
    return _media_key("nexttrack")


def media_prev() -> str:
    return _media_key("prevtrack")


def media_stop() -> str:
    return _media_key("stop")


def media_mute() -> str:
    return "Explicit mute unavailable: keyboard toggle cannot establish mute state. Use toggle_mute explicitly."


def media_unmute() -> str:
    return "Explicit unmute unavailable: keyboard toggle cannot establish mute state. Use toggle_mute explicitly."


def _windows_endpoint():
    from ctypes import POINTER, cast

    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    devices = AudioUtilities.GetSpeakers()
    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(interface, POINTER(IAudioEndpointVolume))


def media_volume_set(level: int) -> str:
    if type(level) is not int or not 0 <= level <= 100:
        return "Invalid volume level: use an integer from 0 to 100."
    if _OS == "Windows":
        try:
            endpoint = _windows_endpoint()
            endpoint.SetMasterVolumeLevelScalar(level / 100, None)
        except Exception:
            return "Volume request failed or is uncertain: Windows audio backend unavailable or returned an error."
        try:
            actual = round(endpoint.GetMasterVolumeLevelScalar() * 100)
        except Exception:
            return f"Volume request submitted: {level}%. Readback unavailable; state not verified."
        if abs(actual - level) > 1:
            return f"Volume target not verified: requested {level}%, read back {actual}%."
        return f"Volume readback: {actual}% (requested {level}%). Mute state unchanged."
    if _OS == "Darwin":
        try:
            subprocess.run(["osascript", "-e", f"set volume output volume {level}"],
                           capture_output=True, check=True, timeout=5)
        except Exception:
            return "Volume request failed or is uncertain: macOS audio command did not complete successfully."
        return f"Volume request submitted: {level}%. Audio state not verified."
    return f"Setting absolute volume is unsupported on {_OS}; no change attempted."


def media_controller_handler(parameters: dict, **kwargs) -> str:
    action = str(parameters.get("action", "play_pause")).lower().strip()
    volume = parameters.get("volume", parameters.get("value"))
    handlers = {
        "play": media_play_pause, "pause": media_play_pause,
        "play_pause": media_play_pause, "toggle": media_play_pause,
        "next": media_next, "next_track": media_next, "skip": media_next,
        "prev": media_prev, "previous": media_prev, "previous_track": media_prev,
        "replay": media_prev, "back": media_prev, "stop": media_stop,
        "mute": media_mute, "unmute": media_unmute,
    }
    if action in handlers:
        return handlers[action]()
    if action == "toggle_mute":
        return _media_key("volumemute")
    if action in ("volume_set", "set_volume"):
        return media_volume_set(volume)
    if action == "volume_up":
        return _media_key("volumeup", 5)
    if action == "volume_down":
        return _media_key("volumedown", 5)
    return f"Unknown media action: '{action}'."


TOOL = {
    "name": "media_controller",
    "description": (
        "Controls media playback and audio on the PC. "
        "Use when user asks to: play music, pause music, skip to next song, "
        "previous track, stop playback or set volume. Keyboard commands are toggles/requests, not verified state. Explicit mute/unmute unsupported; toggle_mute is available. Absolute volume supports Windows/macOS only."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "play_pause | next | previous | stop | mute (unsupported) | unmute (unsupported) | toggle_mute | volume_set | volume_up | volume_down"
            },
            "volume": {
                "type": "INTEGER",
                "description": "Target volume percentage 0-100 (for volume_set)"
            }
        },
        "required": ["action"]
    },
    "handler": media_controller_handler
}
