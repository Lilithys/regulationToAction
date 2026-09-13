"""Stage only public frontend assets for Sites hosting."""
from pathlib import Path
from shutil import copyfile

ROOT = Path(__file__).resolve().parent
ASSETS = ('index.html', 'styles.css', 'icons.js', 'display_text.js', 'api.js', 'app.js')

if __name__ == '__main__':
    output = ROOT / 'dist'
    output.mkdir(exist_ok=True)
    for filename in ASSETS:
        copyfile(ROOT / filename, output / filename)
    unexpected = {p.name for p in output.iterdir()} - set(ASSETS)
    if unexpected:
        raise RuntimeError(f'Unexpected public output files: {sorted(unexpected)}')
    print(f'Staged {len(ASSETS)} public assets in {output}')
