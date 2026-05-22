from strategies.base_strategy import BaseStrategy
from strategies.surround import SurroundStrategy
from strategies.one_side import OneSideStrategy
from strategies.one_corner import OneCornerStrategy

STRATEGIES: dict[str, BaseStrategy] = {
    SurroundStrategy.name: SurroundStrategy(),
    OneSideStrategy.name: OneSideStrategy(),
    OneCornerStrategy.name: OneCornerStrategy(),
}

__all__ = ["BaseStrategy", "SurroundStrategy", "OneSideStrategy", "OneCornerStrategy", "STRATEGIES"]
