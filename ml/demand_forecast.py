import math
from data.db import get_monthly_sales, get_macro_indicator
from ml.ecos_client import EcosApiClient


class DemandForecaster:
    def __init__(self):
        self.models = {}  # product_id -> model state

    def _get_sales_series(self, product_id, window_months=36):
        records = get_monthly_sales(product_id, window_months)
        # Sort ascending by yyyymm
        records = sorted(records, key=lambda r: r["yyyymm"])
        return records

    def _get_gdp_for_month(self, yyyymm):
        """Return GDP growth rate for the quarter containing yyyymm."""
        year = int(str(yyyymm)[:4])
        month = int(str(yyyymm)[4:])
        quarter = f"Q{(month - 1) // 3 + 1}"
        indicator_key = f"GDP_growth_{quarter}"
        cached = get_macro_indicator(indicator_key, f"{year}{quarter}")
        if cached:
            return cached["value"], "cache"
        # Fallback: try fetching
        try:
            client = EcosApiClient()
            result = client.fetch_gdp_growth(year)
            return result.get(quarter, 2.5), result.get("source", "default")
        except Exception:
            return 2.5, "default"

    def _linear_regression(self, x_vals, y_vals):
        """Simple OLS linear regression. Returns (slope, intercept)."""
        n = len(x_vals)
        if n < 2:
            return 0.0, y_vals[0] if y_vals else 0.0
        x_mean = sum(x_vals) / n
        y_mean = sum(y_vals) / n
        numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_vals, y_vals))
        denominator = sum((x - x_mean) ** 2 for x in x_vals)
        slope = numerator / denominator if denominator != 0 else 0.0
        intercept = y_mean - slope * x_mean
        return slope, intercept

    def _calc_mape(self, actuals, predictions):
        """Mean absolute percentage error."""
        errors = []
        for a, p in zip(actuals, predictions):
            if a != 0:
                errors.append(abs((a - p) / a))
        return sum(errors) / len(errors) * 100 if errors else 0.0

    def _ema_forecast(self, values, alpha=None):
        """Exponential Moving Average (EMA). If alpha is None, optimize it."""
        if not values:
            return 0.0, 0.2

        if alpha is None:
            best_alpha = 0.2
            best_mse = float("inf")
            for trial_alpha in [i / 10 for i in range(1, 10)]:
                ema = values[0]
                mse = 0.0
                for i in range(1, len(values)):
                    pred = ema
                    mse += (values[i] - pred) ** 2
                    ema = trial_alpha * values[i] + (1 - trial_alpha) * ema
                mse /= max(len(values) - 1, 1)
                if mse < best_mse:
                    best_mse = mse
                    best_alpha = trial_alpha
            alpha = best_alpha

        ema = values[0]
        for v in values[1:]:
            ema = alpha * v + (1 - alpha) * ema
        return ema, alpha

    def fit(self, product_id, window_months=36):
        """Fit LinearRegression and EMA models."""
        records = self._get_sales_series(product_id, window_months)
        actuals = [r["actual_qty"] for r in records if r.get("actual_qty") is not None]
        yyyymms = [r["yyyymm"] for r in records if r.get("actual_qty") is not None]

        if len(actuals) < 3:
            self.models[product_id] = {
                "actuals": actuals,
                "yyyymms": yyyymms,
                "lr": (0.0, actuals[-1] if actuals else 3000.0),
                "ema_alpha": 0.2,
                "last_ema": actuals[-1] if actuals else 3000.0,
            }
            return

        n = len(actuals)
        x_indices = list(range(n))
        gdp_values = []
        for yyyymm in yyyymms:
            gdp, _ = self._get_gdp_for_month(yyyymm)
            gdp_values.append(gdp)

        # Feature: combined index + gdp influence
        x_combined = [idx + gdp * 10 for idx, gdp in zip(x_indices, gdp_values)]
        slope, intercept = self._linear_regression(x_combined, actuals)

        last_ema, best_alpha = self._ema_forecast(actuals)

        self.models[product_id] = {
            "actuals": actuals,
            "yyyymms": yyyymms,
            "lr": (slope, intercept),
            "n": n,
            "ema_alpha": best_alpha,
            "last_ema": last_ema,
            "gdp_values": gdp_values,
        }

    def predict_next_month(self, product_id):
        """
        Predict next month demand.
        Returns dict with lr_forecast, ema_forecast, recommended, model_used, mape, gdp_used, gdp_source.
        """
        if product_id not in self.models:
            self.fit(product_id)

        model = self.models.get(product_id, {})
        actuals = model.get("actuals", [3000.0])
        n = model.get("n", len(actuals))
        slope, intercept = model.get("lr", (0.0, actuals[-1] if actuals else 3000.0))
        ema_alpha = model.get("ema_alpha", 0.2)
        last_ema = model.get("last_ema", actuals[-1] if actuals else 3000.0)

        from datetime import datetime, timedelta
        next_month_idx = n
        gdp_val, gdp_src = self._get_gdp_for_month(
            (datetime.now().replace(day=1)).strftime("%Y%m")
        )
        x_next = next_month_idx + gdp_val * 10
        lr_forecast = slope * x_next + intercept
        lr_forecast = max(lr_forecast, 0.0)

        ema_forecast = last_ema  # Last EMA value as one-step-ahead forecast

        # MAPE on last 6 months
        if len(actuals) >= 3:
            gdp_vals = model.get("gdp_values", [2.5] * n)
            lr_preds = [slope * (i + gdp_vals[i] * 10) + intercept for i in range(n)]
            mape = self._calc_mape(actuals, lr_preds)
        else:
            mape = 0.0

        # Recommend: if MAPE < 10% prefer LR, else EMA
        if mape < 10.0:
            recommended = lr_forecast
            model_used = "LinearRegression"
        else:
            recommended = ema_forecast
            model_used = "EMA"

        return {
            "lr_forecast": round(lr_forecast, 1),
            "ema_forecast": round(ema_forecast, 1),
            "recommended": round(recommended, 1),
            "model_used": model_used,
            "mape": round(mape, 2),
            "gdp_used": gdp_val,
            "gdp_source": gdp_src,
        }

    def get_forecast_as_reference(self, product_id, plan_qty):
        """
        Compare ML forecast vs plan_qty.
        Returns reference dict; never overrides plan.
        """
        try:
            forecast = self.predict_next_month(product_id)
        except Exception as e:
            return {"error": str(e), "plan_qty": plan_qty, "flag": False}

        recommended = forecast["recommended"]
        diff_pct = abs(recommended - plan_qty) / plan_qty * 100 if plan_qty > 0 else 0
        flag = diff_pct > 10.0

        return {
            "plan_qty": plan_qty,
            "ml_forecast": recommended,
            "model_used": forecast["model_used"],
            "mape": forecast["mape"],
            "diff_pct": round(diff_pct, 1),
            "flag": flag,
            "flag_message": (
                f"ML 예측({recommended:,.0f}톤)과 계획({plan_qty:,.0f}톤)의 차이가 {diff_pct:.1f}%입니다. 계획 재검토를 권장합니다."
                if flag else ""
            ),
            "gdp_used": forecast["gdp_used"],
            "gdp_source": forecast["gdp_source"],
        }
