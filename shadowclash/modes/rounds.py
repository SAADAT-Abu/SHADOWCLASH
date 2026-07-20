"""Best-of-N round bookkeeping for VS matches.

Pure state, no pygame/network dependencies, so both networked clients can run
it independently from the same damage numbers and agree on the outcome.
"""


class RoundTracker:
    def __init__(self, total_rounds: int):
        self.total = max(1, int(total_rounds))
        self.round_no = 1
        self.wins = {"A": 0, "B": 0}

    @property
    def wins_needed(self) -> int:
        return self.total // 2 + 1

    def record(self, winner: str | None) -> None:
        """Score a finished round; None = draw round (nobody scores)."""
        if winner in self.wins:
            self.wins[winner] += 1

    def decided(self) -> bool:
        """True once the match is over: majority reached or rounds exhausted."""
        if max(self.wins.values()) >= self.wins_needed:
            return True
        return self.round_no >= self.total

    def advance(self) -> None:
        self.round_no += 1

    def match_winner(self) -> str | None:
        """'A'/'B' by round wins, or None for an overall draw."""
        if self.wins["A"] > self.wins["B"]:
            return "A"
        if self.wins["B"] > self.wins["A"]:
            return "B"
        return None
