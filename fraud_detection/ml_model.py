import numpy as np
import os
import joblib
from sklearn.linear_model import LogisticRegression

MODEL_PATH = os.path.join(os.path.dirname(__file__), 'fraud_model.joblib')

BILL_MAP = {
    "Electricity":       0,
    "Water":             1,
    "Mobile":            2,
    "Internet":          3,
    "Transfer":          4,
    "External Transfer": 5,
    "Admin Adjustment":  6,
}


def train_model():
    """Train on a larger synthetic dataset and persist to disk."""
    np.random.seed(42)

    # Normal transactions (label=0): amounts 100–8000, various types
    n_normal = 300
    amounts_normal = np.random.uniform(100, 8000, n_normal)
    types_normal   = np.random.randint(0, 7, n_normal)
    X_normal = np.column_stack([amounts_normal, types_normal])
    y_normal = np.zeros(n_normal)

    # Fraud transactions (label=1): amounts 15000–100000
    n_fraud = 100
    amounts_fraud = np.random.uniform(15000, 100000, n_fraud)
    types_fraud   = np.random.randint(0, 7, n_fraud)
    X_fraud = np.column_stack([amounts_fraud, types_fraud])
    y_fraud = np.ones(n_fraud)

    # Edge cases near boundary (8000–15000) — mostly normal
    n_edge = 60
    amounts_edge = np.random.uniform(8000, 15000, n_edge)
    types_edge   = np.random.randint(0, 7, n_edge)
    X_edge = np.column_stack([amounts_edge, types_edge])
    y_edge = np.where(amounts_edge > 12000, 1, 0)

    X = np.vstack([X_normal, X_fraud, X_edge])
    y = np.concatenate([y_normal, y_fraud, y_edge])

    model = LogisticRegression(max_iter=500)
    model.fit(X, y)

    joblib.dump(model, MODEL_PATH)
    return model


_model = None


def get_model():
    global _model
    if _model is None:
        if os.path.exists(MODEL_PATH):
            _model = joblib.load(MODEL_PATH)
        else:
            _model = train_model()
    return _model


def predict_fraud(amount, bill_type):
    bill_code = BILL_MAP.get(bill_type, 0)
    model = get_model()
    prediction = model.predict([[float(amount), bill_code]])
    return prediction[0]
