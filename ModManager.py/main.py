#!/usr/bin/env python3

from datetime import datetime
from pathlib import Path

import argparse
import json
import modio
import os
import requests
import shutil
import subprocess
import uuid
import zipfile

import configparser
config = configparser.ConfigParser()
pwd = Path(__file__).parent
config_file = pwd / "config.ini"
if not config_file.exists():
    raise Exception("No configuration file found")
config.read(str(config_file))

can_download = False
client = None

if "mod.io" in config and "API_KEY" in config['mod.io']:
    can_download = True
    client = modio.ModioClient(api_key=config['mod.io']['API_KEY'])

# Default cache dir
cache_dir_str = "~/.mod.io"
if "core" in config and "CACHE_DIR" in config['core']:
    cache_dir_str = config['core']['CACHE_DIR']

cache_dir = Path(os.path.expanduser(cache_dir_str))
download_dir = cache_dir / "download"
staging_dir_root = cache_dir / "staging"
db_dir = cache_dir / "storage"
profile_dir = cache_dir / "profiles"
deployed_file_name = "deployed.txt"
force_download = False


def get_all_children(p: Path):
    if p.is_dir():
        for c in p.iterdir():
            yield from get_all_children(c)

    if p.is_file():
        yield p


def sizeof_fmt(num, suffix='B'):
    for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix), num
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Yi', suffix), num


def ask_for_confirmation(msg):
    answer = ""
    while answer not in ["y", "n"]:
        answer = input(f"{msg} [y/n] ").lower()
    return answer == "y"


def remove_empty_directories(path: Path, remove_root: bool = False):
    """Function to remove empty folders"""
    if not path.is_dir():
        return

        # remove empty subfolders
    files = path.iterdir()
    for f in files:
        remove_empty_directories(f, True)

    # if folder empty, delete it
    files = [x for x in path.iterdir()]
    if len(files) == 0 and remove_root:
        print(f"Removing empty folder: {path}")
        os.rmdir(path)


