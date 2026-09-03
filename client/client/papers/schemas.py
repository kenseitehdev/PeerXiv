from pydantic import BaseModel, ConfigDict, Field, field_validator

from peerxiv.validation import clean_multiline, clean_single_line, clean_string_list


class PaperCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=3, max_length=500)
    abstract: str = Field(min_length=10, max_length=50_000)
    authors: list[str] = Field(min_length=1, max_length=50)
    subject: str = Field(default="Pending CoU classification", min_length=2, max_length=120)
    subfield: str = Field(default="", max_length=120)
    tags: list[str] = Field(default_factory=list, max_length=24)
    license: str = Field(default="CC BY 4.0", max_length=64)
    open_review: bool = True

    @field_validator("authors")
    @classmethod
    def validate_authors(cls, authors: list[str]) -> list[str]:
        cleaned = clean_string_list(authors)
        if not cleaned:
            raise ValueError("At least one non-empty author is required")
        if any(len(author) > 300 for author in cleaned):
            raise ValueError("Author names must be at most 300 characters")
        return cleaned

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, tags: list[str]) -> list[str]:
        cleaned = clean_string_list(tags, casefold=True)
        if any(len(tag) > 100 for tag in cleaned):
            raise ValueError("Tags must be at most 100 characters")
        return cleaned

    @field_validator("title", "subject", "subfield", "license", mode="before")
    @classmethod
    def normalize_labels(cls, value):
        return clean_single_line(value)

    @field_validator("abstract", mode="before")
    @classmethod
    def normalize_abstract(cls, value):
        return clean_multiline(value)


class PaperPublish(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    authors: list[str] = Field(min_length=1, max_length=50)
    tags: list[str] = Field(default_factory=list, max_length=32)
    manuscript_uri: str | None = Field(default=None, max_length=2048)
    manuscript_checksum: str | None = Field(default=None, max_length=128)
    change_summary: str = Field(default="Initial submission", max_length=2000)

    @field_validator("authors", mode="before")
    @classmethod
    def normalize_authors(cls, value):
        return clean_string_list(value)

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, value):
        return clean_string_list(value, casefold=True)

    @field_validator("change_summary", mode="before")
    @classmethod
    def normalize_change_summary(cls, value):
        return clean_multiline(value)
