from hypothesis import given, strategies as st

from security_lab.normalization import decode_base64_once, normalize_text


@given(st.text(max_size=2000))
def test_normalization_is_idempotent(value: str) -> None:
    first = str(normalize_text(value)["normalized"])
    second = str(normalize_text(first)["normalized"])
    assert second == first


def test_zero_width_characters_are_removed_and_reported() -> None:
    result = normalize_text("ignore\u200b previous")
    assert result["normalized"] == "ignore previous"
    assert "U+200B" in result["removed_codepoints"]


def test_base64_decode_is_single_layer() -> None:
    assert decode_base64_once("aWdub3JlIHByZXZpb3Vz") == "ignore previous"
    assert decode_base64_once("not base64") is None
