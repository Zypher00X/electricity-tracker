"""Make a build/scanner context from an explicit source allowlist, never .env/keys."""
import tarfile
from pathlib import Path

if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    paths = [root / 'Dockerfile.production', root / 'Back__end/requirements.txt', root / 'Back__end/requirements.lock']
    for folder in ('Back__end/app', 'Front__end', 'tests'):
        paths.extend(p for p in (root / folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in {'.pyc', '.log'})
    output = root / 'tmp/security/build-context.tar'
    with tarfile.open(output, 'w') as archive:
        for path in sorted(set(paths)):
            if path.is_symlink(): raise RuntimeError('Symlink not allowed in security build context')
            archive.add(path, arcname=path.relative_to(root).as_posix(), recursive=False)
    print('Source files:', len(set(paths)), 'archive bytes:', output.stat().st_size)
