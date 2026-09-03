"""PeerXiv Flask application factory."""

from pathlib import Path

from flask import Flask, request
from werkzeug.middleware.proxy_fix import ProxyFix

from .extensions import initialize_extensions
from .settings import resolve_config, validate_config


def _configure_request_boundaries(app: Flask) -> None:
    if app.config["PROXY_FIX_ENABLED"]:
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=app.config["PROXY_FIX_X_FOR"],
            x_proto=app.config["PROXY_FIX_X_PROTO"],
            x_host=app.config["PROXY_FIX_X_HOST"],
            x_port=app.config["PROXY_FIX_X_PORT"],
            x_prefix=app.config["PROXY_FIX_X_PREFIX"],
        )

    @app.before_request
    def constrain_json_requests() -> None:
        if request.is_json:
            request.max_content_length = app.config["MAX_JSON_CONTENT_LENGTH"]

    @app.after_request
    def secure_response(response):
        if not app.config["SECURITY_HEADERS_ENABLED"]:
            return response
        response.headers.setdefault("Content-Security-Policy", app.config["CONTENT_SECURITY_POLICY"])
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
        )
        if app.config["HSTS_ENABLED"] and request.is_secure:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        if request.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response


def create_app(config_name: str | None = None, config_overrides: dict | None = None) -> Flask:
    template_root = Path(__file__).resolve().parents[1] / "templates"
    app = Flask(
        __name__,
        static_folder=str(template_root),
        static_url_path="/templates",
        template_folder=str(template_root),
    )
    app.config.from_object(resolve_config(config_name))
    if config_overrides:
        app.config.update(config_overrides)
    validate_config(app.config)
    _configure_request_boundaries(app)

    initialize_extensions(app)

    # Importing the model registry makes all SQLAlchemy metadata visible to
    # Flask-Migrate before Alembic compares the database and model schemas.
    from . import models as _models  # noqa: F401
    from discovery.cou_classifier import CoUPaperClassifierBackend
    from .classifier import classifier
    from .errors import register_error_handlers
    from .realtime import register_socket_handlers
    from .urls import register_urls

    classifier.register(CoUPaperClassifierBackend())
    register_urls(app)
    register_error_handlers(app)
    register_socket_handlers()
    return app
