"""Дерево префлопа: участники, размеры, слияние, терминалы, ICM одним пакетом, головы, пометки.

Спека плана 5, §6.1–§6.7. Стол фикстур — 6-max `conftest.preflop_frame`: кнопка 4, ход `UTG` 7,
`HJ` 2, `CO` 3, `BTN` 4, `SB` 5, `BB` 6, у всех 40 BB, если не сказано иное.
"""

import numpy
import pytest

from conftest import (
    _context,
    preflop_frame,
    preflop_open,
    preflop_open_utg_node,
    preflop_vs_3bet,
    preflop_vs_4bet,
    preflop_vs_allin_after_raise,
    preflop_vs_limp,
    preflop_vs_open,
    pushfold_first_in_node,
)
from poker_engine import allin_matrix, icm_field, preflop_tree, profiles, pushfold_game
from poker_engine.bounty import knockout_cash
from poker_engine.handstate import context_from_dict, node_from_dict, validate_hand
from poker_engine.preflop_line import read_line
from poker_engine.preflop_tree import (
    LIMP_RERAISE,
    Decision,
    Terminal,
    build,
    chip_payoffs,
    icm_payoffs,
)


def _nodes(raws):
    nodes = [node_from_dict(raw) for raw in raws]
    validate_hand(context_from_dict(_context()), nodes)
    return nodes


def _tree(raws):
    nodes = _nodes(raws)
    return build(read_line(nodes), nodes[-1]), nodes[-1]


def _actions(tree, at):
    return [(action.kind, action.to_bb) for action in tree.nodes[at].actions]


def _hero(tree):
    return _actions(tree, tree.hero_node)


def _child(tree, at, kind):
    return next(action.child for action in tree.nodes[at].actions if action.kind == kind)


def _stacks(value):
    return {seat: value for seat in range(2, 8)}


def _sb_open():
    return [preflop_frame(5, folded={7, 2, 3, 4})]


def _sb_limp():
    return [preflop_frame(6, {5: 1.0}, folded={7, 2, 3, 4})]


def _short_open():
    # Герой `CO` с 1.6 BB: открытие по правилу 2.0 не меньше его стека.
    return [preflop_frame(3, folded={7, 2}, starting={3: 1.6})]


FIXTURES = {
    "open": preflop_open,
    "vs_open": preflop_vs_open,
    "vs_limp": preflop_vs_limp,
    "vs_3bet": preflop_vs_3bet,
    "vs_4bet": preflop_vs_4bet,
    "vs_allin_after_raise": preflop_vs_allin_after_raise,
    "sb_limp": _sb_limp,
}


@pytest.fixture
def no_pushfold(monkeypatch):
    """Порог push/fold 0: короткий стек читается линией, а не отдаётся `pushfold`."""
    monkeypatch.setattr(pushfold_game, "PUSHFOLD_MAX_BB", 0.0)


# --- терминалы и линия ---------------------------------------------------------------------


@pytest.mark.parametrize("make", FIXTURES.values(), ids=FIXTURES)
def test_chips_are_conserved_on_every_terminal(make):
    tree, node = _tree(make())
    before = sum(seat.stack_bb for seat in tree.players) + node.pot_bb
    terminals = [n for n in tree.nodes if isinstance(n, Terminal)]
    assert terminals
    for terminal in terminals:
        assert len(terminal.rows) == (1 if terminal.kind == "fold" else 2)
        for row in terminal.rows:
            assert sum(row) == pytest.approx(before, abs=1e-9)
            assert min(row) >= 0


def _parents(tree):
    """Терминал → вид действия, которое в него ведёт."""
    return {
        action.child: action.kind
        for node in tree.nodes
        if isinstance(node, Decision)
        for action in node.actions
    }


@pytest.mark.parametrize("make", FIXTURES.values(), ids=FIXTURES)
def test_realization_only_on_call_terminals(make):
    # Спека модели колла §5.3: терминал реализации — колл (или чек) без олл-ина; у `fold` и
    # `allin` нет ни SPR, ни позиции, а значит и матрицы реализации.
    tree, _ = _tree(make())
    parents = _parents(tree)
    for at, node in enumerate(tree.nodes):
        if not isinstance(node, Terminal):
            continue
        if node.kind == "realization":
            assert parents[at] in ("call", "check")
            assert node.spr is not None and node.opener_in_position is not None
        else:
            assert node.kind in ("fold", "allin")
            assert node.spr is None and node.opener_in_position is None


