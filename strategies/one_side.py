import numpy as np

from strategies.base_strategy import BaseStrategy


class OneSideStrategy(BaseStrategy):
    name = "one_side"

    def generate_points(self, contour: np.ndarray, n: int = 20) -> list[tuple[float, float]]:
        """Deploy along the left third of the contour bounding box."""
        if len(contour) == 0:
            return []
        min_x = float(contour[:, 0].min())
        max_x = float(contour[:, 0].max())
        bbox_width = max_x - min_x
        threshold_x = min_x + bbox_width / 3.0
        left_pts = contour[contour[:, 0] <= threshold_x]
        if len(left_pts) == 0:
            left_pts = contour
        return self._sample(left_pts, n)
