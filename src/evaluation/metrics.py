"""MOD-07 Evaluation metrics (REQ-ML-011). Plain numpy; classes in the fixed order of config.CLASSES."""
import numpy as np
from src.config import CLASSES


def confusion(actual, predicted):
    """Rows = actual class, columns = predicted class, in CLASSES order."""
    m = np.zeros((len(CLASSES), len(CLASSES)), dtype=int)
    for a, p in zip(actual, predicted): m[CLASSES.index(a), CLASSES.index(p)] += 1
    return m


def score(actual, predicted, proba):
    """actual, predicted: sequences of class names; proba: array (n, 3). Returns a dict of metrics.
    hit_rate = share correct; balanced_hit_rate = mean recall over classes present; macro_f1 = mean F-score over
    the three classes (a class with no actual and no predicted case counts 0); brier = mean squared error of the
    probability vector (0 best, 2 worst); log_loss = mean negative log probability of the actual class."""
    n = len(actual)
    if n == 0: return {"n": 0}
    m = confusion(actual, predicted); P = np.asarray(proba, dtype=float)
    onehot = np.zeros((n, len(CLASSES)))
    for i, a in enumerate(actual): onehot[i, CLASSES.index(a)] = 1.0
    recalls, f1s = [], []
    for k in range(len(CLASSES)):
        tp, fn, fp = m[k, k], m[k].sum() - m[k, k], m[:, k].sum() - m[k, k]
        if m[k].sum() > 0: recalls.append(tp / (tp + fn))
        f1s.append(2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) > 0 else 0.0)
    return {"n": n, "hit_rate": float(np.trace(m) / n), "balanced_hit_rate": float(np.mean(recalls)), "macro_f1": float(np.mean(f1s)),
            "brier": float(np.mean(np.sum((P - onehot) ** 2, axis=1))),
            "log_loss": float(-np.mean(np.log(np.clip(np.sum(P * onehot, axis=1), 1e-12, 1.0)))),
            "confusion": m.tolist()}