@pytest.mark.parametrize("make", FIXTURES.values(), ids=FIXTURES)
def test_spr_is_the_short_stack_behind_over_the_pot(make):
    # SPR из рядов: проигравший `a` сохраняет остаток `R_a`, выигравший забирает банк `P`.
    tree, _ = _tree(make())
    for node in tree.nodes:
        if isinstance(node, Terminal) and node.kind == "realization":
            a, b = node.pair
            won, lost = node.rows
            pot = won[a] - lost[a]
            assert node.spr == pytest.approx(min(lost[a], won[b]) / pot, abs=1e-12)


def test_spr_and_position_on_paper():
    # Герой `CO` открыл до 2.0: колл `BB` — банк 2 × 2.0 + `SB` 0.5 + анте 0.75 = 5.25, за ним
    # 38; `CO` на флопе ходит после `BB`. 3-бет `BTN` до 6.0 и колл `CO` — банк 12 + 0.5 + 1.0 +
    # 0.75 = 14.25, за ним 34; `CO` ходит раньше `BTN`.
    tree, _ = _tree(preflop_open())
    opened = _child(tree, tree.root, "raise")
    at = _child(tree, _child(tree, _child(tree, opened, "fold"), "fold"), "call")
    assert tree.nodes[at].pair == (0, 3)
    assert tree.nodes[at].spr == pytest.approx(38.0 / 5.25)
    assert tree.nodes[at].opener_in_position is True
    at = _child(tree, _child(tree, opened, "raise"), "call")
    assert tree.nodes[at].pair == (0, 1)
    assert tree.nodes[at].spr == pytest.approx(34.0 / 14.25)
    assert tree.nodes[at].opener_in_position is False


def test_spr_counts_the_shorter_stack_of_the_pair():
    # `R` — меньший из остатков пары: у `BB` 25 BB до раздачи, после колла открытия 2.0 за ним
    # 23, у `CO` — 38; банк тот же 5.25.
    tree, _ = _tree([preflop_frame(3, folded={7, 2}, starting={6: 25.0})])
    opened = _child(tree, tree.root, "raise")
    at = _child(tree, _child(tree, _child(tree, opened, "fold"), "fold"), "call")
    assert tree.nodes[at].pair == (0, 3)
    assert tree.nodes[at].spr == pytest.approx(23.0 / 5.25)


def test_big_blind_is_in_position_against_the_small_blind():
    # Порядок флопа `SB`, `BB`, `UTG…BTN`: чек `BB` за лимпом `SB` — `BB` в позиции.
    tree, _ = _tree(_sb_limp())
    checked = tree.nodes[_child(tree, tree.root, "check")]
    assert checked.opener_in_position is True
    assert checked.spr == pytest.approx(39.0 / 2.75)


@pytest.mark.parametrize("make", FIXTURES.values(), ids=FIXTURES)
def test_path_leads_from_the_root_to_the_hero(make):
    tree, _ = _tree(make())
    at = tree.root
    for node_at, index in tree.path:
        assert node_at == at
        at = tree.nodes[at].actions[index].child
    assert at == tree.hero_node
    assert tree.players[tree.nodes[tree.hero_node].player].is_hero


def test_path_replays_the_line_with_played_sizes():
    tree, _ = _tree(preflop_vs_4bet())
    # `HJ` сфолдил после открытия: он всё равно отвечающий, линия выбирает его фолд.
    assert [seat.seat_index for seat in tree.players] == [7, 2, 3, 4, 5, 6]
    played = [
        (
            tree.players[tree.nodes[at].player].seat_index,
            tree.nodes[at].actions[index].kind,
            tree.nodes[at].actions[index].to_bb,
        )
        for at, index in tree.path
    ]
    assert played == [(7, "raise", 2.0), (2, "fold", None), (3, "raise", 6.0), (7, "raise", 15.0)]
    assert _hero(tree) == [("fold", None), ("call", 15.0), ("allin", 40.0)]


