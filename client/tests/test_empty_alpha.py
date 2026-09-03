from sqlalchemy import func, select

from accounts.models import Account, Activity, Notification, UserFollow, UserInterest
from discovery.models import DiscoveryProjection
from journals.models import Journal, PublicationLink
from papers.models import Paper, PaperMetadataRecord, PaperMetadataTag, PaperVersion
from peerxiv.extensions import db
from social.models import (
    Comment,
    Conversation,
    ConversationParticipant,
    Discussion,
    DiscussionFollow,
    DiscussionSave,
    DiscussionVote,
    Message,
)
from spaces.models import ResearchSpace, SpaceMember, SpacePaper, SpaceResource


def test_new_alpha_database_and_public_feeds_are_empty(app, anonymous_client):
    models = (
        Account,
        Activity,
        Notification,
        UserFollow,
        UserInterest,
        Paper,
        PaperVersion,
        PaperMetadataRecord,
        PaperMetadataTag,
        DiscoveryProjection,
        Journal,
        PublicationLink,
        Discussion,
        Comment,
        DiscussionFollow,
        DiscussionSave,
        DiscussionVote,
        Conversation,
        ConversationParticipant,
        Message,
        ResearchSpace,
        SpaceMember,
        SpacePaper,
        SpaceResource,
    )

    with app.app_context():
        for model in models:
            assert db.session.scalar(select(func.count()).select_from(model)) == 0

    assert anonymous_client.get("/api/v1/papers").get_json()["results"] == []
    assert anonymous_client.get("/api/v1/social/discussions").get_json()["results"] == []
    assert anonymous_client.get("/api/v1/spaces").get_json()["results"] == []
    assert "demo_data" not in anonymous_client.get("/api/v1/bootstrap").get_json()
