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
    code, data = run(
        ["equity", "--hands", "AhKh,AdKd", "--trials", "2000", "--seed", "1"], capsys
    )
    assert code == 0
    assert data["equities"][0] == pytest.approx(data["equities"][1], abs=1e-9)


def test_invalid_input_returns_error_json(capsys):
    code = main(["icm", "--stacks", "50", "--payouts", "100"])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert code == 1
    assert "error" in data


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
