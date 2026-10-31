import json
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import _context, console_stdin, pushfold_first_in_node
from poker_engine.advice import advise, why
from poker_engine.analyze import analyze
from poker_engine.cli import _build_parser, main
from poker_engine.handstate import node_from_dict


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
    # Ценник 2.50 — наличные целиком: 100 фишек, порог 50 / (100 + 100 + 50).
    assert data["required_equity"] == pytest.approx(0.2)


def test_bounty_command_no_longer_takes_a_split(capsys):
    # Ломающее изменение контракта, сделанное намеренно (план 3, Задача 5):
    # доля не настраивается, она следует из того, что показано на экране.
    code, data = run(
        [
            "bounty-ev",
            "--pot", "100",
            "--call", "50",
            "--villain-stack", "50",
            "--bounty", "2.50",
            "--chip-value", "0.025",
            "--split", "0.5",
        ],
        capsys,
    )
    assert code == 1
    assert data == {"error": "unrecognized arguments: --split 0.5"}


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


def test_an_empty_item_in_a_card_list_is_named_in_the_error(capsys):
    # Без гарда пустой токен дошёл бы до движка как рука '' и отказ пришёл
    # бы оттуда, с текстом про число карт.
    code, data = run(["equity", "--hands", "AhKh,,AdKd"], capsys)
    assert code == 1
    assert data == {"error": "argument --hands: пустой элемент в списке: 'AhKh,,AdKd'"}


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
    # форму ответа, а не про поле.
    analyze_node.update(playersLeft=6, heroRank=6)
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
    analyze_node["seats"][2]["stackBb"] = 0.0  # соперник, место 4
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
    analyze_node.update(playersLeft=6, heroRank=6)
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


def _stdin(monkeypatch, payload):
    monkeypatch.setattr(sys, "stdin", console_stdin(json.dumps(payload, ensure_ascii=False)))


def test_advise_reads_stdin(monkeypatch, capsys):
    envelope = {"context": _context(), "nodes": [pushfold_first_in_node()], "history": []}
    _stdin(monkeypatch, envelope)
    code, data = run(["advise", "--input", "-"], capsys)
    assert code == 0
    assert data["advisor"] == "pushfold"
    assert data["action"] in {"allin", "fold"}
    assert data == advise(_context(), [pushfold_first_in_node()], [])


def test_advise_history_is_optional(monkeypatch, capsys):
    _stdin(monkeypatch, {"context": _context(), "nodes": [pushfold_first_in_node()]})
    code, data = run(["advise", "--input", "-"], capsys)
    assert code == 0
    assert data == advise(_context(), [pushfold_first_in_node()], [])


def test_advise_passes_the_history_to_the_engine(monkeypatch, capsys):
    # Форма `history` проверяется движком: CLI её не глотает и не подменяет на [].
    envelope = {"context": _context(), "nodes": [pushfold_first_in_node()], "history": [7]}
    _stdin(monkeypatch, envelope)
    code, data = run(["advise", "--input", "-"], capsys)
    assert code == 1
    assert data["error"] == "ответ 0 в истории должен быть объектом, получено 7"


@pytest.mark.parametrize("missing", ["context", "nodes"])
def test_advise_without_the_required_keys_is_a_json_error(missing, monkeypatch, capsys):
    # Каждый ключ — отдельно: без проверки `context` конверт `{"nodes": …}` ушёл бы в
    # `KeyError` мимо `main`, который ловит только `ValueError` и `IndexError`.
    envelope = {"context": _context(), "nodes": [pushfold_first_in_node()]}
    del envelope[missing]
    _stdin(monkeypatch, envelope)
    code, data = run(["advise", "--input", "-"], capsys)
    assert code == 1
    assert data["error"] == "во входном JSON нужны ключи 'context' и 'nodes'"


def test_advise_reads_a_file(tmp_path, capsys):
    path = tmp_path / "hand.json"
    path.write_text(
        json.dumps({"context": _context(), "nodes": [pushfold_first_in_node()]}),
        encoding="utf-8",
    )
    code, data = run(["advise", "--input", str(path)], capsys)
    assert code == 0
    assert data["spot"] == "first_in"


# --- coach (план 6, Задача 6) ----------------------------------------------------------------


