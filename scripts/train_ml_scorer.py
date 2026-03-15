#!/usr/bin/env python3
"""
LeadFactory — ML Lead Scorer Training Script

Trains a machine learning model to rank leads based on historical data.
Experiments with multiple model types and selects the best based on
cross-validation metrics.

Usage:
    python scripts/train_ml_scorer.py --input data/enriched/investor_leads_master.csv
    python scripts/train_ml_scorer.py --input data/enriched/investor_leads_master.csv --model-type random_forest

Requirements:
    pip install scikit-learn pandas joblib
"""

import argparse
import json
import sys
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    print("ERROR: pandas is required. Install with: pip install pandas")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Train the ML lead scorer model")
    parser.add_argument("--input", required=True, help="Path to training CSV with lead_score column")
    parser.add_argument("--output", default="models/lead_scorer.joblib", help="Output model path")
    parser.add_argument("--test-size", type=float, default=0.2, help="Test split ratio (default: 0.2)")
    parser.add_argument(
        "--model-type",
        choices=["gradient_boosting", "logistic_regression", "random_forest", "compare_all"],
        default="compare_all",
        help="Model type to train, or 'compare_all' to try all and pick best",
    )
    parser.add_argument("--score-threshold", type=int, default=60, help="Score threshold for positive class (default: 60)")
    args = parser.parse_args()

    try:
        from sklearn.model_selection import train_test_split, cross_val_score
        from sklearn.metrics import classification_report, roc_auc_score
        from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler
        from sklearn.pipeline import Pipeline
        import joblib
    except ImportError:
        print("ERROR: scikit-learn is required. Install with: pip install scikit-learn joblib")
        sys.exit(1)

    print(f"Loading data from {args.input}...")
    df = pd.read_csv(args.input)
    print(f"  Loaded {len(df)} records")

    if "lead_score" not in df.columns:
        print("ERROR: CSV must have a 'lead_score' column")
        print(f"  Available columns: {list(df.columns)}")
        sys.exit(1)

    # Create binary target
    df["target"] = (df["lead_score"] >= args.score_threshold).astype(int)
    print(f"  Target: lead_score >= {args.score_threshold}")
    print(f"  Class distribution: {df['target'].value_counts().to_dict()}")

    # Feature engineering
    features = pd.DataFrame()
    features["has_email"] = df.get("email", pd.Series("N/A")).apply(
        lambda x: 1 if pd.notna(x) and str(x) not in ("N/A", "") and "@" in str(x) else 0
    )
    features["has_linkedin"] = df.get("linkedin", pd.Series("N/A")).apply(
        lambda x: 1 if pd.notna(x) and "linkedin" in str(x) else 0
    )
    features["sector_count"] = df.get("focus_areas", pd.Series("")).apply(
        lambda x: len(str(x).split(";")) if pd.notna(x) and str(x) != "N/A" else 0
    )
    features["has_website"] = df.get("website", pd.Series("N/A")).apply(
        lambda x: 1 if pd.notna(x) and str(x) not in ("N/A", "") else 0
    )
    features["name_length"] = df.get("name", pd.Series("")).apply(lambda x: len(str(x).split()) if pd.notna(x) else 0)

    # Stage encoding
    stage_map = {"pre-seed": 0, "seed": 1, "series-a": 2, "series a": 2, "series-b": 3, "growth": 4}
    features["stage_encoded"] = df.get("stage", pd.Series("")).apply(
        lambda x: stage_map.get(str(x).lower().strip(), -1) if pd.notna(x) else -1
    )

    X = features.fillna(0)
    y = df["target"]

    print(f"\n  Features ({len(X.columns)}): {list(X.columns)}")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=args.test_size, random_state=42, stratify=y
    )
    print(f"  Train: {len(X_train)}, Test: {len(X_test)}")

    # Model definitions
    model_configs = {
        "gradient_boosting": GradientBoostingClassifier(
            n_estimators=100, max_depth=5, learning_rate=0.1, random_state=42
        ),
        "logistic_regression": LogisticRegression(max_iter=1000, random_state=42),
        "random_forest": RandomForestClassifier(
            n_estimators=100, max_depth=10, random_state=42
        ),
    }

    if args.model_type == "compare_all":
        models_to_try = model_configs
    else:
        models_to_try = {args.model_type: model_configs[args.model_type]}

    best_model_name = None
    best_auc = -1
    best_pipeline = None
    results = {}

    for name, model_cls in models_to_try.items():
        print(f"\n{'='*50}")
        print(f"  Training: {name}")
        print(f"{'='*50}")

        pipeline = Pipeline([("scaler", StandardScaler()), ("model", model_cls)])
        pipeline.fit(X_train, y_train)

        y_pred = pipeline.predict(X_test)
        print(classification_report(y_test, y_pred))

        auc = 0.5
        if hasattr(pipeline, "predict_proba"):
            try:
                y_proba = pipeline.predict_proba(X_test)[:, 1]
                auc = roc_auc_score(y_test, y_proba)
                print(f"  ROC AUC: {auc:.4f}")
            except Exception:
                pass

        cv_scores = cross_val_score(pipeline, X, y, cv=5, scoring="accuracy")
        print(f"  CV accuracy: {cv_scores.mean():.4f} (+/- {cv_scores.std():.4f})")

        results[name] = {
            "auc": auc,
            "cv_mean": float(cv_scores.mean()),
            "cv_std": float(cv_scores.std()),
            "test_accuracy": float((y_pred == y_test).mean()),
        }

        if auc > best_auc:
            best_auc = auc
            best_model_name = name
            best_pipeline = pipeline

    # Save best model
    print(f"\n{'='*50}")
    print(f"  Best model: {best_model_name} (AUC={best_auc:.4f})")
    print(f"{'='*50}")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(best_pipeline, output_path)
    print(f"\nModel saved to {output_path}")

    # Save metadata
    metadata = {
        "best_model": best_model_name,
        "features": list(X.columns),
        "score_threshold": args.score_threshold,
        "all_results": results,
        "training_samples": len(X_train),
        "test_samples": len(X_test),
    }
    meta_path = output_path.with_suffix(".json")
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2)
    print(f"Metadata saved to {meta_path}")


if __name__ == "__main__":
    main()
