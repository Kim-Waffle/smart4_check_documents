from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
SHORTCUT_MIME_TYPE = "application/vnd.google-apps.shortcut"
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.metadata.readonly"
SEOUL = ZoneInfo("Asia/Seoul")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def drive_service():
    required = ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN"]
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    credentials = Credentials(
        token=None,
        refresh_token=os.environ["GOOGLE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        scopes=[DRIVE_SCOPE],
    )
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def list_children(service, parent_id: str, folders_only: bool | None = None) -> list[dict[str, Any]]:
    clauses = [f"'{parent_id}' in parents", "trashed = false"]
    if folders_only is True:
        clauses.append(f"(mimeType = '{FOLDER_MIME_TYPE}' or mimeType = '{SHORTCUT_MIME_TYPE}')")
    elif folders_only is False:
        clauses.append(f"mimeType != '{FOLDER_MIME_TYPE}'")

    items: list[dict[str, Any]] = []
    page_token = None
    while True:
        response = (
            service.files()
            .list(
                q=" and ".join(clauses),
                fields=(
                    "nextPageToken, "
                    "files(id, name, mimeType, modifiedTime, webViewLink, "
                    "shortcutDetails(targetId, targetMimeType))"
                ),
                orderBy="folder,name_natural",
                pageSize=1000,
                pageToken=page_token,
                includeItemsFromAllDrives=True,
                supportsAllDrives=True,
            )
            .execute()
        )
        items.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            if folders_only is True:
                return [item for item in items if is_folder_like(item)]
            return items


def is_folder_like(item: dict[str, Any]) -> bool:
    if item.get("mimeType") == FOLDER_MIME_TYPE:
        return True
    shortcut = item.get("shortcutDetails") or {}
    return item.get("mimeType") == SHORTCUT_MIME_TYPE and shortcut.get("targetMimeType") == FOLDER_MIME_TYPE


def effective_id(item: dict[str, Any] | None) -> str | None:
    if not item:
        return None
    shortcut = item.get("shortcutDetails") or {}
    return shortcut.get("targetId") or item.get("id")


def drive_folder_url(folder_id: str | None) -> str | None:
    return f"https://drive.google.com/drive/folders/{folder_id}" if folder_id else None


def drive_file_url(file_id: str | None) -> str | None:
    return f"https://drive.google.com/file/d/{file_id}/view" if file_id else None


def to_seoul_iso(value: str | None) -> str | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(SEOUL).isoformat()


def find_named_folder(folders: list[dict[str, Any]], folder_name: str) -> dict[str, Any] | None:
    expected = normalize_name(folder_name)
    for folder in folders:
        if normalize_name(folder["name"]) == expected:
            return folder
    return None


def normalize_name(value: str) -> str:
    return " ".join(value.strip().split())


def latest_file(files: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not files:
        return None
    return max(files, key=lambda item: item.get("modifiedTime") or "")


def build_document_entry(service, student_folders: list[dict[str, Any]], doc_type: dict[str, Any]) -> dict[str, Any]:
    folder = find_named_folder(student_folders, doc_type["folderName"])
    if not folder:
        return {
            "status": "missing",
            "folderId": None,
            "folderUrl": None,
            "latestFileName": None,
            "latestFileId": None,
            "latestFileUrl": None,
            "latestModifiedAt": None,
        }

    folder_id = effective_id(folder)
    files = list_children(service, folder_id, folders_only=False) if folder_id else []
    latest = latest_file(files)
    latest_id = effective_id(latest)
    return {
        "status": "submitted" if latest else "missing",
        "folderId": folder_id,
        "folderUrl": drive_folder_url(folder_id),
        "latestFileName": latest["name"] if latest else None,
        "latestFileId": latest_id if latest else None,
        "latestFileUrl": drive_file_url(latest_id) if latest else None,
        "latestModifiedAt": to_seoul_iso(latest.get("modifiedTime")) if latest else None,
    }


def build_dashboard(config: dict[str, Any], manual_status: dict[str, Any]) -> dict[str, Any]:
    root_folder_id = os.getenv("GOOGLE_DRIVE_ROOT_FOLDER_ID") or config["sourceFolderId"]
    service = drive_service()
    student_folders = list_children(service, root_folder_id, folders_only=True)
    early_ids = set(manual_status.get("earlyEmployedStudentIds", []))

    students = []
    for student_folder in sorted(student_folders, key=lambda item: item["name"]):
        student_folder_id = effective_id(student_folder)
        child_folders = list_children(service, student_folder_id, folders_only=True) if student_folder_id else []
        documents = {
            doc_type["id"]: build_document_entry(service, child_folders, doc_type)
            for doc_type in config["documentTypes"]
        }
        students.append(
            {
                "id": student_folder_id,
                "name": student_folder["name"],
                "studentStatus": "early_employed" if student_folder_id in early_ids else "active",
                "folderUrl": drive_folder_url(student_folder_id),
                "documents": documents,
            }
        )

    return {
        "generatedAt": datetime.now(SEOUL).isoformat(),
        "sourceFolderId": root_folder_id,
        "documentTypes": config["documentTypes"],
        "students": students,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build dashboard-data.json from Google Drive folders.")
    parser.add_argument("--config", default="data/config.json")
    parser.add_argument("--manual-status", default="data/manual-status.json")
    parser.add_argument("--output", default="data/dashboard-data.json")
    parser.add_argument("--history-dir", default="data/history")
    args = parser.parse_args()

    config = load_json(Path(args.config), {})
    manual_status = load_json(Path(args.manual_status), {"earlyEmployedStudentIds": []})
    dashboard = build_dashboard(config, manual_status)

    output_path = Path(args.output)
    write_json(output_path, dashboard)

    stamp = datetime.now(SEOUL).strftime("%Y-%m-%d-%H%M")
    write_json(Path(args.history_dir) / f"{stamp}.json", dashboard)
    print(f"Wrote {output_path} with {len(dashboard['students'])} students.")


if __name__ == "__main__":
    main()
