"""pytest, backend/ kök dizininden çalışsın diye app paketini yola ekler."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
