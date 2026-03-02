from __future__ import annotations

import re

# Supports ratings like 3.0, 3.5, 3.75, 4.0- (minus only, no plus tier expected).
RATING_PATTERN = re.compile(r"(?<![\d.])([2-7](?:\.\d{1,2})?)(-?)(?![\d.])")


def normalize_rating(value: str) -> float | None:
    if not value:
        return None
    match = RATING_PATTERN.search(value)
    if not match:
        return None
    rating = float(match.group(1))
    is_minus = match.group(2) == "-"
    if rating < 2.0 or rating > 7.0:
        return None
    # "-" tiers are a quarter-step below the base bucket (e.g. 4.0- => 3.75).
    if is_minus:
        rating -= 0.25
    return rating
