"""SQLAlchemy model registry used by Flask-Migrate."""

from accounts.models import Account, Activity, Notification, UserFollow, UserInterest
from discovery.models import DiscoveryProjection
from journals.models import Journal, PublicationLink
from papers.models import Paper, PaperMetadataRecord, PaperMetadataTag, PaperVersion
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
from .classifier import CoUClassificationRun

__all__ = [
    "Account",
    "Activity",
    "Comment",
    "CoUClassificationRun",
    "Conversation",
    "ConversationParticipant",
    "DiscoveryProjection",
    "Discussion",
    "DiscussionFollow",
    "DiscussionSave",
    "DiscussionVote",
    "Journal",
    "Message",
    "Notification",
    "Paper",
    "PaperMetadataRecord",
    "PaperMetadataTag",
    "PaperVersion",
    "PublicationLink",
    "ResearchSpace",
    "SpaceMember",
    "SpacePaper",
    "SpaceResource",
    "UserFollow",
    "UserInterest",
]
