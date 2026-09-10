"""CLI ядра. Единственный канал, через который скиллы получают числа.

Любая ошибка сериализуется в JSON с ключом `error` и кодом возврата 1 —
вызывающая сторона всегда получает разбираемый ответ, а не трейсбек.
"""

from __future__ import annotations

import argparse
import io
import json
import sys

from .bounty import DEFAULT_SPLIT, required_equity_with_bounty
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
                split=args.split,
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
        if args.hands is None:
            raise ValueError("нужен либо --hands, либо --hero вместе с --vs-range")
        return {
            "equities": hand_equity(
                args.hands, board=args.board, trials=args.trials, seed=args.seed
            )
        }

    raise ValueError(f"неизвестная команда: {args.command}")


def _int_list(text: str) -> list[int]:
    return [int(x) for x in text.split(",")]


def _float_list(text: str) -> list[float]:
    return [float(x) for x in text.split(",")]


def _str_list(text: str) -> list[str]:
    tokens = [x.strip() for x in text.split(",")]
    if any(not x for x in tokens):
        raise ValueError(f"пустой элемент в списке: {text!r}")
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
    p_b.add_argument("--split", type=float, default=DEFAULT_SPLIT)

    p_rp = sub.add_parser("risk-premium", help="risk premium и bubble factor")
    p_rp.add_argument("--stacks", type=_int_list, required=True)
    p_rp.add_argument("--payouts", type=_float_list, required=True)
    p_rp.add_argument("--hero", type=int, required=True)
    p_rp.add_argument("--villain", type=int, required=True)

    p_eq = sub.add_parser("equity", help="эквити рук")
    p_eq.add_argument("--hands", type=_str_list, default=None)
    p_eq.add_argument("--hero", type=str, default=None)
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

    return parser


if __name__ == "__main__":
    sys.exit(main())
