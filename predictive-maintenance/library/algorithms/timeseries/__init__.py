"""
Time series forecasting algorithm adapters.
"""

from .xgboost_ts import XGBoostTimeSeriesAdapter

__all__ = [
    "XGBoostTimeSeriesAdapter",
]
