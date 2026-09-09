import json
import subprocess
import sys
from pathlib import Path

import pytest

from poker_engine.cli import main


def run(argv, capsys):
    code = main(argv)
    out = capsys.readouterr().out
    return code, json.loads(out)


def test_icm_command(capsys):
    code, data = run(
        ["icm", "--stacks", "75,25", "--payouts", "70,30"], capsys
    )
    assert code == 0
    assert data["equities"] == pytest.approx([60.0, 40.0])


def test_potodds_command(capsys):
    code, data = run(["potodds", "--pot", "100", "--call", "50"], capsys)
    assert code == 0
    assert data["required_equity"] == pytest.approx(1 / 3)


def test_bounty_command(capsys):
    code, data = run(
        [
            "bounty-ev",
            "--pot", "100",
            "--call", "50",
            "--villain-stack", "50",
            "--bounty", "2.50",
            "--chip-value", "0.025",
        ],
        capsys,
    )
    assert code == 0
    assert data["required_equity"] == pytest.approx(0.25)


def test_riskpremium_command(capsys):
    code, data = run(
        [
            "risk-premium",
            "--stacks", "50,30,20",
            "--payouts", "100,0,0",
            "--hero", "0",
            "--villain", "1",
        ],
        capsys,
    )
    assert code == 0
    assert data["risk_premium"] == pytest.approx(0.0, abs=1e-9)
    assert data["bubble_factor"] == pytest.approx(1.0)


def test_equity_command(capsys):
    # Цель — проверить, что подкоманда equity парсит флаги (включая --board)
    # и сериализует JSON, а не переоткрывать математику эквити. Четыре карты
    # борда оставляют одну карту недостающей, поэтому hand_equity перебирает
    # все 44 ривера точно (trials игнорируется). Борд состоит только из треф
    # и пик, поэтому замена мастей h<->d — биекция оставшейся колоды, которая
    # оставляет борд на месте и переводит AhKh в AdKd и обратно: каждому
    # исходу ривера для первой руки соответствует зеркальный исход для
    # второй, и сплит ровно 50/50.
    code, data = run(
        [
            "equity", "--hands", "AhKh,AdKd", "--board", "2c,7s,9c,Ts",
            "--trials", "1", "--seed", "1",
        ],
        capsys,
    )
    assert code == 0
    assert data["equities"] == pytest.approx([0.5, 0.5], abs=1e-9)


def test_invalid_input_returns_error_json(capsys):
    code = main(["icm", "--stacks", "50", "--payouts", "100"])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert code == 1
    assert "error" in data


def test_malformed_list_flag_returns_error_json(capsys):
    code = main(["icm", "--stacks", "abc", "--payouts", "70,30"])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert code == 1
    assert "error" in data


def test_missing_required_flag_returns_error_json(capsys):
    code = main(["icm", "--stacks", "75,25"])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert code == 1
    assert "error" in data


def test_unknown_subcommand_returns_error_json(capsys):
    code = main(["not-a-command"])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert code == 1
    assert "error" in data


def test_malformed_scalar_flag_returns_error_json(capsys):
    code = main(["equity", "--hands", "AhKh,AdKd", "--trials", "x"])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert code == 1
    assert "error" in data


def test_empty_payouts_string_returns_error_json(capsys):
    # "" когда-то парсился в пустой список выплат вместо отказа, и icm
    # молча возвращал равные нулю эквити с кодом возврата 0.
    code = main(["icm", "--stacks", "75,25", "--payouts", ""])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert code == 1
    assert "error" in data


def test_embedded_empty_token_in_list_returns_error_json(capsys):
    # "50,,30,20" когда-то тихо схлопывался в 3 стека вместо 4, из-за чего
    # --hero 2/--villain 1 адресовали не тех игроков, которых имел в виду
    # пользователь, и команда возвращала правдоподобный, но неверный
    # результат с кодом возврата 0.
    code = main(
        [
            "risk-premium",
            "--stacks", "50,,30,20",
            "--payouts", "50,30,20",
            "--hero", "2",
            "--villain", "1",
        ]
    )
    out = capsys.readouterr().out
    data = json.loads(out)
    assert code == 1
    assert "error" in data


def test_help_still_exits_zero_with_usage_text(capsys):
    # -h/--help должен продолжать работать как раньше: argparse завершает
    # процесс через SystemExit(0) отдельным путём (exit, не error), и это
    # исключение не перехватывается нашим JSON-обработчиком ошибок.
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "usage" in out.lower()
    with pytest.raises(json.JSONDecodeError):
        json.loads(out)


def test_error_json_is_valid_utf8_on_subprocess_console():
    # capsys нельзя использовать здесь: баг воспроизводится только через
    # реальную консоль Windows (cp1252), а не через перехват stdout в
    # том же процессе pytest. Русские сообщения об ошибках из движка
    # должны безопасно сериализоваться в JSON независимо от кодировки
    # консоли вызывающей стороны.
    exe = Path(sys.executable).with_name("poker-engine.exe")
    result = subprocess.run(
        [str(exe), "icm", "--stacks", "50", "--payouts", "100"],
        capture_output=True,
    )
    assert result.returncode == 1
    data = json.loads(result.stdout.decode("utf-8"))
    assert "error" in data
