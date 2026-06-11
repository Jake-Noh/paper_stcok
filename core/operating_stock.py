from core.safety_stock import SafetyStockEngine, Z_TABLE
from core.statistics_engine import StatisticsEngine
from data.db import get_products

WORKING_DAYS = 22


class OperatingStockEngine:
    def __init__(self):
        self.safety_engine = SafetyStockEngine()
        self.stats_engine = StatisticsEngine()

    def calc_cycle_stock(self, d_prime, pc, lt):
        """Cycle stock = d' * (PC + LT) / 2"""
        return d_prime * (pc + lt) / 2

    def calc_operating_stock(self, safety_stock, cycle_stock, d_prime):
        """
        Total operating stock and days.
        Returns {'operating_stock_ton': float, 'operating_stock_days': float}
        """
        total = safety_stock + cycle_stock
        days = total / d_prime if d_prime > 0 else 0.0
        return {"operating_stock_ton": total, "operating_stock_days": days}

    def build_full_result(self, product_id, target_yyyymm, service_level, stats, plan_qty, working_days=WORKING_DAYS):
        """
        Compute full operating stock result.

        stats dict should contain: sigma_d, sigma_lt, avg_lt, z, pc
        plan_qty: monthly plan quantity (tons)
        working_days: trading days in month (default 22)

        Returns dict matching stock_result schema columns.
        """
        from datetime import datetime

        sigma_d = stats["sigma_d"]
        sigma_lt = stats["sigma_lt"]
        avg_lt = stats["avg_lt"]
        pc = stats["pc"]
        z = stats.get("z") or Z_TABLE.get(service_level, 1.645)

        d_prime = plan_qty / working_days if working_days > 0 else plan_qty / WORKING_DAYS

        ss_result = self.safety_engine.calc_safety_stock(z, pc, avg_lt, sigma_d, d_prime, sigma_lt)
        cycle_stock = self.calc_cycle_stock(d_prime, pc, avg_lt)

        op_independent = self.calc_operating_stock(ss_result["independent"], cycle_stock, d_prime)
        op_dependent = self.calc_operating_stock(ss_result["dependent"], cycle_stock, d_prime)

        # Use independent as default operating stock
        calc_yyyymm = datetime.now().strftime("%Y%m")

        return {
            "product_id": product_id,
            "calc_yyyymm": calc_yyyymm,
            "target_yyyymm": target_yyyymm,
            "service_level": service_level,
            "z_value": z,
            "sigma_d": sigma_d,
            "sigma_lt": sigma_lt,
            "avg_lt": avg_lt,
            "d_prime": d_prime,
            "safety_stock_independent": ss_result["independent"],
            "safety_stock_dependent": ss_result["dependent"],
            "cycle_stock": cycle_stock,
            "operating_stock": op_independent["operating_stock_ton"],
            "operating_days": op_independent["operating_stock_days"],
            # Extra context (not stored in DB but useful in UI)
            "operating_stock_dependent": op_dependent["operating_stock_ton"],
            "operating_days_dependent": op_dependent["operating_stock_days"],
            "demand_risk": ss_result["components"]["demand_risk"],
            "supply_risk": ss_result["components"]["supply_risk"],
        }
