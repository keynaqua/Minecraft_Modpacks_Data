from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen


REQUIRED_FIELDS = {"id", "version", "file_name", "sha1", "size"}


def download(url: str, target: Path) -> bytes:
    req = Request(url, headers={"User-Agent": "mod-manifest-filler"})
    with urlopen(req) as response:
        data = response.read()
    target.write_bytes(data)
    return data


def sha1_bytes(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def load_fabric_meta(jar_path: Path) -> dict:
    with zipfile.ZipFile(jar_path) as jar:
        with jar.open("fabric.mod.json") as file:
            data = json.loads(file.read().decode("utf-8"))

    if isinstance(data, list):
        data = next((item for item in data if isinstance(item, dict) and item.get("id")), None)

    if not isinstance(data, dict):
        raise RuntimeError(f"{jar_path.name}: fabric.mod.json inutilisable")

    return data


def fill_mod(entry: dict, temp_dir: Path) -> bool:
    missing = [field for field in REQUIRED_FIELDS if field not in entry or entry[field] in ("", None)]
    if not missing:
        return False

    url = entry.get("download_url")
    if not isinstance(url, str) or not url.strip():
        raise RuntimeError(f"Mod sans download_url: {entry!r}")

    guessed_name = Path(url.split("?", 1)[0]).name or "mod.jar"
    temp_jar = temp_dir / guessed_name
    raw = download(url, temp_jar)
    meta = load_fabric_meta(temp_jar)

    entry.setdefault("id", str(meta.get("id", "")).strip())
    entry.setdefault("version", str(meta.get("version", "")).strip())

    name = meta.get("name")
    if isinstance(name, str) and name.strip():
        entry.setdefault("name", name.strip())

    entry.setdefault("file_name", guessed_name)
    entry.setdefault("sha1", sha1_bytes(raw))
    entry.setdefault("size", len(raw))

    still_missing = [field for field in REQUIRED_FIELDS if not entry.get(field)]
    if still_missing:
        raise RuntimeError(f"{entry.get('download_url')}: champs encore manquants: {still_missing}")

    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()

    manifest_path = args.manifest
    data = json.loads(manifest_path.read_text(encoding="utf-8"))

    raw_mods = data.get("mods")
    if not isinstance(raw_mods, list):
        raise RuntimeError('Le manifest doit contenir une liste "mods".')

    changed = 0
    with tempfile.TemporaryDirectory() as tmp:
        temp_dir = Path(tmp)
        for index, entry in enumerate(raw_mods, start=1):
            if not isinstance(entry, dict):
                raise RuntimeError(f"mods[{index}] doit être un objet JSON")
            if fill_mod(entry, temp_dir):
                changed += 1

    manifest_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"Manifest mis à jour: {changed} mod(s) complété(s).")


if __name__ == "__main__":
    main()
