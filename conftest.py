"""Root pytest configuration."""

import sys
from pathlib import Path

# Add service paths so pytest can import modules without PYTHONPATH tweaks.
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "services" / "api"))
sys.path.insert(0, str(ROOT / "services" / "ocerp"))
sys.path.insert(0, str(ROOT / "services" / "data-pipeline" / "src"))
