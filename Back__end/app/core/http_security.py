"""Small ASGI boundary: browser-origin checks, bounded bodies and response headers."""
import os
from urllib.parse import urlsplit
from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse


def origin(value):
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password:
            return None
        if parsed.path not in ('', '/') or parsed.query or parsed.fragment:
            return None
        return parsed.scheme, parsed.hostname.lower(), parsed.port or (443 if parsed.scheme == 'https' else 80)
    except ValueError:
        return None


class HTTPSecurity:
    def __init__(self, app, public_origin=None, production=False, max_body=65536):
        self.app, self.production, self.max_body = app, production, max_body
        self.public_origin = origin(public_origin) if public_origin else None

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = Headers(scope=scope)

        async def secured(message):
            if message['type'] == 'http.response.start':
                out = MutableHeaders(scope=message)
                script = "'self'" if scope['path'] not in {'/docs', '/redoc'} else "'self' 'unsafe-inline' https://cdn.jsdelivr.net"
                out['Content-Security-Policy'] = (
                    "default-src 'none'; script-src " + script + "; style-src 'self' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
                    "font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; "
                    "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
                out['X-Content-Type-Options'] = 'nosniff'
                out['X-Frame-Options'] = 'DENY'
                out['Referrer-Policy'] = 'no-referrer'
                out['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
                out['Cross-Origin-Resource-Policy'] = 'same-origin'
                if scope['path'].startswith('/api') or 'text/html' in out.get('content-type', ''):
                    out['Cache-Control'] = 'no-store'
                if self.production:
                    out['Strict-Transport-Security'] = 'max-age=31536000'
            await send(message)

        async def reject(code, detail):
            await JSONResponse({'detail': detail}, status_code=code)(scope, receive, secured)

        if scope['method'] not in {'GET', 'HEAD', 'OPTIONS'}:
            supplied = headers.get('origin')
            expected = self.public_origin or origin(scope['scheme'] + '://' + headers.get('host', ''))
            if headers.get('sec-fetch-site') == 'cross-site' or (supplied is not None and (origin(supplied) is None or origin(supplied) != expected)):
                return await reject(403, 'ไม่อนุญาตคำขอจากเว็บไซต์อื่น')
        try:
            length = int(headers.get('content-length', '0'))
        except ValueError:
            return await reject(400, 'ขนาดคำขอไม่ถูกต้อง')
        if length < 0 or length > self.max_body:
            return await reject(413, 'ข้อมูลคำขอมีขนาดใหญ่เกินไป')
        body = bytearray()
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            body.extend(message.get('body', b''))
            if len(body) > self.max_body:
                return await reject(413, 'ข้อมูลคำขอมีขนาดใหญ่เกินไป')
            if not message.get('more_body', False):
                break
        replayed = False

        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
            return await receive()
        await self.app(scope, replay, secured)


def install_http_security(app):
    production = os.getenv('APP_ENV', 'development') == 'production'
    public = os.getenv('PUBLIC_ORIGIN', '')
    if production:
        from app.core.config import COOKIE_SECURE
        if not COOKIE_SECURE or not origin(public) or origin(public)[0] != 'https':
            raise RuntimeError('Production requires secure cookies and an HTTPS PUBLIC_ORIGIN')
        from starlette.middleware.trustedhost import TrustedHostMiddleware
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=[origin(public)[1]])
    app.add_middleware(HTTPSecurity, public_origin=public, production=production)
