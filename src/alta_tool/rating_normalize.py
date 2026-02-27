from __future__ import annotations

import re

RATING_PATTERN = re.compile(r"(\d(?:\.\d)?)")


def normalize_rating(value: str) -> float | None:
    if not value:
        return None
    match = RATING_PATTERN.search(value)
    if not match:
        return None
    rating = float(match.group(1))
    if rating < 2.0 or rating > 7.0:
        return None
    return rating
