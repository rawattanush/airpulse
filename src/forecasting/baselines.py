"""MOD-06 Forecasters, baselines (REQ-ML-007). Each is fitted on the training window only and returns
(predicted class, probabilities in the order of config.CLASSES). Probabilities use add-one smoothing so that
log loss is finite. No feature matrix is needed."""
import numpy as np
from src.config import CLASSES


def _freq(labels):
    c = np.array([sum(1 for y in labels if y == k) for k in CLASSES], dtype=float) + 1.0
    return c / c.sum()


class MajorityBaseline:
    """Class frequencies of the training window; predicts the most frequent class."""
    forecaster_id, name, version, params = "BL-MAJ", "Majority class", "1.0", {"smoothing": "add-one"}

    def fit(self, y_train, context_train=None):
        self.p = _freq(y_train); return self

    def predict(self, context=None):
        return CLASSES[int(np.argmax(self.p))], self.p


class PersistenceBaseline:
    """Predicts the latest known real-time label (that of month t-1, published on the issuance date).
    Probability of that class = share of training months in which the final label repeated the previous
    real-time label; the rest is split equally. Falls back to the majority class when no previous label exists."""
    forecaster_id, name, version, params = "BL-PER", "Persistence of last real-time label", "1.0", {"smoothing": "add-one"}

    def fit(self, y_train, context_train):
        pairs = [(y, c["prev_rt_label"]) for y, c in zip(y_train, context_train) if c["prev_rt_label"] is not None]
        same = sum(1 for y, p in pairs if y == p)
        self.repeat = (same + 1.0) / (len(pairs) + 3.0)
        self.fallback = MajorityBaseline().fit(y_train); return self

    def predict(self, context):
        prev = context["prev_rt_label"]
        if prev is None: return self.fallback.predict()
        p = np.full(3, (1.0 - self.repeat) / 2.0); p[CLASSES.index(prev)] = self.repeat
        return prev, p


class SeasonalBaseline:
    """Class frequencies of the same calendar month in the training window."""
    forecaster_id, name, version, params = "BL-SEA", "Same-calendar-month majority", "1.0", {"smoothing": "add-one"}

    def fit(self, y_train, context_train):
        self.by_month = {}
        for m in range(1, 13):
            self.by_month[m] = _freq([y for y, c in zip(y_train, context_train) if c["month"] == m])
        return self

    def predict(self, context):
        p = self.by_month[context["month"]]
        return CLASSES[int(np.argmax(p))], p
