"""Audit publication candidates; optionally copy a clean, uncommitted review snapshot.

Uses Git's ignore rules in a temporary metadata directory, without initializing the
working project or reading ignored secrets. Never commits, pushes, or creates a remote.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'reports/generated/github-preparation'
PRIVATE = {'docs/plugin-artifacts.md', 'data/benchmarks/reserved.local.json'}
PATTERNS = {
    'possible Google credential': re.compile(rb'AIza[0-9A-Za-z_-]{30,}|AQ\.Ab[0-9A-Za-z_-]{20,}'),
    'possible GitHub credential': re.compile(rb'gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}'),
    'private key': re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'private workspace link': re.compile(rb'https://(?:app\.)?notion\.com/|https://drive\.google\.com/'),
}


def candidates():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='github-audit-', dir=OUTPUT.parent) as temp:
        metadata = Path(temp) / 'metadata.git'
        env = {**os.environ, 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull}
        subprocess.run(['git', '-c', 'init.templateDir=', 'init', '--bare', '--quiet', str(metadata)],
                       check=True, capture_output=True, env=env)
        result = subprocess.run(['git', f'--git-dir={metadata}', f'--work-tree={ROOT}',
                                 'ls-files', '--others', '--exclude-standard', '-z'],
                                cwd=ROOT, check=True, capture_output=True, env=env)
        return sorted(p.decode('utf8') for p in result.stdout.split(b'\0') if p)


def audit(paths):
    errors, manifest = [], []
    for relative in paths:
        path = ROOT / relative
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT):
            errors.append(f'{relative}: external path or symbolic link')
            continue
        if relative in PRIVATE or path.name.startswith('.env') and path.name != '.env.example':
            errors.append(f'{relative}: private file selected')
            continue
        if path.suffix.lower() in {'.db', '.sqlite', '.sqlite3', '.onnx', '.faiss', '.pem', '.key', '.pyc'}:
            errors.append(f'{relative}: local runtime artifact selected')
            continue
        content = path.read_bytes()
        for label, pattern in PATTERNS.items():
            if pattern.search(content): errors.append(f'{relative}: {label}')
        if len(content) > 20 * 1024 * 1024:
            errors.append(f'{relative}: exceeds review size limit')
        if relative == 'data/benchmarks/development.json':
            pack = json.loads(content)
            if any(row['split'] != 'dev' for row in pack['examples']):
                errors.append(f'{relative}: reserved benchmark contents selected')
        manifest.append({'path': relative, 'bytes': len(content),
                         'sha256': hashlib.sha256(content).hexdigest()})
    if errors:
        raise SystemExit('Publication audit failed (values withheld):\n' + '\n'.join(errors))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export', action='store_true', help='Create a new clean review snapshot; refuses overwrite.')
    args = parser.parse_args()
    manifest = audit(candidates())
    for relative in PRIVATE | {'.env'}:
        if relative in {row['path'] for row in manifest}:
            raise SystemExit('Private file unexpectedly selected.')
    print(f'Publication audit passed: {len(manifest)} files, {sum(r["bytes"] for r in manifest):,} bytes.')
    print('Excluded ignored secrets, private tracking, reserved questions, databases, models, builds and dependencies.')
    if args.export:
        OUTPUT.mkdir(exist_ok=True)
        snapshot=OUTPUT / datetime.now(timezone.utc).strftime('source-%Y%m%dT%H%M%S%fZ')
        snapshot.mkdir(exist_ok=False)
        for row in manifest:
            target = snapshot / row['path']
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / row['path'], target)
            if hashlib.sha256(target.read_bytes()).hexdigest() != row['sha256']:
                raise SystemExit('Source changed during export; discard and repeat preparation.')
        manifest_path = snapshot.with_suffix('.manifest.json')
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf8')
        print(f'Clean uncommitted review copy: {snapshot}')
        print(f'File hashes: {manifest_path}')


if __name__ == '__main__':
    main()
