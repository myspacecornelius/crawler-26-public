"""
CRAWL — ML Lead Scoring Module
Machine learning based lead scoring using historical success metrics.

Features: sector, stage, geography, company size, email quality, engagement.
Falls back to the rule-based LeadScorer when the model lacks sufficient data.

Usage:
    from enrichment.ml_scorer import MLLeadScorer
    scorer = MLLeadScorer()
    scorer.load_model("models/lead_scorer.joblib")
    score, confidence = scorer.predict(lead)
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_MODEL_DIR = Path(__file__).resolve().parent.parent / "models"

# Feature definitions for the ML model
FEATURE_COLUMNS = [
    "stage_encoded",
    "sector_count",
    "sector_ai",
    "sector_saas",
    "sector_fintech",
    "sector_health",
    "sector_other",
    "has_email",
    "email_verified",
    "email_catch_all",
    "has_linkedin",
    "role_encoded",
    "check_size_min_normalized",
    "check_size_max_normalized",
    "times_seen",
    "days_since_scraped",
    "has_website",
]

# Stage encoding map
STAGE_ENCODING = {
    "pre-seed": 0, "seed": 1, "series-a": 2, "series a": 2,
    "series-b": 3, "series b": 3, "growth": 4, "late-stage": 5,
    "n/a": -1, "": -1,
}

# Role encoding map
ROLE_ENCODING = {
    "partner": 4, "gp": 4, "managing director": 4,
    "principal": 3, "vp": 3, "director": 3,
    "associate": 2, "analyst": 2,
    "coordinator": 1, "intern": 0, "admin": 1,
}


def extract_features(lead) -> Dict[str, float]:
    """
    Extract ML features from an InvestorLead object.
    Returns a dictionary of feature_name -> float value.
    """
    import re
    from datetime import datetime

    features = {}

    # Stage encoding
    stage = getattr(lead, "stage", "").lower().strip()
    features["stage_encoded"] = STAGE_ENCODING.get(stage, -1)

    # Sector features
    focus_areas = getattr(lead, "focus_areas", []) or []
    focus_lower = [s.lower() for s in focus_areas]
    features["sector_count"] = len(focus_areas)
    features["sector_ai"] = 1.0 if any("ai" in s or "artificial" in s or "machine learning" in s for s in focus_lower) else 0.0
    features["sector_saas"] = 1.0 if any("saas" in s or "software" in s for s in focus_lower) else 0.0
    features["sector_fintech"] = 1.0 if any("fintech" in s or "financial" in s for s in focus_lower) else 0.0
    features["sector_health"] = 1.0 if any("health" in s or "bio" in s or "medical" in s for s in focus_lower) else 0.0
    features["sector_other"] = 1.0 if focus_areas and not any([
        features["sector_ai"], features["sector_saas"],
        features["sector_fintech"], features["sector_health"],
    ]) else 0.0

    # Email features
    email = getattr(lead, "email", "N/A")
    features["has_email"] = 1.0 if email and email not in ("N/A", "N/A (invalid)", "") and "@" in email else 0.0
    email_status = getattr(lead, "email_status", "unknown")
    features["email_verified"] = 1.0 if email_status == "verified" else 0.0
    features["email_catch_all"] = 1.0 if email_status == "catch_all" else 0.0

    # LinkedIn
    linkedin = getattr(lead, "linkedin", "N/A")
    features["has_linkedin"] = 1.0 if linkedin and linkedin not in ("N/A", "") and "linkedin" in linkedin else 0.0

    # Role encoding
    role = getattr(lead, "role", "").lower().strip()
    role_score = -1.0
    for keyword, score in ROLE_ENCODING.items():
        if keyword in role:
            role_score = float(score)
            break
    features["role_encoded"] = role_score

    # Check size
    check_size = getattr(lead, "check_size", "N/A") or "N/A"
    numbers = re.findall(r"[\d,]+", check_size.replace("K", "000").replace("M", "000000"))
    if numbers:
        amounts = [int(n.replace(",", "")) for n in numbers]
        features["check_size_min_normalized"] = min(amounts) / 10_000_000  # normalize to 0-1 range
        features["check_size_max_normalized"] = max(amounts) / 10_000_000
    else:
        features["check_size_min_normalized"] = -1.0
        features["check_size_max_normalized"] = -1.0

    # Times seen
    features["times_seen"] = float(getattr(lead, "times_seen", 1))

    # Days since scraped
    scraped_at = getattr(lead, "scraped_at", "")
    if scraped_at:
        try:
            scraped = datetime.fromisoformat(scraped_at)
            features["days_since_scraped"] = (datetime.now() - scraped).days
        except (ValueError, TypeError):
            features["days_since_scraped"] = -1.0
    else:
        features["days_since_scraped"] = -1.0

    # Website
    website = getattr(lead, "website", "N/A")
    features["has_website"] = 1.0 if website and website not in ("N/A", "") else 0.0

    return features


class MLLeadScorer:
    """
    ML-based lead scoring using scikit-learn.

    Falls back to rule-based scoring when:
    - Model file doesn't exist
    - scikit-learn is not installed
    - Feature extraction fails
    - Model confidence is below threshold
    """

    def __init__(self, model_path: Optional[str] = None, confidence_threshold: float = 0.3):
        self._model = None
        self._model_path = Path(model_path) if model_path else _MODEL_DIR / "lead_scorer.joblib"
        self._confidence_threshold = confidence_threshold
        self._feature_columns = FEATURE_COLUMNS
        self._predictions_made = 0
        self._fallbacks = 0

    def load_model(self, path: Optional[str] = None) -> bool:
        """Load a trained model from disk. Returns True on success."""
        model_path = Path(path) if path else self._model_path
        try:
            import joblib
            if model_path.exists():
                self._model = joblib.load(model_path)
                logger.info("ML scorer loaded model from %s", model_path)
                return True
            logger.info("ML scorer: no model found at %s", model_path)
            return False
        except ImportError:
            logger.info("ML scorer: joblib not installed, using rule-based scoring")
            return False
        except Exception as e:
            logger.warning("ML scorer: failed to load model: %s", e)
            return False

    @property
    def model_available(self) -> bool:
        return self._model is not None

    def predict(self, lead) -> Tuple[float, float]:
        """
        Predict a lead score using the ML model.

        Returns:
            (score: float 0-100, confidence: float 0-1)
            Returns (-1, 0) if model is unavailable (caller should fall back).
        """
        if self._model is None:
            self._fallbacks += 1
            return (-1, 0.0)

        try:
            features = extract_features(lead)
            feature_vector = [features.get(col, 0.0) for col in self._feature_columns]

            # Predict using the model
            import numpy as np
            X = np.array([feature_vector])

            if hasattr(self._model, "predict_proba"):
                proba = self._model.predict_proba(X)[0]
                # For binary classification (good/bad lead), use positive class probability
                confidence = float(max(proba))
                score = float(proba[-1]) * 100  # Map to 0-100
            else:
                prediction = self._model.predict(X)[0]
                score = float(prediction)
                confidence = 0.5  # No probability available

            self._predictions_made += 1

            # If confidence is below threshold, signal for fallback
            if confidence < self._confidence_threshold:
                self._fallbacks += 1
                return (-1, confidence)

            return (max(0, min(100, score)), confidence)

        except Exception as e:
            logger.debug("ML predict failed for %s: %s", getattr(lead, "name", "?"), e)
            self._fallbacks += 1
            return (-1, 0.0)

    def predict_batch(self, leads: list) -> List[Tuple[float, float]]:
        """Predict scores for a batch of leads."""
        return [self.predict(lead) for lead in leads]

    @property
    def stats(self) -> dict:
        return {
            "model_loaded": self._model is not None,
            "predictions_made": self._predictions_made,
            "fallbacks_to_rules": self._fallbacks,
            "model_path": str(self._model_path),
        }


def create_training_script() -> str:
    """
    Returns the content for a standalone training script.
    This can be saved and run independently.
    """
    return '''#!/usr/bin/env python3
"""
LeadFactory — ML Lead Scorer Training Script

