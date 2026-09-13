"""Build manifests protect hand edits and keep generated inputs reproducible."""
import hashlib
import json
from pathlib import Path

from project_paths import PROJECT_ROOT


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_build_manifest(root):
    root = Path(root)
    # Documents and human method config are not generator-owned.
    files = {str(p.relative_to(root)): sha256(p) for p in sorted(root.rglob('*'))
             if p.is_file() and p.suffix in ('.json', '.csv')
             and p.name not in ('build_manifest.json', 'pairwise_matrix_registry.json')}
    inputs = ['scripts/calibrate_dataset.py', 'scripts/m1_contracts.py', 'scripts/dataset_build.py',
              'scripts/project_paths.py', 'scripts/validate_dataset.py', 'scripts/dataset_runtime.py',
              'scripts/regulatory_dates.py',
              'config/dataset_migration_history.json']
    manifest = dict(managed_files=files, build_inputs={p: sha256(PROJECT_ROOT/p) for p in inputs},
                    method_configuration='config/pairwise_matrix_registry.json (outside baseline)',
                    policy='Generated files with local edits must be reconciled in a staged output before publication.')
    (root/'calibration').mkdir(exist_ok=True)
    (root/'calibration/build_manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')


def assert_no_unmerged_edits(root, staged):
    root, staged = Path(root), Path(staged)
    manifest_path = root/'calibration/build_manifest.json'
    if not root.exists():
        return
    if not manifest_path.exists():
        raise ValueError('Existing dataset has no build baseline. Build into a new --output directory and reconcile first.')
    manifest = json.loads(manifest_path.read_text())
    changed = [p for p, digest in manifest['managed_files'].items()
               if not (root/p).is_file() or sha256(root/p) != digest]
    new_collisions = [str(p.relative_to(staged)) for p in staged.rglob('*') if p.is_file()
                      and str(p.relative_to(staged)) not in manifest['managed_files']
                      and p.name != 'build_manifest.json' and (root/p.relative_to(staged)).exists()]
    if changed or new_collisions:
        raise ValueError(f'Unmerged local dataset edits: {changed + new_collisions}. '
                         'Preserved unchanged; build with --output into a new scratch directory for review.')
