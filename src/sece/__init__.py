"""Simply Explained Composition Engine — schemas, validation, compile."""

from sece.constants import SCHEMA_VERSION
from sece.pipeline import run_post_phase1, run_post_phase2

__all__ = ["SCHEMA_VERSION", "run_post_phase1", "run_post_phase2"]
