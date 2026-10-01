"""Install the self-contained skill without overwriting an existing copy."""
import os
from pathlib import Path
import shutil


def main():
    source = Path(__file__).resolve().parents[1] / 'skills/road-maintenance-standards'
    codex_dir = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex')))
    destination = codex_dir / 'skills' / source.name
    if destination.exists():
        raise SystemExit(f'Already exists; compare/back up your changes before updating: {destination}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.tmp'))
    print(f'Installed: {destination}')
    print('Open a new Codex session and invoke $road-maintenance-standards.')


if __name__ == '__main__':
    main()
