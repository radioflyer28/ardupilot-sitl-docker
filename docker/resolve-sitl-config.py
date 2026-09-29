#!/usr/bin/env python3
"""Print validated effective runtime configuration without modifying files."""
import os
from pathlib import Path
import sys

os.execv(sys.executable, [sys.executable, str(Path(__file__).with_name("run-sitl.py")), "--print-effective-config", *sys.argv[1:]])
