"""Build the Windows app: ``dist/CHU2Studio/CHU2Studio.exe`` and a zip to share.

The zip holds the app's files at its root, so extracting it gives one folder
named after the zip, with ``CHU2Studio.exe`` directly inside.

    pip install -e ".[build]"
    python packaging/build_exe.py

One folder, not one file: it starts faster, and antivirus tools flag
self-extracting single files more often. After the build, the .exe is started
once with ``--smoke-test`` (fake CHU 2, temporary data folder); the build fails
if the page doesn't load. Licences: ours and Python's go next to the .exe,
the dependencies' licences are in their ``*.dist-info`` folders under
``_internal``, the page's (Vue, icons, fonts, Catppuccin) under
``_internal/chu2/app/ui``.
"""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from chu2 import __version__  # noqa: E402

NAME = "CHU2Studio"
DIST = os.path.join(ROOT, "dist")
WORK = os.path.join(ROOT, "build", "pyinstaller")
APP_DIR = os.path.join(DIST, NAME)
EXE = os.path.join(APP_DIR, NAME + ".exe")
UI = os.path.join(ROOT, "src", "chu2", "app", "ui")
SMOKE_TIMEOUT = 180  # seconds; must stay above main.SMOKE_PAGE_TIMEOUT_S
ICON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")


def command() -> list:
    """The PyInstaller options for the app."""
    return [
        os.path.join(ROOT, "packaging", "launcher.py"),
        "--name", NAME, "--onedir", "--windowed", "--noconfirm", "--clean",
        "--distpath", DIST, "--workpath", WORK, "--specpath", WORK,
        "--paths", os.path.join(ROOT, "src"),
        "--add-data", f"{UI}{os.pathsep}chu2/app/ui",
        "--icon", ICON,  # packaging/make_icon.py draws it
        "--recursive-copy-metadata", "chu2-dsp",  # the dependencies' licence files
        "--exclude-module", "tkinter",
        "--exclude-module", "usb",  # research tools only (chu2.research)
    ]


def build() -> None:
    import PyInstaller.__main__

    PyInstaller.__main__.run(command())


def smoke_log() -> str:
    """The log of the last ``--smoke-test`` run: a build machine deletes its
    temp folder, so a failure has to carry the log with it."""
    folders = glob.glob(os.path.join(tempfile.gettempdir(), "chu2-smoke-*"))
    for folder in sorted(folders, key=os.path.getmtime, reverse=True):
        try:
            with open(os.path.join(folder, "chu2-studio.log"), encoding="utf-8") as handle:
                return handle.read()[-4000:]
        except OSError:
            continue
    return "(no log found)"


def check() -> None:
    if not glob.glob(os.path.join(APP_DIR, "_internal", "hid*.pyd")):
        sys.exit("hidapi (hid.pyd) is missing from the build: the app couldn't find a real CHU 2")
    if not os.path.isfile(os.path.join(APP_DIR, "_internal", "chu2", "app", "ui", "index.html")):
        sys.exit("the page (chu2/app/ui) is missing from the build")
    try:
        result = subprocess.run([EXE, "--smoke-test"], timeout=SMOKE_TIMEOUT)
    except subprocess.TimeoutExpired:
        sys.exit(f"{NAME}.exe --smoke-test did not finish in {SMOKE_TIMEOUT} s\n{smoke_log()}")
    if result.returncode != 0:
        sys.exit(f"{NAME}.exe --smoke-test failed (exit {result.returncode})\n{smoke_log()}")
    print(f"smoke test passed: {EXE}")


def package() -> str:
    shutil.copy(os.path.join(ROOT, "LICENSE"), os.path.join(APP_DIR, "LICENSE.txt"))
    shutil.copy(os.path.join(sys.base_prefix, "LICENSE.txt"), os.path.join(APP_DIR, "LICENSE-Python.txt"))
    base = os.path.join(DIST, f"{NAME}-{__version__}-win64")
    # The app's files sit at the root of the zip, not inside another CHU2Studio folder:
    # Windows already makes a folder named after the zip when you extract it, so wrapping
    # them gave everyone ...\CHU2Studio-0.1.1-win64\CHU2Studio\CHU2Studio.exe.
    return shutil.make_archive(base, "zip", APP_DIR)


if __name__ == "__main__":
    build()
    check()
    print("zip:", package())
