"""Stage a public build only after editorial acceptance and automated QA."""
import hashlib, json, shutil, subprocess, sys
from pathlib import Path
from verify_release import verify
ROOT = Path(__file__).resolve().parents[1]

def main():
    source = ROOT / "dist"
    target = (ROOT / "release").resolve()
    if target.parent != ROOT.resolve() or target.name != "release" or target.is_symlink():
        raise ValueError("Unsafe staging path.")
    manifest = json.loads((source / "build-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("mode") != "public" or manifest.get("human_approval") != "approved":
        raise ValueError("Build an accepted public edition before staging.")
    subprocess.run([sys.executable, str(ROOT / "scripts/qa.py"), "--root", "dist"], check=True)
    if target.exists():
        existing = list(target.iterdir())
        if existing and not (target / "build-manifest.json").exists() and any(p.name != ".gitkeep" for p in existing):
            raise ValueError("Refusing to replace an unrecognised release directory.")
        shutil.rmtree(target)
    shutil.copytree(source, target)
    checksums = {p.relative_to(target).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in target.rglob("*") if p.is_file()}
    (target / "release-checksums.json").write_text(json.dumps(checksums, indent=2), encoding="utf-8")
    verified = verify(target)
    print(json.dumps({"staged": True, "articles": verified["article_count"], "path": str(target)}))

if __name__ == "__main__":
    main()
