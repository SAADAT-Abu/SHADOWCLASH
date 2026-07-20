from shadowclash.modes.rounds import RoundTracker


def test_best_of_three_ends_at_two_wins():
    t = RoundTracker(3)
    assert t.wins_needed == 2
    t.record("A")
    assert not t.decided()
    t.advance()
    t.record("A")
    assert t.decided()
    assert t.match_winner() == "A"


def test_full_distance_split_rounds():
    t = RoundTracker(3)
    for winner in ("A", "B", "B"):
        t.record(winner)
        if not t.decided():
            t.advance()
    assert t.decided()
    assert t.match_winner() == "B"
    assert t.round_no == 3


def test_draw_rounds_score_nobody():
    t = RoundTracker(3)
    t.record(None)
    t.advance()
    t.record(None)
    t.advance()
    t.record("B")
    assert t.decided()  # rounds exhausted
    assert t.match_winner() == "B"


def test_all_draws_is_match_draw():
    t = RoundTracker(3)
    for _ in range(3):
        t.record(None)
        if not t.decided():
            t.advance()
    assert t.decided()
    assert t.match_winner() is None


def test_best_of_seven():
    t = RoundTracker(7)
    assert t.wins_needed == 4
    for _ in range(4):
        assert not t.decided() or t.wins["A"] >= 4
        t.record("A")
        if not t.decided():
            t.advance()
    assert t.decided()
    assert t.match_winner() == "A"
    assert t.round_no == 4  # early finish, rounds 5-7 never played


def test_degenerate_single_round():
    t = RoundTracker(1)
    assert t.wins_needed == 1
    t.record("B")
    assert t.decided()
    assert t.match_winner() == "B"
