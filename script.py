import io
import json
import zipfile
import urllib.request
from urllib.error import URLError, HTTPError


def read_fabric_mod_json_from_url(url):
    """
    Télécharge un fichier .jar depuis l'URL, ouvre l'archive,
    puis lit fabric.mod.json pour récupérer id et version.
    """
    try:
        with urllib.request.urlopen(url) as response:
            jar_data = response.read()
    except HTTPError as e:
        raise RuntimeError(f"HTTP error {e.code} pour l'URL: {url}")
    except URLError as e:
        raise RuntimeError(f"Impossible de télécharger l'URL: {url} ({e.reason})")

    try:
        with zipfile.ZipFile(io.BytesIO(jar_data), "r") as jar:
            if "fabric.mod.json" not in jar.namelist():
                raise RuntimeError(f"fabric.mod.json introuvable dans: {url}")

            with jar.open("fabric.mod.json") as f:
                mod_json = json.load(f)
    except zipfile.BadZipFile:
        raise RuntimeError(f"Le fichier téléchargé n'est pas un .jar valide: {url}")
    except json.JSONDecodeError:
        raise RuntimeError(f"fabric.mod.json invalide dans: {url}")

    mod_id = mod_json.get("id")
    version = mod_json.get("version")

    if not mod_id:
        raise RuntimeError(f"Champ 'id' introuvable dans fabric.mod.json pour: {url}")
    if not version:
        raise RuntimeError(f"Champ 'version' introuvable dans fabric.mod.json pour: {url}")

    return mod_id, version


def enrich_mods(data):
    mods = data.get("mods", [])
    new_mods = []

    for i, mod in enumerate(mods, start=1):
        url = mod.get("download_url")
        if not url:
            print(f"[WARN] Mod #{i}: pas de champ download_url, ignoré.")
            continue

        try:
            mod_id, version = read_fabric_mod_json_from_url(url)

            # on reconstruit le dict dans le bon ordre
            new_mod = {
                "id": mod_id,
                "version": version,
                "download_url": url
            }

            new_mods.append(new_mod)
            print(f"[OK] {mod_id} -> {version}")

        except RuntimeError as e:
            print(f"[ERREUR] {e}")

    data["mods"] = new_mods
    return data



def main():
    input_file = "tests.json"
    output_file = "mods_out.json"

    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    data = enrich_mods(data)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\nFichier généré : {output_file}")


if __name__ == "__main__":
    main()
