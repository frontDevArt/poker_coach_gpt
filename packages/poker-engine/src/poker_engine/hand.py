"""Состояние раздачи для советников (спека тренера §7.1).

`Hand` — контекст турнира и узлы решения героя по порядку, уже разобранные и проверенные
`validate_hand`, плюс итоги закрытых улиц. Итог улицы считает её советник (реестр
`advice.STREET_CLOSERS`): это его диапазоны, и советник следующей улицы читает их отсюда, а не
пересчитывает. Итог считается лениво, при первом вопросе, и кешируется: узлы `Hand` не меняются.
"""

from __future__ import annotations

from .handstate import STREETS, DecisionNode, TournamentContext


class Hand:
    """Раздача: `context`, `nodes` и итоги закрытых улиц."""

    def __init__(self, context: TournamentContext, nodes: list[DecisionNode]) -> None:
        self.context = context
        self.nodes = list(nodes)
        self._summaries: dict[str, dict | None] = {}

    def street_summary(self, street: str) -> dict | None:
        """Итог улицы `street` или `None`: улица не закрыта либо её итог никто не считает.

        Улица закрыта, когда в раздаче есть кадр следующей за ней улицы.
        """
        if street not in self._summaries:
            # Реестр — в `advice`, а он импортирует советников, которые импортируют `Hand`.
            from .advice import STREET_CLOSERS

            closer = STREET_CLOSERS.get(street)
            self._summaries[street] = (
                closer(self) if closer is not None and self._closed(street) else None
            )
        return self._summaries[street]

    def _closed(self, street: str) -> bool:
        return street in STREETS and any(
            STREETS.index(node.street) > STREETS.index(street) for node in self.nodes
        )
