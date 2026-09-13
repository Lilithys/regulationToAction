"""Real rebuild checks: reproducibility, human-config preservation, edit protection."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from project_paths import PROJECT_ROOT, METHOD_REGISTRY, DATASET_ROOT
from dataset_runtime import DEFAULT_ROOT, load_runtime, calculate_options


def hashes(root):
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


class BuildContractTests(unittest.TestCase):
    def build(self, output):
        return subprocess.run([sys.executable,str(PROJECT_ROOT/'scripts/calibrate_dataset.py'),
            '--output',str(output),'--build-timestamp','2026-09-12T00:00:00Z'],capture_output=True,text=True)

    def test_rebuild_is_reproducible_and_protects_manual_changes(self):
        registry=METHOD_REGISTRY.read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            a,b=Path(tmp,'a'),Path(tmp,'b')
            for target in (a,b):
                result=self.build(target)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual(hashes(a),hashes(b))
            costs=calculate_options(load_runtime(a))
            self.assertEqual([o['scenarios']['base']['three_year_tco_eur'] for o in costs['options']],
                             [806818,451436,481002])
            target=a/'01_entity/bank_profile.json'
            changed=json.loads(target.read_text());changed['manual_note']='Keep my unmerged edit'
            target.write_text(json.dumps(changed))
            before=target.read_bytes()
            result=self.build(a)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('Unmerged local dataset edits',result.stderr)
            self.assertEqual(target.read_bytes(),before)
        self.assertEqual(METHOD_REGISTRY.read_bytes(),registry)

    def test_one_default_dataset_root_and_config_is_not_runtime_input(self):
        self.assertEqual(DEFAULT_ROOT,DATASET_ROOT)
        files=load_runtime()
        self.assertFalse(any('pairwise_matrix_registry' in p for p in files))
        manifest=json.loads((DATASET_ROOT/'dataset_manifest.json').read_text())
        self.assertEqual(manifest['dataset_version'],'0.2.1')
