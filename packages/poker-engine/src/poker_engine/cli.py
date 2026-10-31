"""CLI ядра. Единственный канал, через который скиллы получают числа.

Любая ошибка сериализуется в JSON с ключом `error` и кодом возврата 1 —
вызывающая сторона всегда получает разбираемый ответ, а не трейсбек.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

from . import coach, lobby
from .advice import advise
from .analyze import analyze
from .bounty import required_equity_with_bounty
from .equity import equity_vs_range, hand_equity
from .icm import bubble_factor, icm_equities, risk_premium
from .potodds import required_equity
from .ranges import parse_range


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdout()
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
        payload = _dispatch(args)
    except (ValueError, IndexError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(payload, ensure_ascii=False))
    return 0


class _JsonErrorArgumentParser(argparse.ArgumentParser):
    """Парсер, чьи собственные ошибки уходят в тот же JSON-путь, что и
    ошибки движка, вместо usage-текста в stderr и кода возврата 2.

    Текст сообщения не переформулируется — он ровно тот, что даёт argparse.
    `add_subparsers` по умолчанию передаёт класс родителя сабпарсерам,
    поэтому ошибки уровня подкоманды тоже попадают сюда. `-h`/`--help`
    завершается через `SystemExit(0)` из другого пути (`exit`, не `error`),
    поэтому не перехватывается и продолжает работать как раньше.
    """

    def error(self, message: str) -> None:  # noqa: D102 - сигнатура argparse
        raise ValueError(message)


def _ensure_utf8_stdout() -> None:
    """Гарантирует, что stdout примет любой Unicode до первого print.

    Сообщения об ошибках движка на русском, а консоль на Windows по
    умолчанию открывает stdout в cp1252 — обычный print на такой
    консоли роняет UnicodeEncodeError ещё до того, как единственный
    путь вернуть вызывающей стороне разбираемую ошибку успевает
    сработать. Переводим stdout в UTF-8 независимо от кодировки
    консоли, чтобы и успешный, и аварийный вывод всегда были валидным
    JSON.
    """
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8")
    else:  # pragma: no cover - запасной путь для нестандартных потоков
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="strict"
        )


def _dispatch(args: argparse.Namespace) -> dict:
    if args.command == "icm":
        return {"equities": icm_equities(args.stacks, args.payouts)}

    if args.command == "potodds":
        return {"required_equity": required_equity(args.pot, args.call)}

    if args.command == "bounty-ev":
        return {
            "required_equity": required_equity_with_bounty(
                pot_before_call=args.pot,
                call_amount=args.call,
                villain_stack=args.villain_stack,
                bounty=args.bounty,
                chip_value=args.chip_value,
            )
        }

    if args.command == "risk-premium":
        return {
            "risk_premium": risk_premium(
                args.stacks, args.payouts, args.hero, args.villain
            ),
            "bubble_factor": bubble_factor(
                args.stacks, args.payouts, args.hero, args.villain
            ),
        }

    if args.command == "equity":
        # Это не валидация значений (та живёт в движке), а выбор формы
        # вызова: какую из двух функций движка звать. Движок выразить это
        # не может — у него для этого две разные сигнатуры.
        if args.vs_range is not None:
            if args.hero is None:
                raise ValueError("для --vs-range нужен --hero")
            if args.hands is not None:
                raise ValueError("--hands и --vs-range взаимоисключающи")
            return {
                "equities": equity_vs_range(
                    args.hero,
                    parse_range(args.vs_range),
                    board=args.board,
                    trials=args.trials,
                    seed=args.seed,
                )
            }
        if args.hero is not None:
            raise ValueError("--hero без --vs-range ничего не делает: добавьте --vs-range")
        if args.hands is None:
            raise ValueError("нужен либо --hands, либо --hero вместе с --vs-range")
        return {
            "equities": hand_equity(
                args.hands, board=args.board, trials=args.trials, seed=args.seed
            )
        }

    if args.command == "analyze":
        payload = _read_json(args.input)
        # Не валидация входа, а разбор конверта файла: `{context, nodes}` —
        # формат аргумента командной строки, а не сигнатура движка, и движку
        # он не виден. Без проверки здесь был бы `KeyError` мимо `main`,
        # который ловит `(ValueError, IndexError)`. Форму самих `context` и
        # `nodes` проверяет уже движок — эти гарды сюда не поднимать.
        if "context" not in payload or "nodes" not in payload:
            raise ValueError("во входном JSON нужны ключи 'context' и 'nodes'")
        return analyze(
            payload["context"], payload["nodes"], trials=args.trials, seed=args.seed
        )

    if args.command == "advise":
        payload = _read_json(args.input)
        # Тот же конверт, что у `analyze`, плюс необязательная `history`: её форму, как и
        # форму `context` и `nodes`, проверяет движок.
        if "context" not in payload or "nodes" not in payload:
            raise ValueError("во входном JSON нужны ключи 'context' и 'nodes'")
        return advise(payload["context"], payload["nodes"], payload.get("history", []))

    if args.command == "coach":
        # Форму контекста и кадра проверяет движок (`coach`, `frames`), здесь — только чтение.
        if args.coach_command == "start":
            late_reg = {None: None, "open": True, "closed": False}[args.late_reg]
            return coach.start(args.hand, _read_json(args.context), late_reg_open=late_reg)
        if args.coach_command == "step":
            return coach.step(args.hand, _read_json(args.frame))
        if args.coach_command == "lint":
            return coach.lint(args.hand, _read_text(args.text))
        return coach.undo(args.hand)

    if args.command == "lobby":
        # Распознавание, разбор, проверки и дата съёмки — в движке (`lobby.read`), здесь — вызов.
        if args.lobby_command == "read":
            return lobby.read(args.frames, args.dir)
        return {"tournaments": lobby.find(args.dir, args.title)}

    raise ValueError(f"неизвестная команда: {args.command}")


def _read_text(source: str) -> str:
    if source != "-":
        return _read_file(source)
    # stdin — в UTF-8, как файл: консоль Windows открывает его в cp1252, и кириллица из пайпа
    # приходила бы мусором (то же, что `_ensure_utf8_stdout` делает для stdout).
    return sys.stdin.buffer.read().decode("utf-8")


def _read_json(source: str) -> dict:
    text = _read_text(source)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"вход не является корректным JSON: {exc}") from exc
    # Корректный JSON — это ещё и `5`, `null`, `true` и список: без этой
    # проверки они уходили бы в движок и всплывали внутренним TypeError
    # вместо разбираемого ответа с ключом `error`.
    if not isinstance(payload, dict):
        raise ValueError(f"во входном JSON ожидается объект, получено {payload!r}")
    return payload


def _read_file(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError as exc:
        raise ValueError(f"не удалось прочитать {path!r}: {exc}") from exc


def _int_list(text: str) -> list[int]:
    return [int(x) for x in text.split(",")]


def _float_list(text: str) -> list[float]:
    return [float(x) for x in text.split(",")]


def _str_list(text: str) -> list[str]:
    tokens = [x.strip() for x in text.split(",")]
    if any(not x for x in tokens):
        # `ArgumentTypeError`, а не `ValueError`: на `ValueError` из `type=`
        # argparse подставляет свой текст «invalid _str_list value», и
        # пользователь не увидел бы, что именно не так.
        raise argparse.ArgumentTypeError(f"пустой элемент в списке: {text!r}")
    return tokens


def _build_parser() -> argparse.ArgumentParser:
    parser = _JsonErrorArgumentParser(prog="poker-engine")
    sub = parser.add_subparsers(dest="command", required=True)

    p_icm = sub.add_parser("icm", help="ICM-эквити по Malmuth-Harville")
    p_icm.add_argument("--stacks", type=_int_list, required=True)
    p_icm.add_argument("--payouts", type=_float_list, required=True)

    p_po = sub.add_parser("potodds", help="порог эквити по пот-оддсам")
    p_po.add_argument("--pot", type=float, required=True)
    p_po.add_argument("--call", type=float, required=True)

    p_b = sub.add_parser("bounty-ev", help="порог эквити с учётом головы PKO")
    p_b.add_argument("--pot", type=float, required=True)
    p_b.add_argument("--call", type=float, required=True)
    p_b.add_argument("--villain-stack", type=float, required=True)
    p_b.add_argument("--bounty", type=float, required=True)
    p_b.add_argument("--chip-value", type=float, required=True)

    p_rp = sub.add_parser("risk-premium", help="risk premium и bubble factor")
    p_rp.add_argument("--stacks", type=_int_list, required=True)
    p_rp.add_argument("--payouts", type=_float_list, required=True)
    p_rp.add_argument("--hero", type=int, required=True)
    p_rp.add_argument("--villain", type=int, required=True)

    p_eq = sub.add_parser("equity", help="эквити рук")
    p_eq.add_argument(
        "--hands",
        type=_str_list,
        default=None,
        help="руки через запятую, например 'AhKh,AdKd'",
    )
    p_eq.add_argument(
        "--hero",
        type=str,
        default=None,
        help="рука героя для --vs-range, например 'JhTh'",
    )
    p_eq.add_argument(
        "--vs-range",
        dest="vs_range",
        type=str,
        default=None,
        help=(
            "диапазон соперника для --hero: 'AA' (пара), 'AKs'/'AKo' "
            "(одномастная/разномастная), 'AK' (обе), 'AsKh' (конкретная "
            "комбинация). '+' раздвигает диапазон вверх: у пары растёт "
            "ранг ('TT+' = TT..AA), у двух рангов поднимается МЛАДШАЯ "
            "карта при фиксированной старшей ('ATs+' = ATs..AKs) — это "
            "не то же самое, что цепочка коннекторов ('76s+' = 76s..AKs) "
            "из Equilab/Flopzilla; к конкретной комбинации '+' неприменим"
        ),
    )
    p_eq.add_argument("--board", type=_str_list, default=[])
    p_eq.add_argument("--trials", type=int, default=10_000)
    p_eq.add_argument("--seed", type=int, default=None)

    p_an = sub.add_parser("analyze", help="разбор состояния, снятого со скриншота")
    p_an.add_argument("--input", required=True, help="файл с JSON или '-' для stdin")
    p_an.add_argument("--trials", type=int, default=10_000)
    p_an.add_argument("--seed", type=int, default=None)

    p_ad = sub.add_parser("advise", help="совет на последнем узле раздачи (push/fold)")
    p_ad.add_argument("--input", required=True, help="файл с JSON или '-' для stdin")

    p_co = sub.add_parser("coach", help="пошаговый разбор раздачи в файле раздачи")
    co_sub = p_co.add_subparsers(dest="coach_command", required=True)
    p_start = co_sub.add_parser("start", help="новый файл раздачи с контекстом")
    p_start.add_argument("--hand", required=True, help="файл раздачи")
    p_start.add_argument("--context", required=True, help="файл с JSON или '-' для stdin")
    p_start.add_argument(
        "--late-reg",
        choices=("open", "closed"),
        default=None,
        help="была ли открыта поздняя регистрация (перекрывает lateRegOpen контекста)",
    )
    p_step = co_sub.add_parser("step", help="кадр в конец раздачи и совет на нём")
    p_step.add_argument("--hand", required=True, help="файл раздачи")
    p_step.add_argument("--frame", required=True, help="файл с JSON или '-' для stdin")
    p_undo = co_sub.add_parser("undo", help="снять последний кадр и его шаг")
    p_undo.add_argument("--hand", required=True, help="файл раздачи")
    p_lint = co_sub.add_parser("lint", help="числа текста ответа без следа в фактах шагов")
    p_lint.add_argument("--hand", required=True, help="файл раздачи")
    p_lint.add_argument("--text", required=True, help="файл с текстом ответа или '-' для stdin")

    p_lo = sub.add_parser("lobby", help="файл турнира из скриншотов лобби")
    lo_sub = p_lo.add_subparsers(dest="lobby_command", required=True)
    tournaments = str(Path.home() / "Documents" / "poker-coach" / "tournaments")
    p_read = lo_sub.add_parser("read", help="заход: кадры лобби → файл турнира")
    p_read.add_argument("frames", nargs="+", help="скриншоты лобби (PNG), порядок не важен")
    p_read.add_argument("--dir", default=tournaments, help="папка турниров")
    p_find = lo_sub.add_parser("find", help="файлы турниров с этим названием")
    p_find.add_argument("--title", required=True, help="название турнира из заголовка стола")
    p_find.add_argument("--dir", default=tournaments, help="папка турниров")

    return parser


if __name__ == "__main__":
    sys.exit(main())
