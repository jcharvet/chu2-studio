"""Build the Windows app: ``dist/CHU2Studio/CHU2Studio.exe`` and a zip to share.

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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from chu2 import __version__  # noqa: E402

NAME = "CHU2Studio"
DIST = os.path.join(ROOT, "dist")
WORK = os.path.join(ROOT, "build", "pyinstaller")
APP_DIR = os.path.join(DIST, NAME)
EXE = os.path.join(APP_DIR, NAME + ".exe")
UI = os.path.join(ROOT, "src", "chu2", "app", "ui")
SMOKE_TIMEOUT = 120  # seconds; the first WebView2 start can be slow


def build() -> None:
    import PyInstaller.__main__

    PyInstaller.__main__.run([
        os.path.join(ROOT, "packaging", "launcher.py"),
        "--name", NAME, "--onedir", "--windowed", "--noconfirm", "--clean",
        "--distpath", DIST, "--workpath", WORK, "--specpath", WORK,
        "--paths", os.path.join(ROOT, "src"),
        "--add-data", f"{UI}{os.pathsep}chu2/app/ui",
        "--recursive-copy-metadata", "chu2-dsp",  # the dependencies' licence files
        "--exclude-module", "tkinter",
        "--exclude-module", "usb",  # research tools only (chu2.research)
    ])


def check() -> None:
    if not glob.glob(os.path.join(APP_DIR, "_internal", "hid*.pyd")):
        sys.exit("hidapi (hid.pyd) is missing from the build: the app couldn't find a real CHU 2")
    if not os.path.isfile(os.path.join(APP_DIR, "_internal", "chu2", "app", "ui", "index.html")):
        sys.exit("the page (chu2/app/ui) is missing from the build")
    try:
        result = subprocess.run([EXE, "--smoke-test"], timeout=SMOKE_TIMEOUT)
    except subprocess.TimeoutExpired:
        sys.exit(f"{NAME}.exe --smoke-test did not finish in {SMOKE_TIMEOUT} s")
    if result.returncode != 0:
        sys.exit(f"{NAME}.exe --smoke-test failed (exit {result.returncode}); "
                 "see chu2-studio.log in the chu2-smoke-* folder under %TEMP%")
    print(f"smoke test passed: {EXE}")


def package() -> str:
    shutil.copy(os.path.join(ROOT, "LICENSE"), os.path.join(APP_DIR, "LICENSE.txt"))
    shutil.copy(os.path.join(sys.base_prefix, "LICENSE.txt"), os.path.join(APP_DIR, "LICENSE-Python.txt"))
    base = os.path.join(DIST, f"{NAME}-{__version__}-win64")
    return shutil.make_archive(base, "zip", DIST, NAME)


if __name__ == "__main__":
    build()
    check()
    print("zip:", package())
