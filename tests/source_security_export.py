"""Export tracked and non-ignored source for local secret scanning, not secrets."""
import shutil
import subprocess
import tempfile
from pathlib import Path

if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    output = Path(tempfile.mkdtemp(prefix='source-export-', dir=root / 'tmp/security'))
    listing = subprocess.check_output(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=root)
    ignored_result = subprocess.run(['git', 'check-ignore', '--no-index', '-z', '--stdin'],
                                    input=listing, capture_output=True, cwd=root)
    if ignored_result.returncode not in (0, 1):
        raise RuntimeError('Cannot verify ignored source paths')
    ignored = set(ignored_result.stdout.split(b'\0'))
    copied = 0
    for raw in listing.split(b'\0'):
        if not raw or raw in ignored: continue
        relative = Path(raw.decode('utf-8')); path = root / relative
        if not path.is_file(): continue
        if path.is_symlink() or not path.resolve().is_relative_to(root): raise RuntimeError('Unexpected source link')
        if path.stat().st_size > 2_000_000: continue
        target = output / relative; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target); copied += 1
    (root / 'tmp/security/source-export-path.txt').write_text(output.name, encoding='utf-8')
    print('Exported non-ignored source files:', copied, 'directory:', output.name)
