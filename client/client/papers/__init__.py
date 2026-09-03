from flask import Blueprint

blueprint = Blueprint("papers", __name__)

from . import views as _views  # noqa: E402,F401
