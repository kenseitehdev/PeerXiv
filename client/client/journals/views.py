from flask import jsonify
from sqlalchemy import select

from peerxiv.extensions import db

from . import blueprint
from .models import Journal


@blueprint.get("")
def index():
    journals = db.session.scalars(select(Journal).order_by(Journal.name))
    return jsonify(
        {
            "results": [
                {
                    "id": journal.id,
                    "name": journal.name,
                    "issn": journal.issn,
                    "homepage_url": journal.homepage_url,
                    "open_access": journal.open_access,
                }
                for journal in journals
            ]
        }
    )
