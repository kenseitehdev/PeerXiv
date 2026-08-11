from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, field_validator

from peerxiv.validation import clean_json, clean_multiline, clean_single_line, clean_string_list


SpaceKind = Literal["workspace", "presentation", "conference", "journal"]


class SpaceCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    kind: SpaceKind
    title: str = Field(min_length=2, max_length=300)
    description: str = Field(default="", max_length=5000)
    visibility: Literal["public", "private"] = "public"
    status: str = Field(default="active", max_length=40)
    details: dict = Field(default_factory=dict)
    paper_identifiers: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("title", "status", mode="before")
    @classmethod
    def normalize_labels(cls, value):
        return clean_single_line(value)

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, value):
        return clean_multiline(value)

    @field_validator("paper_identifiers", mode="before")
    @classmethod
    def normalize_papers(cls, value):
        return clean_string_list(value)

    @field_validator("details", mode="before")
    @classmethod
    def normalize_details(cls, value):
        return clean_json(value)


class SpaceUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    title: str | None = Field(default=None, min_length=2, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    visibility: Literal["public", "private"] | None = None
    status: str | None = Field(default=None, max_length=40)
    details: dict | None = None

    @field_validator("title", "status", mode="before")
    @classmethod
    def normalize_labels(cls, value):
        return clean_single_line(value) if value is not None else None

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, value):
        return clean_multiline(value) if value is not None else None

    @field_validator("details", mode="before")
    @classmethod
    def normalize_details(cls, value):
        return clean_json(value) if value is not None else None


class SpaceResourceCreate(BaseModel):
    resource_type: str = Field(min_length=2, max_length=60)
    title: str = Field(min_length=2, max_length=300)
    url: HttpUrl | None = None
    details: dict = Field(default_factory=dict)

    @field_validator("resource_type", "title", mode="before")
    @classmethod
    def normalize_labels(cls, value):
        return clean_single_line(value)

    @field_validator("details", mode="before")
    @classmethod
    def normalize_details(cls, value):
        return clean_json(value)


class SpaceMemberCreate(BaseModel):
    email: EmailStr
    role: Literal["editor", "collaborator", "viewer"] = "collaborator"

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        return str(value).strip().casefold()


class SpacePaperCreate(BaseModel):
    paper_identifier: str = Field(min_length=3, max_length=32)
    relationship: str = Field(default="linked", max_length=80)

    @field_validator("paper_identifier", "relationship", mode="before")
    @classmethod
    def normalize_labels(cls, value):
        return clean_single_line(value)
