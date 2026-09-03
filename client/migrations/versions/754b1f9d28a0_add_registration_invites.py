"""add registration invitations

Revision ID: 754b1f9d28a0
Revises: 32cbf120a88f
Create Date: 2026-08-12 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "754b1f9d28a0"
down_revision = "32cbf120a88f"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "registration_invites",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("code_digest", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=160), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("max_uses", sa.Integer(), nullable=False),
        sa.Column("use_count", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("max_uses > 0", name="ck_registration_invite_max_uses"),
        sa.CheckConstraint("use_count >= 0", name="ck_registration_invite_use_count"),
        sa.CheckConstraint(
            "use_count <= max_uses", name="ck_registration_invite_use_limit"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("registration_invites", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_registration_invites_code_digest"),
            ["code_digest"],
            unique=True,
        )
        batch_op.create_index(
            batch_op.f("ix_registration_invites_created_at"),
            ["created_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_registration_invites_email"), ["email"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_registration_invites_expires_at"),
            ["expires_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_registration_invites_revoked_at"),
            ["revoked_at"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table("registration_invites", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_registration_invites_revoked_at"))
        batch_op.drop_index(batch_op.f("ix_registration_invites_expires_at"))
        batch_op.drop_index(batch_op.f("ix_registration_invites_email"))
        batch_op.drop_index(batch_op.f("ix_registration_invites_created_at"))
        batch_op.drop_index(batch_op.f("ix_registration_invites_code_digest"))
    op.drop_table("registration_invites")
