import os
import json
import hashlib
import urllib.request
from urllib.error import URLError, HTTPError
from urllib.parse import urlparse, unquote


def get_file_name_from_url(url):
    parsed = urlparse(url)
    file_name = os.path.basename(parsed.path)
    file_name = unquote(file_name)

    if not file_name:
        raise RuntimeError(f"Nom de fichier introuvable dans l'URL: {url}")

    return file_name


def download_and_hash(url):
    """
    Télécharge le fichier depuis l'URL et retourne son sha256.
    """
    sha256 = hashlib.sha256()

    try:
        with urllib.request.urlopen(url) as response:
            while True:
                chunk = response.read(8192)
                if not chunk:
                    break
                sha256.update(chunk)

    except HTTPError as e:
        raise RuntimeError(f"HTTP error {e.code} pour l'URL: {url}")
    except URLError as e:
        raise RuntimeError(f"Impossible de télécharger l'URL: {url} ({e.reason})")

    return sha256.hexdigest()


def enrich_packs(data):
    packs = data.get("packs", [])
    new_packs = []

    for i, pack in enumerate(packs, start=1):
        url = pack.get("download_url")
        if not url:
            print(f"[WARN] Pack #{i}: pas de champ download_url, ignoré.")
            continue

        try:
            file_name = get_file_name_from_url(url)
            sha256 = download_and_hash(url)

            new_pack = {
                "file_name": file_name,
                "download_url": url,
                "sha256": sha256
            }

            new_packs.append(new_pack)
            print(f"[OK] {file_name} -> {sha256}")

        except RuntimeError as e:
            print(f"[ERREUR] {e}")

    data["packs"] = new_packs
    return data


def main():
    input_file = "ress.json"
    output_file = "ressourcepacks_out.json"

    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    data = enrich_packs(data)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"\nFichier généré : {output_file}")


if __name__ == "__main__":
    main()