def test_open_tree_starts_at_the_hero():
    tree, _ = _tree(preflop_open())
    assert [seat.seat_index for seat in tree.players] == [3, 4, 5, 6]
    assert tree.hero_node == tree.root
    assert tree.path == []
    assert _hero(tree) == [("fold", None), ("raise", 2.0), ("allin", 40.0)]
    # Фолд корня — банк большому блайнду (участник 3), как `walk` плана 4.
    walk = tree.nodes[_child(tree, tree.root, "fold")]
    assert walk.kind == "fold"
    assert walk.rows[0][3] == pytest.approx(40.0 + 0.5 + 0.75)
    # Колл открытия без олл-ина — у закрывающего `BB` (участник 3), вскрытие без ставок.
    at = _child(tree, _child(tree, _child(tree, tree.root, "raise"), "fold"), "fold")
    called = tree.nodes[_child(tree, at, "call")]
    assert (called.kind, called.pair) == ("realization", (0, 3))


# --- колл только у закрывающего (спека модели колла §4, инвариант 1) ------------------------


def test_non_closing_responder_has_no_call():
    # 6-max, `UTG` открывает при 25 BB: колл открытия — только у `BB`, он закрывает действие.
    tree, _ = _tree([preflop_open_utg_node(pushfold_first_in_node)])
    assert [seat.seat_index for seat in tree.players] == [7, 2, 3, 4, 5, 6]
    at = _child(tree, tree.root, "raise")
    for player in range(1, 5):
        assert tree.nodes[at].player == player
        assert [kind for kind, _ in _actions(tree, at)] == ["fold", "raise", "allin"]
        at = _child(tree, at, "fold")
    assert tree.nodes[at].player == 5
    assert [kind for kind, _ in _actions(tree, at)] == ["fold", "call", "raise", "allin"]


def test_call_against_an_open_allin_stays():
    # Корень пошёл олл-ин: колл у каждого отвечающего, как у push/fold плана 4.
    tree, _ = _tree([preflop_open_utg_node(pushfold_first_in_node)])
    at = _child(tree, tree.root, "allin")
    for player in range(1, 6):
        assert tree.nodes[at].player == player
        assert [kind for kind, _ in _actions(tree, at)] == ["fold", "call"]
        at = _child(tree, at, "fold")


def test_limper_closes_against_isolation():
    # Герой `BTN` изолирует лимп `UTG`: блайнды без колла, лимпер закрывает действие.
    tree, _ = _tree(preflop_vs_limp())
    at = _child(tree, tree.root, "raise")
    for player in (1, 2):
        assert tree.nodes[at].player == player
        assert [kind for kind, _ in _actions(tree, at)] == ["fold", "raise", "allin"]
        at = _child(tree, at, "fold")
    assert tree.nodes[at].player == 3
    assert [kind for kind, _ in _actions(tree, at)] == ["fold", "call", "allin"]


# --- против лимпа --------------------------------------------------------------------------


def test_vs_limp_tree_starts_at_the_hero_and_ends_with_the_limper():
    tree, _ = _tree(preflop_vs_limp())
    assert [seat.seat_index for seat in tree.players] == [4, 5, 6, 7]
    assert tree.hero_node == tree.root
    assert _hero(tree) == [("fold", None), ("raise", 4.0), ("allin", 40.0)]
    at = _child(tree, tree.root, "raise")
    for _ in (5, 6):
        # Отвечающие на изоляцию: колла нет (закрывает лимпер); 3-бет без позиции
        # 4 × 4.0 = 16.0 = 0.4 × 40 — не слит.
        assert _actions(tree, at) == [("fold", None), ("raise", 16.0), ("allin", 40.0)]
        at = _child(tree, at, "fold")
    # Лимпер против изоляции: без рейза.
    assert tree.nodes[at].player == 3
    assert _actions(tree, at) == [("fold", None), ("call", 4.0), ("allin", 40.0)]
    # Лимпер сфолдил: теряет свой лимп 1.0, герой забирает его, блайнды и анте 0.75.
    folded = tree.nodes[_child(tree, at, "fold")]
    assert folded.rows[0] == pytest.approx([40.0 + 1.0 + 0.5 + 1.0 + 0.75, 39.5, 39.0, 39.0])


