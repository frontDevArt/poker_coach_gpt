import json
import subprocess
import sys
from pathlib import Path

import pytest

from poker_engine.analyze import analyze
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


def test_riskpremium_command_hero_villain_are_not_interchangeable(capsys):
    # В отличие от test_riskpremium_command выше, выплаты здесь НЕ
    # winner-take-all (50/30/20, а не 100/0/0) — при плоской (WTA) лесенке
    # risk premium/bubble factor у героя и виллана совпадают почти всегда,
    # и подстановка --hero/--villain не в тот аргумент CLI ничего не меняет
    # в результате. При лесенке 50/30/20 стек 30 значит для риска не то же
    # самое, что стек 20 (у второго меньше падать при проигрыше и меньше
    # получать при выигрыше относительно поля), поэтому если cli.py перепутает
    # местами --hero и --villain при вызове risk_premium/bubble_factor,
    # числа изменятся — это ловит именно порядок аргументов, а не их наличие.
    code, data = run(
        [
            "risk-premium",
            "--stacks", "50,30,20",
            "--payouts", "50,30,20",
            "--hero", "0",
            "--villain", "1",
        ],
        capsys,
    )
    assert code == 0
    assert data["risk_premium"] == pytest.approx(0.03896103896103875)
    assert data["bubble_factor"] == pytest.approx(1.1690140845070411)


def test_equity_command_board_changes_result(capsys):
    # Борд здесь оставляет ровно одну карту недостающей до ривера, поэтому
    # hand_equity перебирает все 44 исхода точно (--trials игнорируется) —
    # результат детерминирован и не зависит от seed. Если cli.py забудет
    # передать args.board и подставит [], hand_equity вместо точного перебора
    # уйдёт в Monte-Carlo с --trials 1 по неполной раздаче: величина совпадёт
    # с borded-результатом только случайно, поэтому число здесь доказывает,
    # что --board действительно дошёл до движка.
    code, data = run(
        [
            "equity", "--hands", "AhAd,KhKd", "--board", "2c,7s,9c,Ts",
            "--trials", "1", "--seed", "1",
        ],
        capsys,
    )
    assert code == 0
    assert data["equities"] == pytest.approx(
        [0.9545454545454546, 0.045454545454545456]
    )


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


def test_equity_accepts_a_range(capsys):
    # Борд 8c,2s,9d,4c,Tc отдаёт герою JhTh ровно 15/16 против диапазона
    # AK (см. вывод в tests/test_equity_vs_range.py) — сквозная проверка
    # парсер -> parse_range -> equity_vs_range -> JSON на настоящем числе,
    # а не просто на форме ответа.
    code, data = run(
        [
            "equity",
            "--hero", "JhTh",
            "--vs-range", "AK",
            "--board", "8c,2s,9d,4c,Tc",
        ],
        capsys,
    )
    assert code == 0
    assert len(data["equities"]) == 2
    assert data["equities"][0] == pytest.approx(15 / 16)


def test_equity_without_hands_or_range_is_a_json_error(capsys):
    code, data = run(["equity", "--board", "8c,2s,9d"], capsys)
    assert code == 1
    assert "error" in data


def test_equity_rejects_hands_and_range_together(capsys):
    code, data = run(
        ["equity", "--hands", "JhTh,AsKd", "--hero", "JhTh", "--vs-range", "AA"],
        capsys,
    )
    assert code == 1
    assert "error" in data


def test_hero_without_vs_range_is_a_json_error(capsys):
    # Зеркало теста ниже: --hero без --vs-range молча ушёл бы в hand_equity
    # и упал бы там сообщением про --hands, которого пользователь не писал.
    code, data = run(["equity", "--hero", "JhTh"], capsys)
    assert code == 1
    assert "--hero без --vs-range" in data["error"]


def test_vs_range_without_hero_is_a_json_error(capsys):
    code, data = run(["equity", "--vs-range", "AA"], capsys)
    assert code == 1
    assert "error" in data


def test_error_json_is_valid_utf8_on_subprocess_console():
    # capsys нельзя использовать здесь: баг воспроизводится только через
    # реальную консоль Windows (cp1252), а не через перехват stdout в
    # том же процессе pytest. Русские сообщения об ошибках из движка
    # должны безопасно сериализоваться в JSON независимо от кодировки
    # консоли вызывающей стороны.
    # Консольный скрипт лежит рядом с интерпретатором venv: на Windows —
    # `poker-engine.exe`, на Linux и macOS — `poker-engine` без суффикса.
    script = "poker-engine.exe" if sys.platform == "win32" else "poker-engine"
    exe = Path(sys.executable).with_name(script)
    result = subprocess.run(
        [str(exe), "icm", "--stacks", "50", "--payouts", "100"],
        capture_output=True,
    )
    assert result.returncode == 1
    data = json.loads(result.stdout.decode("utf-8"))
    assert "error" in data


