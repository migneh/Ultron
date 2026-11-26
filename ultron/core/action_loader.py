"""
Action discovery, validation, and dispatch — the built-in twin of plugin_loader.

Every actions/*.py that exposes a module-level ``TOOL`` dict is auto-discovered
here, exactly like a drop-in plugin, so main.py never has to hardcode a tool
declaration or a dispatch branch for it. Adding a new bundled action is then the
same one-file operation as writing a plugin: define ``TOOL`` and a handler.

``TOOL`` shape (see actions/open_app.py for a live example):

    TOOL = {
        "name":        "open_app",              # unique, ^[a-zA-Z_][a-zA-Z0-9_]{0,63}$
        "description":  "...",                   # what Gemini reads to route the call
        "parameters":  {"type": "OBJECT", ...}, # Gemini function-declaration schema
        "handler":      open_app,                # the callable to run
    }

The handler is invoked through signature introspection: it receives ``parameters``
plus whichever of ``player`` / ``speak`` / ``response`` / ``session_memory`` it
actually declares. Named-field handlers explicitly opt in with
``"argument_mode": "keywords"``; this metadata is never sent to the model.

Discovery runs once at startup; import errors, validation errors, and name
collisions are logged and the offending file is skipped — they NEVER raise out
of discover_actions() and never abort the scan of the remaining files.
"""

from __future__ import annotations

import importlib.util
import inspect
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,63}$")
_DEFAULT_PARAMS = {"type": "OBJECT", "properties": {}}
_CTX_KEYS = ("player", "speak", "response", "session_memory")


# A tool may declare that the model should NOT be held up waiting for it.
# `behavior` goes to the API with the declaration; `scheduling` decides when the
# eventual result is allowed back into the conversation:
#   WHEN_IDLE  — wait for a gap in the speech (the sane default)
#   SILENT     — record it, do not prompt a reply (the tool already announced)
#   INTERRUPT  — cut in immediately (only when the answer cannot wait)
_BEHAVIORS = ("BLOCKING", "NON_BLOCKING")
_SCHEDULING = ("WHEN_IDLE", "SILENT", "INTERRUPT")


def _opt_upper(value, allowed: tuple[str, ...]) -> Optional[str]:
    v = str(value or "").strip().upper()
    return v if v in allowed else None


@dataclass
class ActionRecord:
    name: str
    description: str = ""
    parameters: dict = field(default_factory=lambda: dict(_DEFAULT_PARAMS))
    handler: Optional[Callable] = None
    file: str = ""
    valid: bool = False
    error: str = ""
    behavior: Optional[str] = None  # None = the API's default (blocking)
    scheduling: Optional[str] = None  # None = the API's default (WHEN_IDLE)
    argument_mode: str = "parameters"  # explicit opt-in for legacy named-field handlers


