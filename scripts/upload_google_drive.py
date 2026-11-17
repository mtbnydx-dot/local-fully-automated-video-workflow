r"""Upload files and directory trees to Google Drive, preserving their original formats.

First login (install google-auth-oauthlib in the project's environment):
    .venv/bin/python -m pip install 'google-auth-oauthlib>=1.2,<2'
    .venv/bin/python scripts/upload_google_drive.py --login --pick-folder \
        --client-secrets /path/to/desktop-client.json

For a remote host, forward port 8765 from your browser's machine first:
    ssh -N -L 8765:127.0.0.1:8765 USER@HOST
Open the printed Google URL in that machine's browser to authorize.

OAuth credentials are cached in ~/.config/google-drive-upload/credentials.json.
Uploads refresh the access token at startup. --credentials overrides the cache
location. GOOGLE_DRIVE_ACCESS_TOKEN overrides the default cached credentials.
Login requests drive.file scope (files created or opened with this application).

Upload one file, one directory, or multiple paths from the repository root:
    .venv/bin/python scripts/upload_google_drive.py /path/to/file.txt
    .venv/bin/python scripts/upload_google_drive.py /path/to/folder
    .venv/bin/python scripts/upload_google_drive.py /path/to/file.txt /path/to/folder

Relative paths are resolved from the working directory; absolute paths also work.
--parent-folder accepts a Drive folder ID; the default is My Drive/H3剧本包.
Each run creates new copies, including the
top-level directory. Failed runs leave completed uploads in Drive and exit 1.
--dry-run lists local entries without credentials or network requests.
"""

import argparse
import json
import mimetypes
import os
import sys
from pathlib import Path

import httpx


DEFAULT_CREDENTIALS = Path.home() / ".config/google-drive-upload/credentials.json"
DEFAULT_PARENT_FOLDER = "1b7aloIcVg-Enjq92vYZaeTkgH3Uoz_9u"


def main() -> None:
    args = _parse_args()
    if args.login:
        _login(args.client_secrets, args.credentials or DEFAULT_CREDENTIALS, args.port, args.pick_folder)
        return
    with httpx.Client(timeout=300) as client:
        if not args.dry_run:
            token = _access_token(client, args.credentials)
            client.headers["Authorization"] = f"Bearer {token}"
        for path in args.paths:
            _upload(client, path, args.parent_folder, args.dry_run)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="*", type=Path, help="Local files or folders")
    parser.add_argument("--parent-folder", default=DEFAULT_PARENT_FOLDER,
                        help="Destination Drive folder ID (default: My Drive/H3剧本包)")
    parser.add_argument("--credentials", type=Path, help="Google OAuth authorized-user JSON file")
    parser.add_argument("--dry-run", action="store_true", help="List entries without uploading")
    parser.add_argument("--login", action="store_true", help="Authorize and save OAuth credentials only")
    parser.add_argument("--pick-folder", action="store_true", help="Select an existing Drive folder during login (requires Google Picker API)")
    parser.add_argument("--client-secrets", type=Path, help="Google Desktop app OAuth client JSON")
    parser.add_argument("--port", type=int, default=8765, help="Loopback OAuth callback port (default: 8765)")
    args = parser.parse_args()
    if args.login:
        if args.paths or args.dry_run:
            parser.error("Run --login separately from uploads and --dry-run")
        if not args.client_secrets or not args.client_secrets.expanduser().is_file():
            parser.error("--login requires --client-secrets pointing to a Desktop app OAuth client JSON")
        if not 1 <= args.port <= 65535:
            parser.error("--port must be between 1 and 65535")
        return args
    if args.client_secrets or args.pick_folder:
        parser.error("Use --client-secrets and --pick-folder with --login")
    if not args.paths:
        parser.error("Supply at least one local file or directory")
    for path in args.paths:
        if not path.is_file() and not path.is_dir():
            parser.error(f"File or directory does not exist: {path}")
    if not args.dry_run and not args.credentials and not os.environ.get("GOOGLE_DRIVE_ACCESS_TOKEN"):
        if not DEFAULT_CREDENTIALS.is_file():
            parser.error("Authorize first with --login --client-secrets /path/to/desktop-client.json")
        args.credentials = DEFAULT_CREDENTIALS
    return args


