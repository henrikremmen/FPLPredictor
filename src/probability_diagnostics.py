"""Fixed probability bins for held-out calibration diagnostics, not fitting."""
import numpy as np


def calibration_bins(probabilities, outcomes):
    probabilities = np.asarray(probabilities, dtype=float)
    outcomes = np.asarray(outcomes, dtype=float)
    if (probabilities.ndim != 1 or probabilities.shape != outcomes.shape
            or not np.isfinite(probabilities).all()
            or not ((probabilities >= 0) & (probabilities <= 1)).all()
            or not np.isin(outcomes, [0, 1]).all()):
        raise ValueError("Expected matched binary outcomes and probabilities in [0, 1]")
    bins = np.minimum((probabilities * 5).astype(int), 4)
    result = []
    for index in range(5):
        selected = bins == index
        row = {"lower": index / 5, "upper": (index + 1) / 5,
               "upper_inclusive": index == 4, "rows": int(selected.sum())}
        if selected.any():
            row.update(mean_probability=float(probabilities[selected].mean()),
                       observed_rate=float(outcomes[selected].mean()))
        result.append(row)
    return result
