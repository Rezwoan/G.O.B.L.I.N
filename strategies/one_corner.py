import numpy as np

from strategies.base_strategy import BaseStrategy


class OneCornerStrategy(BaseStrategy):
    name = "one_corner"
    _radius = 0.15

    def generate_points(self, contour: np.ndarray, n: int = 20) -> list[tuple[float, float]]:
        """Deploy near the contour corner closest to the frame center (0.5, 0.5)."""
        if len(contour) == 0:
            return []

        min_x, min_y = contour[:, 0].min(), contour[:, 1].min()
        max_x, max_y = contour[:, 0].max(), contour[:, 1].max()

        corners = np.array([
            [min_x, min_y],
            [max_x, min_y],
            [min_x, max_y],
            [max_x, max_y],
        ])
        frame_center = np.array([0.5, 0.5])
        dists = np.linalg.norm(corners - frame_center, axis=1)
        nearest_corner = corners[np.argmin(dists)]

        diff = contour - nearest_corner
        distances = np.sqrt((diff ** 2).sum(axis=1))
        corner_pts = contour[distances <= self._radius]

        if len(corner_pts) == 0:
            corner_pts = contour
        return self._sample(corner_pts, n)
