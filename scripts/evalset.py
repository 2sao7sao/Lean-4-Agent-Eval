"""Repository entry point for M2 dataset generation and independent checking."""

from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from lean4_agent_eval.dataset_cli import main

if __name__ == '__main__':
    raise SystemExit(main())
