#!/usr/bin/env python3
"""Copy personal skills between this repository and a local Codex installation."""
import argparse
from datetime import datetime
from pathlib import Path
import os
import re
import shutil
import tempfile

REPO = Path(__file__).resolve().parent / 'skills'
IGNORE = shutil.ignore_patterns('.git', '.DS_Store', '__pycache__', '*.pyc',
                               '.env', '.env.*', 'node_modules', '.venv', 'venv')
SECRET = re.compile(r'tm_(?:test|live)_[A-Za-z0-9_-]{20,}|\bsk-[A-Za-z0-9_-]{20,}|'
                    r'\bgh[pousr]_[A-Za-z0-9_]{25,}|github_pat_[A-Za-z0-9_]{20,}|'
                    r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')


def local_skills():
    if os.environ.get('CODEX_HOME'):
        return Path(os.environ['CODEX_HOME']).expanduser() / 'skills'
    return Path.home() / '.agents/skills'


def skill_dirs(root):
    if not root.is_dir():
        raise ValueError(f'Skills directory does not exist: {root}')
    return sorted(p for p in root.iterdir()
                  if not p.name.startswith('.') and p.is_dir() and not p.is_symlink()
                  and (p / 'SKILL.md').is_file())


def scan(root):
    for current, dirs, files in os.walk(root, followlinks=False):
        current = Path(current)
        ignored = set(IGNORE(str(current), dirs + files))
        for name in dirs + files:
            if name not in ignored and (current / name).is_symlink():
                raise ValueError(f'Symlink requires manual review: {current / name}')
        dirs[:] = [name for name in dirs if name not in ignored]
        for name in files:
            if name not in ignored and SECRET.search((current / name).read_text(errors='ignore')):
                raise ValueError(f'Potential credential material: {current / name} (contents hidden)')


def transfer(source, destination, replace=False):
    source, destination = Path(source).expanduser().resolve(), Path(destination).expanduser().absolute()
    resolved = destination.resolve()
    if source == resolved or source in resolved.parents or resolved in source.parents:
        raise ValueError('Source and destination must be separate, non-overlapping directories.')
    skills = skill_dirs(source)
    # Check the whole source before copying anything; never print matched values.
    for skill in skills:
        scan(skill)
    destination.mkdir(parents=True, exist_ok=True)
    installed, skipped, backup = [], [], None
    for skill in skills:
        target = destination / skill.name
        if target.exists() or target.is_symlink():
            if not replace:
                skipped.append(skill.name)
                continue
            if backup is None:
                backup_root = destination.parent / 'skill-backups'
                backup_root.mkdir(parents=True, exist_ok=True)
                backup = Path(tempfile.mkdtemp(prefix=datetime.now().strftime('%Y%m%d-%H%M%S-'), dir=backup_root))
            shutil.move(str(target), str(backup / skill.name))
        try:
            shutil.copytree(skill, target, ignore=IGNORE)
        except Exception:
            if target.exists():
                shutil.rmtree(target)
            if backup and (backup / skill.name).exists():
                shutil.move(str(backup / skill.name), str(target))
            raise
        installed.append(skill.name)
    return installed, skipped, backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    install = sub.add_parser('install', help='Install repo skills locally; existing skills are skipped.')
    install.add_argument('--dest', type=Path, default=local_skills())
    install.add_argument('--replace', action='store_true', help='Back up and replace existing skills.')
    export = sub.add_parser('export', help='Copy local skills into the repo; does not delete removed skills.')
    export.add_argument('--source', type=Path, default=local_skills())
    export.add_argument('--replace', action='store_true', help='Back up and replace existing repo skills.')
    args = parser.parse_args()
    source, destination = (REPO, args.dest) if args.action == 'install' else (args.source, REPO)
    try:
        installed, skipped, backup = transfer(source, destination, args.replace)
    except (ValueError, OSError) as exc:
        parser.exit(1, f'{exc}\n')
    print(f'Copied {len(installed)} skills to {destination.expanduser()}')
    if skipped:
        print(f'Skipped {len(skipped)} existing skills; use --replace to back up and replace them.')
    if backup:
        print(f'Previous versions saved in {backup}')


if __name__ == '__main__':
    main()
