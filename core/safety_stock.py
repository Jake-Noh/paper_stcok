import math

Z_TABLE = {0.90: 1.282, 0.95: 1.645, 0.99: 2.326}


class SafetyStockEngine:
    def calc_safety_stock(self, z, pc, lt, sigma_d, d_prime, sigma_lt):
        """
        Calculate safety stock using both independent and dependent formulas.

        Formula (independent):
            SS = Z * sqrt( (PC + LT) * sigma_d^2 + d'^2 * sigma_LT^2 )

        Formula (dependent):
            SS = Z * sigma_d * sqrt(PC + LT) + Z * d' * sigma_LT
        """
        demand_risk = (pc + lt) * (sigma_d ** 2)
        supply_risk = (d_prime ** 2) * (sigma_lt ** 2)
        independent = z * math.sqrt(demand_risk + supply_risk)
        dependent = z * sigma_d * math.sqrt(pc + lt) + z * d_prime * sigma_lt
        return {
            "independent": independent,
            "dependent": dependent,
            "components": {
                "demand_risk": demand_risk,
                "supply_risk": supply_risk,
            },
        }

    def calc_for_all_service_levels(self, pc, lt, sigma_d, d_prime, sigma_lt):
        """
        Calculate safety stock for 90%, 95%, and 99% service levels.
        Returns dict keyed by '90%', '95%', '99%'.
        """
        results = {}
        for level, z in Z_TABLE.items():
            label = f"{int(level * 100)}%"
            results[label] = self.calc_safety_stock(z, pc, lt, sigma_d, d_prime, sigma_lt)
        return results
