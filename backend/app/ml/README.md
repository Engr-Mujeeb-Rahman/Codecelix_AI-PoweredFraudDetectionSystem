# Machine Learning (ML) Artifacts & Production Pipelines

This directory contains the original serialized machine learning pipelines, benchmark models, and decision configuration used by the Fraud & Risk Decision Engine.

## Directory Structure

```
backend/app/ml/
├── __init__.py
├── README.md
└── artifacts/
    ├── .gitkeep
    ├── report.txt                         # Canonical risk decision threshold specification
    ├── synthetic_fraud_pipeline.joblib    # PRIMARY: Hybrid Ensemble (XGBoost 75% + Isolation Forest 25%)
    ├── ulb_hybrid_fraud_pipeline.joblib   # BENCHMARK: Hybrid Credit-Card PCA Pipeline (V1–V28)
    ├── final_fraud_pipeline.pkl           # BENCHMARK: IEEE-CIS Identity Pipeline
    └── Old/
        ├── isolation_forest.joblib        # Legacy baseline isolation forest
        └── model_meta.joblib              # Legacy metadata
```

## Primary Production Pipeline (`synthetic_fraud_pipeline.joblib`)

- **Architecture**: **Hybrid Ensemble (XGBoost + Isolation Forest)**
  - Preprocessing: `StandardScaler` fitted on 43 transactional & behavioral features
  - Unsupervised Anomaly Detection: `IsolationForest` (normalized anomaly score appended as 44th feature)
  - Supervised Fraud Classifier: `XGBClassifier`
  - Ensemble Weights: $0.75 \times P(\text{fraud}) + 0.25 \times \text{Isolation Anomaly}$
- **Decision Calibration** (Piecewise Linear per `report.txt`):
  - **0–30**: `LOW` risk &rarr; `APPROVE`
  - **31–70**: `MEDIUM` risk &rarr; `REVIEW`
  - **71–100**: `HIGH` risk &rarr; `REVIEW` / `REJECT` (`BLOCK`)

## 43 Raw Input Features

| Category | Features |
| :--- | :--- |
| **Transaction Amounts** | `amount`, `log_amount`, `customer_avg_amount`, `amount_deviation`, `amount_anomaly_flag`, `amount_vs_customer_avg` |
| **Account Profile** | `account_age_days`, `new_account_flag` |
| **Device Telemetry** | `device_age_days`, `is_new_device`, `device_customer_count`, `shared_device_flag`, `new_device_high_amount` |
| **Network Telemetry** | `ip_account_count`, `shared_ip_flag` |
| **Geospatial & Travel** | `distance_from_home_km`, `is_new_location` |
| **Velocity & Frequency** | `transactions_last_10min`, `transactions_last_1hr`, `velocity_flag` |
| **Temporal Context** | `hour`, `hour_sin`, `hour_cos`, `day_of_week`, `is_weekend` |
| **Payment Method (One-Hot)** | `payment_bank_transfer`, `payment_credit_card`, `payment_debit_card`, `payment_digital_wallet`, `payment_paypal` |
| **Device Type (One-Hot)** | `device_type_desktop`, `device_type_mobile`, `device_type_tablet` |
| **Country (One-Hot)** | `country_Australia`, `country_Canada`, `country_Germany`, `country_India`, `country_Pakistan`, `country_Saudi Arabia`, `country_Singapore`, `country_UAE`, `country_United Kingdom`, `country_United States` |

## Retraining & Metrics

- **`GET /api/risk-metrics`**: Returns active model status (`active (Hybrid XGBoost + Isolation Forest)`), precision, and recall approximation based on analyst verdicts.
- **`POST /api/risk/retrain`**: Admin endpoint to verify and retrain models on live historical database records.
