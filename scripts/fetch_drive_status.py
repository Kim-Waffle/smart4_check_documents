from __future__ import annotations

import argparse
import json
import os
import re
import unicodedata
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
INTERVIEW_DOCUMENT_ID = "interview"
ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\ufeff]")
ORDER_PREFIX_RE = re.compile(r"^\s*\d+\s*[\.\)\]\-_:]+\s*")
NUMBERED_STUDENT_FOLDER_RE = re.compile(r"^\s*\d+\s*[\.\)\]\-_:]+\s*(.+?)\s*$")
TRAILING_ANNOTATION_RE = re.compile(r"\s*[\(\[\{][^()\[\]{}]+[\)\]\}]\s*$")


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


def normalize_spaces(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value))
    normalized = ZERO_WIDTH_RE.sub("", normalized)
    return " ".join(normalized.strip().split())


def normalize_name(value: str) -> str:
    return ORDER_PREFIX_RE.sub("", normalize_spaces(value))


def normalize_student_match_key(value: str) -> str:
    return normalize_spaces(value).casefold()


def extract_interview_student_name(folder_name: str) -> str | None:
    match = NUMBERED_STUDENT_FOLDER_RE.match(normalize_spaces(folder_name))
    return normalize_spaces(match.group(1)) if match else None


def strip_trailing_annotation(value: str) -> str:
    return normalize_spaces(TRAILING_ANNOTATION_RE.sub("", value))


def find_named_folder(folders: list[dict[str, Any]], folder_name: str) -> dict[str, Any] | None:
    expected = normalize_name(folder_name)
    for folder in folders:
        actual = normalize_name(folder["name"])
        if actual == expected or expected in actual:
            return folder
    return None


