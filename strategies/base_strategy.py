from abc import ABC, abstractmethod

import numpy as np


class BaseStrategy(ABC):
    name: str = "base"

    @abstractmethod
    def generate_points(self, contour: np.ndarray, n: int = 20) -> list[tuple[float, float]]:
        """
        Given a contour array of shape (N, 2) with relative 0–1 coords,
        return n deployment points as list of (rx, ry) tuples.
        """
        ...

    def _sample(self, pts: np.ndarray, n: int) -> list[tuple[float, float]]:
        """Uniformly sample n points from pts array (N, 2)."""
        if len(pts) == 0:
            return []
        indices = np.linspace(0, len(pts) - 1, min(n, len(pts)), dtype=int)
        return [(float(pts[i, 0]), float(pts[i, 1])) for i in indices]
