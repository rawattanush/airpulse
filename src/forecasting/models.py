"""MOD-06 Forecasters, models (REQ-ML-008, REQ-ML-010). Each model is created and fitted anew at every
forecast origin on the training window only; imputation and scaling are part of the fitted pipeline.
Hyperparameters are fixed in advance and are not tuned on any test month."""
import numpy as np
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from src.config import CLASSES, RANDOM_SEED


def _full_proba(model_classes, proba_row):
    """Map a model's probability row to the fixed class order; a class absent from training gets 0."""
    p = np.zeros(len(CLASSES))
    for c, v in zip(model_classes, proba_row): p[CLASSES.index(c)] = v
    return p / p.sum()


class LogisticModel:
    forecaster_id, name, version = "ML-LOGIT", "Multinomial logistic regression", "1.0"
    params = {"C": 1.0, "max_iter": 2000, "imputer": "median", "scaler": "standard", "seed": RANDOM_SEED}

    def fit(self, X, y):
        self.pipe = Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler()),
                              ("clf", LogisticRegression(C=1.0, max_iter=2000, random_state=RANDOM_SEED))])
        self.pipe.fit(np.asarray(X, dtype=float), np.asarray(y)); return self

    def predict(self, x):
        p = _full_proba(self.pipe.classes_, self.pipe.predict_proba(np.asarray(x, dtype=float).reshape(1, -1))[0])
        return CLASSES[int(np.argmax(p))], p


class GradientBoostedModel:
    forecaster_id, name, version = "ML-GBT", "Gradient-boosted trees (LightGBM), shallow", "1.0"
    params = {"n_estimators": 100, "learning_rate": 0.05, "max_depth": 2, "num_leaves": 4, "min_child_samples": 10,
              "reg_lambda": 1.0, "seed": RANDOM_SEED, "deterministic": True, "n_jobs": 1}

    def fit(self, X, y):
        from lightgbm import LGBMClassifier
        self.clf = LGBMClassifier(n_estimators=100, learning_rate=0.05, max_depth=2, num_leaves=4, min_child_samples=10,
                                  reg_lambda=1.0, random_state=RANDOM_SEED, deterministic=True, force_row_wise=True, n_jobs=1, verbose=-1)
        self.clf.fit(np.asarray(X, dtype=float), np.asarray(y)); return self

    def predict(self, x):
        p = _full_proba(self.clf.classes_, self.clf.predict_proba(np.asarray(x, dtype=float).reshape(1, -1))[0])
        return CLASSES[int(np.argmax(p))], p
