import math

import pytest
from pydantic import ValidationError

from papers.schemas import PaperCreate
from peerxiv.validation import clean_json


def test_research_text_is_unicode_normalized_cleaned_and_deduplicated():
    payload = PaperCreate.model_validate(
        {
            "title": "  A\tClean\u202e  Research   Title ",
            "abstract": " First\tparagraph.\r\n\r\n\r\n Second paragraph. ",
            "authors": [" Maya\tChen ", "maya chen", "Noor Al-Sayed"],
            "tags": [" Validation ", "validation", "Predictive\u200b Skill"],
        }
    )
    assert payload.title == "A Clean Research Title"
    assert payload.abstract == "First paragraph.\n\nSecond paragraph."
    assert payload.authors == ["Maya Chen", "Noor Al-Sayed"]
    assert payload.tags == ["validation", "predictive skill"]


def test_metadata_rejects_nonfinite_deep_or_colliding_values():
    with pytest.raises(ValueError, match="finite"):
        clean_json({"score": math.nan})
    with pytest.raises(ValueError, match="unique"):
        clean_json({"safe\u202e": "one", "safe": "two"})

    nested = {"level": {"level": {"level": {"level": {"level": {"level": {"level": 1}}}}}}}
    with pytest.raises(ValueError, match="six levels"):
        clean_json(nested)


def test_text_lists_reject_non_string_values():
    with pytest.raises(ValidationError):
        PaperCreate.model_validate(
            {
                "title": "Typed author validation",
                "abstract": "A long enough abstract for the input validation test.",
                "authors": ["Researcher", None],
            }
        )