def _write(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def test_coach_start_step_undo(tmp_path, capsys):
    hand = str(tmp_path / "hand.json")
    context = _write(tmp_path / "context.json", _context())
    frame = _write(tmp_path / "frame.json", pushfold_first_in_node())

    code, data = run(["coach", "start", "--hand", hand, "--context", context], capsys)
    assert (code, data) == (0, {"hand": hand, "steps": 0})

    code, data = run(["coach", "step", "--hand", hand, "--frame", frame], capsys)
    answer = advise(_context(), [pushfold_first_in_node()], [])
    assert code == 0
    facts = why(answer, node_from_dict(pushfold_first_in_node()))
    assert data == {
        "step": 1, "advisor": "pushfold", "answer": answer, "why": facts, "streets": {}
    }

    code, data = run(["coach", "undo", "--hand", hand], capsys)
    assert (code, data) == (0, {"undone": 1, "steps": 0})


@pytest.mark.parametrize(
    "extra, expected", [([], None), (["--late-reg", "open"], True), (["--late-reg", "closed"], False)]
)
def test_coach_start_late_reg_flag(tmp_path, capsys, monkeypatch, extra, expected):
    seen = {}

    def fake_start(path, context, late_reg_open=None):
        seen["late_reg_open"] = late_reg_open
        return {"hand": path, "steps": 0}

    monkeypatch.setattr("poker_engine.cli.coach.start", fake_start)
    context = _write(tmp_path / "context.json", _context())
    hand = str(tmp_path / "hand.json")
    code, _ = run(["coach", "start", "--hand", hand, "--context", context, *extra], capsys)
    assert code == 0 and seen["late_reg_open"] is expected


def test_coach_start_late_reg_rejects_other_values(tmp_path, capsys):
    hand = tmp_path / "hand.json"
    context = _write(tmp_path / "context.json", _context())
    code, data = run(
        ["coach", "start", "--hand", str(hand), "--context", context, "--late-reg", "maybe"], capsys
    )
    assert code == 1 and "--late-reg" in data["error"] and "maybe" in data["error"]
    assert not hand.exists()


def test_coach_start_late_reg_open_is_written(tmp_path, capsys):
    hand = tmp_path / "hand.json"
    context = _write(tmp_path / "context.json", {**_context(), "lateRegOpen": False})
    code, _ = run(["coach", "start", "--hand", str(hand), "--context", context,
                   "--late-reg", "open"], capsys)
    assert code == 0
    assert json.loads(hand.read_text(encoding="utf-8"))["context"]["lateRegOpen"] is True


def test_coach_step_reads_the_frame_from_stdin(tmp_path, monkeypatch, capsys):
    hand = str(tmp_path / "hand.json")
    _stdin(monkeypatch, _context())
    assert run(["coach", "start", "--hand", hand, "--context", "-"], capsys)[0] == 0
    _stdin(monkeypatch, pushfold_first_in_node())
    code, data = run(["coach", "step", "--hand", hand, "--frame", "-"], capsys)
    assert code == 0
    assert data["answer"] == advise(_context(), [pushfold_first_in_node()], [])


def test_coach_step_reads_a_cyrillic_frame_from_stdin(tmp_path, monkeypatch, capsys):
    # Ник кириллицей через пайп консоли Windows: кадр в файле раздачи — как пришёл.
    hand = tmp_path / "hand.json"
    _stdin(monkeypatch, _context())
    assert run(["coach", "start", "--hand", str(hand), "--context", "-"], capsys)[0] == 0
    frame = pushfold_first_in_node()
    frame["seats"][0]["name"] = "Игрок"
    _stdin(monkeypatch, frame)
    code, _ = run(["coach", "step", "--hand", str(hand), "--frame", "-"], capsys)
    assert code == 0
    assert json.loads(hand.read_text(encoding="utf-8"))["frames"] == [frame]


def test_coach_errors_are_json_with_code_1(tmp_path, capsys):
    hand = str(tmp_path / "hand.json")
    code, data = run(["coach", "undo", "--hand", hand], capsys)
    assert (code, data) == (1, {"error": f"файла раздачи нет: {hand}"})
    context = _write(tmp_path / "context.json", _context())
    run(["coach", "start", "--hand", hand, "--context", context], capsys)
    code, data = run(["coach", "start", "--hand", hand, "--context", context], capsys)
    assert (code, data) == (1, {"error": f"файл раздачи уже есть: {hand}"})
    frame = _write(tmp_path / "frame.json", {**pushfold_first_in_node(), "potChips": 3150})
    code, data = run(["coach", "step", "--hand", hand, "--frame", frame], capsys)
    assert (code, data) == (1, {"error": "поле potChips не для кадра в bb"})


def test_coach_needs_a_subcommand(capsys):
    code, data = run(["coach"], capsys)
    assert code == 1
    assert "coach_command" in data["error"] or "required" in data["error"]


# --- lobby (план D40, Задача 5) --------------------------------------------------------------


def test_lobby_read_without_the_lobby_dependencies_is_a_json_error(tmp_path, monkeypatch, capsys):
    import poker_engine.lobby_ocr as lobby_ocr

    monkeypatch.setitem(sys.modules, "rapidocr_onnxruntime", None)
    monkeypatch.setitem(sys.modules, "PIL", None)
    monkeypatch.setattr(lobby_ocr, "_engine", None)
    frame = tmp_path / "pass2-prizes-level17.png"
    frame.write_bytes(b"")
    code, data = run(["lobby", "read", str(frame), "--dir", str(tmp_path / "t")], capsys)
    assert code == 1
    prefix = 'для разбора лобби нужны зависимости: pip install -e ".[lobby]"'
    assert data["error"].startswith(prefix)
    assert not (tmp_path / "t").exists()


def test_lobby_read_passes_the_frames_and_the_folder(tmp_path, monkeypatch, capsys):
    seen = {}

    def fake_read(paths, directory):
        seen.update(paths=paths, directory=directory)
        return {"tournament": "t.json", "payoutsFinal": True, "warnings": []}

    monkeypatch.setattr("poker_engine.cli.lobby.read", fake_read)
    code, data = run(["lobby", "read", "a.png", "b.png", "--dir", str(tmp_path)], capsys)
    assert (code, data) == (0, {"tournament": "t.json", "payoutsFinal": True, "warnings": []})
    assert seen == {"paths": ["a.png", "b.png"], "directory": str(tmp_path)}


def test_lobby_read_needs_a_frame(capsys):
    code, data = run(["lobby", "read"], capsys)
    assert code == 1 and "frames" in data["error"]


def test_lobby_read_error_is_json_with_code_1(tmp_path, capsys):
    missing = str(tmp_path / "нет-кадра.png")
    code, data = run(["lobby", "read", missing, "--dir", str(tmp_path / "t")], capsys)
    assert code == 1 and data["error"].startswith(f"не удалось прочитать {missing!r}: ")


def _tournament(path, title, start):
    path.write_text(
        json.dumps(
            {"format": "poker-coach-tournament", "title": title, "start": start,
             "payoutsFinal": False}
        ),
        encoding="utf-8",
    )


def test_lobby_find_lists_files_of_one_title_by_start(tmp_path, capsys):
    # имена файлов против порядка дат: сортировка — по `start`, а не по имени
    _tournament(tmp_path / "a.json", "Fifty Stack $5.50", "2026-10-31T23:05")
    _tournament(tmp_path / "b.json", "Fifty Stack $5.50", "2026-10-30T23:05")
    _tournament(tmp_path / "c.json", "Bounty Hunters $5.50", "2026-10-29T20:00")
    code, data = run(
        ["lobby", "find", "--title", "Fifty Stack $5.50", "--dir", str(tmp_path)], capsys
    )
    assert code == 0
    assert data == {
        "tournaments": [
            {"path": str(tmp_path / "b.json"), "start": "2026-10-30T23:05", "payoutsFinal": False},
            {"path": str(tmp_path / "a.json"), "start": "2026-10-31T23:05", "payoutsFinal": False},
        ]
    }


def test_lobby_find_needs_a_title(capsys):
    code, data = run(["lobby", "find"], capsys)
    assert code == 1 and "--title" in data["error"]


@pytest.mark.parametrize("argv", [["read", "a.png"], ["find", "--title", "T"]])
def test_lobby_default_folder(argv):
    # значение парсера, без записи в настоящую папку пользователя
    args = _build_parser().parse_args(["lobby", *argv])
    assert args.dir == str(Path.home() / "Documents" / "poker-coach" / "tournaments")


def test_lobby_needs_a_subcommand(capsys):
    code, data = run(["lobby"], capsys)
    assert code == 1
    assert "lobby_command" in data["error"] or "required" in data["error"]
