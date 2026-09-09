import pytest

from poker_engine.equity import hand_equity


def test_mirror_hands_split_equity_exactly():
    # Доска из четырёх карт ("2c7s9cTs") только треф и пик -> need == 1,
    # ветка Ruling-1 перебирает все 44 ривера точно, без Monte-Carlo.
    # Перестановка мастей h<->d фиксирует доску (в ней нет ни h, ни d),
    # является биекцией оставшейся колоды и переводит AhKh в AdKd и
    # обратно. Значит каждому ривер-исходу для AhKh соответствует
    # ривер-исход для AdKd с точно такой же победой/поражением/сплитом
    # (просто на другой карте той же биекции) -> сумма по всем 44
    # ривера делится ровно пополам, без всякой статистической ошибки.
    result = hand_equity(
        ["AhKh", "AdKd"], board=["2c", "7s", "9c", "Ts"], trials=1, seed=1
    )
    assert result == pytest.approx([0.5, 0.5], abs=1e-9)


def test_mirror_hands_split_equity_within_sampling_error():
    # Без доски (need == 5) считается Monte-Carlo: симметрия h<->d верна
    # только в математическом ожидании по всем возможным доскам, а не
    # для конкретной случайной выборки. Допуск берём порядка масштаба
    # самой выборки (~0.5/sqrt(trials) на сторону), а не машинного эпсилон.
    result = hand_equity(["AhKh", "AdKd"], board=[], trials=4000, seed=1)
    assert result[0] == pytest.approx(result[1], abs=0.02)


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
