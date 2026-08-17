from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parent.parent
SOURCE_CATALOG = ROOT / "catalog.source.json"
PACKS_DIR = ROOT / "packs"
PUBLIC_DIR = ROOT / "public"
MANIFEST_NAMES = (
    "mods.json",
    "resourcepacks.json",
    "shaderpacks.json",
    "datapacks.json",
    "configs.json",
)
CATEGORY_DIRECTORIES = {
    "mods.json": "mods",
    "resourcepacks.json": "resourcepacks",
    "shaderpacks.json": "shaderpacks",
    "datapacks.json": "datapacks",
}


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"Fichier introuvable : {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"JSON invalide dans {path}: {exc}") from exc


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def file_digest(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def pack_revision(pack_dir: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted((p for p in pack_dir.rglob("*") if p.is_file()), key=lambda p: p.as_posix()):
        relative = path.relative_to(pack_dir).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()[:16]


def safe_local_file(pack_dir: Path, directory: str, file_name: str) -> Path:
    candidate = (pack_dir / directory / file_name).resolve()
    allowed = (pack_dir / directory).resolve()
    try:
        candidate.relative_to(allowed)
    except ValueError as exc:
        raise RuntimeError(f"Chemin local interdit : {directory}/{file_name}") from exc
    if not candidate.is_file():
        raise RuntimeError(
            f"URL vide mais fichier local introuvable : {pack_dir.name}/{directory}/{file_name}"
        )
    return candidate


def public_file_url(base_url: str, pack_id: str, directory: str, file_name: str, revision: str) -> str:
    encoded = "/".join(quote(part) for part in Path(file_name).parts)
    return f"{base_url}/packs/{quote(pack_id)}/{quote(directory)}/{encoded}?v={revision}"


def validate_hash(path: Path, entry: dict, context: str) -> None:
    for algorithm in ("sha1", "sha256"):
        expected = entry.get(algorithm)
        if isinstance(expected, str) and expected and file_digest(path, algorithm).lower() != expected.lower():
            raise RuntimeError(f"Hash {algorithm} incorrect pour {context}")


def process_download_entry(
    entry: dict,
    pack_dir: Path,
    pack_id: str,
    directory: str,
    base_url: str,
    revision: str,
    context: str,
) -> int:
    file_name = entry.get("file_name")
    if not isinstance(file_name, str) or not file_name.strip():
        raise RuntimeError(f"file_name manquant dans {context}")

    url = entry.get("download_url")
    if not isinstance(url, str):
        raise RuntimeError(f"download_url invalide dans {context}")

    size = entry.get("size_bytes")
    if not url.strip():
        local = safe_local_file(pack_dir, directory, file_name)
        validate_hash(local, entry, context)
        size = local.stat().st_size
        entry["size_bytes"] = size
        entry["download_url"] = public_file_url(base_url, pack_id, directory, file_name, revision)

    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise RuntimeError(
            f"size_bytes manquant dans {context}. Relance build_modpack.py avec cette version."
        )
    return size


def process_manifest(
    path: Path, pack_dir: Path, pack_id: str, base_url: str, revision: str
) -> tuple[object, int]:
    data = read_json(path)
    directory = CATEGORY_DIRECTORIES.get(path.name)
    if not directory:
        return data, 0

    key = "mods" if path.name == "mods.json" else "packs"
    entries = data.get(key) if isinstance(data, dict) else None
    if not isinstance(entries, list):
        raise RuntimeError(f"Liste '{key}' manquante dans {path}")

    total = 0
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise RuntimeError(f"Entrée {index} invalide dans {path}")
        total += process_download_entry(
            entry,
            pack_dir,
            pack_id,
            directory,
            base_url,
            revision,
            f"{pack_id}/{path.name}[{index}]",
        )
    return data, total


def copy_pack(pack_dir: Path, destination: Path) -> None:
    def ignored(_directory: str, names: list[str]):
        return {name for name in names if name in {"__pycache__", ".DS_Store"}}

    # copyfile copie le contenu sans propager les attributs Windows en lecture seule
    # de certains JAR, afin que le dossier public reste remplaçable au build suivant.
    shutil.copytree(pack_dir, destination, ignore=ignored, copy_function=shutil.copyfile)


def build(base_url: str) -> None:
    source = read_json(SOURCE_CATALOG)
    entries = source.get("modpacks") if isinstance(source, dict) else None
    if not isinstance(entries, list):
        raise RuntimeError("catalog.source.json doit contenir une liste 'modpacks'")

    base_url = base_url.rstrip("/")
    stage = ROOT / ".public.tmp"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir()

    generated = []
    seen = set()
    try:
        for index, editable in enumerate(entries, start=1):
            if not isinstance(editable, dict):
                raise RuntimeError(f"Entrée de catalogue {index} invalide")
            pack_id = editable.get("id")
            if not isinstance(pack_id, str) or not pack_id.strip():
                raise RuntimeError(f"id manquant pour le modpack {index}")
            if pack_id in seen:
                raise RuntimeError(f"id dupliqué : {pack_id}")
            seen.add(pack_id)

            pack_dir = PACKS_DIR / pack_id
            if not pack_dir.is_dir():
                if editable.get("enabled") is True:
                    raise RuntimeError(f"Modpack activé mais dossier introuvable : packs/{pack_id}")
                generated.append(dict(editable))
                continue

            destination = stage / "packs" / pack_id
            copy_pack(pack_dir, destination)
            revision = pack_revision(pack_dir)
            total_size = 0
            manifest_urls = {}
            for name in MANIFEST_NAMES:
                source_path = pack_dir / "manifests" / name
                if not source_path.is_file():
                    if name == "configs.json":
                        continue
                    raise RuntimeError(f"Manifest introuvable : {source_path}")
                data, manifest_size = process_manifest(
                    source_path, pack_dir, pack_id, base_url, revision
                )
                total_size += manifest_size
                write_json(destination / "manifests" / name, data)
                manifest_urls[name.removesuffix(".json")] = (
                    f"{base_url}/packs/{quote(pack_id)}/manifests/{quote(name)}"
                )

            result = dict(editable)
            result.update(
                revision=revision,
                size_bytes=total_size,
                size_mb=round(total_size / (1024 * 1024), 1),
                base_url=f"{base_url}/packs/{quote(pack_id)}",
                logo=f"{base_url}/packs/{quote(pack_id)}/assets/logo.png",
                manifests=manifest_urls,
            )
            generated.append(result)
            print(f"[OK] {pack_id}: {result['size_mb']} Mio, révision {revision}")

        generated.sort(key=lambda item: (item.get("order", 999999), item.get("name", "")))
        write_json(
            stage / "catalog.json",
            {
                "schema_version": 2,
                "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "installer": source.get("installer", {}),
                "modpacks": generated,
            },
        )
        (stage / "_headers").write_text(
            "/catalog.json\n  Cache-Control: no-cache, must-revalidate\n\n"
            "/packs/*/manifests/*\n  Cache-Control: no-cache, must-revalidate\n\n"
            "/packs/*/assets/*\n  Cache-Control: public, max-age=3600\n\n"
            "/packs/*/mods/*\n  Cache-Control: public, max-age=31536000, immutable\n\n"
            "/packs/*/resourcepacks/*\n  Cache-Control: public, max-age=31536000, immutable\n\n"
            "/packs/*/shaderpacks/*\n  Cache-Control: public, max-age=31536000, immutable\n\n"
            "/packs/*/datapacks/*\n  Cache-Control: public, max-age=31536000, immutable\n",
            encoding="utf-8",
        )

        if PUBLIC_DIR.exists():
            shutil.rmtree(PUBLIC_DIR)
        os.replace(stage, PUBLIC_DIR)
    except Exception:
        if stage.exists():
            shutil.rmtree(stage)
        raise

    print(f"[OK] Publication générée dans {PUBLIC_DIR}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Génère le catalogue et le dossier Cloudflare Pages.")
    parser.add_argument(
        "--base-url",
        default=(
            os.getenv("PUBLIC_BASE_URL")
            or os.getenv("CF_PAGES_URL")
            or "https://kayou-modpacks.pages.dev"
        ),
        help="URL publique Pages (PUBLIC_BASE_URL, puis CF_PAGES_URL par défaut).",
    )
    args = parser.parse_args()
    build(args.base_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