class Profile(object):

    @staticmethod
    def create_empty(path: Path):
        p = Profile(path)

        p.data['name'] = p.name
        p.data['id'] = p.id
        p.data['install_directory'] = p.install_directory
        p.data['mods'] = p.mod_dict

        p.write_to_file()
        return p

    def __init__(self, path: Path):
        self.path = path

        if path.exists():
            text = path.read_text()
            self.data = data = json.loads(text)
            self.name = data['name']
            self.id = data['id']
            self.install_directory = data['install_directory']
            self.mod_dict = data['mods']
        else:
            self.data = {}
            self.name = None
            self.id = -1
            self.install_directory = None
            self.mod_dict = {}
        self.uuid = self.data['uuid'] if "uuid" in self.data and self.data["uuid"] else self.generate_uuid()

    def write_to_file(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2))

    @property
    def reference(self):
        return self.path.name[:self.path.name.index(".")]

    @property
    def is_valid(self):
        return len(self.data) > 0 and self.name is not None and self.id >= 0 and self.install_directory is not None

    @property
    def mods(self):
        return self.mod_dict.items()

    @property
    def download_dir(self):
        d = download_dir / self.name
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def staging_dir(self):
        d = staging_dir_root / str(self.id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def deployed_file_manifest(self):
        return self.db_dir / deployed_file_name

    @property
    def db_dir(self):
        d = db_dir / self.uuid
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def install_path(self):
        return Path(self.install_directory)

    def generate_uuid(self):
        id = str(uuid.uuid4())
        self.data['uuid'] = id
        print(f"Generating new UUID for {self.name}, writing to {self.path}")
        self.write_to_file()
        return id

    def __str__(self):
        return f"{self.name} [{self.id}, {self.install_dir}], mods: {len(self.mods)}"


def download(url: str, file: Path):
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with file.open(mode='wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)


def try_download(profile: Profile, mod: modio.Mod, file: modio.File):
    print(f"Trying to download {profile.name} / {mod.name} / {file.name}")

    mod_dir = profile.download_dir / str(mod.id)
    mod_dir.mkdir(parents=True, exist_ok=True)

    file_loc = mod_dir / file.name
    if file_loc.exists():
        if file_loc.stat().st_mtime >= file.timestamp and not force_download:
            print("  > Not downloading, remote file is older than the local")
            return False
        file_loc.unlink()
    download(file.download_url, file_loc)
    fmt = sizeof_fmt(file_loc.stat().st_size)
    print(f"  > Successfully downloaded {fmt[0]} byte{'s' if fmt[1] != 1 else ''} to {str(file_loc)}")
    return file_loc


def get_latest_file(directory: Path):
    print(f"[DEBUG] Getting latest file in {directory}")
    latest_child = None
    for child in directory.iterdir():
        print(f"[DEBUG]   Testing {child}")
        if latest_child:
            if child.stat().st_mtime > latest_child.stat().st_mtime:
                print(f"[DEBUG]     {child} is now the latest child")
                latest_child = child
        else:
            print(f"[DEBUG]     First {child}")
            latest_child = child
    return latest_child


def run_download(profile: Profile):
    if not can_download:
        print(f"No API key provided, downloads cannot be performed")
        return
    print(f"Updating {profile.name}")
    for mod_name, mod_id in profile.mods:
        print(f"Updating {mod_name}")
        mod = client.get_mod(profile.id, mod_id)
        file = mod.get_latest_file()
        try_download(profile, mod, file)


def cleanup(profile: Profile):
    deployed_file_manifest = profile.deployed_file_manifest
    if not deployed_file_manifest.exists():
        print("Found no deployment metadata, cannot perform cleanup")
        return
    installed_dir = profile.install_path
    text = deployed_file_manifest.read_text()
    for line in text.splitlines():
        deployed_file = installed_dir / line
        if deployed_file.exists() and deployed_file.is_file():
            print(f" - Removing {str(deployed_file)}")
            deployed_file.unlink()

    remove_empty_directories(installed_dir, False)
    deployed_file_manifest.unlink()


def deploy(profile: Profile):
    print(f"Deploying staged mods for {profile.name}")
    game_db_dir = profile.db_dir
    deployed_file = game_db_dir / deployed_file_name
    installed_dir = profile.install_path

    if deployed_file.exists():
        cleanup(profile)

    deployed_lines = []

    for child in profile.staging_dir.iterdir():
        print(f"  > Deploying {child}")
        if child.suffix == ".dll":
            deployed_lines.append(child.name)
            target = installed_dir / child.name
            shutil.move(str(child), str(target))
        elif child.is_dir():
            root = child
            root_path = str(root.parent.resolve())
            for c in get_all_children(child):
                path = str(c.resolve())[len(root_path)+1:]
                deployed_lines.append(path)

            target = installed_dir / child.name
            shutil.move(str(child), str(target))
        else:
            print(f"    > Unsupported mod type: {child}")
            continue

    print("  > Writing deployment manifest")
    deployed_file.write_text("\n".join(deployed_lines))


def stage(profile: Profile):
    game_mod_dir = profile.download_dir
    print(f"Staging {profile.name} mods")
    for mod_name, mod_id in profile.mods:
        mod_dir = game_mod_dir / str(mod_id)
        if not mod_dir.exists():
            print(f"  > Mod {mod_name} not found, is it downloaded? (looking for {mod_dir})")
            continue
        mod_file = get_latest_file(mod_dir)
        if mod_file.suffix == ".zip":
            print(f"  > Staging {mod_name}")
            with zipfile.ZipFile(str(mod_file), "r") as zip:
                zip.extractall(str(profile.staging_dir))
        else:
            print(f"  > Mod {mod_name} is an unsupported file type [{mod_file}]")


def run_profile(profile: Profile):
    cleanup(profile)
    run_download(profile)
    stage(profile)
    deploy(profile)


def get_profiles():
    global profile_dir
    for child in profile_dir.iterdir():
        if child.name.endswith(".json"):
            yield Profile(child)

def do():
    parser = argparse.ArgumentParser()

    # Stages
    #  - Download
    #  - Stage
    #  - Deploy
    #  - Cleanup

    parser.add_argument("--cache-dir", action="store_true")
    parser.add_argument("--download-dir", action="store_true")
    parser.add_argument("--staging-dir", action="store_true")
    parser.add_argument("--db-dir", action="store_true")
    parser.add_argument("--profile-dir", action="store_true")

    parser.add_argument("--edit", action="store_true", help="Opens the given profiles in `edit`")
    parser.add_argument("--edit-with", type=str, help="Opens the given profiles in the provided editor")
    parser.add_argument("--delete", action="store_true", help="Delete the given profiles")

    parser.add_argument("--view", "-v", action="store_true", help="Outputs the given profiles")
    parser.add_argument("--force", "-f", action="store_true", help="Force download")
    parser.add_argument("--download", "-D", action="store_true", help="Perform Download")
    parser.add_argument("--stage", "-s", action="store_true", help="Perform Staging")
    parser.add_argument("--deploy", "-d", action="store_true", help="Perform Deployment")
    parser.add_argument("--cleanup", "-c", action="store_true", help="Perform Cleanup")

    parser.add_argument("--get", type=str)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--list-deployed", action="store_true")

    parser.add_argument("profiles", type=str, nargs="*", help="The profiles to process")

    args = parser.parse_args()

    if args.list:
        print(f"Profiles:")
        for profile in get_profiles():
            print(f" - {profile.reference}")
        return

    if args.cache_dir:
        print(str(cache_dir))
        return
    if args.download_dir:
        print(str(download_dir))
        return
    if args.staging_dir:
        print(str(staging_dir_root))
        return
    if args.db_dir:
        print(str(db_dir))
        return
    if args.profile_dir:
        print(str(profile_dir))
        return

    if len(args.profiles) == 0:
        print("No profile names provided")
        return

    global force_download
    force_download = args.force

    for p in args.profiles:
        profile_path = profile_dir / (p + ".json")

        if args.edit or args.edit_with:
            editor = args.edit_with if args.edit_with else "edit"
            if not profile_path.exists():
                tmp = Profile.create_empty(profile_path)
                subprocess.call([editor, str(profile_path)])
                tmp.write_to_file()
            else:
                subprocess.call([editor, str(profile_path)])
            continue

        if not profile_path.exists():
            print(f"No profile called {p} can be found, check that it exists in {profile_path}")
            continue

        if args.view:
            print(profile_path.read_text())

        if args.delete:
            if ask_for_confirmation(f"Do you want to delete {profile_path}?"):
                profile_path.unlink()
            continue

        profile = Profile(profile_path)
        if not profile.is_valid:
            print(f"Profile found at {profile_path} is not valid")
            continue

        if args.list_deployed:
            m = profile.deployed_file_manifest
            if not m.exists():
                print(f"No deployment manifest found for {profile.name} at {str(m)}")
                continue
            print(f"{profile.name} deployment manifest")
            for line in m.read_text().splitlines():
                print(f" - {line}")
            continue

        if args.get:
            if args.get in profile.data:
                prefix = f"{profile.name}/{args.get} = " if len(args.profiles) > 1 else ""
                print(f"{prefix}{profile.data[args.get]}")
            else:
                print(f"{args.get} not found in {profile.name}")
            continue

        should_run_profile = True

        if args.cleanup:
            should_run_profile = False
            cleanup(profile)

        if args.download:
            should_run_profile = False
            run_download(profile)

        if args.stage:
            should_run_profile = False
            stage(profile)

        if args.deploy:
            should_run_profile = False
            deploy(profile)

        if should_run_profile:
            print(f"Running full process for {p}")
            run_profile(profile)


if __name__ == '__main__':
    do()
