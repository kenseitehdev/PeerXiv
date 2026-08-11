from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from peerxiv.validation import clean_json, clean_multiline, clean_single_line, clean_string_list


class PaperSectionInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    heading: str = Field(default="Untitled section", max_length=300)
    text: str = Field(min_length=1, max_length=100_000)

    @field_validator("heading", mode="before")
    @classmethod
    def normalize_heading(cls, value):
        return clean_single_line(value)

    @field_validator("text", mode="before")
    @classmethod
    def normalize_text(cls, value):
        return clean_multiline(value)


class PaperClassificationInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=3, max_length=500)
    abstract: str = Field(min_length=10, max_length=50_000)
    authors: list[str] = Field(default_factory=list, max_length=50)
    keywords: list[str] = Field(default_factory=list, max_length=32)
    sections: list[PaperSectionInput] = Field(default_factory=list, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("authors", "keywords")
    @classmethod
    def normalize_strings(cls, values: list[str]) -> list[str]:
        return clean_string_list(values)

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, value):
        return clean_single_line(value)

    @field_validator("abstract", mode="before")
    @classmethod
    def normalize_abstract(cls, value):
        return clean_multiline(value)

    @field_validator("metadata", mode="before")
    @classmethod
    def normalize_metadata(cls, value):
        return clean_json(value)


class StoredPaperClassificationInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    keywords: list[str] = Field(default_factory=list, max_length=32)
    sections: list[PaperSectionInput] = Field(default_factory=list, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("keywords")
    @classmethod
    def normalize_keywords(cls, values: list[str]) -> list[str]:
        return clean_string_list(values)

    @field_validator("metadata", mode="before")
    @classmethod
    def normalize_metadata(cls, value):
        return clean_json(value)


class InterestTagInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    facet: str = Field(min_length=1, max_length=80)
    namespace: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=1, max_length=160)
    label: str = Field(min_length=1, max_length=240)
    weight: float = Field(ge=0.0, le=1.0)

    @field_validator("facet", "namespace", "slug", "label", mode="before")
    @classmethod
    def normalize_labels(cls, value):
        return clean_single_line(value)


class NotificationMatchInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    source_kind: Literal["research", "comment", "discussion"] = "research"
    source_id: str | None = Field(default=None, max_length=160)
    source_title: str = Field(default="Research activity", max_length=500)
    tags: list[InterestTagInput] = Field(min_length=1, max_length=128)
    exclude_identifiers: list[str] = Field(default_factory=list, max_length=128)
    exclude_authors: list[str] = Field(default_factory=list, max_length=32)
    limit: int = Field(default=12, ge=1, le=50)

    @field_validator("source_id", "source_title", mode="before")
    @classmethod
    def normalize_labels(cls, value):
        return clean_single_line(value) if value is not None else None

    @field_validator("exclude_identifiers", "exclude_authors", mode="before")
    @classmethod
    def normalize_exclusions(cls, value):
        return clean_string_list(value)


class NotificationClassificationInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    source_kind: Literal["research", "comment", "discussion"]
    source_id: str | None = Field(default=None, max_length=160)
    title: str = Field(min_length=3, max_length=500)
    text: str = Field(min_length=10, max_length=50_000)
    keywords: list[str] = Field(default_factory=list, max_length=32)
    exclude_identifiers: list[str] = Field(default_factory=list, max_length=128)
    exclude_authors: list[str] = Field(default_factory=list, max_length=32)
    limit: int = Field(default=12, ge=1, le=50)

    @field_validator("keywords", "exclude_identifiers", "exclude_authors")
    @classmethod
    def normalize_notification_strings(cls, values: list[str]) -> list[str]:
        return clean_string_list(values)

    @field_validator("source_id", "title", mode="before")
    @classmethod
    def normalize_labels(cls, value):
        return clean_single_line(value) if value is not None else None

    @field_validator("text", mode="before")
    @classmethod
    def normalize_text(cls, value):
        return clean_multiline(value)
