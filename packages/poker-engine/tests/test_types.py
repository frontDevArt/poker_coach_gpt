from poker_engine.types import Position, Street, positions_for


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
