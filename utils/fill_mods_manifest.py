from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen


MANIFEST = Path(r"C:\Users\keynm\Documents\Minecraft_Modpacks_Data\manifests\mods.json")
ROOT_FIELDS = ("mods", "blacklist", "safe_mode")
MOD_FIELDS = ("id", "version", "download_url", "file_name", "sha1")
RULE_FIELDS = ("id", "reason")


def keep_only(entry: dict, fields: tuple[str, ...]) -> bool:
    clean = {field: entry[field] for field in fields if entry.get(field) not in (None, "")}
    changed = entry != clean
    entry.clear()
    entry.update(clean)
    return changed


def jar_name(url: str) -> str:
    name = Path(unquote(urlparse(url).path)).name
    if not name.lower().endswith(".jar"):
        raise RuntimeError(f"URL sans .jar: {url}")
    return name


def download_sha1(url: str, target: Path) -> str:
    req = Request(url, headers={"User-Agent": "KayouInstaller-manifest-tool"})
    sha1 = hashlib.sha1()

    with urlopen(req, timeout=90) as response, target.open("wb") as file:
        while chunk := response.read(1024 * 1024):
            file.write(chunk)
            sha1.update(chunk)

    if target.stat().st_size == 0:
        raise RuntimeError("telechargement vide")

    return sha1.hexdigest()


def update_mod(mod: dict, index: int, tmp: Path) -> bool:
    label = mod.get("id") or f"mods[{index}]"
    changed = keep_only(mod, MOD_FIELDS)

    missing = [field for field in ("file_name", "sha1") if not mod.get(field)]
    if not missing:
        print(f"[{index}] SKIP: {label}")
        return changed

    url = mod.get("download_url")
    if not url:
        print(f"[{index}] ERROR: {label} -> download_url manquant")
        return changed

    try:
        name = jar_name(url)
        print(f"[{index}] UPDATE: {label} -> {', '.join(missing)}")
        mod["file_name"] = name
        mod["sha1"] = download_sha1(url, tmp / name)
        return True
    except Exception as exc:
        print(f"[{index}] ERROR: {label} -> {exc}")
        return changed


def clean_rules(data: dict, section: str) -> bool:
    changed = False
    rules = data.get(section, [])

    if not isinstance(rules, list):
        data[section] = []
        print(f"WARN: {section} remplace par une liste vide")
        return True

    for rule in rules:
        if isinstance(rule, dict):
            changed |= keep_only(rule, RULE_FIELDS)

    return changed


def main() -> None:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    changed = keep_only(data, ROOT_FIELDS)

    mods = data.get("mods")
    if not isinstance(mods, list):
        raise RuntimeError('Le manifest doit contenir une liste "mods".')

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        for index, mod in enumerate(mods, start=1):
            if not isinstance(mod, dict):
                print(f"[{index}] ERROR: entree mod invalide")
                continue
            changed |= update_mod(mod, index, tmp)

    changed |= clean_rules(data, "blacklist")
    changed |= clean_rules(data, "safe_mode")

    MANIFEST.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("\nManifest nettoye." if changed else "\nManifest deja propre.")


if __name__ == "__main__":
    main()