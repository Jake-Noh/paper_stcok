from data.db import get_stock_results, get_leadtime_records
from core.statistics_engine import StatisticsEngine


class RuleEngine:
    def __init__(self):
        self.stats_engine = StatisticsEngine()

    def apply_all_rules(self, product_id, result):
        """
        Apply business rules to a result dict.
        Adds 'flags' list to result in place and returns modified result.

        Rules:
        1. Warn if sample_count < 12
        2. Recommend service level adjustment based on trend
        3. Warn if sigma_d changed > 20% vs previous month
        4. Enforce minimum 1 day operating stock
        5. Warn if outlier rate > 20% in recent 12 months
        """
        flags = []

        # Rule 1: Insufficient sample data
        sample_count = self.stats_engine.get_sample_count(product_id, window_months=36)
        if sample_count < 12:
            flags.append({
                "level": "warning",
                "code": "INSUFFICIENT_SAMPLE",
                "message": f"샘플 데이터 부족: {sample_count}개 (최소 12개 권장). 통계 신뢰도가 낮을 수 있습니다.",
            })

        # Rule 2: Service level recommendation based on trend
        from data.db import get_products
        products = {p["product_id"]: p for p in get_products()}
        product = products.get(product_id, {})
        trend = product.get("trend", "stable")
        current_sl = result.get("service_level", 0.95)
        if trend == "growth" and current_sl < 0.99:
            flags.append({
                "level": "info",
                "code": "SL_RECOMMEND_UP",
                "message": f"수요 성장 추세 감지: 서비스 수준을 {int(current_sl*100)}%에서 99%로 상향 검토 권장.",
            })
        elif trend == "decline" and current_sl > 0.90:
            flags.append({
                "level": "info",
                "code": "SL_RECOMMEND_DOWN",
                "message": f"수요 감소 추세 감지: 서비스 수준을 {int(current_sl*100)}%에서 90%로 하향 검토 권장.",
            })

        # Rule 3: sigma_d change > 20% vs previous result
        prev_results = get_stock_results(product_id, limit=2)
        if len(prev_results) >= 1:
            prev_sigma = prev_results[0].get("sigma_d", 0)
            curr_sigma = result.get("sigma_d", 0)
            if prev_sigma > 0:
                change_rate = abs(curr_sigma - prev_sigma) / prev_sigma
                if change_rate > 0.20:
                    flags.append({
                        "level": "warning",
                        "code": "SIGMA_D_CHANGE",
                        "message": f"수요편차(σd) 전월 대비 {change_rate*100:.1f}% 변동. 데이터 이상 여부 확인 필요.",
                    })

        # Rule 4: Minimum 1 day operating stock
        if result.get("operating_days", 0) < 1.0:
            result["operating_days"] = max(result.get("operating_days", 0), 1.0)
            d_prime = result.get("d_prime", 1.0)
            result["operating_stock"] = max(result.get("operating_stock", 0), d_prime)
            flags.append({
                "level": "warning",
                "code": "MIN_STOCK_ENFORCED",
                "message": "운영재고 최소 1일치 기준 적용됨.",
            })

        # Rule 5: Outlier rate > 20% in recent 12 months
        lt_records = get_leadtime_records(product_id, window_months=12)
        if lt_records:
            outlier_count = sum(1 for r in lt_records if r.get("is_outlier"))
            outlier_rate = outlier_count / len(lt_records)
            if outlier_rate > 0.20:
                flags.append({
                    "level": "warning",
                    "code": "HIGH_OUTLIER_RATE",
                    "message": f"최근 12개월 리드타임 이상치 비율 {outlier_rate*100:.1f}% (기준: 20%). 공급 안정성 검토 필요.",
                })

        result["flags"] = flags
        return result
