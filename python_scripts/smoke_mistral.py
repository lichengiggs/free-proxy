from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from python_scripts.smoke import print_smoke


if __name__ == '__main__':
    sys.exit(print_smoke('mistral', 'mistral-small-latest'))
