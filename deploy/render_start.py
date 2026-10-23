"""Render entrypoint: respect PORT; never trust arbitrary forwarded IP headers."""
import os


def command():
    port = int(os.getenv('PORT', '10000'))
    workers = int(os.getenv('WEB_CONCURRENCY', '1'))
    if not 1 <= port <= 65535 or not 1 <= workers <= 4:
        raise ValueError('Invalid PORT or WEB_CONCURRENCY')
    return ['uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', str(port),
            '--workers', str(workers), '--no-server-header', '--no-proxy-headers']


if __name__ == '__main__':
    os.execvp('uvicorn', command())
