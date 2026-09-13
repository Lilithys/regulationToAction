"""Single source of project paths. Runtime state never belongs in the baseline."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DATA_ROOT = PROJECT_ROOT / 'data'
DATASET_ROOT = PROJECT_ROOT / 'calibrated_v0_2'
RUNS_ROOT = PROJECT_ROOT / 'runs'
METHOD_REGISTRY = PROJECT_ROOT / 'config' / 'pairwise_matrix_registry.json'
