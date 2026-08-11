from flask import Blueprint

blueprint = Blueprint("spaces", __name__)

from . import views as _views  # noqa: E402,F401
