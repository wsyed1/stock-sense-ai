"""Hand-labeled evaluation cases for directional sentiment accuracy.

Each case is a ticker plus the *direction* a human would expect the sentiment to
fall in, given the general news climate. This is intentionally coarse — the goal
is a directional sanity check, not a precise score target.

`expected_direction` is one of: "bullish", "bearish", "neutral".

These labels are subjective and time-sensitive (news changes), so treat the
accuracy number as directional signal, not ground truth. Update the labels when
you refresh the evaluation.
"""

# The recommendation labels the service can emit (from sentiment_service).
BULLISH_LABELS = {"Strongly Bullish", "Bullish"}
BEARISH_LABELS = {"Bearish"}
NEUTRAL_LABELS = {"Neutral"}


LABELED_CASES = [
    {"ticker": "NVDA", "expected_direction": "bullish"},
    {"ticker": "AAPL", "expected_direction": "bullish"},
    {"ticker": "MSFT", "expected_direction": "bullish"},
    {"ticker": "GOOGL", "expected_direction": "bullish"},
    {"ticker": "AMZN", "expected_direction": "bullish"},
    {"ticker": "META", "expected_direction": "bullish"},
    {"ticker": "TSLA", "expected_direction": "neutral"},
    {"ticker": "INTC", "expected_direction": "bearish"},
]


def direction_of(recommendation: str) -> str:
    """Collapse a recommendation label into a bullish/bearish/neutral direction."""
    if recommendation in BULLISH_LABELS:
        return "bullish"
    if recommendation in BEARISH_LABELS:
        return "bearish"
    if recommendation in NEUTRAL_LABELS:
        return "neutral"
    return "no_data"
