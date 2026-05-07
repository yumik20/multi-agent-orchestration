"""
Pytest configuration. Adds each top-level sample directory to sys.path
so tests can import the modules without package-ifying the repo (the
hyphens in folder names like `quality-gates` make standard package
imports awkward, and the repo's structure is intentionally folder-per-
demonstration rather than a single installable package).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

for sub in (
    "quality-gates",
    "cost-optimization",
    "skill-rating-eval",
    "agent-orchestration",
    "scan-pipeline",
    "mcp-server",
    "error-handling",
):
    p = ROOT / sub
    if p.exists() and str(p) not in sys.path:
        sys.path.insert(0, str(p))