def test_limper_range_is_the_vpip_profile():
    tree, _ = _tree(preflop_vs_limp())
    assert list(tree.fixed_ranges) == [3]
    share = tree.fixed_ranges[3]
    combos = numpy.array([allin_matrix.combos_of(name) for name in allin_matrix.CLASSES])
    expected, _ = profiles.range_for_vpip(25.0, 60)
    assert share @ combos == pytest.approx(len(expected))
    assert share.min() >= 0 and share.max() <= 1


def test_big_blind_checks_behind_a_small_blind_limp():
    tree, _ = _tree(_sb_limp())
    assert [seat.seat_index for seat in tree.players] == [6, 5]
    assert _hero(tree) == [("check", None), ("raise", 4.0), ("allin", 40.0)]
    checked = tree.nodes[_child(tree, tree.root, "check")]
    assert (checked.kind, checked.pair) == ("realization", (0, 1))


def test_a_limper_allin_over_the_isolation_is_played():
    raws = [
        preflop_frame(4, {7: 1.0}, folded={2, 3}),
        preflop_frame(4, {7: 40.0, 4: 4.0}, folded={2, 3, 5, 6}),
    ]
    tree, _ = _tree(raws)
    assert [seat.seat_index for seat in tree.players] == [4, 5, 6, 7]
    assert _hero(tree) == [("fold", None), ("call", 40.0)]


def test_a_limp_reraise_not_allin_is_refused():
    raws = [
        preflop_frame(4, {7: 1.0}, folded={2, 3}),
        preflop_frame(4, {7: 12.0, 4: 4.0}, folded={2, 3, 5, 6}),
    ]
    nodes = _nodes(raws)
    assert read_line(nodes).kind == "vs_3bet"
    assert build(read_line(nodes), nodes[-1]) == LIMP_RERAISE
    assert LIMP_RERAISE == "лимпер ответил на изоляцию рейзом не олл-ином: вне дерева префлопа"


def test_a_blind_already_allin_is_refused():
    raws = [preflop_frame(3, folded={7, 2}, starting={6: 1.0})]
    nodes = _nodes(raws)
    assert build(read_line(nodes), nodes[-1]) == "место 6 уже в олл-ине с блайнда: вне модели"


def test_a_zero_stack_out_of_the_hand_is_refused():
    # `HJ` после открывшего `UTG` — участник дерева, но стека у него нет.
    raws = [preflop_frame(3, {7: 2.0}, folded={2}, starting={2: 0.0})]
    nodes = _nodes(raws)
    assert (
        build(read_line(nodes), nodes[-1])
        == "на месте 2 стек 0 вне раздачи: ICM не определён"
    )


# --- размеры --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raws", "size"),
    [
        (preflop_open(), 2.0),  # открытие не с SB
        (_sb_open(), 3.0),  # открытие с SB
        (preflop_vs_limp(), 4.0),  # изоляция 3.0 + 1.0 за лимпера
        ([preflop_frame(6, {7: 1.0}, folded={2, 3, 4, 5})], 4.0),  # изоляция из BB
        (preflop_vs_open(), 6.0),  # 3-бет в позиции: 3 × 2.0
        ([preflop_frame(5, {7: 2.0}, folded={2, 3, 4})], 8.0),  # 3-бет SB: 4 × 2.0
        ([preflop_frame(6, {7: 2.0}, folded={2, 3, 4, 5})], 8.0),  # 3-бет BB: 4 × 2.0
        ([preflop_frame(6, {5: 3.0}, folded={7, 2, 3, 4})], 9.0),  # BB против SB в позиции
        (preflop_vs_3bet(), 15.4),  # 4-бет: 2.2 × 7.0
    ],
    ids=[
        "open",
        "open_sb",
        "iso",
        "iso_bb",
        "3bet_ip",
        "3bet_sb",
        "3bet_bb",
        "3bet_bb_vs_sb",
        "4bet",
    ],
)
def test_sizes_follow_the_rule(raws, size):
    tree, _ = _tree(raws)
    assert ("raise", size) in _hero(tree)
    assert "fixed_sizing" in tree.flags


