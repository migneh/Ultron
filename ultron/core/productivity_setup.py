"""Host-only setup. Run on the desktop where Ultron and the OS keyring live."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from ultron.core import google_workspace as workspace
from ultron.core import productivity_store as store


def configure_root(path, *, remove=False):
    candidate = Path(path).expanduser().resolve(strict=not remove)
    if not remove and (not candidate.is_dir() or candidate == Path(candidate.anchor)):
        raise ValueError("Choose a specific existing document directory, not a filesystem root.")
    roots = store.setting("document_roots", [])
    roots = [root for root in roots if root != str(candidate)]
    if not remove:
        if len(roots) >= 20:
            raise ValueError("At most 20 document roots.")
        roots.append(str(candidate))
    store.set_setting("document_roots", roots)
    return {"document_roots": roots}


def connect(client_secrets, *, drive=False, calendar=False, calendar_id="primary", file_ids=None, allow_model_context=False):
    from google_auth_oauthlib.flow import InstalledAppFlow
    if store.setting("workspace", {}):
        raise ValueError("Disconnect the existing Workspace installation before replacing its account/scopes.")
    config = {"drive": drive, "calendar": calendar, "calendar_id": calendar_id, "file_ids": file_ids or [],
              "model_context_allowed": allow_model_context}
    if not workspace.scopes(config) or len(config["file_ids"]) > 50 or any(not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", item) for item in config["file_ids"]):
        raise ValueError("Choose at least one service and at most 50 exact Drive file IDs.")
    if not isinstance(calendar_id, str) or not 1 <= len(calendar_id) <= 254:
        raise ValueError("Invalid calendar ID.")
    secret_path = Path(client_secrets).expanduser()
    with secret_path.open("rb") as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise ValueError("Client configuration too large.")
    client = json.loads(raw).get("installed", {})
    if client.get("token_uri") != workspace.TOKEN_URI or client.get("auth_uri") != "https://accounts.google.com/o/oauth2/auth":
        raise ValueError("Use a Google Desktop OAuth client configuration with the official auth/token endpoints.")
    keyring = workspace.backend()  # fail before browser/consent if no secure store
    flow = InstalledAppFlow.from_client_config({"installed": client}, scopes=workspace.scopes(config), autogenerate_code_verifier=True)
    credentials = flow.run_local_server(host="127.0.0.1", port=0, open_browser=True, timeout_seconds=120,
                                        prompt="consent", include_granted_scopes="false")
    granted = set(credentials.granted_scopes or credentials.scopes or [])
    if granted != set(workspace.scopes(config)):
        raise ValueError("Partial/unexpected consent. No tokens stored; review permissions in your Google account and retry deliberately.")
    keyring.set_password(workspace.SERVICE, workspace.ACCOUNT, credentials.to_json())
    store.set_setting("workspace", config)
    return {"configured": True, "services": {"drive": drive, "calendar": calendar},
            "warning": "Host file IDs restrict Ultron but do not authorize files at Google. drive.file needs app-selected/app-created files. No whole-Drive search or Picker UI is included."}


def disconnect(*, local_only=False):
    keyring = workspace.backend()
    secret = keyring.get_password(workspace.SERVICE, workspace.ACCOUNT)
    revoked = False
    if secret and not local_only:
        import requests
        data = json.loads(secret)
        token = data.get("refresh_token") or data.get("token")
        if token:
            try:
                response = requests.post("https://oauth2.googleapis.com/revoke", data={"token": token}, timeout=(5, 10), allow_redirects=False)
                revoked = response.status_code == 200
            except requests.RequestException:
                pass
    if secret:
        keyring.delete_password(workspace.SERVICE, workspace.ACCOUNT)
    store.set_setting("workspace", {})
    return {"local_credentials_removed": True, "remote_revocation_confirmed": revoked,
            "note": "If revocation is unconfirmed/local-only, remove access in Google Account permissions. No account content is cached by this adapter."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("allow-root", "revoke-root"):
        command = commands.add_parser(name)
        command.add_argument("path")
    commands.add_parser("status")
    command = commands.add_parser("local-notifications")
    command.add_argument("mode", choices=["on", "off"])
    command = commands.add_parser("workspace-connect")
    command.add_argument("--client-secrets", required=True)
    command.add_argument("--drive", action="store_true")
    command.add_argument("--calendar", action="store_true")
    command.add_argument("--calendar-id", default="primary")
    command.add_argument("--file-id", action="append", default=[])
    command.add_argument("--allow-model-context", action="store_true",
                         help="Allow explicitly requested API results to enter Ultron's configured model context")
    command = commands.add_parser("workspace-disconnect")
    command.add_argument("--local-only", action="store_true")
    args = parser.parse_args()
    try:
        if args.command in {"allow-root", "revoke-root"}:
            result = configure_root(args.path, remove=args.command == "revoke-root")
        elif args.command == "local-notifications":
            from ultron.core.local_notifications import configure
            result = configure(args.mode == "on")
        elif args.command == "workspace-connect":
            result = connect(args.client_secrets, drive=args.drive, calendar=args.calendar,
                             calendar_id=args.calendar_id, file_ids=args.file_id, allow_model_context=args.allow_model_context)
        elif args.command == "workspace-disconnect":
            result = disconnect(local_only=args.local_only)
        else:
            result = {"document_roots": store.setting("document_roots", []), "workspace": workspace.workspace("status"),
                      "local_notification_delivery": store.setting("local_notification_delivery", {"enabled": False})}
        print(json.dumps(result, indent=2))
    except Exception:
        parser.exit(1, "Setup failed. Check host paths, optional dependencies, OS credential-store availability and Google consent/configuration. No credentials are printed.\n")


if __name__ == "__main__":
    main()
