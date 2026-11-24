"""Idempotently integrate the overlay into the existing FaceLab checkout.

Place extracted patch files directly in the project root, then run:
    python apply_patch.py
"""
from pathlib import Path
from shutil import copy2

ROOT = Path(__file__).resolve().parent
MAIN = ROOT / "backend/app/main.py"
REQUIREMENTS = ROOT / "backend/requirements.txt"
DOCKERFILE = ROOT / "backend/Dockerfile"
DOCKERIGNORE = ROOT / "backend/.dockerignore"
HTML = ROOT / "frontend/index.html"
README = ROOT / "README.md"


def edit(path, transform):
    if not path.is_file():
        raise SystemExit(f"Missing original repository file: {path}")
    original = path.read_text(encoding="utf-8")
    changed = transform(original)
    if changed != original:
        backup = path.with_name(path.name + ".before-offloading.bak")
        if not backup.exists():
            copy2(path, backup)
        path.write_text(changed, encoding="utf-8")
        print("UPDATED:", path.relative_to(ROOT))
    else:
        print("UNCHANGED:", path.relative_to(ROOT))


def patch_main(src):
    import_line = "from .offloading.api import router as offloading_router"
    if import_line not in src:
        anchor = "from .execution import Strategy, execute_local"
        if anchor not in src:
            raise SystemExit("Cannot find main.py import anchor; inspect source before patching")
        src = src.replace(anchor, anchor + "\n" + import_line, 1)
    include = "app.include_router(offloading_router)"
    if include not in src:
        anchor = 'app = FastAPI(title="FaceLab API", lifespan=lifespan)'
        if anchor not in src:
            raise SystemExit("Cannot find FastAPI app anchor; inspect source before patching")
        src = src.replace(anchor, anchor + "\n" + include, 1)
    return src


def patch_requirements(src):
    req = "simpy==4.1.1"
    if any(x.strip().lower().startswith("simpy") for x in src.splitlines()):
        return src
    return src.rstrip() + "\n" + req + "\n"


def patch_dockerfile(src):
    if "COPY tests ./tests" in src:
        return src
    anchor = "COPY app ./app"
    if anchor not in src:
        raise SystemExit("Cannot find Dockerfile app COPY anchor")
    return src.replace(anchor, anchor + "\nCOPY tests ./tests", 1)


def patch_dockerignore(src):
    return "\n".join(line for line in src.split("\n") if line.strip() != "tests")


def patch_html(src):
    if 'href="/simulator.html"' in src:
        return src
    anchor = '<div id="root"></div>'
    if anchor not in src:
        raise SystemExit("Cannot find root element in frontend/index.html")
    addition = ('<a href="/simulator.html" '
                'style="position:fixed;bottom:18px;right:18px;z-index:1000;'
                'background:#225d45;color:white;padding:11px 15px;border-radius:8px;'
                'font:600 13px system-ui;text-decoration:none;box-shadow:0 4px 16px #0003">'
                '卸載模擬器 ↗</a>')
    return src.replace(anchor, anchor + addition, 1)


def patch_readme(src):
    line = "\n\n## Local–Edge–Cloud 卸載模擬\n\n詳見 [README_OFFLOADING.md](README_OFFLOADING.md)。\n"
    return src if "README_OFFLOADING.md" in src else src.rstrip() + line


def main():
    edit(MAIN, patch_main)
    edit(REQUIREMENTS, patch_requirements)
    edit(DOCKERFILE, patch_dockerfile)
    edit(DOCKERIGNORE, patch_dockerignore)
    edit(HTML, patch_html)
    edit(README, patch_readme)
    print("Completed. Then run: docker compose up -d --build")


if __name__ == "__main__":
    main()