def test_isolation_from_the_big_blind_is_flat(monkeypatch):
    # За лимпера доплачивает только изоляция не из BB.
    monkeypatch.setattr(preflop_tree, "ISO_PER_LIMPER_BB", 2.0)
    tree, _ = _tree(preflop_vs_limp())
    assert ("raise", 5.0) in _hero(tree)
    tree, _ = _tree([preflop_frame(6, {7: 1.0}, folded={2, 3, 4, 5})])
    assert ("raise", 4.0) in _hero(tree)


def test_rule_raise_above_commit_share_becomes_allin():
    # 15 BB, `UTG` открыл до 2.0, герой `BB`: 3-бет по правилу 8.0 > 0.4 × 15 = 6.0.
    tree, _ = _tree([preflop_frame(6, {7: 2.0}, folded={2, 3, 4, 5}, starting=_stacks(15.0))])
    assert _hero(tree) == [("fold", None), ("call", 2.0), ("allin", 15.0)]


def test_rule_raise_at_commit_share_stays_a_raise():
    # Граница «больше»: 3-бет в позиции 6.0 = 0.4 × 15 — ещё рейз.
    tree, _ = _tree([preflop_frame(3, {7: 2.0}, folded={2}, starting=_stacks(15.0))])
    assert _hero(tree) == [("fold", None), ("raise", 6.0), ("allin", 15.0)]


@pytest.mark.parametrize(
    ("raws", "hero"),
    [
        # Открытие: у героя 40, у отвечающих по 4 — 2.0 > 0.4 × 4.
        (
            [preflop_frame(3, folded={7, 2}, starting={4: 4.0, 5: 4.0, 6: 4.0})],
            [("fold", None), ("allin", 40.0)],
        ),
        # 3-бет: `UTG` с 10 открыл до 2.0 — 6.0 > 0.4 × 10.
        (
            [preflop_frame(3, {7: 2.0}, folded={2}, starting={7: 10.0})],
            [("fold", None), ("allin", 40.0)],
        ),
        # 4-бет: `BTN` с 20 — 3-бет до 7.0, 15.4 > 0.4 × 20.
        (
            [
                preflop_frame(3, folded={7, 2}, starting={4: 20.0}),
                preflop_frame(3, {3: 2.0, 4: 7.0}, folded={7, 2, 5, 6}, starting={4: 20.0}),
            ],
            [("fold", None), ("call", 7.0), ("allin", 40.0)],
        ),
    ],
    ids=["open", "3bet", "4bet"],
)
def test_commit_share_is_of_the_effective_stack(no_pushfold, raws, hero):
    # Эффективный стек — меньший из двух: короткий соперник сливает рейз длинного героя.
    tree, _ = _tree(raws)
    assert _hero(tree) == hero


def test_played_size_is_kept():
    # Review Focus 3: фактический 3-бет 8.0 больше 0.4 × 15, но сыгран — остаётся рейзом.
    raws = [
        preflop_frame(3, folded={7, 2}, starting=_stacks(15.0)),
        preflop_frame(3, {3: 2.0, 4: 8.0}, folded={7, 2, 5, 6}, starting=_stacks(15.0)),
    ]
    tree, _ = _tree(raws)
    at, index = tree.path[-1]
    # `BTN` не закрывает действие: колла открытия у него нет.
    assert _actions(tree, at) == [("fold", None), ("raise", 8.0), ("allin", 15.0)]
    assert index == 1
    # У открывшего против него — без 4-бета: 2.2 × 8.0 по правилу слит.
    assert _hero(tree) == [("fold", None), ("call", 8.0), ("allin", 15.0)]


def test_short_hero_has_only_fold_and_allin(no_pushfold):
    # Review Focus 5: стек героя 1.6 BB меньше открытия по правилу.
    tree, _ = _tree(_short_open())
    assert _hero(tree) == [("fold", None), ("allin", 1.6)]
    for terminal in (n for n in tree.nodes if isinstance(n, Terminal)):
        assert all(min(row) >= 0 for row in terminal.rows)


