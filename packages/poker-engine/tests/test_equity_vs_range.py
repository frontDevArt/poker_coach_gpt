"""Инварианты эквити против диапазона.

Ни одно ожидание здесь не является запомненным числом: это либо тождества
(сумма долей банка равна единице), либо факты, доказуемые без счёта
(против одной пары тузов у тузов ровно половина — банк всегда делится).
"""

import pytest

from poker_engine.equity import equity_vs_range, hand_equity
from poker_engine.ranges import parse_range

TRIALS = 20_000
SEED = 7


def test_shares_sum_to_one():
    shares = equity_vs_range("JhTh", parse_range("22+"), [], TRIALS, SEED)
    assert len(shares) == 2
    assert sum(shares) == pytest.approx(1.0)


def test_seed_makes_result_reproducible():
    first = equity_vs_range("JhTh", parse_range("AK"), [], TRIALS, SEED)
    second = equity_vs_range("JhTh", parse_range("AK"), [], TRIALS, SEED)
    assert first == second


def test_range_of_one_combo_agrees_with_direct_equity():
    # Диапазон из одной комбинации — это и есть конкретная рука.
    # Обе стороны выборочные, поэтому допуск масштаба выборки, а не 1e-9.
    ranged = equity_vs_range("JhTh", ["AsKd"], [], TRIALS, SEED)
    direct = hand_equity(["JhTh", "AsKd"], [], TRIALS, SEED)
    assert ranged[0] == pytest.approx(direct[0], abs=0.02)


def test_aces_against_only_aces_split_the_pot():
    # Единственная оставшаяся комбинация тузов после блокеров — AcAd.
    # На пустой доске это НЕ гарантированная ничья на каждом ранауте: масти
    # у героя и соперника разные (As/Ah против Ac/Ad), и борд с четырьмя
    # картами одной масти отдаёт флеш только тому, чья дырка в этой масти —
    # это реальная асимметрия исхода, а не шум выборки (проверено отдельно:
    # борд 2s,7s,9s,Ks,4d даёт [1.0, 0.0], а вовсе не сплит). Поэтому здесь
    # берём дорисованную доску, где ни у одной масти нет четырёх карт: флеш
    # недостижим ни для кого, ранги дырок совпадают (AA против AA), и
    # раздача обязана закончиться точной ничьей независимо от числа
    # прогонов — доска полная, значит trials движком вообще не используется.
    board = ["8c", "2s", "9d", "4c", "Tc"]
    shares = equity_vs_range("AsAh", parse_range("AA"), board, 200, SEED)
    assert shares[0] == pytest.approx(0.5)


def test_best_starting_hand_is_never_behind_a_range():
    shares = equity_vs_range("AsAh", parse_range("22+,A2s+,K2s+"), [], TRIALS, SEED)
    assert shares[0] >= 0.5


def test_complete_board_needs_no_sampling():
    # Доска дорисована: исход каждой комбинации диапазона определён,
    # и число прогонов на результат не влияет.
    board = ["8c", "2s", "9d", "4c", "Tc"]
    few = equity_vs_range("JhTh", parse_range("AA"), board, 50, SEED)
    many = equity_vs_range("JhTh", parse_range("AA"), board, 5_000, SEED)
    assert few[0] == pytest.approx(many[0])


def test_range_fully_blocked_by_known_cards_is_rejected():
    with pytest.raises(ValueError):
        equity_vs_range("AsAh", parse_range("AA"), ["Ad", "Ac", "2s"], TRIALS, SEED)


def test_hero_card_duplicated_on_board_is_rejected():
    with pytest.raises(ValueError):
        equity_vs_range("AsAh", parse_range("KK"), ["As", "2s", "3d"], TRIALS, SEED)


def test_non_positive_trials_rejected():
    with pytest.raises(ValueError):
        equity_vs_range("JhTh", parse_range("AA"), [], 0, SEED)
