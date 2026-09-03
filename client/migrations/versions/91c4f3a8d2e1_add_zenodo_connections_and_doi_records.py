"""add Zenodo connections and version-scoped DOI records

Revision ID: 91c4f3a8d2e1
Revises: b7a8f2d91c40
Create Date: 2026-08-12 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "91c4f3a8d2e1"
down_revision = "b7a8f2d91c40"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "zenodo_connections",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("environment", sa.String(length=24), nullable=False),
        sa.Column("encrypted_token", sa.Text(), nullable=False),
        sa.Column("token_hint", sa.String(length=16), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "environment", name="uq_zenodo_connection"),
    )
    with op.batch_alter_table("zenodo_connections", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_zenodo_connections_account_id"), ["account_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_zenodo_connections_environment"), ["environment"], unique=False
        )

    op.create_table(
        "paper_doi_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("paper_version_id", sa.String(length=36), nullable=False),
        sa.Column("created_by_id", sa.String(length=36), nullable=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("environment", sa.String(length=24), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("doi", sa.String(length=255), nullable=True),
        sa.Column("doi_url", sa.Text(), nullable=True),
        sa.Column("concept_doi", sa.String(length=255), nullable=True),
        sa.Column("provider_record_id", sa.String(length=120), nullable=True),
        sa.Column("provider_record_url", sa.Text(), nullable=True),
        sa.Column("landing_url", sa.Text(), nullable=False),
        sa.Column("metadata_hash", sa.String(length=128), nullable=False),
        sa.Column("metadata_payload", sa.JSON(), nullable=False),
        sa.Column("manuscript_checksum", sa.String(length=128), nullable=False),
        sa.Column("provider_payload", sa.JSON(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["paper_version_id"], ["paper_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("doi", name="uq_paper_doi"),
        sa.UniqueConstraint("paper_version_id", name="uq_paper_version_doi"),
    )
    with op.batch_alter_table("paper_doi_records", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_paper_doi_records_concept_doi"), ["concept_doi"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_paper_doi_records_created_by_id"), ["created_by_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_paper_doi_records_doi"), ["doi"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_paper_doi_records_environment"), ["environment"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_paper_doi_records_paper_version_id"),
            ["paper_version_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_paper_doi_records_provider"), ["provider"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_paper_doi_records_provider_record_id"),
            ["provider_record_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_paper_doi_records_published_at"), ["published_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_paper_doi_records_reserved_at"), ["reserved_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_paper_doi_records_state"), ["state"], unique=False
        )


def downgrade():
    with op.batch_alter_table("paper_doi_records", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_paper_doi_records_state"))
        batch_op.drop_index(batch_op.f("ix_paper_doi_records_reserved_at"))
        batch_op.drop_index(batch_op.f("ix_paper_doi_records_published_at"))
        batch_op.drop_index(batch_op.f("ix_paper_doi_records_provider_record_id"))
        batch_op.drop_index(batch_op.f("ix_paper_doi_records_provider"))
        batch_op.drop_index(batch_op.f("ix_paper_doi_records_paper_version_id"))
        batch_op.drop_index(batch_op.f("ix_paper_doi_records_environment"))
        batch_op.drop_index(batch_op.f("ix_paper_doi_records_doi"))
        batch_op.drop_index(batch_op.f("ix_paper_doi_records_created_by_id"))
        batch_op.drop_index(batch_op.f("ix_paper_doi_records_concept_doi"))
    op.drop_table("paper_doi_records")

    with op.batch_alter_table("zenodo_connections", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_zenodo_connections_environment"))
        batch_op.drop_index(batch_op.f("ix_zenodo_connections_account_id"))
    op.drop_table("zenodo_connections")
