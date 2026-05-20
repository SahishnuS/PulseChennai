"""
Model Inspector — Reverse-engineer .pkl models and data schemas
================================================================
Inspects all .pkl files in models/ directory to discover:
- Model type (XGBoost, LightGBM, RandomForest, etc.)
- Input features (names, count, types)
- Output structure
- Preprocessing expectations
- Training metadata

Also inspects uber_data.csv for schema discovery.
"""

import os
import sys
import pickle
import json
from pathlib import Path

def inspect_pkl_file(filepath):
    """Inspect a single .pkl file and extract metadata."""
    info = {"file": str(filepath), "size_bytes": os.path.getsize(filepath)}
    
    try:
        with open(filepath, "rb") as f:
            obj = pickle.load(f)
        
        info["type"] = type(obj).__name__
        info["module"] = type(obj).__module__
        info["class"] = f"{type(obj).__module__}.{type(obj).__name__}"
        
        # Check for sklearn-style models
        if hasattr(obj, "get_params"):
            info["params"] = {}
            try:
                params = obj.get_params()
                # Convert to serializable
                for k, v in params.items():
                    try:
                        json.dumps(v)
                        info["params"][k] = v
                    except (TypeError, ValueError):
                        info["params"][k] = str(v)
            except Exception as e:
                info["params_error"] = str(e)
        
        # Feature names
        if hasattr(obj, "feature_names_in_"):
            info["feature_names"] = list(obj.feature_names_in_)
            info["n_features"] = len(obj.feature_names_in_)
        elif hasattr(obj, "feature_name_"):
            info["feature_names"] = list(obj.feature_name_())
            info["n_features"] = len(info["feature_names"])
        elif hasattr(obj, "n_features_in_"):
            info["n_features"] = obj.n_features_in_
        elif hasattr(obj, "n_features_"):
            info["n_features"] = obj.n_features_
        
        # Feature importances
        if hasattr(obj, "feature_importances_"):
            imp = obj.feature_importances_
            info["n_feature_importances"] = len(imp)
            info["top_5_importance_indices"] = list(imp.argsort()[-5:][::-1])
            if hasattr(obj, "feature_names_in_"):
                names = list(obj.feature_names_in_)
                top_idx = imp.argsort()[-10:][::-1]
                info["top_features"] = [
                    {"name": names[i], "importance": float(imp[i])} 
                    for i in top_idx if i < len(names)
                ]
        
        # Number of classes (classifiers)
        if hasattr(obj, "classes_"):
            info["classes"] = [str(c) for c in obj.classes_]
            info["n_classes"] = len(obj.classes_)
        
        # Number of estimators (ensemble)
        if hasattr(obj, "n_estimators"):
            info["n_estimators"] = obj.n_estimators
        if hasattr(obj, "n_estimators_"):
            info["n_estimators_actual"] = obj.n_estimators_
        
        # XGBoost specific
        if "xgboost" in info["module"].lower() or "xgb" in info["type"].lower():
            if hasattr(obj, "get_booster"):
                booster = obj.get_booster()
                if hasattr(booster, "feature_names"):
                    info["xgb_feature_names"] = booster.feature_names
                if hasattr(booster, "num_features"):
                    fn = booster.num_features()
                    info["xgb_n_features"] = fn
        
        # LightGBM specific
        if "lightgbm" in info["module"].lower() or "lgb" in info["type"].lower():
            if hasattr(obj, "booster_"):
                booster = obj.booster_
                if hasattr(booster, "feature_name"):
                    fn = booster.feature_name()
                    info["lgb_feature_names"] = fn
                if hasattr(booster, "num_feature"):
                    fn = booster.num_feature()
                    info["lgb_n_features"] = fn
        
        # RandomForest specific
        if "forest" in info["type"].lower() or "RandomForest" in info["type"]:
            if hasattr(obj, "estimators_"):
                info["n_trees"] = len(obj.estimators_)
                if len(obj.estimators_) > 0:
                    tree = obj.estimators_[0]
                    if hasattr(tree, "n_features_in_"):
                        info["tree_n_features"] = tree.n_features_in_
                    if hasattr(tree, "tree_"):
                        info["max_depth_tree0"] = int(tree.tree_.max_depth)
        
        # Check if regressor or classifier
        if hasattr(obj, "_estimator_type"):
            info["estimator_type"] = obj._estimator_type
        
        # Training metadata
        if hasattr(obj, "best_score_"):
            info["best_score"] = float(obj.best_score_)
        if hasattr(obj, "best_params_"):
            info["best_params"] = str(obj.best_params_)
            
    except Exception as e:
        info["error"] = str(e)
        import traceback
        info["traceback"] = traceback.format_exc()
    
    return info


