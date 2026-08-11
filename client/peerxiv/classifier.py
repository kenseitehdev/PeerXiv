"""Versioned Calculus of Uncertainty classification boundary.

PeerXiv does not provide a substitute CoU implementation here. The classifier
retains the complete uncertainty-relevant input structure and delegates to a
registered, versioned CoU backend when one is installed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Mapping, Protocol
from uuid import uuid4

from .extensions import db


class CoUClassifierUnavailable(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CoUSnapshot:
    subject_type: str
    subject_id: str
    subject_version: str
    state: Mapping[str, Any]
    evidence: tuple[Mapping[str, Any], ...] = ()
    history: tuple[Mapping[str, Any], ...] = ()
    validation: tuple[Mapping[str, Any], ...] = ()
    movement: tuple[Mapping[str, Any], ...] = ()
    dependency: tuple[Mapping[str, Any], ...] = ()
    context: Mapping[str, Any] = field(default_factory=dict)
    observed_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject_type": self.subject_type,
            "subject_id": self.subject_id,
            "subject_version": self.subject_version,
            "state": dict(self.state),
            "evidence": list(self.evidence),
            "history": list(self.history),
            "validation": list(self.validation),
            "movement": list(self.movement),
            "dependency": list(self.dependency),
            "context": dict(self.context),
            "observed_at": self.observed_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class CoUClassification:
    run_id: str
    classifier_version: str
    subject_type: str
    subject_id: str
    subject_version: str
    label: str
    components: Mapping[str, Any]
    trace: tuple[Mapping[str, Any], ...]
    classified_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "classifier_version": self.classifier_version,
            "subject_type": self.subject_type,
            "subject_id": self.subject_id,
            "subject_version": self.subject_version,
            "label": self.label,
            "components": dict(self.components),
            "trace": list(self.trace),
            "classified_at": self.classified_at.isoformat(),
        }

    @classmethod
    def create(
        cls,
        *,
        classifier_version: str,
        snapshot: CoUSnapshot,
        label: str,
        components: Mapping[str, Any],
        trace: tuple[Mapping[str, Any], ...],
    ) -> "CoUClassification":
        return cls(
            run_id=str(uuid4()),
            classifier_version=classifier_version,
            subject_type=snapshot.subject_type,
            subject_id=snapshot.subject_id,
            subject_version=snapshot.subject_version,
            label=label,
            components=components,
            trace=trace,
            classified_at=datetime.now(UTC),
        )


class CoUBackend(Protocol):
    @property
    def version(self) -> str: ...

    def classify(self, snapshot: CoUSnapshot) -> CoUClassification: ...


class CoUClassifier:
    def __init__(self) -> None:
        self._backend: CoUBackend | None = None

    @property
    def configured(self) -> bool:
        return self._backend is not None

    @property
    def version(self) -> str | None:
        return self._backend.version if self._backend else None

    def register(self, backend: CoUBackend) -> None:
        if not backend.version.strip():
            raise ValueError("A CoU backend must expose a non-empty version")
        self._backend = backend

    def classify(self, snapshot: CoUSnapshot) -> CoUClassification:
        if self._backend is None:
            raise CoUClassifierUnavailable("No CoU classifier backend is registered")
        result = self._backend.classify(snapshot)
        if result.subject_id != snapshot.subject_id or result.subject_version != snapshot.subject_version:
            raise ValueError("CoU result subject does not match the requested snapshot")
        return result

    def status(self) -> dict[str, object]:
        return {"configured": self.configured, "version": self.version}


classifier = CoUClassifier()


class CoUClassificationRun(db.Model):
    """Append-oriented record of a requested or completed CoU classification."""

    __tablename__ = "cou_classification_runs"
    __table_args__ = (
        db.UniqueConstraint(
            "subject_type",
            "subject_id",
            "subject_version",
            "classifier_version",
            "input_hash",
            name="uq_cou_run_input",
        ),
    )

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid4()))
    subject_type = db.Column(db.String(80), nullable=False, index=True)
    subject_id = db.Column(db.String(80), nullable=False, index=True)
    subject_version = db.Column(db.String(80), nullable=False)
    classifier_version = db.Column(db.String(80), nullable=False)
    input_hash = db.Column(db.String(128), nullable=False)
    status = db.Column(db.String(24), nullable=False, default="queued", index=True)
    snapshot = db.Column(db.JSON, nullable=False)
    label = db.Column(db.String(120))
    components = db.Column(db.JSON)
    trace = db.Column(db.JSON)
    error = db.Column(db.Text)
    requested_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    completed_at = db.Column(db.DateTime(timezone=True))

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "subject_type": self.subject_type,
            "subject_id": self.subject_id,
            "subject_version": self.subject_version,
            "classifier_version": self.classifier_version,
            "input_hash": self.input_hash,
            "status": self.status,
            "label": self.label,
            "components": self.components,
            "trace": self.trace,
            "error": self.error,
            "requested_at": self.requested_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
