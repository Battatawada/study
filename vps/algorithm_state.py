"""Algorithm state model — re-export from shared composition_motion package."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from composition_motion.algorithm_state import *  # noqa: F403
