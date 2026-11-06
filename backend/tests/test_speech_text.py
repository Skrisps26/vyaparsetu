from app.speech_text import confirmation_text


def test_credit_confirmation_has_no_decimal_digits_or_currency_symbol() -> None:
    text = confirmation_text(14960, "credit", 24960)
    assert "ഡെമോ അക്കൗണ്ടിൽ ചേർത്തു" in text
    assert "₹" not in text
    assert not any(char.isdecimal() for char in text)


def test_cash_confirmation_omits_credit_balance() -> None:
    text = confirmation_text(10500, "cash")
    assert "ആകെ ബാക്കി" not in text
    assert not any(char.isdecimal() for char in text)
