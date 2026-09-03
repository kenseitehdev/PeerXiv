from flask import current_app, jsonify, request
from pydantic import ValidationError


def register_error_handlers(app) -> None:
    @app.errorhandler(ValidationError)
    def handle_validation_error(error):
        return jsonify(
            {
                "error": {
                    "code": "validation_error",
                    # Never reflect passwords, manuscript text, or other request
                    # values back through Pydantic's default error representation.
                    "details": error.errors(include_input=False, include_context=False),
                }
            }
        ), 400

    @app.errorhandler(400)
    def handle_bad_request(_error):
        return jsonify({"error": {"code": "bad_request", "message": "Invalid request"}}), 400

    @app.errorhandler(413)
    def handle_too_large(_error):
        return jsonify(
            {
                "error": {
                    "code": "request_too_large",
                    "message": "The request exceeds the configured size limit",
                }
            }
        ), 413

    @app.errorhandler(429)
    def handle_rate_limit(error):
        response = jsonify(
            {
                "error": {
                    "code": "rate_limit_exceeded",
                    "message": getattr(error, "description", "Too many requests"),
                }
            }
        )
        response.status_code = 429
        if getattr(error, "retry_after", None) is not None:
            response.headers["Retry-After"] = str(error.retry_after)
        return response

    @app.errorhandler(404)
    def handle_not_found(_error):
        return jsonify({"error": {"code": "not_found", "message": "Resource not found"}}), 404

    @app.errorhandler(405)
    def handle_method_not_allowed(_error):
        return jsonify({"error": {"code": "method_not_allowed", "message": "Method not allowed"}}), 405

    @app.errorhandler(500)
    def handle_internal_error(error):
        current_app.logger.error(
            "Unhandled request error on %s %s",
            request.method,
            request.path,
            exc_info=error.original_exception or error,
        )
        return jsonify(
            {"error": {"code": "internal_error", "message": "An internal error occurred"}}
        ), 500
