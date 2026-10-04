from dataclasses import dataclass


@dataclass(frozen=True)
class Match:
    start: int
    end: int
    kind: str  # placeholder kind: EMAIL, IBAN, SECRET, LINK...
    rule_id: str


def non_overlapping(matches: list[Match], priority: list[str]) -> list[Match]:
    """Keep the highest-priority match where matches overlap (e.g. IBAN digits are not also a phone)."""
    rank = {kind: i for i, kind in enumerate(priority)}
    accepted: list[Match] = []
    for m in sorted(matches, key=lambda m: (rank.get(m.kind, len(rank)), m.start)):
        if all(m.end <= a.start or m.start >= a.end for a in accepted):
            accepted.append(m)
    return sorted(accepted, key=lambda m: m.start)


def apply_placeholders(text: str, matches: list[Match], placeholder) -> str:
    """Replace matched spans. `placeholder(kind, value) -> str`.

    Placeholders are assigned in reading order ([EMAIL_1] is the first email), then spliced in
    right to left so earlier offsets stay valid."""
    ordered = sorted(matches, key=lambda m: m.start)
    labels = [placeholder(m.kind, text[m.start : m.end]) for m in ordered]
    for m, label in reversed(list(zip(ordered, labels))):
        text = text[: m.start] + label + text[m.end :]
    return text
