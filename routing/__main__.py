import os
import sys

# Works both as `python3 -m routing ...` (package context) and as
# `python3 routing ...` (script execution): put the repo root on sys.path
# so the absolute import resolves in either mode.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from routing.cli import main

sys.exit(main())
