import pytest

from poker_engine.equity import hand_equity


def test_mirror_hands_split_equity_exactly():
    # AhKh против AdKd симметричны относительно перестановки мастей,
    # поэтому эквити обязано делиться пополам при любом числе прогонов.
    result = hand_equity(["AhKh", "AdKd"], board=[], trials=4000, seed=1)
    assert result[0] == pytest.approx(result[1], abs=1e-9)


def test_equities_sum_to_one():
    result = hand_equity(["AsAd", "KsKd"], board=[], trials=4000, seed=1)
    assert sum(result) == pytest.approx(1.0)


def test_dominant_pair_beats_lower_pair():
    result = hand_equity(["AsAd", "KsKd"], board=[], trials=4000, seed=1)
    assert result[0] > result[1]


def test_made_nuts_on_river_wins_outright():
    # Готовый стрит-флеш на ривере: доска дорисована, случайности нет.
    result = hand_equity(
        ["9h8h", "AcAd"], board=["7h", "6h", "5h", "2c", "2d"], trials=1, seed=1
    )
    assert result == pytest.approx([1.0, 0.0])


def test_identical_hole_cards_on_board_split():
    # Обе руки играют доску -> ровный сплит.
    result = hand_equity(
        ["2c3d", "2h3s"], board=["As", "Ks", "Qs", "Js", "Ts"], trials=1, seed=1
    )
    assert result == pytest.approx([0.5, 0.5])


def test_same_seed_gives_same_result():
    a = hand_equity(["AsAd", "KsKd"], board=[], trials=2000, seed=42)
    b = hand_equity(["AsAd", "KsKd"], board=[], trials=2000, seed=42)
    assert a == pytest.approx(b)


def test_rejects_duplicate_cards():
    with pytest.raises(ValueError):
        hand_equity(["AsAd", "AsKd"], board=[], trials=100, seed=1)


def test_rejects_oversized_board():
    with pytest.raises(ValueError):
        hand_equity(
            ["AsAd", "KsKd"],
            board=["2c", "3c", "4c", "5c", "6c", "7c"],
            trials=100,
            seed=1,
        )


def test_rejects_nonpositive_trials_when_monte_carlo_needed():
    # Префлоп: need=5, попадаем в ветку Monte-Carlo, где trials обязателен.
    with pytest.raises(ValueError):
        hand_equity(["AsAd", "KsKd"], board=[], trials=0, seed=1)
