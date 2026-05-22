import numpy as np

from strategies.base_strategy import BaseStrategy


class SurroundStrategy(BaseStrategy):
    name = "surround"

    def generate_points(self, contour: np.ndarray, n: int = 20) -> list[tuple[float, float]]:
        """Evenly distribute n points around the full contour perimeter."""
        return self._sample(contour, n)
