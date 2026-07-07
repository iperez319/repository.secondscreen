#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import hashlib
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree


REPO_ID = "repository.secondscreen"
RAW_BASE_URL = "https://raw.githubusercontent.com/iperez319/repository.secondscreen/main/zips"
ADDON_ZIP_RETENTION_COUNT = 5

ROOT = Path(__file__).resolve().parent
ZIPS_DIR = ROOT / "zips"
RELEASES_DIR = ROOT / "releases"

ADDON_SOURCES = [
    Path("/Users/iperez/Documents/Projects/kodi/plugin.video.themoviedb.helper"),
    Path("/Users/iperez/Documents/Projects/kodi/plugin.video.watchservice"),
]


def run(cmd, cwd=None):
    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{detail}")
    return result.stdout.strip()


def parse_addon_xml(xml_path):
    tree = ElementTree.parse(xml_path)
    root = tree.getroot()
    addon_id = root.attrib.get("id")
    version = root.attrib.get("version")
    name = root.attrib.get("name", addon_id)
    if not addon_id or not version:
        raise ValueError(f"{xml_path} must contain addon id and version")
    return {"id": addon_id, "version": version, "name": name}


def version_key(path):
    name = Path(path).name
    stem = name[:-4] if name.endswith(".zip") else name
    parts = stem.split("-")[-1].split(".")
    key = []
    for part in parts:
        try:
            key.append(int(part))
        except ValueError:
            key.append(0)
    while len(key) < 3:
        key.append(0)
    return tuple(key)


def ensure_clean_git_repo(source):
    toplevel = Path(run(["git", "rev-parse", "--show-toplevel"], cwd=source)).resolve()
    if toplevel != source.resolve():
        raise ValueError(f"{source} must be the git repository root, got {toplevel}")

    status = run(["git", "status", "--porcelain"], cwd=source)
    if status:
        raise RuntimeError(f"{source} has uncommitted changes:\n{status}")

    sha = run(["git", "rev-parse", "--short", "HEAD"], cwd=source)
    full_sha = run(["git", "rev-parse", "HEAD"], cwd=source)
    remote = run(["git", "remote", "get-url", "origin"], cwd=source) if has_remote(source) else ""
    return {"sha": sha, "full_sha": full_sha, "remote": remote}


def has_remote(source):
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=str(source),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return result.returncode == 0


def ensure_tmdb_fork_version(addon):
    if addon["id"] != "plugin.video.themoviedb.helper":
        return
    parts = addon["version"].split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise ValueError("TMDb Helper fork version must be numeric x.y.z")
    if int(parts[2]) < 100:
        raise ValueError(
            "TMDb Helper fork version must use the fork-safe patch band, "
            f"for example 6.15.100. Found {addon['version']}."
        )


def read_addon_xml_without_declaration(xml_path):
    lines = xml_path.read_text(encoding="utf-8").splitlines()
    if lines and lines[0].lstrip().startswith("<?xml"):
        lines = lines[1:]
    return "\n".join(lines).strip() + "\n"


def validate_zip_top_level(zip_path, addon_id):
    with zipfile.ZipFile(zip_path, "r") as archive:
        names = [name for name in archive.namelist() if name and not name.endswith("/")]
    top_levels = {name.split("/", 1)[0] for name in names}
    if top_levels != {addon_id}:
        raise ValueError(f"{zip_path} top-level folders must be exactly {{{addon_id}}}: {top_levels}")
    addon_xml = f"{addon_id}/addon.xml"
    if addon_xml not in names:
        raise ValueError(f"{zip_path} is missing {addon_xml}")


def prune_old_zips(target_dir, addon_id):
    zip_files = sorted(target_dir.glob(f"{addon_id}-*.zip"), key=version_key, reverse=True)
    for old_zip in zip_files[ADDON_ZIP_RETENTION_COUNT:]:
        old_zip.unlink()
        print(f"Removed old zip: {old_zip.relative_to(ROOT)}")


def package_addon(source, addon):
    addon_id = addon["id"]
    version = addon["version"]
    target_dir = ZIPS_DIR / addon_id
    target_dir.mkdir(parents=True, exist_ok=True)
    zip_path = target_dir / f"{addon_id}-{version}.zip"

    if zip_path.exists():
        zip_path.unlink()

    run(
        [
            "git",
            "archive",
            "--format=zip",
            f"--prefix={addon_id}/",
            "-o",
            str(zip_path),
            "HEAD",
        ],
        cwd=source,
    )
    validate_zip_top_level(zip_path, addon_id)
    prune_old_zips(target_dir, addon_id)
    print(f"Created addon zip: {zip_path.relative_to(ROOT)}")
    return zip_path


