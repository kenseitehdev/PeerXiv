from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from peerxiv.validation import clean_multiline, clean_single_line


class DiscussionCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    title: str = Field(min_length=5, max_length=500)
    body: str = Field(min_length=20, max_length=20000)
    topic: str = Field(default="Research Practice", min_length=2, max_length=120)
    paper_identifier: str | None = Field(default=None, max_length=32)

    @field_validator("title", "topic", "paper_identifier", mode="before")
    @classmethod
    def normalize_labels(cls, value):
        return clean_single_line(value) if value is not None else None

    @field_validator("body", mode="before")
    @classmethod
    def normalize_body(cls, value):
        return clean_multiline(value)


class CommentCreate(BaseModel):
    body: str = Field(min_length=10, max_length=10000)
    parent_id: str | None = Field(default=None, max_length=36)

    @field_validator("body", mode="before")
    @classmethod
    def normalize_body(cls, value):
        return clean_multiline(value)


class ConversationCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    recipient_email: EmailStr
    body: str = Field(min_length=1, max_length=10_000)
    title: str | None = Field(default=None, max_length=240)

    @field_validator("recipient_email")
    @classmethod
    def normalize_email(cls, value):
        return str(value).strip().casefold()

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, value):
        return clean_single_line(value) if value else None

    @field_validator("body", mode="before")
    @classmethod
    def normalize_body(cls, value):
        return clean_multiline(value)


class MessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=10_000)

    @field_validator("body", mode="before")
    @classmethod
    def normalize_body(cls, value):
        return clean_multiline(value)


class ToggleInput(BaseModel):
    enabled: bool | None = None


class VoteInput(BaseModel):
    value: int = Field(ge=-1, le=1)
