"""add ORCID identity and workspace roles

Revision ID: b7a8f2d91c40
Revises: 754b1f9d28a0
Create Date: 2026-08-12 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "b7a8f2d91c40"
down_revision = "754b1f9d28a0"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("accounts", schema=None) as batch_op:
        batch_op.add_column(sa.Column("orcid_id", sa.String(length=19), nullable=True))
        batch_op.add_column(sa.Column("orcid_name", sa.String(length=160), nullable=True))
        batch_op.add_column(sa.Column("orcid_linked_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index(batch_op.f("ix_accounts_orcid_id"), ["orcid_id"], unique=True)
        batch_op.create_index(
            batch_op.f("ix_accounts_orcid_linked_at"), ["orcid_linked_at"], unique=False
        )

    # A workspace owner was represented as an editor in 0.7.  Preserve the
    # membership row while making the authority explicit for the new policy.
    op.execute(
        sa.text(
            "UPDATE space_members SET role = 'owner' "
            "WHERE EXISTS ("
            "SELECT 1 FROM research_spaces "
            "WHERE research_spaces.id = space_members.space_id "
            "AND research_spaces.owner_id = space_members.user_id"
            ")"
        )
    )


def downgrade():
    op.execute(sa.text("UPDATE space_members SET role = 'editor' WHERE role = 'owner'"))
    with op.batch_alter_table("accounts", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_accounts_orcid_linked_at"))
        batch_op.drop_index(batch_op.f("ix_accounts_orcid_id"))
        batch_op.drop_column("orcid_linked_at")
        batch_op.drop_column("orcid_name")
        batch_op.drop_column("orcid_id")