def inspect_encoding_file(filepath):
    """Inspect label encoding .pkl files."""
    info = {"file": str(filepath), "size_bytes": os.path.getsize(filepath)}
    
    try:
        with open(filepath, "rb") as f:
            obj = pickle.load(f)
        
        info["type"] = type(obj).__name__
        info["module"] = type(obj).__module__
        
        if hasattr(obj, "classes_"):
            classes = list(obj.classes_)
            info["n_classes"] = len(classes)
            info["sample_classes"] = classes[:20]
        elif isinstance(obj, dict):
            info["n_keys"] = len(obj)
            info["sample_keys"] = list(obj.keys())[:20]
            info["sample_values"] = list(obj.values())[:20]
        elif isinstance(obj, list):
            info["length"] = len(obj)
            info["sample"] = obj[:20]
        else:
            info["repr"] = repr(obj)[:500]
            
    except Exception as e:
        info["error"] = str(e)
    
    return info


def inspect_csv(filepath, nrows=5):
    """Inspect CSV file schema."""
    info = {"file": str(filepath)}
    
    try:
        import pandas as pd
        df = pd.read_csv(filepath, nrows=nrows)
        info["columns"] = list(df.columns)
        info["dtypes"] = {col: str(dtype) for col, dtype in df.dtypes.items()}
        info["shape_sample"] = list(df.shape)
        info["sample_data"] = df.head(3).to_dict(orient="records")
        
        # Get full row count
        total = sum(1 for _ in open(filepath, encoding="utf-8", errors="ignore")) - 1
        info["total_rows"] = total
        
        # Numeric column stats
        info["numeric_cols"] = list(df.select_dtypes(include=["number"]).columns)
        info["object_cols"] = list(df.select_dtypes(include=["object"]).columns)
        
    except Exception as e:
        info["error"] = str(e)
    
    return info


def main():
    base = Path(r"c:\SEM3 SHIT\unisys")
    models_dir = base / "models"
    data_dir = base / "data"
    
    print("=" * 70)
    print("PULSE-CHENNAI MODEL INSPECTOR")
    print("=" * 70)
    
    # 1. Inspect ML models
    print("\n\n### ML MODELS ###\n")
    model_files = ["xgb_model.pkl", "lgb_model.pkl", "rf_model.pkl"]
    for mf in model_files:
        path = models_dir / mf
        if path.exists():
            print(f"\n--- {mf} ---")
            info = inspect_pkl_file(path)
            for k, v in info.items():
                if k == "params":
                    print(f"  {k}:")
                    for pk, pv in v.items():
                        print(f"    {pk}: {pv}")
                elif k == "top_features":
                    print(f"  {k}:")
                    for feat in v:
                        print(f"    {feat['name']}: {feat['importance']:.4f}")
                else:
                    print(f"  {k}: {v}")
        else:
            print(f"  {mf}: NOT FOUND")
    
    # 2. Inspect encoding files
    print("\n\n### ENCODING FILES ###\n")
    enc_files = ["source_encoding.pkl", "dest_encoding.pkl", 
                 "source_hex_encoding.pkl", "dest_hex_encoding.pkl"]
    for ef in enc_files:
        path = models_dir / ef
        if path.exists():
            print(f"\n--- {ef} ---")
            info = inspect_encoding_file(path)
            for k, v in info.items():
                print(f"  {k}: {v}")
    
    # 3. Inspect CSV data
    print("\n\n### DATA FILES ###\n")
    csv_path = data_dir / "uber_data.csv"
    if csv_path.exists():
        print(f"\n--- uber_data.csv ---")
        info = inspect_csv(str(csv_path))
        for k, v in info.items():
            print(f"  {k}: {v}")
    
    drivers_path = data_dir / "drivers.csv"
    if drivers_path.exists():
        print(f"\n--- drivers.csv ---")
        info = inspect_csv(str(drivers_path))
        for k, v in info.items():
            print(f"  {k}: {v}")
    
    print("\n" + "=" * 70)
    print("INSPECTION COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
