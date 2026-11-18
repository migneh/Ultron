"""
core/cli.py — the command-line surface of `main.py`.

Separate module on purpose: `main.py` imports sounddevice and PyQt6 at module
level, so nothing that merely needs to *parse arguments* can import it — and a
strict flag parser is exactly what you want tested. `parse_args()` is pure: it
turns argv into a namespace or exits with status 2, and touches nothing else.

`--doctor` is deliberately NOT here. It is answered at the top of `main.py`,
before the heavy imports, because the environment check has to run in a broken
environment.
"""

from __future__ import annotations

from core import providers as _providers


def parse_args(argv: list[str] | None = None):
    """Options for the `ultron` launcher.

    Deliberately small: four things a person actually wants when starting the
    assistant. Anything else is a typo, and a typo must fail loudly rather than
    be swallowed — a silently ignored `--provder ollama` would look like Ultron
    choosing Gemini on its own.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="ultron",
        description="Start Ultron. With no arguments it uses the provider and model "
                    "you last chose in the AI MODEL panel.",
        epilog="Something not working? Run:  ultron --doctor",
    )
    parser.add_argument("--provider", metavar="NAME", default=None,
                        help="provider for this session only "
                             f"({', '.join(_providers.names())})")
    parser.add_argument("--model", metavar="NAME", default=None,
                        help="model for this session only")
    parser.add_argument("--pick", action="store_true",
                        help="open the AI MODEL panel on startup")
    args = parser.parse_args(argv)

    if args.provider and not _providers.exists(args.provider):
        parser.error(f"unknown provider '{args.provider}' — choose one of: "
                     f"{', '.join(_providers.names())}")
    return args
