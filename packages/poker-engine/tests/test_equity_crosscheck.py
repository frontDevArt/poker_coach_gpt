import pytest

from poker_engine.equity import FULL_DECK, hand_equity


def _exact_flop_equity(hands, flop):
    """Точное эквити на флопе путём усреднения полного перебора для каждой карты тёрна.

    На флопе остаются две карты (тёрн и ривер). Вместо прямого перебора всех 45*44 пар,
    мы для каждой из 45 возможных карт тёрна вызываем hand_equity с этой картой на доске:
    функция перечисляет точно все 44 возможных ривера (need=1 включает exhaustive branch).
    Усредняя результаты по всем 45 тёрнам, мы получаем точное эквити флопа независимо
    от выборки: это определение точного эквити — математическое ожидание по всем возможным
    доскам.
    """
    # Распарсим карты из рук (каждая рука это строка вида "AsKd")
    known_cards = set(flop)
    for hand in hands:
        for i in range(0, len(hand), 2):
            known_cards.add(hand[i:i+2])

    remaining_cards = [c for c in FULL_DECK if c not in known_cards]

    # remaining_cards должна содержать 45 карт (52 - 2 - 2 - 3)
    assert len(remaining_cards) == 45

    exact_wins = [0.0] * len(hands)
    for turn_card in remaining_cards:
        runout = hand_equity(hands, board=flop + [turn_card], trials=1, seed=0)
        for i in range(len(hands)):
            exact_wins[i] += runout[i]

    return [w / len(remaining_cards) for w in exact_wins]


def test_monte_carlo_converges_to_exhaustive_on_flop():
    hands = ["AsKs", "7h7d"]
    flop = ["Kc", "8c", "3d"]

    exact = _exact_flop_equity(hands, flop)
    sampled = hand_equity(hands, board=flop, trials=20_000, seed=7)

    assert sampled[0] == pytest.approx(exact[0], abs=0.01)
    assert sampled[1] == pytest.approx(exact[1], abs=0.01)


def test_equity_is_symmetric_under_hand_order():
    forward = hand_equity(["AsAd", "KsKd"], board=[], trials=8000, seed=3)
    backward = hand_equity(["KsKd", "AsAd"], board=[], trials=8000, seed=3)
    assert forward[0] == pytest.approx(backward[1], abs=0.02)