@pytest.mark.parametrize("stack", [1.5, 2.0])
def test_a_stack_below_the_bet_calls_allin(stack):
    # `BTN` с 1.5 BB и ровно 2.0 против открытия до 2.0: колл на все, а не колл и олл-ин.
    tree, _ = _tree([preflop_frame(3, folded={7, 2}, starting={4: stack})])
    at = _child(tree, tree.root, "raise")
    assert _actions(tree, at) == [("fold", None), ("allin", stack)]
    assert tree.nodes[_child(tree, at, "allin")].kind == "allin"


def test_a_stack_equal_to_the_3bet_calls_allin(no_pushfold):
    # Герой `CO` с 8.0 открыл до 2.0, `BTN` — 3-бет ровно до 8.0: колл — на все.
    raws = [
        preflop_frame(3, folded={7, 2}, starting={3: 8.0}),
        preflop_frame(3, {3: 2.0, 4: 8.0}, folded={7, 2, 5, 6}, starting={3: 8.0}),
    ]
    tree, _ = _tree(raws)
    assert _hero(tree) == [("fold", None), ("allin", 8.0)]
    showdown = tree.nodes[_child(tree, tree.hero_node, "allin")]
    assert showdown.kind == "allin"
    assert min(min(row) for row in showdown.rows) == 0


# --- ICM и головы ---------------------------------------------------------------------------


