from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from peerxiv.validation import clean_multiline, clean_single_line


class RegisterInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: EmailStr
    password: str = Field(min_length=12, max_length=256)
    display_name: str = Field(min_length=2, max_length=160)
    role: str = Field(default="Researcher", max_length=160)
    bio: str = Field(default="", max_length=2000)
    invite_code: str | None = Field(default=None, max_length=256)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        return str(value).strip().casefold()

    @field_validator("display_name", "role", mode="before")
    @classmethod
    def normalize_labels(cls, value):
        return clean_single_line(value)

    @field_validator("bio", mode="before")
    @classmethod
    def normalize_bio(cls, value):
        return clean_multiline(value)


class LoginInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        return str(value).strip().casefold()


class ProfileInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    display_name: str = Field(min_length=2, max_length=160)
    role: str = Field(min_length=2, max_length=160)
    bio: str = Field(default="", max_length=2000)

    @field_validator("display_name", "role", mode="before")
    @classmethod
    def normalize_labels(cls, value):
        return clean_single_line(value)

    @field_validator("bio", mode="before")
    @classmethod
    def normalize_bio(cls, value):
        return clean_multiline(value)
