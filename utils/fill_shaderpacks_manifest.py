from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen


MANIFEST = Path(r"C:\Users\keynm\Documents\Minecraft_Modpacks_Data\manifests\shaderpacks.json")
ROOT_FIELDS = ("packs",)
PACK_FIELDS = ("file_name", "download_url", "sha256")
VALID_SUFFIXES = (".zip",)


def keep_only(entry: dict, fields: tuple[str, ...]) -> bool:
    clean = {field: entry[field] for field in fields if entry.get(field) not in (None, "")}
    changed = entry != clean
    entry.clear()
    entry.update(clean)
    return changed


def pack_name(url: str) -> str:
    name = Path(unquote(urlparse(url).path)).name
    if not any(name.lower().endswith(suffix) for suffix in VALID_SUFFIXES):
        raise RuntimeError(f"URL sans extension attendue {VALID_SUFFIXES}: {url}")
    return name


def download_sha256(url: str, target: Path) -> str:
    req = Request(url, headers={"User-Agent": "KayouInstaller-manifest-tool"})
    sha256 = hashlib.sha256()

    with urlopen(req, timeout=90) as response, target.open("wb") as file:
        while chunk := response.read(1024 * 1024):
            file.write(chunk)
            sha256.update(chunk)

    if target.stat().st_size == 0:
        raise RuntimeError("telechargement vide")

    return sha256.hexdigest()


def update_pack(pack: dict, index: int, tmp: Path) -> bool:
    label = pack.get("file_name") or f"packs[{index}]"
    changed = keep_only(pack, PACK_FIELDS)

    missing = [field for field in PACK_FIELDS if not pack.get(field)]
    if not missing:
        print(f"[{index}] SKIP: {label}")
        return changed

    url = pack.get("download_url")
    if not url:
        print(f"[{index}] ERROR: {label} -> download_url manquant")
        return changed

    try:
        print(f"[{index}] UPDATE: {label} -> {', '.join(missing)}")
        if not pack.get("file_name"):
            pack["file_name"] = pack_name(url)
        if not pack.get("sha256"):
            pack["sha256"] = download_sha256(url, tmp / pack["file_name"])
        return True
    except Exception as exc:
        print(f"[{index}] ERROR: {label} -> {exc}")
        return changed


def main() -> None:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    changed = keep_only(data, ROOT_FIELDS)

    packs = data.get("packs")
    if not isinstance(packs, list):
        raise RuntimeError('Le manifest doit contenir une liste "packs".')

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        for index, pack in enumerate(packs, start=1):
            if not isinstance(pack, dict):
                print(f"[{index}] ERROR: entree pack invalide")
                continue
            changed |= update_pack(pack, index, tmp)

    if changed:
        MANIFEST.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("\nManifest nettoye.")
    else:
        print("\nManifest deja propre.")


if __name__ == "__main__":
    main()