def test_icm_is_one_batch_per_tree(monkeypatch):
    tree, node = _tree(preflop_vs_3bet())
    calls = []
    real = icm_field.table_equities_batch

    def counted(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(icm_field, "table_equities_batch", counted)
    payoffs = icm_payoffs(tree, node, context_from_dict(_context()), bounties=False)
    assert len(calls) == 1
    for n, pay in zip(tree.nodes, payoffs, strict=True):
        assert (pay is None) == isinstance(n, Decision)


def _priced(raw, price):
    for seat in raw["seats"]:
        seat["bountyUsd"] = price
    return raw


def test_bounty_only_on_knockouts():
    # `BTN` с 60 BB накрывает героя: его проигранный олл-ин — не нокаут.
    raws = [_priced(preflop_frame(3, folded={7, 2}, starting={4: 60.0}), 5.0)]
    tree, node = _tree(raws)
    context = context_from_dict(_context())
    plain = icm_payoffs(tree, node, context, bounties=False)
    pko = icm_payoffs(tree, node, context, bounties=True)
    seen = set()
    for n, without, with_heads in zip(tree.nodes, plain, pko, strict=True):
        if without is None:
            continue
        for r, row in enumerate(n.rows):
            expected = numpy.zeros(len(tree.players))
            if n.kind == "allin":
                winner, loser = n.pair if r == 0 else n.pair[::-1]
                if row[loser] == 0:
                    expected[winner] = knockout_cash(5.0)
                    seen.add("knockout")
                else:
                    seen.add("covered")
            seen.add(n.kind)
            assert with_heads[r] - without[r] == pytest.approx(expected, abs=1e-12)
    assert seen == {"knockout", "covered", "allin", "realization", "fold"}


def test_busted_gets_the_prize_of_his_place():
    # Защита на баббле: вылетевший получает возврат 10 как приз места `playersLeft`, а не
    # эквити по столу (оно у нулевого стека ноль).
    tree, node = _tree(preflop_open())
    context = context_from_dict({**_context(), "bubbleRefundUsd": 10.0})
    payoffs = icm_payoffs(tree, node, context, bounties=False)
    knockouts = 0
    for n, pay in zip(tree.nodes, payoffs, strict=True):
        if isinstance(n, Terminal):
            for r, row in enumerate(n.rows):
                for p, stack in enumerate(row):
                    if stack == 0:
                        assert pay[r, p] == pytest.approx(10.0)
                        knockouts += 1
    assert knockouts > 0


def test_fold_tree_matches_pushfold_subgame(monkeypatch):
    # Все рейзы слиты с олл-ином — дерево `open` ровно подыгра push/fold плана 4.
    nodes = _nodes([pushfold_first_in_node()])
    node = nodes[0]
    spot = pushfold_game.read_spot(node)
    assert isinstance(spot, pushfold_game.Spot)
    context = context_from_dict(_context())
    chips = pushfold_game.chip_outcomes(spot)
    icm = pushfold_game.icm_outcomes(spot, node, context, bounties=False)

    monkeypatch.setattr(pushfold_game, "PUSHFOLD_MAX_BB", 0.0)
    monkeypatch.setattr(preflop_tree, "COMMIT_SHARE", 0.0)
    tree = build(read_line(nodes), node)
    assert [p.seat_index for p in tree.players] == [p.seat_index for p in spot.players]
    assert "fixed_sizing" not in tree.flags
    assert "postflop_realization" not in tree.flags

    for payoffs, outcomes in (
        (chip_payoffs(tree), chips),
        (icm_payoffs(tree, node, context, bounties=False), icm),
    ):
        assert _actions(tree, tree.root) == [("fold", None), ("allin", 10.0)]
        assert payoffs[_child(tree, tree.root, "fold")][0] == pytest.approx(outcomes.walk)
        at = _child(tree, tree.root, "allin")
        for j in range(len(tree.players) - 1):
            assert [kind for kind, _ in _actions(tree, at)] == ["fold", "call"]
            showdown = payoffs[_child(tree, at, "call")]
            assert showdown[0] == pytest.approx(outcomes.win[j])
            assert showdown[1] == pytest.approx(outcomes.lose[j])
            at = _child(tree, at, "fold")
        assert payoffs[at][0] == pytest.approx(outcomes.steal)


# --- пометки ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("flag", "make", "expected"),
    [
        ("fixed_sizing", preflop_open, True),
        ("fixed_sizing", _short_open, False),
        ("postflop_realization", preflop_open, True),
        ("postflop_realization", _short_open, False),
        ("deep_stack", lambda: [preflop_frame(3, folded={7, 2}, starting=_stacks(60.0))], True),
        ("deep_stack", preflop_open, False),  # ровно 40 BB — ещё не глубоко
        # Эффективный стек — против самого большого соперника, а не стек героя.
        ("deep_stack", lambda: [preflop_frame(3, folded={7, 2}, starting={3: 60.0})], False),
        ("no_overcall", preflop_open, True),
        ("no_overcall", lambda: [preflop_frame(4, folded={7, 2, 3})], True),  # BTN, SB, BB
        ("no_overcall", _sb_open, False),
        ("fold_as_walk", preflop_open, True),
        ("fold_as_walk", _sb_open, False),
        ("fold_as_walk", _sb_limp, False),  # у BB против лимпа фолда нет
        ("limper_range_profile", preflop_vs_limp, True),
        ("limper_range_profile", preflop_open, False),
        ("no_hero_limp", _sb_open, True),
        ("no_hero_limp", preflop_open, False),
        ("no_hero_limp", _sb_limp, False),
        # Инвариант 2: незакрывающий против открытия — без колла, `BB` закрывает.
        ("no_cold_call", preflop_vs_open, True),
        ("no_cold_call", lambda: [preflop_frame(6, {7: 2.0}, folded={2, 3, 4, 5})], False),
        ("no_cold_call", preflop_open, False),
        ("no_cold_call", preflop_vs_limp, False),
        ("no_cold_call", preflop_vs_allin_after_raise, False),
        # Стек героя 1.6 не выше открытия 2.0: колла нет из-за стека, олл-ин и есть колл.
        (
            "no_cold_call",
            lambda: [preflop_frame(3, {7: 2.0}, folded={2}, starting={3: 1.6})],
            False,
        ),
    ],
)
def test_flags_are_true_only_when_true(no_pushfold, flag, make, expected):
    tree, _ = _tree(make())
    assert (flag in tree.flags) is expected


def test_deep_stack_threshold_is_the_realization_trust(monkeypatch):
    # Порог `deep_stack` — константа `REALIZATION_TRUST_BB`, а не число в коде: 40 BB глубже 30.
    assert preflop_tree.REALIZATION_TRUST_BB == 40.0
    monkeypatch.setattr(preflop_tree, "REALIZATION_TRUST_BB", 30.0)
    tree, _ = _tree(preflop_open())
    assert "deep_stack" in tree.flags