Usage:
    python scripts/train_ml_scorer.py --input data/enriched/investor_leads_master.csv --output models/lead_scorer.joblib

Requirements:
    pip install scikit-learn pandas joblib
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

def main():
    parser = argparse.ArgumentParser(description="Train the ML lead scorer model")
    parser.add_argument("--input", required=True, help="Path to training CSV")
    parser.add_argument("--output", default="models/lead_scorer.joblib", help="Output model path")
    parser.add_argument("--test-size", type=float, default=0.2, help="Test split ratio")
    parser.add_argument("--model-type", choices=["gradient_boosting", "logistic_regression", "random_forest"],
                        default="gradient_boosting", help="Model type to train")
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

    # Create binary target: leads with score >= 60 are "good"
    if "lead_score" not in df.columns:
        print("ERROR: CSV must have a 'lead_score' column")
        sys.exit(1)

    df["target"] = (df["lead_score"] >= 60).astype(int)

    # Feature engineering
    features = pd.DataFrame()
    features["has_email"] = df["email"].apply(lambda x: 1 if pd.notna(x) and x not in ("N/A", "") and "@" in str(x) else 0)
    features["has_linkedin"] = df.get("linkedin", pd.Series("N/A")).apply(lambda x: 1 if pd.notna(x) and "linkedin" in str(x) else 0)
    features["sector_count"] = df.get("focus_areas", pd.Series("")).apply(lambda x: len(str(x).split(";")) if pd.notna(x) and x != "N/A" else 0)

    X = features.fillna(0)
    y = df["target"]

    print(f"  Features: {list(X.columns)}")
    print(f"  Target distribution: {y.value_counts().to_dict()}")

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=args.test_size, random_state=42, stratify=y)

    # Select model
    models = {
        "gradient_boosting": GradientBoostingClassifier(n_estimators=100, max_depth=5, random_state=42),
        "logistic_regression": LogisticRegression(max_iter=1000, random_state=42),
        "random_forest": RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42),
    }

    model_cls = models[args.model_type]
    pipeline = Pipeline([("scaler", StandardScaler()), ("model", model_cls)])

    print(f"\\nTraining {args.model_type}...")
    pipeline.fit(X_train, y_train)

    # Evaluate
    y_pred = pipeline.predict(X_test)
    print("\\n--- Classification Report ---")
    print(classification_report(y_test, y_pred))

    if hasattr(pipeline, "predict_proba"):
        y_proba = pipeline.predict_proba(X_test)[:, 1]
        auc = roc_auc_score(y_test, y_proba)
        print(f"ROC AUC: {auc:.4f}")

    # Cross-validation
    cv_scores = cross_val_score(pipeline, X, y, cv=5, scoring="accuracy")
    print(f"\\nCross-validation accuracy: {cv_scores.mean():.4f} (+/- {cv_scores.std():.4f})")

    # Save model
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, output_path)
    print(f"\\nModel saved to {output_path}")

    # Save metadata
    metadata = {
        "model_type": args.model_type,
        "features": list(X.columns),
        "test_accuracy": float((y_pred == y_test).mean()),
        "cv_accuracy_mean": float(cv_scores.mean()),
        "cv_accuracy_std": float(cv_scores.std()),
        "training_samples": len(X_train),
        "test_samples": len(X_test),
    }
    meta_path = output_path.with_suffix(".json")
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2)
    print(f"Metadata saved to {meta_path}")


if __name__ == "__main__":
    main()
'''
