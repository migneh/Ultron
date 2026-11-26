"""Launch with python -m ultron; configuration/help stay free of GUI imports."""
from __future__ import annotations

import argparse
import json


def main(argv=None):
    parser = argparse.ArgumentParser(description="Ultron desktop assistant")
    from ultron import __version__
    parser.add_argument("--version", action="version", version=f"Ultron {__version__}")
    commands = parser.add_subparsers(dest="command")
    version = commands.add_parser("version", help="show the application version without GUI/audio imports")
    version.add_argument("--json", action="store_true", help="machine-readable version output")
    doctor = commands.add_parser("doctor", help="inspect local prerequisite metadata without starting services")
    doctor.add_argument("--profile", choices=("desktop", "test", "workspace"), default="desktop")
    doctor.add_argument("--json", action="store_true", help="structured diagnostics without secret values")
    wake = commands.add_parser("wake-config", help="show or save local wake model settings; restart after changes")
    wake.add_argument("--model", help="supported builtin ID or absolute trusted .onnx file")
    wake.add_argument("--threshold", type=float, help="score >0 and <=1")
    wake.add_argument("--label", help="display label only; does not train a phrase")
    args = parser.parse_args(argv)
    if args.command == "doctor":
        from ultron.core.diagnostics import inspect
        report = inspect(args.profile)
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print(f"Ultron {__version__}: {args.profile} prerequisites " + ("present" if report["prerequisites_present"] else "incomplete"))
            for dependency in report["dependencies"]:
                print(f"  {dependency['distribution']}: {dependency['status']}")
            print("Configuration: " + report["configuration_status"])
            print(report["limits"])
        return 0 if report["prerequisites_present"] else 1
    if args.command == "version":
        print(json.dumps({"application": "ultron-ai", "version": __version__}) if args.json else f"Ultron {__version__}")
        return
    if args.command == "wake-config":
        from ultron.core.wake_word import settings
        from ultron.memory.config_manager import load_api_keys, save_wake_settings
        updates = {key: value for key, value in {
            "wake_word_model": args.model, "wake_word_threshold": args.threshold,
            "wake_word_label": args.label}.items() if value is not None}
        try:
            if updates:
                save_wake_settings(**updates)
            selected = settings(load_api_keys())
        except (ValueError, OSError) as error:
            parser.error(str(error))
        print(json.dumps({"wake_word_model": selected.model, "wake_word_threshold": selected.threshold,
                          "wake_word_label": selected.label}, indent=2))
        return
    from ultron.app import main as run
    run()


if __name__ == "__main__":
    raise SystemExit(main())