def latest_file(files: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not files:
        return None
    return max(files, key=lambda item: item.get("modifiedTime") or "")


def empty_document_entry(status: str) -> dict[str, Any]:
    return {
        "status": status,
        "folderId": None,
        "folderUrl": None,
        "latestFileName": None,
        "latestFileId": None,
        "latestFileUrl": None,
        "latestModifiedAt": None,
    }


def build_document_entry(service, student_folders: list[dict[str, Any]], doc_type: dict[str, Any]) -> dict[str, Any]:
    folder = find_named_folder(student_folders, doc_type["folderName"])
    if not folder:
        return empty_document_entry("missing")

    folder_id = effective_id(folder)
    files = list_children(service, folder_id, folders_only=False) if folder_id else []
    valid_files = [item for item in files if not is_folder_like(item)]
    latest = latest_file(valid_files)
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


def build_interview_entry(service, interview_folder: dict[str, Any] | None) -> dict[str, Any]:
    if not interview_folder:
        return empty_document_entry("not_applicable")

    folder_id = effective_id(interview_folder)
    files = list_children(service, folder_id, folders_only=False) if folder_id else []
    valid_files = [item for item in files if not is_folder_like(item)]
    latest = latest_file(valid_files)
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


def build_alias_map(raw_aliases: dict[str, str], student_keys: set[str]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for source_name, target_name in raw_aliases.items():
        source_key = normalize_student_match_key(source_name)
        target_key = normalize_student_match_key(target_name)
        if target_key not in student_keys:
            raise RuntimeError(
                f"Interview name alias target does not exist in the dashboard student list: "
                f"{source_name!r} -> {target_name!r}"
            )
        if source_key in aliases and aliases[source_key] != target_key:
            raise RuntimeError(f"Conflicting interview aliases for {source_name!r}")
        aliases[source_key] = target_key
    return aliases


def resolve_interview_student_key(
    extracted_name: str,
    student_keys: set[str],
    aliases: dict[str, str],
) -> tuple[str | None, str]:
    exact_key = normalize_student_match_key(extracted_name)
    if exact_key in student_keys:
        return exact_key, "exact"
    if exact_key in aliases:
        return aliases[exact_key], "alias"

    without_annotation = strip_trailing_annotation(extracted_name)
    annotation_key = normalize_student_match_key(without_annotation)
    if annotation_key != exact_key:
        if annotation_key in student_keys:
            return annotation_key, "trailing_annotation"
        if annotation_key in aliases:
            return aliases[annotation_key], "trailing_annotation_alias"

    return None, "unmatched"


def build_interview_folder_index(
    service,
    interview_root_id: str,
    student_names: list[str],
    raw_aliases: dict[str, str],
) -> dict[str, dict[str, Any]]:
    student_keys = [normalize_student_match_key(name) for name in student_names]
    duplicate_student_keys = {key for key in student_keys if student_keys.count(key) > 1}
    if duplicate_student_keys:
        raise RuntimeError(
            "Duplicate dashboard student names after normalization: " + ", ".join(sorted(duplicate_student_keys))
        )

    student_key_set = set(student_keys)
    aliases = build_alias_map(raw_aliases, student_key_set)
    resolved: dict[str, dict[str, Any]] = {}
    duplicate_matches: set[str] = set()

    team_folders = list_children(service, interview_root_id, folders_only=True)
    for team_folder in sorted(team_folders, key=lambda item: item["name"]):
        team_id = effective_id(team_folder)
        if not team_id:
            continue
        children = list_children(service, team_id, folders_only=True)
        for folder in children:
            extracted_name = extract_interview_student_name(folder["name"])
            if not extracted_name:
                continue

            student_key, resolution = resolve_interview_student_key(extracted_name, student_key_set, aliases)
            if not student_key:
                print(
                    "WARNING unmatched interview student folder:"
                    f" team={team_folder['name']!r} folder={folder['name']!r}"
                )
                continue

            if resolution != "exact":
                print(
                    "INFO normalized interview student folder:"
                    f" team={team_folder['name']!r} folder={folder['name']!r} rule={resolution}"
                )

            if student_key in resolved:
                previous = resolved[student_key]
                print(
                    "WARNING duplicate interview student folders; marking the student as not applicable:"
                    f" first={previous.get('name')!r} second={folder.get('name')!r}"
                )
                duplicate_matches.add(student_key)
                continue

            resolved[student_key] = folder

    for student_key in duplicate_matches:
        resolved.pop(student_key, None)

    return resolved


def build_dashboard(config: dict[str, Any], manual_status: dict[str, Any]) -> dict[str, Any]:
    root_folder_id = os.getenv("GOOGLE_DRIVE_ROOT_FOLDER_ID") or config["sourceFolderId"]
    interview_root_id = (
        os.getenv("GOOGLE_DRIVE_INTERVIEW_ROOT_FOLDER_ID")
        or config.get("interviewSourceFolderId")
    )
    debug_student_name = os.getenv("DEBUG_STUDENT_NAME", "").strip()
    service = drive_service()
    student_folders = list_children(service, root_folder_id, folders_only=True)
    early_ids = set(manual_status.get("earlyEmployedStudentIds", []))

    interview_type = next(
        (doc_type for doc_type in config["documentTypes"] if doc_type["id"] == INTERVIEW_DOCUMENT_ID),
        None,
    )
    regular_document_types = [
        doc_type for doc_type in config["documentTypes"] if doc_type["id"] != INTERVIEW_DOCUMENT_ID
    ]

    interview_folders: dict[str, dict[str, Any]] = {}
    if interview_type:
        if not interview_root_id:
            raise RuntimeError(
                "Missing interviewSourceFolderId in data/config.json or "
                "GOOGLE_DRIVE_INTERVIEW_ROOT_FOLDER_ID environment variable."
            )
        interview_folders = build_interview_folder_index(
            service,
            interview_root_id,
            [folder["name"] for folder in student_folders],
            config.get("interviewNameAliases", {}),
        )

    students = []
    for student_folder in sorted(student_folders, key=lambda item: item["name"]):
        student_folder_id = effective_id(student_folder)
        child_items = list_children(service, student_folder_id, folders_only=None) if student_folder_id else []
        child_folders = [item for item in child_items if is_folder_like(item)]
        student_key = normalize_student_match_key(student_folder["name"])
        interview_folder = interview_folders.get(student_key)

        if debug_student_name and debug_student_name in student_folder["name"]:
            print_drive_diagnostics(
                service,
                student_folder,
                student_folder_id,
                child_items,
                regular_document_types,
                interview_folder,
            )

        documents = {
            doc_type["id"]: build_document_entry(service, child_folders, doc_type)
            for doc_type in regular_document_types
        }
        if interview_type:
            documents[INTERVIEW_DOCUMENT_ID] = build_interview_entry(service, interview_folder)

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
        "interviewSourceFolderId": interview_root_id,
        "documentTypes": config["documentTypes"],
        "students": students,
    }


def print_drive_diagnostics(
    service,
    student_folder: dict[str, Any],
    student_folder_id: str | None,
    child_items: list[dict[str, Any]],
    document_types: list[dict[str, Any]],
    interview_folder: dict[str, Any] | None,
) -> None:
    print(f"DEBUG student: {student_folder['name']} ({student_folder_id})")
    print(f"DEBUG child item count: {len(child_items)}")
    for item in child_items:
        shortcut = item.get("shortcutDetails") or {}
        target = shortcut.get("targetId", "")
        target_mime = shortcut.get("targetMimeType", "")
        print(
            "DEBUG child:"
            f" name={item.get('name')!r}"
            f" id={item.get('id')}"
            f" effective_id={effective_id(item)}"
            f" mimeType={item.get('mimeType')}"
            f" targetId={target}"
            f" targetMimeType={target_mime}"
        )

    child_folders = [item for item in child_items if is_folder_like(item)]
    for doc_type in document_types:
        folder = find_named_folder(child_folders, doc_type["folderName"])
        folder_id = effective_id(folder)
        if not folder_id:
            print(f"DEBUG document folder not found: {doc_type['folderName']!r}")
            continue
        files = [
            item
            for item in list_children(service, folder_id, folders_only=False)
            if not is_folder_like(item)
        ]
        print(f"DEBUG document folder: {doc_type['folderName']!r} ({folder_id}) file_count={len(files)}")
        for file in files[:20]:
            print(
                "DEBUG file:"
                f" name={file.get('name')!r}"
                f" id={effective_id(file)}"
                f" mimeType={file.get('mimeType')}"
                f" modifiedTime={file.get('modifiedTime')}"
            )

    interview_folder_id = effective_id(interview_folder)
    if not interview_folder_id:
        print("DEBUG interview folder not assigned")
        return

    interview_files = [
        item
        for item in list_children(service, interview_folder_id, folders_only=False)
        if not is_folder_like(item)
    ]
    print(
        f"DEBUG interview folder: {interview_folder.get('name')!r} "
        f"({interview_folder_id}) file_count={len(interview_files)}"
    )
    for file in interview_files[:20]:
        print(
            "DEBUG interview file:"
            f" name={file.get('name')!r}"
            f" id={effective_id(file)}"
            f" mimeType={file.get('mimeType')}"
            f" modifiedTime={file.get('modifiedTime')}"
        )


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
