from flask import g, jsonify, request
from sqlalchemy import or_, select

from accounts.auth import current_account, require_auth
from accounts.models import Account
from accounts.services import create_notification, notify_followers, record_activity
from papers.models import Paper
from peerxiv.extensions import db

from . import blueprint
from .models import ResearchSpace, SpaceMember, SpacePaper, SpaceResource
from .schemas import SpaceCreate, SpaceMemberCreate, SpacePaperCreate, SpaceResourceCreate, SpaceUpdate


def _space_or_404(space_id: str):
    space = db.session.get(ResearchSpace, space_id)
    if space is None:
        return None, (jsonify({"error": {"code": "space_not_found"}}), 404)
    account = current_account()
    if space.visibility == "private" and (
        account is None
        or not (
            account.id == space.owner_id
            or any(member.user_id == account.id for member in space.members)
        )
    ):
        return None, (jsonify({"error": {"code": "space_not_found"}}), 404)
    return space, None


def _can_edit(space: ResearchSpace, user_id: str) -> bool:
    return space.owner_id == user_id or any(
        member.user_id == user_id and member.role == "editor" for member in space.members
    )


@blueprint.get("")
def index():
    account = current_account()
    kind = request.args.get("kind")
    statement = select(ResearchSpace)
    if account is None:
        statement = statement.where(ResearchSpace.visibility == "public")
    else:
        member_space_ids = select(SpaceMember.space_id).where(SpaceMember.user_id == account.id)
        statement = statement.where(
            or_(
                ResearchSpace.visibility == "public",
                ResearchSpace.owner_id == account.id,
                ResearchSpace.id.in_(member_space_ids),
            )
        )
    if kind:
        statement = statement.where(ResearchSpace.kind == kind)
    spaces = db.session.scalars(statement.order_by(ResearchSpace.updated_at.desc())).unique()
    return jsonify({"results": [space.to_dict() for space in spaces]})


@blueprint.post("")
@require_auth
def create():
    payload = SpaceCreate.model_validate(request.get_json(silent=True) or {})
    account = g.current_account
    space = ResearchSpace(
        owner_id=account.id,
        kind=payload.kind,
        title=payload.title.strip(),
        description=payload.description.strip(),
        visibility=payload.visibility,
        status=payload.status,
        details=payload.details,
    )
    db.session.add(space)
    db.session.flush()
    db.session.add(SpaceMember(space=space, user_id=account.id, role="editor"))
    for identifier in dict.fromkeys(payload.paper_identifiers):
        paper = db.session.scalar(select(Paper).where(Paper.identifier == identifier))
        if paper is not None:
            db.session.add(SpacePaper(space=space, paper=paper))
    record_activity(
        account.id,
        verb="created",
        object_type="research-space",
        object_id=space.id,
        summary=f"{account.display_name} created {space.title}",
        payload={"kind": space.kind},
    )
    notify_followers(
        account.id,
        kind="new-research-space",
        text=f"{account.display_name} created {space.title}",
        dedupe_suffix=f"space:{space.id}",
        object_type="research-space",
        object_id=space.id,
        payload={"kind": space.kind},
    )
    db.session.commit()
    return jsonify(space.to_dict()), 201


@blueprint.get("/<space_id>")
def detail(space_id: str):
    space, error = _space_or_404(space_id)
    return error or jsonify(space.to_dict())


@blueprint.patch("/<space_id>")
@require_auth
def update(space_id: str):
    space, error = _space_or_404(space_id)
    if error:
        return error
    if not _can_edit(space, g.current_account.id):
        return jsonify({"error": {"code": "space_forbidden"}}), 403
    payload = SpaceUpdate.model_validate(request.get_json(silent=True) or {})
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(space, field, value.strip() if isinstance(value, str) else value)
    record_activity(
        g.current_account.id,
        verb="updated",
        object_type="research-space",
        object_id=space.id,
        summary=f"{g.current_account.display_name} updated {space.title}",
        payload={"kind": space.kind},
    )
    db.session.commit()
    return jsonify(space.to_dict())


@blueprint.post("/<space_id>/resources")
@require_auth
def add_resource(space_id: str):
    space, error = _space_or_404(space_id)
    if error:
        return error
    if not _can_edit(space, g.current_account.id):
        return jsonify({"error": {"code": "space_forbidden"}}), 403
    payload = SpaceResourceCreate.model_validate(request.get_json(silent=True) or {})
    resource = SpaceResource(
        space=space,
        resource_type=payload.resource_type,
        title=payload.title,
        url=str(payload.url) if payload.url else None,
        details=payload.details,
    )
    db.session.add(resource)
    db.session.flush()
    record_activity(
        g.current_account.id,
        verb="attached",
        object_type="space-resource",
        object_id=resource.id,
        summary=f"{g.current_account.display_name} attached {resource.title} to {space.title}",
        payload={"space_id": space.id, "resource_type": resource.resource_type},
    )
    db.session.commit()
    return jsonify(resource.to_dict()), 201


@blueprint.post("/<space_id>/papers")
@require_auth
def add_paper(space_id: str):
    space, error = _space_or_404(space_id)
    if error:
        return error
    if not _can_edit(space, g.current_account.id):
        return jsonify({"error": {"code": "space_forbidden"}}), 403
    payload = SpacePaperCreate.model_validate(request.get_json(silent=True) or {})
    paper = db.session.scalar(select(Paper).where(Paper.identifier == payload.paper_identifier))
    if paper is None:
        return jsonify({"error": {"code": "paper_not_found"}}), 404
    existing = db.session.scalar(
        select(SpacePaper).where(SpacePaper.space_id == space.id, SpacePaper.paper_id == paper.id)
    )
    if existing is None:
        existing = SpacePaper(space=space, paper=paper, relationship=payload.relationship)
        db.session.add(existing)
        record_activity(
            g.current_account.id,
            verb="linked",
            object_type="space-paper",
            object_id=paper.identifier,
            summary=f"{g.current_account.display_name} linked {paper.title} to {space.title}",
            payload={"space_id": space.id, "relationship": payload.relationship},
        )
        db.session.commit()
    return jsonify(existing.to_dict()), 201


@blueprint.post("/<space_id>/members")
@require_auth
def add_member(space_id: str):
    space, error = _space_or_404(space_id)
    if error:
        return error
    if space.owner_id != g.current_account.id:
        return jsonify({"error": {"code": "space_owner_required"}}), 403
    payload = SpaceMemberCreate.model_validate(request.get_json(silent=True) or {})
    account = db.session.scalar(select(Account).where(Account.email == payload.email.casefold()))
    if account is None:
        return jsonify({"error": {"code": "account_not_found"}}), 404
    member = db.session.scalar(
        select(SpaceMember).where(SpaceMember.space_id == space.id, SpaceMember.user_id == account.id)
    )
    if member is None:
        member = SpaceMember(space=space, user=account, role=payload.role)
        db.session.add(member)
    else:
        member.role = payload.role
    create_notification(
        account.id,
        actor_id=g.current_account.id,
        kind="research-space-member",
        text=f"{g.current_account.display_name} added you to {space.title}",
        object_type="research-space",
        object_id=space.id,
        payload={"role": payload.role, "kind": space.kind},
        dedupe_key=f"space-member:{space.id}:{account.id}",
    )
    record_activity(
        g.current_account.id,
        verb="added",
        object_type="space-member",
        object_id=account.id,
        summary=f"{g.current_account.display_name} added {account.display_name} to {space.title}",
        payload={"space_id": space.id, "role": payload.role},
    )
    db.session.commit()
    return jsonify(member.to_dict()), 201
