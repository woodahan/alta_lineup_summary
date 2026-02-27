from __future__ import annotations

import re

# Supports ratings like 3.0, 3.5, 4.0- (minus only, no plus tier expected).
RATING_PATTERN = re.compile(r"(\d(?:\.\d)?)(-?)")


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
    # Keep "-" tiers slightly below the base bucket for comparison ordering.
    if is_minus:
        rating -= 0.01
    return rating
