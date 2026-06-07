"""Test fixtures and path setup for thai-novel tests."""
import sys
from pathlib import Path

# Make src/ importable without an editable install
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
# And make simulation/ importable (it's a top-level package at repo root)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
