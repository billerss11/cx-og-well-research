import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd


SCRIPT = Path(__file__).with_name("build_well_research.py")
spec = importlib.util.spec_from_file_location("build_well_research", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def write_fixture(data_dir: Path, filename: str, rows: list[dict]) -> None:
    pd.DataFrame(rows).to_parquet(data_dir / filename, index=False)


class DecomResearchTests(unittest.TestCase):
    def test_emit_result_does_not_crash_on_non_gbk_stdout(self):
        result = {"text": "¿"}
        stdout = io.TextIOWrapper(io.BytesIO(), encoding="gbk", errors="strict")

        with patch.object(sys, "stdout", stdout):
            mod.emit_result(result, "json", None, mod.print_dossier)

    def test_ranked_dataset_accepts_metric_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            write_fixture(
                data_dir,
                "df_wellpath_metrics.parquet",
                [
                    {"API Number": "111", "calc_max_horizontal_departure_ft": 300.0},
                    {"API Number": "222", "calc_max_horizontal_departure_ft": 900.0},
                ],
            )

            result = mod.build_ranked_dataset(
                data_dir=data_dir,
                table="wellpath_metrics",
                rank_by="horizontal_departure",
                limit=1,
            )

        self.assertEqual(result["requested_rank_by"], "horizontal_departure")
        self.assertEqual(result["rank_by"], "calc_max_horizontal_departure_ft")
        self.assertEqual(result["sample"][0]["API Number"], "222")

    def test_ranked_production_dataset_reports_rank_unit(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            write_fixture(
                data_dir,
                "df_gom_production.parquet",
                [
                    {"Api Well Number": "111", "Monthly Oil Volume": 100.0},
                    {"Api Well Number": "222", "Monthly Oil Volume": 300.0},
                ],
            )

            result = mod.build_ranked_dataset(
                data_dir=data_dir,
                table="production",
                rank_by="production_oil",
                limit=1,
            )

        self.assertEqual(result["rank_by"], "Monthly Oil Volume")
        self.assertEqual(result["rank_unit"], "bbl")

    def test_describe_production_reports_daily_average_units(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            write_fixture(
                data_dir,
                "df_gom_production.parquet",
                [
                    {
                        "Api Well Number": "111",
                        "Day_Aver_Oil": 10.0,
                        "Day_Aver_Water": 2.0,
                        "Day_Aver_Gas": 100.0,
                        "Day_Aver_Oil_bbl_per_day": 10.0,
                        "Day_Aver_Water_bbl_per_day": 2.0,
                        "Day_Aver_Gas_mcf_per_day": 100.0,
                    },
                ],
            )

            result = mod.describe_table(data_dir, "production", limit=1)

        self.assertEqual(result["units"]["Day_Aver_Oil"], "bbl/day")
        self.assertEqual(result["units"]["Day_Aver_Water"], "bbl/day")
        self.assertEqual(result["units"]["Day_Aver_Gas"], "mcf/day")
        self.assertEqual(result["units"]["Day_Aver_Oil_bbl_per_day"], "bbl/day")
        self.assertEqual(result["units"]["Day_Aver_Water_bbl_per_day"], "bbl/day")
        self.assertEqual(result["units"]["Day_Aver_Gas_mcf_per_day"], "mcf/day")

    def test_describe_table_reports_columns_units_aliases_and_sample(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            write_fixture(
                data_dir,
                "df_wellpath_metrics.parquet",
                [
                    {
                        "API Number": "111",
                        "calc_max_horizontal_departure_ft": 300.0,
                        "calc_trajectory_type": "horizontal",
                    },
                    {
                        "API Number": "222",
                        "calc_max_horizontal_departure_ft": 900.0,
                        "calc_trajectory_type": "horizontal",
                    },
                ],
            )

            result = mod.describe_table(data_dir, "wellpath_metrics", limit=1)

        column_names = [column["name"] for column in result["columns"]]
        self.assertEqual(result["kind"], "table_description")
        self.assertEqual(result["table"], "wellpath_metrics")
        self.assertEqual(result["source"], "df_wellpath_metrics.parquet")
        self.assertEqual(result["records_sampled"], 1)
        self.assertIn("calc_max_horizontal_departure_ft", column_names)
        self.assertEqual(result["units"]["calc_max_horizontal_departure_ft"], "ft")
        self.assertEqual(result["metric_aliases"]["horizontal_departure"], "calc_max_horizontal_departure_ft")
        self.assertEqual(result["sample"][0]["API Number"], "111")

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