def _login(client_secrets: Path, destination: Path, port: int, pick_folder: bool) -> None:
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise ValueError("Install login dependency: .venv/bin/python -m pip install 'google-auth-oauthlib>=1.2,<2'") from exc
    config = json.loads(client_secrets.expanduser().read_text(encoding="utf-8"))
    if "installed" not in config:
        raise ValueError("Create an OAuth client of type Desktop app and download its JSON")
    flow = InstalledAppFlow.from_client_config(
        config, scopes=["https://www.googleapis.com/auth/drive.file"],
        autogenerate_code_verifier=True,
    )
    credentials = flow.run_local_server(
        host="127.0.0.1", port=port, open_browser=False, timeout_seconds=600,
        prompt="consent", access_type="offline",
        authorization_prompt_message="Open this URL in your browser:\n{url}",
        success_message="Google Drive authorization received. You can close this tab.",
        **({"trigger_onepick": "true", "allow_folder_selection": "true",
            "mimetypes": "application/vnd.google-apps.folder"} if pick_folder else {}),
    )
    if not credentials.refresh_token:
        raise ValueError("Google did not return a refresh token; run --login and grant offline access again")
    destination = destination.expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as output:
        os.fchmod(output.fileno(), 0o600)
        output.write(credentials.to_json())
    print(f"OAuth credentials saved: {destination}", flush=True)


def _access_token(client: httpx.Client, credentials: Path | None) -> str:
    if credentials is None:
        return os.environ["GOOGLE_DRIVE_ACCESS_TOKEN"]
    data = json.loads(credentials.expanduser().read_text(encoding="utf-8"))
    required = ("client_id", "client_secret", "refresh_token")
    if any(not data.get(key) for key in required):
        raise ValueError("Credentials must contain client_id, client_secret, and refresh_token")
    response = client.post("https://oauth2.googleapis.com/token", data={
        **{key: data[key] for key in required},
        "grant_type": "refresh_token",
    })
    response.raise_for_status()
    return response.json()["access_token"]


def _upload(client: httpx.Client, path: Path, parent: str, dry_run: bool) -> None:
    # Directory symlinks can recurse outside the selected tree or create cycles.
    if path.is_symlink():
        print(f"SKIP symlink: {path}", flush=True)
        return
    directory = path.is_dir()
    if dry_run:
        print(f"{'DIR ' if directory else 'FILE'} {path}", flush=True)
        folder_id = parent
    else:
        metadata = {"name": path.absolute().name, "parents": [parent]}
        params = {"fields": "id,webViewLink", "supportsAllDrives": "true"}
        if directory:
            response = client.post("https://www.googleapis.com/drive/v3/files", params=params,
                                   json={**metadata, "mimeType": "application/vnd.google-apps.folder"})
        else:
            mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            size = path.stat().st_size
            session = client.post("https://www.googleapis.com/upload/drive/v3/files",
                                  params={**params, "uploadType": "resumable"}, json=metadata,
                                  headers={"X-Upload-Content-Type": mime_type,
                                           "X-Upload-Content-Length": str(size)})
            session.raise_for_status()
            with path.open("rb") as source:
                response = client.put(session.headers["Location"],
                                      content=iter(lambda: source.read(1024 * 1024), b""),
                                      headers={"Content-Type": mime_type, "Content-Length": str(size)})
        response.raise_for_status()
        result = response.json()
        folder_id = result["id"]
        url = result.get("webViewLink") or f"https://drive.google.com/open?id={folder_id}"
        print(f"UPLOADED {path} -> {url}", flush=True)
    if directory:
        for child in sorted(path.iterdir()):
            _upload(client, child, folder_id, dry_run)


if __name__ == "__main__":
    try:
        main()
    except httpx.HTTPStatusError as exc:
        print(f"Google API error {exc.response.status_code}: {exc.response.text}", file=sys.stderr)
        sys.exit(1)
    except (OSError, ValueError, httpx.RequestError) as exc:
        print(f"Upload failed: {exc}", file=sys.stderr)
        sys.exit(1)
