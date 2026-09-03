from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from sqlalchemy import or_, select

from peerxiv.extensions import db

from .models import Account, Activity, Notification, UserFollow, UserInterest, utc_now


def record_activity(
    actor_id: str,
    *,
    verb: str,
    object_type: str,
    object_id: str,
    summary: str,
    payload: dict[str, Any] | None = None,
) -> Activity:
    activity = Activity(
        actor_id=actor_id,
        verb=verb,
        object_type=object_type,
        object_id=object_id,
        summary=summary,
        payload=payload or {},
    )
    db.session.add(activity)
    return activity


def create_notification(
    user_id: str,
    *,
    kind: str,
    text: str,
    dedupe_key: str,
    actor_id: str | None = None,
    reason: str | None = None,
    object_type: str | None = None,
    object_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> Notification:
    existing = db.session.scalar(
        select(Notification).where(
            Notification.user_id == user_id,
            Notification.dedupe_key == dedupe_key,
        )
    )
    if existing is not None:
        return existing
    notification = Notification(
        user_id=user_id,
        actor_id=actor_id,
        kind=kind,
        text=text,
        reason=reason,
        object_type=object_type,
        object_id=object_id,
        payload=payload or {},
        dedupe_key=dedupe_key,
    )
    db.session.add(notification)
    return notification


def notify_followers(
    actor_id: str,
    *,
    kind: str,
    text: str,
    dedupe_suffix: str,
    object_type: str,
    object_id: str,
    payload: dict[str, Any] | None = None,
) -> int:
    follower_ids = db.session.scalars(
        select(UserFollow.follower_id).where(UserFollow.followed_id == actor_id)
    ).all()
    for follower_id in follower_ids:
        create_notification(
            follower_id,
            actor_id=actor_id,
            kind=kind,
            text=text,
            object_type=object_type,
            object_id=object_id,
            payload=payload,
            dedupe_key=f"follow:{actor_id}:{dedupe_suffix}",
        )
    return len(follower_ids)


def record_interests(user_id: str, tags: Iterable[Any], *, source_kind: str) -> int:
    updated = 0
    for raw in tags:
        if isinstance(raw, dict):
            get = raw.get
        else:
            get = lambda key, default=None: getattr(raw, key, default)
        facet = str(get("facet", "")).casefold()
        namespace = str(get("namespace", "")).casefold()
        slug = str(get("slug", "")).casefold()
        label = str(get("label", slug))
        if not facet or not namespace or not slug:
            continue
        weight = float(get("weight", 0.0) or 0.0)
        interest = db.session.scalar(
            select(UserInterest).where(
                UserInterest.user_id == user_id,
                UserInterest.facet == facet,
                UserInterest.namespace == namespace,
                UserInterest.slug == slug,
            )
        )
        if interest is None:
            interest = UserInterest(
                user_id=user_id,
                facet=facet,
                namespace=namespace,
                slug=slug,
                label=label,
                weight=weight,
                observations=1,
                source_kinds=[source_kind],
            )
            db.session.add(interest)
        else:
            interest.label = label
            interest.weight = max(float(interest.weight), weight)
            interest.observations += 1
            interest.source_kinds = sorted(set([*interest.source_kinds, source_kind]))
        updated += 1
    return updated


def notify_relevant_users(
    *,
    actor_id: str,
    paper_identifier: str,
    paper_title: str,
    tags: Iterable[Any],
) -> int:
    exact = set()
    for raw in tags:
        get = raw.get if isinstance(raw, dict) else lambda key, default=None: getattr(raw, key, default)
        facet = str(get("facet", "")).casefold()
        if facet not in {"concept", "method"}:
            continue
        exact.add((facet, str(get("namespace", "")).casefold(), str(get("slug", "")).casefold(), str(get("label", ""))))
    if not exact:
        return 0
    conditions = [
        (UserInterest.facet == facet)
        & (UserInterest.namespace == namespace)
        & (UserInterest.slug == slug)
        for facet, namespace, slug, _label in exact
    ]
    interests = db.session.scalars(
        select(UserInterest).where(UserInterest.user_id != actor_id, or_(*conditions))
    ).all()
    matches: dict[str, list[str]] = defaultdict(list)
    for interest in interests:
        matches[interest.user_id].append(interest.label)
    for user_id, labels in matches.items():
        labels = sorted(set(labels))
        create_notification(
            user_id,
            actor_id=actor_id,
            kind="relevant-paper",
            text=f"Research matching your exact subtopics: {paper_title}",
            reason=f"Exact overlap: {', '.join(labels[:4])}",
            object_type="paper",
            object_id=paper_identifier,
            payload={"paper": paper_identifier, "matched_labels": labels},
            dedupe_key=f"relevant-paper:{paper_identifier}",
        )
    return len(matches)


def persist_match_notifications(user_id: str, matches: Iterable[dict[str, Any]]) -> int:
    count = 0
    for match in matches:
        paper_identifier = str(match.get("paper", ""))
        source_id = str(match.get("source", {}).get("id", "activity"))
        if not paper_identifier:
            continue
        create_notification(
            user_id,
            kind=str(match.get("kind", "relevant-research")),
            text=str(match.get("text", "Related research found")),
            reason=str(match.get("reason", "")) or None,
            object_type="paper",
            object_id=paper_identifier,
            payload=match,
            dedupe_key=f"match:{source_id}:{paper_identifier}",
        )
        count += 1
    return count


def recommended_people(user_id: str, *, limit: int = 12) -> list[dict[str, Any]]:
    followed_ids = set(
        db.session.scalars(
            select(UserFollow.followed_id).where(UserFollow.follower_id == user_id)
        ).all()
    )
    own = {
        (interest.facet, interest.namespace, interest.slug): interest
        for interest in db.session.scalars(
            select(UserInterest).where(UserInterest.user_id == user_id)
        ).all()
    }
    candidates = db.session.scalars(
        select(Account).where(Account.id != user_id, Account.active.is_(True))
    ).all()
    candidate_ids = [candidate.id for candidate in candidates]
    candidate_interests: dict[str, list[UserInterest]] = defaultdict(list)
    if candidate_ids:
        for interest in db.session.scalars(
            select(UserInterest).where(UserInterest.user_id.in_(candidate_ids))
        ).all():
            candidate_interests[interest.user_id].append(interest)
    results = []
    for candidate in candidates:
        shared = []
        score = 0.0
        for interest in candidate_interests[candidate.id]:
            source = own.get((interest.facet, interest.namespace, interest.slug))
            if source is None:
                continue
            shared.append(interest.label)
            score += min(float(source.weight), float(interest.weight))
        results.append(
            {
                **candidate.to_dict(),
                "following": candidate.id in followed_ids,
                "shared_interests": sorted(set(shared))[:6],
                "score": round(score, 6),
                "reason": (
                    f"Shared research: {', '.join(sorted(set(shared))[:3])}"
                    if shared
                    else "New researcher on PeerXiv"
                ),
            }
        )
    results.sort(key=lambda item: (-item["score"], item["display_name"]))
    return results[:limit]


def activity_feed(user_id: str, *, limit: int = 50) -> list[Activity]:
    followed = db.session.scalars(
        select(UserFollow.followed_id).where(UserFollow.follower_id == user_id)
    ).all()
    actor_ids = [user_id, *followed]
    return list(
        db.session.scalars(
            select(Activity)
            .where(Activity.actor_id.in_(actor_ids))
            .order_by(Activity.created_at.desc())
            .limit(limit)
        )
    )
