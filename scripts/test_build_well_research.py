import importlib.util
import tempfile
import unittest
from pathlib import Path

import pandas as pd


SCRIPT = Path(__file__).with_name("build_well_research.py")
spec = importlib.util.spec_from_file_location("build_well_research", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def write_fixture(data_dir: Path, filename: str, rows: list[dict]) -> None:
    pd.DataFrame(rows).to_parquet(data_dir / filename, index=False)


class DecomResearchTests(unittest.TestCase):
    def test_filters_decom_data_by_lease_api_and_min_cost(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            write_fixture(
                data_dir,
                "df_mv_decom_cost_totals.parquet",
                [
                    {"AUTH_TYPE_CODE": "LSE", "AUTH_NUMBER": "G34454", "TYPE": "Wells Decom Cost", "CNT": 1, "P50_COST": 100, "P70_COST": 150, "P90_COST": 200, "DTR_COST": 0},
                    {"AUTH_TYPE_CODE": "LSE", "AUTH_NUMBER": "G99999", "TYPE": "Wells Decom Cost", "CNT": 1, "P50_COST": 900, "P70_COST": 950, "P90_COST": 1000, "DTR_COST": 0},
                ],
            )
            write_fixture(
                data_dir,
                "df_mv_decom_cost_spud_well.parquet",
                [
                    {"API_WELL_NUMBER": "123", "BOTM_LEASE_NUM": "G34454", "SURF_LEASE_NUM": "G34454", "WELL_NAME": "A001", "WELL_INST_DCOM_P50": 110, "WELL_INST_DCOM_P70": 160, "WELL_INST_DCOM_P90": 210, "WELL_INST_DCOM_INDTR": 0, "BOTM_AREA_CODE": "GC", "BOTM_BLOCK_NUM": "100", "BOREHOLE_STAT_CD": "COM", "EFFECTIVE_DATE": "2020-01-01"},
                    {"API_WELL_NUMBER": "456", "BOTM_LEASE_NUM": "G34454", "SURF_LEASE_NUM": "G34454", "WELL_NAME": "A002", "WELL_INST_DCOM_P50": 10, "WELL_INST_DCOM_P70": 20, "WELL_INST_DCOM_P90": 30, "WELL_INST_DCOM_INDTR": 0, "BOTM_AREA_CODE": "GC", "BOTM_BLOCK_NUM": "100", "BOREHOLE_STAT_CD": "TA", "EFFECTIVE_DATE": "2020-01-01"},
                ],
            )
            write_fixture(
                data_dir,
                "df_mv_decom_cost_estimates.parquet",
                [
                    {"LEASE_NUMBER": "34454", "LEASE_STATUS_CD": "ACTIVE", "BLK_MAX_WTR_DPTH": 5000, "PA_ADJUSTMENT_FL": "Y", "WELL_INST_DCOM_COUNT": 1, "WELL_PRP_DCOM_COUNT": 0, "PTFRM_INST_DCOM_COUNT": 0, "PTFRM_PRP_SITE_CLRNCE_COUNT": 0, "PTFRM_PRP_DCOM_COUNT": 0, "PTFRM_INST_SITE_CLRNCE_COUNT": 0, "PPL_INST_DCOM_COUNT": 0, "PPL_PRP_DCOM_COUNT": 0, "AREA_CODE": "GC", "BLOCK_NUMBER": "100", "UPDATED_DATE": "2020-01-01", "ROW_NUMBER": "", "RUE_NUMBER": ""},
                ],
            )

            result = mod.build_decom_research(
                data_dir=data_dir,
                lease="G34454",
                api="123",
                area=None,
                block=None,
                min_cost=100,
                cost_case="p90",
                pa_adjustment="Y",
                limit=10,
            )

        self.assertEqual(result["filters"]["lease"], "G34454")
        self.assertEqual(result["sections"]["totals"]["records"], 1)
        self.assertEqual(result["sections"]["installed_wells"]["records"], 1)
        self.assertEqual(result["sections"]["lease_estimates"]["records"], 1)
        self.assertEqual(result["sections"]["installed_wells"]["sample"][0]["API_WELL_NUMBER"], "123")

    def test_api_only_decom_query_does_not_return_unrelated_global_totals(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            write_fixture(
                data_dir,
                "df_mv_decom_cost_totals.parquet",
                [
                    {"AUTH_TYPE_CODE": "LSE", "AUTH_NUMBER": "G34454", "TYPE": "Wells Decom Cost", "CNT": 1, "P50_COST": 100, "P70_COST": 150, "P90_COST": 200, "DTR_COST": 0},
                    {"AUTH_TYPE_CODE": "LSE", "AUTH_NUMBER": "G99999", "TYPE": "Wells Decom Cost", "CNT": 1, "P50_COST": 900, "P70_COST": 950, "P90_COST": 1000, "DTR_COST": 0},
                ],
            )
            write_fixture(
                data_dir,
                "df_mv_decom_cost_spud_well.parquet",
                [
                    {"API_WELL_NUMBER": "123", "BOTM_LEASE_NUM": "G34454", "SURF_LEASE_NUM": "G34454", "WELL_NAME": "A001", "WELL_INST_DCOM_P50": 110, "WELL_INST_DCOM_P70": 160, "WELL_INST_DCOM_P90": 210, "WELL_INST_DCOM_INDTR": 0, "BOTM_AREA_CODE": "GC", "BOTM_BLOCK_NUM": "100", "BOREHOLE_STAT_CD": "COM", "EFFECTIVE_DATE": "2020-01-01"},
                ],
            )

            result = mod.build_decom_research(
                data_dir=data_dir,
                lease=None,
                api="123",
                area=None,
                block=None,
                min_cost=None,
                cost_case="p90",
                pa_adjustment=None,
                limit=10,
            )

        self.assertEqual(result["sections"]["totals"]["records"], 1)
        self.assertEqual(result["sections"]["totals"]["sample"][0]["AUTH_NUMBER"], "G34454")


if __name__ == "__main__":
    unittest.main()
