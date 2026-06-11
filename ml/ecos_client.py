import os
import requests
from data.db import get_setting, save_macro_indicator, get_macro_indicator


class EcosApiClient:
    BASE_URL = "https://ecos.bok.or.kr/api/StatisticSearch"
    GDP_STAT_CODE = "111Y002"

    def __init__(self):
        # 우선순위: DB 설정 → Streamlit secrets → 환경변수
        api_key = get_setting("ecos_api_key")
        if not api_key:
            try:
                import streamlit as st
                api_key = st.secrets.get("ECOS_API_KEY", "")
            except Exception:
                pass
        if not api_key:
            api_key = os.environ.get("ECOS_API_KEY", "")
        self.api_key = api_key

    def _is_configured(self):
        return bool(self.api_key and self.api_key.strip())

    def fetch_gdp_growth(self, year):
        """
        Fetch quarterly GDP growth data for a given year from ECOS API.
        On failure, returns cached values from DB.
        Returns {'Q1': float, 'Q2': float, 'Q3': float, 'Q4': float, 'annual': float, 'source': str}
        """
        quarters = {"Q1": None, "Q2": None, "Q3": None, "Q4": None}
        source = "cache"

        if self._is_configured():
            url = (
                f"{self.BASE_URL}/{self.api_key}/json/kr/1/4/"
                f"{self.GDP_STAT_CODE}/Q/{year}Q1/{year}Q4"
            )
            try:
                resp = requests.get(url, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                rows = data.get("StatisticSearch", {}).get("row", [])
                for row in rows:
                    period = row.get("TIME", "")
                    try:
                        value = float(row.get("DATA_VALUE", 0))
                    except (ValueError, TypeError):
                        value = 0.0
                    # Period format: "2024Q1"
                    if period.endswith("Q1"):
                        quarters["Q1"] = value
                    elif period.endswith("Q2"):
                        quarters["Q2"] = value
                    elif period.endswith("Q3"):
                        quarters["Q3"] = value
                    elif period.endswith("Q4"):
                        quarters["Q4"] = value

                # Save to cache
                for q_key, q_val in quarters.items():
                    if q_val is not None:
                        indicator_key = f"GDP_growth_{q_key}"
                        save_macro_indicator(indicator_key, f"{year}{q_key}", q_val, "ECOS_API")

                source = "ECOS_API"
            except Exception:
                # Fall through to cached data
                source = "cache"

        # Fill missing from cache
        for q_key in ["Q1", "Q2", "Q3", "Q4"]:
            if quarters[q_key] is None:
                indicator_key = f"GDP_growth_{q_key}"
                cached = get_macro_indicator(indicator_key, f"{year}{q_key}")
                if cached:
                    quarters[q_key] = cached["value"]
                else:
                    quarters[q_key] = 2.5  # Default fallback

        valid = [v for v in quarters.values() if v is not None]
        annual = sum(valid) / len(valid) if valid else 2.5

        return {
            "Q1": quarters["Q1"],
            "Q2": quarters["Q2"],
            "Q3": quarters["Q3"],
            "Q4": quarters["Q4"],
            "annual": annual,
            "source": source,
        }

    def update_all_cached_gdp(self, from_year=2023):
        """Loop from from_year to current year and cache GDP data."""
        from datetime import datetime
        current_year = datetime.now().year
        results = {}
        for year in range(from_year, current_year + 1):
            try:
                results[year] = self.fetch_gdp_growth(year)
            except Exception as e:
                results[year] = {"error": str(e)}
        return results
