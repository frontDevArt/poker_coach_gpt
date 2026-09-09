"""ICM по Malmuth-Harville плюс производные метрики риска.

Известное ограничение модели: M-H систематически завышает вероятность
второго места для крупного стека. На баббле результат стоит сверять с
Monte-Carlo ICM (план 5). Здесь это не исправляется, а документируется.

Сложность: `walk` перебирает упорядоченные префиксы игроков до глубины
`depth` (число значимых выплат) — это порядка n! / (n − depth)! вызовов,
т.е. падающий факториал, а не 2^n. Мемоизация `place_probs` ускоряет
вычисление отдельной вероятности, но не схлопывает перебор порядков
внутри `walk`. Для типичной турнирной лесенки (3–6 оплачиваемых мест)
это быстро даже на 9-max; но полностью оплаченное поле или стол из
10+ игроков с глубокой лесенкой считается заметно дольше — от секунд
до минуты.
"""

from __future__ import annotations

from functools import lru_cache


def icm_equities(stacks: list[int], payouts: list[float]) -> list[float]:
    """Денежное эквити каждого игрока по модели Malmuth-Harville.

    stacks — фишки игроков в текущем порядке.
    payouts — призовые по местам, от первого. Короче списка игроков — добьётся нулями.
    """
    _validate(stacks, payouts)
    n = len(stacks)
    padded = list(payouts) + [0.0] * (n - len(payouts))
    depth = _significant_depth(padded)

    total = float(sum(stacks))
    frozen = tuple(float(s) for s in stacks)

    @lru_cache(maxsize=None)
    def place_probs(taken: frozenset[int], player: int) -> float:
        """Вероятность, что `player` займёт следующее место среди оставшихся."""
        remaining = total - sum(frozen[i] for i in taken)
        if remaining <= 0:
            return 0.0
        return frozen[player] / remaining

    equities = [0.0] * n

    def walk(taken: frozenset[int], prob: float, place: int) -> None:
        if place >= depth or prob == 0.0:
            return
        for player in range(n):
            if player in taken:
                continue
            p = prob * place_probs(taken, player)
            if p == 0.0:
                continue
            equities[player] += p * padded[place]
            walk(taken | {player}, p, place + 1)

    walk(frozenset(), 1.0, 0)

    # Места глубже depth оплачиваются нулём, но остаточная вероятность
    # обязана быть учтена в сумме — при нулевой выплате вклад нулевой.
    return equities


def bubble_factor(
    stacks: list[int], payouts: list[float], hero: int, villain: int
) -> float:
    """Во сколько раз проигрыш дороже выигрыша в деньгах против фишек.

    1.0 — денежная лесенка не давит (winner-take-all).
    Больше 1.0 — герой рискует деньгами сильнее, чем фишками.
    """
    now, win, lose = _icm_branches(stacks, payouts, hero, villain)
    money_down = now - lose
    money_up = win - now
    if money_up <= 0:
        raise ValueError("выигрыш не увеличивает ICM-эквити, bubble factor не определён")

    chips_now = float(stacks[hero])
    chips_win = float(stacks[hero] + min(stacks[hero], stacks[villain]))
    chips_lose = float(stacks[hero] - min(stacks[hero], stacks[villain]))
    chip_down = chips_now - chips_lose
    chip_up = chips_win - chips_now

    return (money_down / money_up) / (chip_down / chip_up)


def risk_premium(
    stacks: list[int], payouts: list[float], hero: int, villain: int
) -> float:
    """Насколько выше должно быть эквити героя из-за ICM.

    Разница между порогом безубыточности в деньгах и в фишках.
    Ноль при winner-take-all, положительно при лесенке выплат.
    """
    now, win, lose = _icm_branches(stacks, payouts, hero, villain)
    if win == lose:
        raise ValueError(
            "исход олл-ина не меняет ICM-эквити героя, risk premium не определён"
        )
    money_threshold = (now - lose) / (win - lose)

    chips_win = float(stacks[hero] + min(stacks[hero], stacks[villain]))
    chips_lose = float(stacks[hero] - min(stacks[hero], stacks[villain]))
    chip_threshold = (float(stacks[hero]) - chips_lose) / (chips_win - chips_lose)

    return money_threshold - chip_threshold


def _icm_branches(
    stacks: list[int], payouts: list[float], hero: int, villain: int
) -> tuple[float, float, float]:
    """ICM-эквити героя сейчас, после выигрыша и после проигрыша олл-ина."""
    n = len(stacks)
    if not (0 <= hero < n):
        raise ValueError(f"hero={hero} вне диапазона игроков [0, {n - 1}]")
    if not (0 <= villain < n):
        raise ValueError(f"villain={villain} вне диапазона игроков [0, {n - 1}]")
    if hero == villain:
        raise ValueError("hero и villain должны различаться")
    at_risk = min(stacks[hero], stacks[villain])
    if at_risk <= 0:
        raise ValueError("эффективный стек равен нулю")

    now = icm_equities(stacks, payouts)[hero]

    won = list(stacks)
    won[hero] += at_risk
    won[villain] -= at_risk
    win = _equity_with_busts(won, payouts, hero)

    lost = list(stacks)
    lost[hero] -= at_risk
    lost[villain] += at_risk
    lose = _equity_with_busts(lost, payouts, hero)

    return now, win, lose


def _equity_with_busts(stacks: list[int], payouts: list[float], hero: int) -> float:
    """ICM-эквити героя после раздачи, где кто-то мог вылететь.

    Вылетевшие получают выплату за своё место и убираются из расчёта.
    Для двухстороннего олл-ина вылететь может только один из двоих,
    поэтому достаточно отбросить нулевые стеки и сдвинуть выплаты.
    """
    survivors = [(i, s) for i, s in enumerate(stacks) if s > 0]
    busted = len(stacks) - len(survivors)
    if busted == 0:
        return icm_equities(stacks, payouts)[hero]

    if stacks[hero] <= 0:
        # Герой вылетел: получает выплату за первое место среди выбывших.
        place_index = len(survivors)
        padded = list(payouts) + [0.0] * (len(stacks) - len(payouts))
        return padded[place_index]

    if len(survivors) == 1:
        # Остался один игрок — он и есть герой, забирает первое место.
        padded = list(payouts) + [0.0] * (len(stacks) - len(payouts))
        return padded[0]

    shifted_stacks = [s for _, s in survivors]
    shifted_payouts = list(payouts)[: len(survivors)]
    hero_index = [i for i, _ in survivors].index(hero)
    return icm_equities(shifted_stacks, shifted_payouts)[hero_index]


def _significant_depth(payouts: list[float]) -> int:
    """Глубина рекурсии: дальше последней ненулевой выплаты считать нечего."""
    for i in range(len(payouts) - 1, -1, -1):
        if payouts[i] != 0.0:
            return i + 1
    return 0


def _validate(stacks: list[int], payouts: list[float]) -> None:
    if len(stacks) < 2:
        raise ValueError(f"нужно минимум 2 игрока, получено {len(stacks)}")
    if any(s <= 0 for s in stacks):
        raise ValueError(f"все стеки должны быть положительными: {stacks}")
    if len(payouts) > len(stacks):
        raise ValueError(
            f"выплат ({len(payouts)}) больше, чем игроков ({len(stacks)})"
        )
    if any(p < 0 for p in payouts):
        raise ValueError(f"выплаты не могут быть отрицательными: {payouts}")