class ActionRegistry:
    def __init__(self, actions: dict[str, ActionRecord], logger: Callable[[str], None]):
        self._actions = actions  # name -> ActionRecord, VALID entries only
        self._all_records: list[ActionRecord] = []
        self._logger = logger

    # -- called by main.py at LiveConnectConfig build time --
    def get_tool_declarations(self) -> list[dict]:
        out = []
        for rec in self._actions.values():
            decl = {"name": rec.name, "description": rec.description, "parameters": rec.parameters}
            if rec.behavior:
                decl["behavior"] = rec.behavior
            out.append(decl)
        return out

    def has(self, name: str) -> bool:
        return name in self._actions

    def scheduling(self, name: str) -> Optional[str]:
        """How this action's result should re-enter the conversation, if it said."""
        rec = self._actions.get(name)
        return rec.scheduling if rec else None

    def names(self) -> set[str]:
        return set(self._actions.keys())

    def register_action(self, rec: ActionRecord) -> bool:
        """Dynamically hot-load a validated action record at runtime."""
        if not rec.valid:
            self._logger(f"Action hot-load rejected: {rec.name} — {rec.error}")
            return False
        self._actions[rec.name] = rec
        self._all_records.append(rec)
        self._logger(f"Action hot-loaded: {rec.name} ({rec.file})")
        return True

    # -- called by main.py from _execute_tool --
    def run(self, name: str, parameters: dict, ctx: dict | None = None) -> str:
        from ultron.core.tool_observability import OBSERVER, DispatchIssue

        def invoke():
            if not isinstance(name, str):
                raise DispatchIssue("UNAVAILABLE")
            rec = self._actions.get(name)
            if rec is None or not rec.valid or rec.handler is None:
                raise DispatchIssue("UNAVAILABLE")
            if not isinstance(parameters, dict) or (ctx is not None and not isinstance(ctx, dict)):
                raise DispatchIssue("INVALID_ARGUMENTS")
            if rec.argument_mode == "keywords":
                properties = rec.parameters.get("properties", {})
                required = rec.parameters.get("required", [])
                if (parameters.keys() - properties.keys()
                        or any(key not in parameters for key in required)):
                    raise DispatchIssue("INVALID_ARGUMENTS")
            return _call_handler(rec.handler, parameters, ctx or {}, rec.argument_mode) or "Done."

        return OBSERVER.invoke("action", name, invoke, self._logger)

    def status_snapshot(self) -> list[dict]:
        """Discovery state only: registration is not a capability/live-health test."""
        from ultron.core.tool_observability import safe_name

        records = {rec.name: rec for rec in self._all_records}
        records.update(self._actions)
        return [
            {
                "name": safe_name(rec.name),
                "state": "registered" if rec.name in self._actions and rec.valid else "rejected",
            }
            for rec in list(records.values())[:200]
        ]


def _call_handler(fn: Callable, parameters: dict, ctx: dict,
                  argument_mode: str = "parameters") -> str:
    """Invoke an explicitly declared convention, never infer it from **kwargs.

    Named-field handlers receive only explicitly declared host context. In
    particular, context must not leak into a handler's validated option bag.
    Model arguments can never supply or override host context.
    """
    sig = inspect.signature(fn)
    has_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
    if argument_mode == "keywords":
        from ultron.core.tool_observability import DispatchIssue

        if parameters.keys() & (set(_CTX_KEYS) | {"parameters"}):
            raise DispatchIssue("INVALID_ARGUMENTS")
        kwargs = dict(parameters)
        for key in _CTX_KEYS:
            param = sig.parameters.get(key)
            if param is not None and param.kind in (
                inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY
            ):
                kwargs[key] = ctx.get(key)
    elif argument_mode == "parameters":
        kwargs = {"parameters": parameters}
        for key in _CTX_KEYS:
            if has_var_kw or key in sig.parameters:
                kwargs[key] = ctx.get(key)
    else:
        raise ValueError("Unsupported action argument mode")
    result = fn(**kwargs)
    return str(result) if result is not None else ""


