"""Validate the exact public artifact staged for the manual Pages workflow."""
import hashlib, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def verify(folder):
    folder = Path(folder)
    manifest = json.loads((folder / "build-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("mode") != "public" or manifest.get("human_approval") != "approved":
        raise ValueError("Only an accepted public build can be deployed.")
    if manifest.get("article_count", 0) < 1:
        raise ValueError("Empty release.")
    seal = json.loads((folder / "release-checksums.json").read_text(encoding="utf-8"))
    files = {p.relative_to(folder).as_posix(): p for p in folder.rglob("*") if p.is_file() and p.name != "release-checksums.json"}
    if set(files) != set(seal):
        raise ValueError("Release files changed after staging.")
    for name, path in files.items():
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != seal[name]:
            raise ValueError("Release checksum mismatch: " + name)
        if path.suffix == ".html" and 'name="robots" content="noindex' in path.read_text(encoding="utf-8"):
            raise ValueError("Review page in public release: " + name)
    catalog = json.loads((folder / "catalog.json").read_text(encoding="utf-8"))
    if catalog.get("status") != "published" or len(catalog["articles"]) != manifest["article_count"]:
        raise ValueError("Catalogue differs from release.")
    for article in catalog["articles"]:
        if article.get("status") != "published" or not article.get("english_publication_date"):
            raise ValueError("Unpublished article in release.")
    return manifest

if __name__ == "__main__":
    result = verify(ROOT / "release")
    print(json.dumps({"verified": True, "articles": result["article_count"]}))
