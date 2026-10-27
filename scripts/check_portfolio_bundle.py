"""Fail a release if the guided build includes local API code or obvious secrets."""
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
folder=ROOT/'frontend/dist-portfolio'
if not (folder/'index.html').is_file():
    raise SystemExit('Build the portfolio first.')
scripts=list((folder/'assets').glob('*.js'))
assert scripts, 'Missing JavaScript assets'
for path in scripts:
    text=path.read_text(encoding='utf-8')
    for forbidden in ['127.0.0.1:8000','/api/oracle','/api/evaluation','GEMINI_API_KEY','"reviewer":','review_snapshot','reserved_test']:
        assert forbidden not in text, f'Forbidden runtime marker in {path.name}: {forbidden}'
    assert not re.search(r'AIza[0-9A-Za-z_-]{30,}|AQ\.Ab[0-9A-Za-z_-]{20,}',text), 'Possible credential'
    assert not re.search(r'\bfetch\s*\(',text), 'Guided runtime must not call fetch'
for path in folder.rglob('*'):
    if path.is_file():
        assert path.suffix not in {'.sqlite3','.sqlite','.db','.onnx','.map'}, 'Private or unnecessary artifact'
        assert not path.name.startswith('.env'), 'Environment file in public build'
config=json.loads((ROOT/'frontend/vercel.json').read_text())
assert any("connect-src 'none'" in header['value'] for entry in config['headers'] for header in entry['headers'])
print(f'Portfolio safety checks passed: {len(scripts)} JavaScript asset(s), no API fetch paths or private artifact types.')
