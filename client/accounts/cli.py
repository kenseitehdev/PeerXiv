from __future__ import annotations

from datetime import timedelta

import click
from email_validator import EmailNotValidError, validate_email
from flask.cli import AppGroup
from sqlalchemy import select

from peerxiv.extensions import db
from peerxiv.validation import clean_single_line

from .invitations import create_invitation
from .models import RegistrationInvite, utc_now


invites = AppGroup("invites", help="Create and manage registration invitations.")


def _normalized_email(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return validate_email(value, check_deliverability=False).normalized.casefold()
    except EmailNotValidError as error:
        raise click.ClickException(str(error)) from error


@invites.command("create")
@click.option("--email", help="Restrict the invitation to one email address.")
@click.option("--label", help="Private operator label for this invitation.")
@click.option(
    "--uses",
    "max_uses",
    type=click.IntRange(min=1, max=100),
    default=1,
    show_default=True,
)
@click.option(
    "--days",
    type=click.IntRange(min=0, max=365),
    default=14,
    show_default=True,
    help="Days until expiration; zero disables expiration.",
)
def create_command(email: str | None, label: str | None, max_uses: int, days: int) -> None:
    normalized_email = _normalized_email(email)
    normalized_label = clean_single_line(label or normalized_email or "Alpha invitation")
    if len(normalized_label) > 160:
        raise click.ClickException("Invitation label must contain at most 160 characters")
    expires_at = utc_now() + timedelta(days=days) if days else None
    invitation, code = create_invitation(
        label=normalized_label,
        email=normalized_email,
        max_uses=max_uses,
        expires_at=expires_at,
    )
    click.echo(f"Invite code (shown once): {code}")
    click.echo(f"Invite id: {invitation.id}")
    click.echo(f"Email: {invitation.email or 'any invited researcher'}")
    click.echo(f"Uses: {invitation.max_uses}")
    click.echo(f"Expires: {invitation.expires_at.isoformat() if invitation.expires_at else 'never'}")


@invites.command("list")
@click.option("--all", "include_inactive", is_flag=True, help="Include used, expired, and revoked invites.")
def list_command(include_inactive: bool) -> None:
    invitations = db.session.scalars(
        select(RegistrationInvite).order_by(RegistrationInvite.created_at.desc()).limit(200)
    ).all()
    if not include_inactive:
        invitations = [item for item in invitations if item.status() == "active"]
    if not invitations:
        click.echo("No matching invitations.")
        return
    click.echo("ID\tSTATUS\tUSES\tEXPIRES\tEMAIL\tLABEL")
    for invitation in invitations:
        click.echo(
            "\t".join(
                (
                    invitation.id,
                    invitation.status(),
                    f"{invitation.use_count}/{invitation.max_uses}",
                    invitation.expires_at.isoformat() if invitation.expires_at else "never",
                    invitation.email or "any",
                    invitation.label,
                )
            )
        )


@invites.command("revoke")
@click.argument("invitation_id")
def revoke_command(invitation_id: str) -> None:
    invitation = db.session.get(RegistrationInvite, invitation_id)
    if invitation is None:
        raise click.ClickException("Invitation not found")
    if invitation.revoked_at is None:
        invitation.revoked_at = utc_now()
        db.session.commit()
    click.echo(f"Revoked invitation {invitation.id}.")
