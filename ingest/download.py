"""Download the WoW Avatar History dataset (parquet version) and verify it.

Source: Vincent Warmerdam's parquet conversion of the WoWAH dataset
(github.com/koaning/wow-avatar-datasets, also linked from calmcode.io), stored
with Git LFS. The original RAR archive is on the WPI MMSys dataset page.

Usage: python ingest/download.py [--out data/raw/wow-full.parquet]
"""

import argparse
import hashlib
import shutil
import sys
import urllib.request
from pathlib import Path

URLS = [
    "https://media.githubusercontent.com/media/koaning/wow-avatar-datasets/main/wow-full.parquet",
    "https://calmcode.io/static/data/wow-full.parquet",
]
SHA256 = "4d9a0583a9e6bf513c3f9326d348f7673df274585cf4c161562be5f1253e7cfd"
SIZE = 318_753_193


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url, dest):
    tmp = dest.with_suffix(".part")
    with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f, length=1 << 20)
    tmp.replace(dest)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/raw/wow-full.parquet")
    args = ap.parse_args()
    dest = Path(args.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size == SIZE and sha256(dest) == SHA256:
        print(f"{dest} already downloaded and verified")
        return
    for url in URLS:
        try:
            print(f"downloading {url} ...")
            download(url, dest)
        except Exception as e:  # noqa: BLE001
            print(f"  failed: {e}")
            continue
        if sha256(dest) == SHA256:
            print(f"saved {dest} ({dest.stat().st_size:,} bytes, checksum ok)")
            return
        print("  checksum mismatch, trying the next source")
    sys.exit("Could not download a verified copy. Get wow-full.parquet manually and put it in data/raw/.")


if __name__ == "__main__":
    main()
