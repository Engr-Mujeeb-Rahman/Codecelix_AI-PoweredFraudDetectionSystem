# Machine Learning (ML) Artifacts & Anomaly Detection

This directory contains the serialized machine learning models and training metadata used by the Fraud & Risk Decision Engine.

## Directory Structure

```
backend/app/ml/
├── __init__.py
├── README.md
└── artifacts/
    ├── isolation_forest.joblib    # Serialized Scikit-Learn IsolationForest model
    └── model_meta.joblib          # Training metadata (sample count, timestamp, feature dimensionality)
```

## Model Details

- **Algorithm**: `sklearn.ensemble.IsolationForest`
- **Serialization Format**: `joblib` (`.joblib`)
- **Features (10 Dimensions)**:
  1. `log_amt`: Natural log of transaction amount
  2. `amt_ratio`: Current amount / (customer historical average + 1.0)
  3. `acc_age`: Customer account age in days
  4. `vel_1h`: 1-hour transaction velocity
  5. `vel_24h`: 24-hour transaction velocity
  6. `new_dev`: Binary indicator for unseen device fingerprint (1.0 / 0.0)
  7. `new_ip`: Binary indicator for unseen IP address (1.0 / 0.0)
  8. `vpn`: Binary indicator for VPN / proxy / Tor exit node (1.0 / 0.0)
  9. `hour`: Hour of transaction creation (0–23)
  10. `day`: Day of week (0–6)

## Training & Retraining

1. **Cold Start**: If no model artifacts exist on disk, the system automatically uses statistical Z-score baseline deviation (`_statistical_anomaly_score` in `ml_detector.py`).
2. **Live Retraining**: Admins can trigger model retraining on real historical database transactions via:
   ```http
   POST /api/risk/retrain
   Authorization: Bearer <ADMIN_JWT>
   ```
3. **Model Metrics**: Fraud analysts and admins can inspect model performance and feedback labels via:
   ```http
   GET /api/risk-metrics
   ```
