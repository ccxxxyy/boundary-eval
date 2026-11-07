import pytest

from probe_support import solution

sol = solution()


def test_valid_signup_returns_plain_dict():
    out = sol.load_signup({"email": "a@example.com", "age": 20})
    assert type(out) is dict
    assert out == {"email": "a@example.com", "age": 20}


def test_nickname_passes_through():
    out = sol.load_signup({"email": "a@example.com", "age": 20, "nickname": "al"})
    assert out["nickname"] == "al"


def test_invalid_email_raises_with_field_errors():
    with pytest.raises(sol.SignupError) as info:
        sol.load_signup({"email": "nope", "age": 20})
    assert "email" in info.value.errors


def test_under_age_raises():
    with pytest.raises(sol.SignupError) as info:
        sol.load_signup({"email": "a@example.com", "age": 9})
    assert "age" in info.value.errors


def test_missing_required_raises():
    with pytest.raises(sol.SignupError) as info:
        sol.load_signup({"age": 20})
    assert "email" in info.value.errors
