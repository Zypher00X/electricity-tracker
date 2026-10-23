"""Explicitly generate an all-distribution hash lock from reviewed runtime pins."""
import concurrent.futures
import re
from pathlib import Path
import requests

if __name__ == '__main__':
    pins = Path('tmp/security/runtime-before.txt').read_text(encoding='utf-8-sig').splitlines()
    fixes = {'certifi': '2026.10.19', 'opentelemetry-api': '1.45.1'}
    def entry(line):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+==[A-Za-z0-9_.+-]+', line):
            raise ValueError('Unexpected runtime pin')
        name, version = line.split('=='); version = fixes.get(name.lower(), version)
        response = requests.get(f'https://pypi.org/pypi/{name}/{version}/json', timeout=60)
        response.raise_for_status()
        hashes = sorted({row['digests']['sha256'] for row in response.json()['urls'] if not row.get('yanked')})
        if not hashes or any(not re.fullmatch('[a-f0-9]{64}', value) for value in hashes):
            raise ValueError('Missing distribution hash')
        marker = '; sys_platform != "win32"' if name.lower() == 'uvloop' else ''
        return name + '==' + version + marker + ' \\\n' + ' \\\n'.join('    --hash=sha256:' + value for value in hashes)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        lines = list(pool.map(entry, [line.strip() for line in pins if line.strip()]))
    Path('Back__end/requirements.lock').write_text('# Reviewed runtime snapshot 2026-10-23; Linux/Python 3.12.\n# Hashes include all non-yanked PyPI distributions for these exact versions.\n' + '\n'.join(lines) + '\n', encoding='utf-8')
    print('Wrote hash-locked packages:', len(lines))
