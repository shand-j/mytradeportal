"""WSGI middleware that answers Railway healthchecks before Django boots.

Django validates ALLOWED_HOSTS for every request, including Railway's
internal healthcheck probes. The Host header on those probes is not
under our control, so this middleware intercepts the healthcheck path and
returns 200 without invoking Django.
"""

HEALTHCHECK_PATHS = {"/health", "/health/"}


class HealthCheckMiddleware:
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        if environ.get("PATH_INFO") in HEALTHCHECK_PATHS:
            status = "200 OK"
            headers = [("Content-Type", "text/plain; charset=utf-8")]
            start_response(status, headers)
            return [b"ok"]
        return self.app(environ, start_response)
