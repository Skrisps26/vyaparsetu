from __future__ import annotations

from indic_numtowords import num2words


def _words(value: int) -> str:
    if value < 0:
        raise ValueError("amount cannot be negative")
    return str(num2words(value, lang="ml"))


def _amount_words(amount_paise: int) -> str:
    rupees, paise = divmod(amount_paise, 100)
    suffix = f" {_words(paise)} പൈസ" if paise else ""
    return f"{_words(rupees)} രൂപ{suffix}"


def confirmation_text(amount_paise: int, payment_mode: str, balance_paise: int | None = None) -> str:
    text = f"ബിൽ തുക {_amount_words(amount_paise)}."
    if payment_mode == "credit":
        if balance_paise is None:
            raise ValueError("credit confirmation requires balance")
        text += f" ഡെമോ അക്കൗണ്ടിൽ ചേർത്തു. ആകെ ബാക്കി {_amount_words(balance_paise)}."
    if any(char.isdecimal() for char in text) or "₹" in text:
        raise ValueError("normalized TTS text contains a digit or currency symbol")
    return text
