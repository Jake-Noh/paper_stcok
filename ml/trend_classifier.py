from data.db import get_monthly_sales, get_products, get_conn


class TrendClassifier:
    def _linear_slope(self, values):
        """Return normalized annual slope as fraction of mean."""
        n = len(values)
        if n < 2:
            return 0.0
        x = list(range(n))
        x_mean = sum(x) / n
        y_mean = sum(values) / n
        if y_mean == 0:
            return 0.0
        numerator = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, values))
        denominator = sum((xi - x_mean) ** 2 for xi in x)
        if denominator == 0:
            return 0.0
        monthly_slope = numerator / denominator  # tons/month
        # Annualize and normalize
        annual_slope_pct = (monthly_slope * 12) / y_mean
        return annual_slope_pct

    def classify(self, product_id):
        """
        Classify trend based on last 12 months actual sales.
        slope > +5%/year -> 'growth'
        slope < -5%/year -> 'decline'
        else -> 'stable'
        """
        records = get_monthly_sales(product_id, window_months=12)
        records = sorted(records, key=lambda r: r["yyyymm"])
        actuals = [r["actual_qty"] for r in records if r.get("actual_qty") is not None]

        if len(actuals) < 3:
            return "stable"

        slope_pct = self._linear_slope(actuals)

        if slope_pct > 0.05:
            return "growth"
        elif slope_pct < -0.05:
            return "decline"
        else:
            return "stable"

    def update_all_products(self):
        """Run classify for all products and update product.trend in DB."""
        products = get_products()
        results = {}
        from data.db import get_conn as _get_conn
        with _get_conn() as conn:
            for p in products:
                pid = p["product_id"]
                trend = self.classify(pid)
                conn.execute(
                    "UPDATE product SET trend=? WHERE product_id=?",
                    (trend, pid),
                )
                results[pid] = trend
        return results
