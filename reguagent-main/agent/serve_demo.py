#!/usr/bin/env python3
"""Serve a disposable, replay-only demo; recreate its cases after storage resets."""
import os
from pathlib import Path

from api_server import make_server
from case_store import CaseStore
from compressed_demo import run as compressed_run
from project_paths import PROJECT_ROOT
from run_case import GOAL, run
from source_intake import open_registered_case


def initialize_demo(db_path):
    """Seed an empty database atomically; preserve decisions while it exists."""
    with CaseStore(db_path) as store:
        if store.cases():
            return False
        with store.transaction():
            case_id, _ = open_registered_case(store, GOAL, 'replay', nonce='hosted-demo')
            run(store, case_id)
            compressed_run(store, PROJECT_ROOT / 'materials/esg_demo/request_regulation.json', mode='replay')
        return True


def main():
    state_dir = Path(os.environ.get('DEMO_STATE_DIR', '/tmp/regulation-to-action-demo'))
    db_path = state_dir / 'cases.sqlite3'
    created = initialize_demo(db_path)
    server = make_server(db_path, host='0.0.0.0', port=int(os.environ.get('PORT', '8765')), replay_only=True)
    print(f'Replay demo ready; seeded={created}; temporary storage={state_dir}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.case_store.close()
        server.server_close()


if __name__ == '__main__':
    main()