def _validate(module, filename: str) -> ActionRecord:
    """Returns an ActionRecord; .valid=False + .error set on any problem. Never raises."""
    tool = getattr(module, "TOOL", None)
    if not isinstance(tool, dict):
        return ActionRecord(
            name=Path(filename).stem,
            file=filename,
            error="No module-level TOOL dict (not a discoverable action).",
        )

    name = tool.get("name")
    if not isinstance(name, str) or not _NAME_RE.match(name):
        return ActionRecord(
            name=str(name or Path(filename).stem),
            file=filename,
            error="TOOL['name'] missing or not a valid identifier.",
        )

    description = tool.get("description")
    if not isinstance(description, str) or not description.strip():
        return ActionRecord(name=name, file=filename, error="TOOL['description'] missing or empty.")

    parameters = tool.get("parameters", _DEFAULT_PARAMS)
    if not isinstance(parameters, dict) or parameters.get("type") != "OBJECT":
        return ActionRecord(
            name=name,
            file=filename,
            error='TOOL[\'parameters\'] must be a dict with "type": "OBJECT".',
        )

    handler = tool.get("handler")
    if not callable(handler):
        return ActionRecord(
            name=name, file=filename, error="TOOL['handler'] missing or not callable."
        )

    argument_mode = tool.get("argument_mode", "parameters")
    if argument_mode not in ("parameters", "keywords"):
        return ActionRecord(name=name, file=filename, error="Invalid TOOL argument_mode.")
    try:
        sig = inspect.signature(handler)
        # Bind without running the handler. **kwargs-only handlers retain the
        # original parameters-dict convention unless they explicitly opt in.
        if argument_mode == "parameters":
            sample = {"parameters": {}}
        else:
            properties = parameters.get("properties", {})
            if not isinstance(properties, dict) or properties.keys() & (set(_CTX_KEYS) | {"parameters"}):
                raise ValueError("Named fields collide with reserved host arguments")
            required = parameters.get("required", [])
            if (not isinstance(required, list)
                    or any(not isinstance(key, str) or key not in properties for key in required)):
                raise ValueError("Required fields must be declared properties")
            sample = dict.fromkeys(properties)
        for key in _CTX_KEYS:
            if key in sig.parameters:
                sample[key] = None
        sig.bind(**sample)
    except (TypeError, ValueError):
        return ActionRecord(name=name, file=filename, error="Handler does not match declared argument convention/schema.")

    return ActionRecord(
        name=name,
        description=description.strip(),
        parameters=parameters,
        handler=handler,
        argument_mode=argument_mode,
        file=filename,
        valid=True,
        error="",
        behavior=_opt_upper(tool.get("behavior"), _BEHAVIORS),
        scheduling=_opt_upper(tool.get("scheduling"), _SCHEDULING),
    )


def discover_actions(
    actions_dir: Path, reserved_names: set[str] | None = None, logger: Callable[[str], None] = print
) -> ActionRegistry:
    """
    Scans actions_dir for *.py files (skips files starting with '_'). A file is
    only treated as an action if it exposes a module-level TOOL dict; files
    without one (shared helpers, capture-only modules) are silently ignored.
    Import/validation errors and name collisions are logged and the file is
    skipped — they NEVER raise out of this function.
    """
    reserved = reserved_names or set()
    actions_dir.mkdir(parents=True, exist_ok=True)
    valid: dict[str, ActionRecord] = {}
    all_records: list[ActionRecord] = []

    files = sorted(actions_dir.glob("*.py"), key=lambda p: p.name)  # deterministic order
    for path in files:
        if path.name.startswith("_"):
            continue
        try:
            module_name = f"ultron.actions.{path.stem}"
            # Reuse the already-imported module when present so handlers are the
            # same objects the rest of the app holds.
            module = sys.modules.get(module_name)
            if module is None:
                spec = importlib.util.spec_from_file_location(module_name, path)
                if spec is None or spec.loader is None:
                    raise ImportError("could not build import spec")
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                try:
                    spec.loader.exec_module(module)
                except Exception:
                    sys.modules.pop(module_name, None)
                    raise

            if getattr(module, "TOOL", None) is None:
                continue  # not an action file — a helper/capture-only module

            rec = _validate(module, path.name)

            if rec.valid and rec.name in reserved:
                rec = ActionRecord(
                    name=rec.name,
                    file=path.name,
                    error=f"Name '{rec.name}' collides with a reserved core tool — rejected.",
                )
            elif rec.valid and rec.name in valid:
                other = valid[rec.name].file
                rec = ActionRecord(
                    name=rec.name,
                    file=path.name,
                    error=f"Name '{rec.name}' already used by action '{other}' — rejected.",
                )

        except Exception:
            rec = ActionRecord(
                name=path.stem,
                file=path.name,
                error="Failed to load [IMPORT_FAILED]; exception details omitted",
            )

        all_records.append(rec)
        if rec.valid:
            valid[rec.name] = rec
            logger(f"Action loaded: {rec.name} ({path.name})")
        else:
            # Only log a rejection if the file actually tried to be an action.
            logger(f"Action rejected: {path.name} — {rec.error}")

    registry = ActionRegistry(valid, logger)
    registry._all_records = all_records
    logger(f"Action discovery complete: {len(valid)} active.")
    return registry
