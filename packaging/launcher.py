"""CHU2Studio.exe's entry point: PyInstaller runs this file as ``__main__``."""

import sys

from chu2.app.main import main

sys.exit(main())