def test_analyze_reads_a_file(tmp_path, capsys, analyze_context, analyze_node):
    # Финальный стол вместо плановых 496 живых: тест про чтение файла и
    # форму ответа, а свёртка поля стоит ему десять лишних секунд.
    analyze_node.update(playersLeft=8, heroRank=8)
    path = tmp_path / "hand.json"
    path.write_text(
        json.dumps({"context": analyze_context, "nodes": [analyze_node]}),
        encoding="utf-8",
    )
    code, data = run(
        ["analyze", "--input", str(path), "--trials", "500", "--seed", "3"], capsys
    )
    assert code == 0
    assert data["street"] == "preflop"
    assert "flags" in data


def test_analyze_on_broken_json_is_a_json_error(tmp_path, capsys):
    path = tmp_path / "hand.json"
    path.write_text("{не json", encoding="utf-8")
    code, data = run(["analyze", "--input", str(path)], capsys)
    assert code == 1
    assert "вход не является корректным JSON" in data["error"]


def test_analyze_on_missing_file_is_a_json_error(capsys):
    code, data = run(["analyze", "--input", "нет-такого.json"], capsys)
    assert code == 1
    assert "не удалось прочитать" in data["error"]


def test_analyze_without_the_required_keys_is_a_json_error(tmp_path, capsys):
    path = tmp_path / "hand.json"
    path.write_text(json.dumps({"nodes": []}), encoding="utf-8")
    code, data = run(["analyze", "--input", str(path)], capsys)
    assert code == 1
    assert "нужны ключи 'context' и 'nodes'" in data["error"]


def test_analyze_on_a_null_inside_seats_is_a_json_error(
    tmp_path, capsys, analyze_context, analyze_node
):
    # Форма самого конверта цела, испорчен элемент вложенного списка — то,
    # что vision-модель отдаёт не реже, чем сломанный верхний уровень.
    # Контракт `cli` («любая ошибка сериализуется в JSON с ключом error»)
    # держится только если движок бросает ValueError: TypeError пролетает
    # мимо `main`, который ловит `(ValueError, IndexError)`.
    analyze_node["seats"] = [None] + analyze_node["seats"][1:]
    path = tmp_path / "hand.json"
    path.write_text(
        json.dumps({"context": analyze_context, "nodes": [analyze_node]}),
        encoding="utf-8",
    )
    code, data = run(["analyze", "--input", str(path)], capsys)
    assert code == 1
    assert "ожидался объект с полем 'seatIndex'" in data["error"]


def test_analyze_on_a_json_scalar_is_a_json_error(tmp_path, capsys):
    # `5` — корректный JSON, но не объект: без проверки формы он уходил бы
    # в движок и всплывал внутренним TypeError мимо ключа `error`.
    path = tmp_path / "hand.json"
    path.write_text("5", encoding="utf-8")
    code, data = run(["analyze", "--input", str(path)], capsys)
    assert code == 1
    assert "во входном JSON ожидается объект" in data["error"]


def test_analyze_on_an_all_in_opponent_is_a_json_error(
    tmp_path, capsys, analyze_context, analyze_node
):
    # Известное ограничение модели (см. докстринг `analyze`): соперник с
    # нулевым стеком отвергается. Наружу это обязано выходить разбираемым
    # ответом с кодом 1, а не трейсбеком.
    analyze_node["seats"][4]["stackBb"] = 0.0
    path = tmp_path / "hand.json"
    path.write_text(
        json.dumps({"context": analyze_context, "nodes": [analyze_node]}),
        encoding="utf-8",
    )
    code, data = run(["analyze", "--input", str(path)], capsys)
    assert code == 1
    assert "стек на месте 4 должен быть > 0" in data["error"]


def test_analyze_passes_trials_and_seed_to_the_engine(
    tmp_path, capsys, analyze_context, analyze_node
):
    # Оба параметра меняют результат Monte-Carlo, поэтому совпадение с
    # прямым вызовом движка на тех же значениях — единственная проверка
    # того, что CLI их действительно передаёт, а не роняет в умолчания.
    # Разбор здесь считается дважды, поэтому узел — финальный стол: ICM к
    # пробросу `--trials` и `--seed` отношения не имеет.
    analyze_node.update(playersLeft=8, heroRank=8)
    path = tmp_path / "hand.json"
    path.write_text(
        json.dumps({"context": analyze_context, "nodes": [analyze_node]}),
        encoding="utf-8",
    )
    code, data = run(
        ["analyze", "--input", str(path), "--trials", "400", "--seed", "5"], capsys
    )
    direct = analyze(analyze_context, [analyze_node], trials=400, seed=5)
    assert code == 0
    assert data["equity"]["hero"] == direct["equity"]["hero"]
