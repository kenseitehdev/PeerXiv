from __future__ import annotations


def register_urls(app) -> None:
    from accounts import blueprint as accounts_blueprint
    from discovery import blueprint as discovery_blueprint
    from journals import blueprint as journals_blueprint
    from papers import blueprint as papers_blueprint
    from social import blueprint as social_blueprint
    from spaces import blueprint as spaces_blueprint

    from .server_api import blueprint as server_blueprint

    app.register_blueprint(server_blueprint)
    app.register_blueprint(papers_blueprint, url_prefix="/api/v1/papers")
    app.register_blueprint(social_blueprint, url_prefix="/api/v1/social")
    app.register_blueprint(spaces_blueprint, url_prefix="/api/v1/spaces")
    app.register_blueprint(discovery_blueprint, url_prefix="/api/v1/discovery")
    app.register_blueprint(journals_blueprint, url_prefix="/api/v1/journals")
    app.register_blueprint(accounts_blueprint, url_prefix="/api/v1/accounts")
