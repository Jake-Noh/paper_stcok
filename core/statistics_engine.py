import math
from data.db import get_monthly_sales, get_leadtime_records

WORKING_DAYS = 22


class StatisticsEngine:
    OUTLIER_THRESHOLD_DAYS = 30
    MIN_SAMPLE_SIZE = 12

    def calc_sigma_d(self, product_id, window_months=36):
        """
        Compute monthly demand standard deviation from sales deviations.
        Returns daily sigma_d = monthly_sigma_d / working_days.
        """
        records = get_monthly_sales(product_id, window_months)
        deviations = [r["deviation"] for r in records if r.get("deviation") is not None]

        if len(deviations) < 2:
            # Not enough data; use 10% of average plan as fallback
            plans = [r["plan_qty"] for r in records if r.get("plan_qty") is not None]
            avg_plan = sum(plans) / len(plans) if plans else 3000.0
            monthly_sigma = avg_plan * 0.10
        else:
            n = len(deviations)
            mean = sum(deviations) / n
            variance = sum((d - mean) ** 2 for d in deviations) / (n - 1)
            monthly_sigma = math.sqrt(variance)

        # Convert monthly sigma to daily sigma
        daily_sigma = monthly_sigma / WORKING_DAYS
        return daily_sigma

    def calc_sigma_lt(self, product_id, window_months=12, use_weighted=False):
        """
        Compute average LT and LT standard deviation from lead time records.
        Uses lt_adjusted (outlier-corrected) values.
        Returns (avg_lt, sigma_lt).
        """
        records = get_leadtime_records(product_id, window_months)
        lt_values = [r["lt_adjusted"] for r in records if r.get("lt_adjusted") is not None]
        weights = [r.get("weight_qty") or 1.0 for r in records if r.get("lt_adjusted") is not None]

        if not lt_values:
            return 5.0, 1.0  # Fallback defaults

        if use_weighted and any(w != 1.0 for w in weights):
            total_weight = sum(weights)
            avg_lt = sum(v * w for v, w in zip(lt_values, weights)) / total_weight
            variance = sum(w * (v - avg_lt) ** 2 for v, w in zip(lt_values, weights)) / total_weight
        else:
            n = len(lt_values)
            avg_lt = sum(lt_values) / n
            if n < 2:
                variance = 0.0
            else:
                variance = sum((v - avg_lt) ** 2 for v in lt_values) / (n - 1)

        sigma_lt = math.sqrt(variance)
        return avg_lt, sigma_lt

    def get_sample_count(self, product_id, window_months=36):
        """Return number of monthly sales records available."""
        records = get_monthly_sales(product_id, window_months)
        return len([r for r in records if r.get("actual_qty") is not None])