def write_changelog(source, addon):
    addon_id = addon["id"]
    version = addon["version"]
    target = ZIPS_DIR / addon_id / f"changelog-{version}.txt"

    candidates = [
        source / f"changelog-{version}.txt",
        source / f"CHANGELOG-{version}.txt",
        source / "changelog.txt",
        source / "CHANGELOG.txt",
        source / "CHANGELOG.md",
    ]
    for candidate in candidates:
        if candidate.exists():
            shutil.copyfile(candidate, target)
            return target

    if addon_id == "plugin.video.themoviedb.helper":
        content = (
            f"changelog-{version}.txt\n"
            "- Base upstream: jurialmunkey/plugin.video.themoviedb.helper 6.15.8\n"
            "- Fork changes: Watch Service player, resume override, episode-group mapping, "
            "and watch-service indicators.\n"
        )
    elif addon_id == "plugin.video.watchservice":
        content = (
            f"changelog-{version}.txt\n"
            "- Watch Service Bridge release for the Kodi second-screen stack.\n"
        )
    else:
        content = f"changelog-{version}.txt\n- Packaged for the Kodi second-screen repository.\n"

    target.write_text(content, encoding="utf-8", newline="\n")
    return target


def package_repository_addon(repo_addon):
    version = repo_addon["version"]
    target_dir = ZIPS_DIR / REPO_ID
    target_dir.mkdir(parents=True, exist_ok=True)
    zip_path = target_dir / f"{REPO_ID}-{version}.zip"

    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for filename in ["addon.xml", "README.md", "icon.png", "fanart.jpg"]:
            path = ROOT / filename
            if path.exists():
                archive.write(path, f"{REPO_ID}/{filename}")

    validate_zip_top_level(zip_path, REPO_ID)
    print(f"Created repository zip: {zip_path.relative_to(ROOT)}")

    index_path = target_dir / "index.html"
    index_path.write_text(
        "<!DOCTYPE html>\n"
        "<html>\n"
        "<head><meta charset=\"UTF-8\"><title>Ian's Kodi Second Screen Repository</title></head>\n"
        "<body>\n"
        "<h1>Ian's Kodi Second Screen Repository</h1>\n"
        f"<a href=\"{zip_path.name}\">{zip_path.name}</a>\n"
        "</body>\n"
        "</html>\n",
        encoding="utf-8",
        newline="\n",
    )
    return zip_path


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def generate_addons_xml(addon_xml_paths):
    xml_parts = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<addons>\n']
    for xml_path in addon_xml_paths:
        xml_parts.append(read_addon_xml_without_declaration(xml_path))
    xml_parts.append("</addons>\n")

    content = "".join(xml_parts)
    addons_xml_path = ZIPS_DIR / "addons.xml"
    addons_xml_path.write_text(content, encoding="utf-8", newline="\n")
    ElementTree.fromstring(content)

    md5 = hashlib.md5(content.encode("utf-8")).hexdigest()
    (ZIPS_DIR / "addons.xml.md5").write_text(md5, encoding="utf-8", newline="\n")
    print(f"Created {addons_xml_path.relative_to(ROOT)} and zips/addons.xml.md5")
    return addons_xml_path


def write_release_manifest(packaged):
    RELEASES_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    manifest_path = RELEASES_DIR / f"release-{stamp}.md"
    lines = [
        f"# Release {stamp}",
        "",
        f"Repository addon: {REPO_ID}",
        f"Repository base URL: {RAW_BASE_URL}",
        "",
        "## Components",
        "",
    ]
    for item in packaged:
        lines.extend(
            [
                f"### {item['id']}",
                "",
                f"- Version: {item['version']}",
                f"- Source: {item.get('source', 'local repository addon')}",
                f"- Source SHA: {item.get('full_sha', 'n/a')}",
                f"- Zip: `{item['zip'].relative_to(ROOT)}`",
                f"- Zip SHA256: `{sha256_file(item['zip'])}`",
                "",
            ]
        )
    manifest_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"Created release manifest: {manifest_path.relative_to(ROOT)}")
    return manifest_path


def main():
    os.chdir(ROOT)
    ZIPS_DIR.mkdir(parents=True, exist_ok=True)

    repo_addon = parse_addon_xml(ROOT / "addon.xml")
    if repo_addon["id"] != REPO_ID:
        raise ValueError(f"Repository addon id must be {REPO_ID}")

    addon_xml_paths = []
    packaged = []

    for source in ADDON_SOURCES:
        addon_xml = source / "addon.xml"
        if not addon_xml.exists():
            raise FileNotFoundError(addon_xml)

        addon = parse_addon_xml(addon_xml)
        ensure_tmdb_fork_version(addon)
        git_info = ensure_clean_git_repo(source)
        zip_path = package_addon(source, addon)
        write_changelog(source, addon)
        addon_xml_paths.append(addon_xml)
        packaged.append(
            {
                "id": addon["id"],
                "version": addon["version"],
                "source": git_info["remote"] or str(source),
                "full_sha": git_info["full_sha"],
                "zip": zip_path,
            }
        )

    repo_zip = package_repository_addon(repo_addon)
    addon_xml_paths.append(ROOT / "addon.xml")
    packaged.append(
        {
            "id": REPO_ID,
            "version": repo_addon["version"],
            "zip": repo_zip,
        }
    )

    generate_addons_xml(addon_xml_paths)
    write_release_manifest(packaged)
    print("Repository generation complete.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
