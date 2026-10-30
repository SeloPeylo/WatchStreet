"""Pure argument parsers for agent tools: clean values in, model-readable errors out."""

import pytest

from watchstreet.agents.tools import ToolError
from watchstreet.domain import ThesisStatus
from watchstreet.workflows.tool_args import (
    choice_arg,
    enum_arg,
    int_arg,
    number_arg,
    text_arg,
    to_json,
)
from watchstreet.workflows.tool_schemas import object_schema, string_enum


def test_text_arg_strips_and_requires() -> None:
    assert text_arg({"a": "  hi "}, "a") == "hi"
    with pytest.raises(ToolError, match="'a' is required"):
        text_arg({"a": "  "}, "a")


def test_number_arg_accepts_blank_and_rejects_text() -> None:
    assert number_arg({}, "n") is None
    assert number_arg({"n": ""}, "n") is None
    assert number_arg({"n": "2.5"}, "n") == 2.5
    with pytest.raises(ToolError, match="'n' must be a number"):
        number_arg({"n": "abc"}, "n")


def test_int_arg_uses_default_when_missing() -> None:
    assert int_arg({}, "n", 7) == 7
    assert int_arg({"n": 3}, "n", 7) == 3


def test_enum_and_choice_list_allowed_values() -> None:
    assert enum_arg({"s": "active"}, "s", ThesisStatus) is ThesisStatus.ACTIVE
    with pytest.raises(ToolError, match="active, confirmed"):
        enum_arg({"s": "nope"}, "s", ThesisStatus)
    assert choice_arg({"k": "b"}, "k", ["a", "b"]) == "b"
    with pytest.raises(ToolError, match="'k' must be one of: a, b"):
        choice_arg({"k": "c"}, "k", ["a", "b"])


def test_to_json_is_compact() -> None:
    assert to_json({"a": [1, 2], "ü": "x"}) == '{"a":[1,2],"ü":"x"}'


def test_schema_helpers() -> None:
    assert object_schema({"x": {"type": "string"}}) == {
        "type": "object",
        "properties": {"x": {"type": "string"}},
    }
    assert object_schema({}, ["x"])["required"] == ["x"]
    assert string_enum(("a", "b")) == {"type": "string", "enum": ["a", "b"]}
