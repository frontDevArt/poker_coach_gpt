import pytest

from poker_engine.types import (
    ChipConservationError,
    Position,
    Street,
    TableSnapshot,
    positions_for,
)


def test_street_order():
    assert Street.PREFLOP < Street.FLOP < Street.TURN < Street.RIVER


def test_positions_for_six_max():
    assert positions_for(6) == [
        Position.UTG,
        Position.HJ,
        Position.CO,
        Position.BTN,
        Position.SB,
        Position.BB,
    ]


def test_positions_for_eight_max_is_gg_default():
    assert positions_for(8) == [
        Position.UTG1,
        Position.MP,
        Position.LJ,
        Position.HJ,
        Position.CO,
        Position.BTN,
        Position.SB,
        Position.BB,
    ]


def test_positions_for_heads_up():
    assert positions_for(2) == [Position.SB, Position.BB]


def test_snapshot_conserves_chips():
    snap = TableSnapshot(stacks=[1000, 2000, 3000], pot=500, total_chips=6500)
    assert snap.is_consistent()


def test_snapshot_rejects_chip_leak():
    with pytest.raises(ChipConservationError):
        TableSnapshot(stacks=[1000, 2000, 3000], pot=500, total_chips=9000).validate()


def test_effective_stack_is_second_largest_when_heads_up():
    snap = TableSnapshot(stacks=[1200, 800], pot=0, total_chips=2000)
    assert snap.effective_stack(0, 1) == 800
