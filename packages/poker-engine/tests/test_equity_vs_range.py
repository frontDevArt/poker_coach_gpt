"""Инварианты эквити против диапазона.

Ни одно ожидание здесь не является запомненным числом: это либо тождества
(сумма долей банка равна единице), либо факты, доказуемые без счёта
(против одной пары тузов у тузов ровно половина — банк всегда делится).
"""

import re

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
    # берём дорисованную доску 8c,2s,9d,4c,Tc. На ней три трефы — этого
    # хватило бы на флеш тому, у кого в руке два трефовых блокера (см.
    # test_complete_board_enumerates_the_range_instead_of_sampling ниже,
    # где именно так и выигрывает AcKc). Но здесь расклад другой: у героя
    # AsAh треф нет вообще (0 + 3 борда = 3), а у единственной живой руки
    # соперника AcAd — ровно одна (1 + 3 борда = 4) — обоим не хватает до
    # пяти, флеш недостижим ни для кого именно в этой паре рук. Ранги дырок
    # совпадают (AA против AA), значит раздача обязана закончиться точной
    # ничьей независимо от числа прогонов — доска полная, trials движком
    # вообще не используется.
    board = ["8c", "2s", "9d", "4c", "Tc"]
    shares = equity_vs_range("AsAh", parse_range("AA"), board, 200, SEED)
    assert shares[0] == pytest.approx(0.5)


def test_best_starting_hand_is_never_behind_a_range():
    shares = equity_vs_range("AsAh", parse_range("22+,A2s+,K2s+"), [], TRIALS, SEED)
    assert shares[0] >= 0.5


def test_complete_board_enumerates_the_range_instead_of_sampling():
    # Доска 8c,2s,9d,4c,Tc: три трефы. Из 16 комбинаций AK ровно одна,
    # AcKc, добирает пятую трефу и выигрывает флешем; остальные 15 — туз
    # старшая, проигрывают паре десяток героя (Th + Tc). Значит доля
    # героя ровно 15/16. Число выводится на бумаге, а не из выборки:
    # получить его можно только перебрав диапазон целиком.
    board = ["8c", "2s", "9d", "4c", "Tc"]
    shares = equity_vs_range("JhTh", parse_range("AK"), board, 50, SEED)
    assert shares[0] == pytest.approx(15 / 16)


def test_turn_board_enumerates_every_river_card():
    # Тёрн 8c,2s,9d,4c против AA: шесть живых комбинаций (тузов ни на
    # доске, ни у героя), у каждой 52-6-2 = 44 ривера. Спарившись (JJ
    # или TT), герой всё равно отстаёт от пары тузов, флеша нет ни у
    # кого — герой выигрывает ровно стритом: ривер 7 (7-8-9-T-J) или Q
    # (8-9-T-J-Q), это 4+4 = 8 карт из 44. Доля героя ровно 8/44, число
    # с бумаги, а не с выборки.
    board = ["8c", "2s", "9d", "4c"]
    shares = equity_vs_range("JhTh", parse_range("AA"), board, 10, SEED)
    assert shares[0] == pytest.approx(8 / 44)
    assert sum(shares) == pytest.approx(1.0)
    assert shares == equity_vs_range("JhTh", parse_range("AA"), board, 50_000, SEED)


def test_range_equity_is_the_mean_over_its_combos():
    # Комбинация внутри диапазона выбирается равновероятно, и у каждой
    # свой полный набор ранаутов — значит эквити против диапазона это
    # ровно среднее эквити против каждой комбинации. Тождество, а не
    # число: оба конца считает hand_equity прямо здесь.
    vs_ak = hand_equity(["JhTh", "AsKd"], [], TRIALS, SEED)[0]
    vs_22 = hand_equity(["JhTh", "2c2d"], [], TRIALS, SEED)[0]
    assert abs(vs_ak - vs_22) > 0.05  # концы различимы, среднее осмысленно
    mixed = equity_vs_range("JhTh", ["2c2d", "AsKd"], [], TRIALS, SEED)[0]
    assert mixed == pytest.approx((vs_ak + vs_22) / 2, abs=0.02)


def test_range_fully_blocked_by_known_cards_is_rejected():
    # `match=` различает этот отказ от дубля карты и от пустого диапазона:
    # в вызове ниже блокированы все комбинации соперника, а не карты героя.
    with pytest.raises(
        ValueError,
        match=re.escape("диапазон соперника пуст после исключения известных карт"),
    ):
        equity_vs_range("AsAh", parse_range("AA"), ["Ad", "Ac", "2s"], TRIALS, SEED)


def test_hero_card_duplicated_on_board_is_rejected():
    # Отвергнуть обязан гард дублей, а не пустой диапазон соперника.
    with pytest.raises(ValueError, match=re.escape("карта 'As' встречается дважды")):
        equity_vs_range("AsAh", parse_range("KK"), ["As", "2s", "3d"], TRIALS, SEED)


def test_non_positive_trials_rejected():
    with pytest.raises(ValueError, match=re.escape("trials должен быть > 0")):
        equity_vs_range("JhTh", parse_range("AA"), [], 0, SEED)
