import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_well_research.py"
spec = importlib.util.spec_from_file_location("build_well_research", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def write_fixture(data_dir: Path, filename: str, rows: list[dict]) -> None:
    pd.DataFrame(rows).to_parquet(data_dir / filename, index=False)


def decom_total_row(auth_number: str, p50: int, p70: int, p90: int) -> dict:
    return {
        "AUTH_TYPE_CODE": "LSE",
        "AUTH_NUMBER": auth_number,
        "TYPE": "Wells Decom Cost",
        "CNT": 1,
        "P50_COST": p50,
        "P70_COST": p70,
        "P90_COST": p90,
        "DTR_COST": 0,
    }


def decom_totals_rows() -> list[dict]:
    return [decom_total_row("G34454", 100, 150, 200), decom_total_row("G99999", 900, 950, 1000)]


def decom_spud_well_row(api: str, name: str, p50: int, p70: int, p90: int, status: str) -> dict:
    return {
        "API_WELL_NUMBER": api,
        "BOTM_LEASE_NUM": "G34454",
        "SURF_LEASE_NUM": "G34454",
        "WELL_NAME": name,
        "WELL_INST_DCOM_P50": p50,
        "WELL_INST_DCOM_P70": p70,
        "WELL_INST_DCOM_P90": p90,
        "WELL_INST_DCOM_INDTR": 0,
        "BOTM_AREA_CODE": "GC",
        "BOTM_BLOCK_NUM": "100",
        "BOREHOLE_STAT_CD": status,
        "EFFECTIVE_DATE": "2020-01-01",
    }


def decom_spud_well_rows(include_unmatched: bool = True) -> list[dict]:
    rows = [decom_spud_well_row("123", "A001", 110, 160, 210, "COM")]
    if include_unmatched:
        rows.append(decom_spud_well_row("456", "A002", 10, 20, 30, "TA"))
    return rows


def decom_estimate_rows() -> list[dict]:
    zero_count_fields = [
        "WELL_PRP_DCOM_COUNT",
        "PTFRM_INST_DCOM_COUNT",
        "PTFRM_PRP_SITE_CLRNCE_COUNT",
        "PTFRM_PRP_DCOM_COUNT",
        "PTFRM_INST_SITE_CLRNCE_COUNT",
        "PPL_INST_DCOM_COUNT",
        "PPL_PRP_DCOM_COUNT",
    ]
    row = {field: 0 for field in zero_count_fields}
    row.update(
        {
            "LEASE_NUMBER": "34454",
            "LEASE_STATUS_CD": "ACTIVE",
            "BLK_MAX_WTR_DPTH": 5000,
            "PA_ADJUSTMENT_FL": "Y",
            "WELL_INST_DCOM_COUNT": 1,
            "AREA_CODE": "GC",
            "BLOCK_NUMBER": "100",
            "UPDATED_DATE": "2020-01-01",
            "ROW_NUMBER": "",
            "RUE_NUMBER": "",
        }
    )
    return [row]


def lease_fixture_rows() -> dict[str, list[dict]]:
    return {
        "df_boreholes.parquet": [
            {
                "API_WELL_NUMBER": "123456789000",
                "WELL_NAME": "A-1",
                "WELL_NAME_SUFFIX": "ST01",
                "SURF_LEASE_NUMBER": "G36102",
                "BOTM_LEASE_NUMBER": "G36102",
                "SURF_AREA_CODE": "AC",
                "SURF_BLOCK_NUMBER": "336",
                "BOTM_AREA_CODE": "AC",
                "BOTM_BLOCK_NUMBER": "336",
            }
        ],
        "df_lease_data.parquet": [
            {
                "LEASE_NUMBER": "G36102",
                "LEASE_STATUS_CODE": "UNIT",
                "LEASE_EFFECTIVE_DATE": "2020-01-01",
                "LEASE_EXPIRATION_DATE": "2030-01-01",
                "CURRENT_AREA": 5760.0,
                "ROYALTY_RATE": 18.75,
            }
        ],
        "df_lease_owner_designated_operator.parquet": [
            {
                "LEASE_NUMBER": "G36102",
                "MMS_COMPANY_NUM": "00002",
                "ASSIGNMENT_PCT": 50.0,
                "ASGN_STATUS_CODE": "C",
                "ASGN_APRV_DATE": "2024-10-01",
                "ASGN_EFF_DATE": "2024-10-01",
                "LEASE_DESIG_DATE": "2024-10-05",
                "OPERATOR_NUM": "00003",
            }
        ],
        "df_lease_owner.parquet": [
            {
                "LEASE_NUMBER": "G36102",
                "MMS_COMPANY_NUM": "00001",
                "ASSIGNMENT_PCT": 100.0,
                "ASGN_STATUS_CODE": "T",
                "ASGN_APRV_DATE": "2022-01-01",
                "ASGN_EFF_DATE": "2022-01-01",
                "ASGN_TERM_DATE": "2023-01-01",
                "OWNER_GROUP_CODE": "",
                "SN_LSE_OWNER": "10",
            },
            {
                "LEASE_NUMBER": "G36102",
                "MMS_COMPANY_NUM": "00002",
                "ASSIGNMENT_PCT": 50.0,
                "ASGN_STATUS_CODE": "C",
                "ASGN_APRV_DATE": "2024-10-01",
                "ASGN_EFF_DATE": "2024-10-01",
                "ASGN_TERM_DATE": None,
                "OWNER_GROUP_CODE": "",
                "SN_LSE_OWNER": "11",
            },
        ],
        "df_lease_owner_remarks.parquet": [
            {
                "LEASE_NUMBER": "G36102",
                "MMS_COMPANY_NUM": "00002",
                "ASSIGNMENT_PCT": 50.0,
                "ASGN_APRV_DATE": "2024-10-01",
                "ASGN_EFF_DATE": "2024-10-01",
                "OWNER_ALIQUOT_CD": "1",
                "OWNER_ALQT_DESC": "All rights",
                "ALIQUOT_AREA": 2880.0,
            }
        ],
        "df_company_all.parquet": [
            {
                "MMS_COMPANY_NUM": "00001",
                "BUS_ASC_NAME": "Seller Energy",
                "MMS_START_DATE": "2020-01-01",
                "MMS_TERM_DATE": None,
            },
            {
                "MMS_COMPANY_NUM": "00002",
                "BUS_ASC_NAME": "Buyer Offshore",
                "MMS_START_DATE": "2024-01-01",
                "MMS_TERM_DATE": None,
            },
            {
                "MMS_COMPANY_NUM": "00003",
                "BUS_ASC_NAME": "Operator LLC",
                "MMS_START_DATE": "2024-01-01",
                "MMS_TERM_DATE": None,
            },
        ],
    }


class DecomResearchTests(unittest.TestCase):
    def test_emit_result_does_not_crash_on_non_gbk_stdout(self):
        result = {"text": "¿"}
        stdout = io.TextIOWrapper(io.BytesIO(), encoding="gbk", errors="strict")

        with patch.object(sys, "stdout", stdout):
            mod.emit_result(result, "json", None, mod.print_dossier)

    def test_markdown_dossier_output_cleans_war_remarks(self):
        dossier = {
            "api_query": "123",
            "data_dir": "fixture",
            "identity": {},
            "availability": {"war_remarks": 1},
            "sections": {
                "war_remarks": {
                    "records": 1,
                    "sample": [{"TEXT_REMARK": "remark " * 100}],
                }
            },
        }
        stdout = io.StringIO()

        with patch.object(sys, "stdout", stdout):
            mod.emit_result(dossier, "markdown", None, mod.print_dossier)

        self.assertIn("remark", stdout.getvalue())

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
                decom_totals_rows(),
            )
            write_fixture(
                data_dir,
                "df_mv_decom_cost_spud_well.parquet",
                decom_spud_well_rows(),
            )
            write_fixture(
                data_dir,
                "df_mv_decom_cost_estimates.parquet",
                decom_estimate_rows(),
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
                decom_totals_rows(),
            )
            write_fixture(
                data_dir,
                "df_mv_decom_cost_spud_well.parquet",
                decom_spud_well_rows(include_unmatched=False),
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

    def test_dossier_includes_lease_block_ownership_and_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            for filename, rows in lease_fixture_rows().items():
                write_fixture(data_dir, filename, rows)

            result = mod.build_dossier(data_dir, "123456789000", limit=10, min_step=100.0)

        lease = result["sections"]["lease_information"]
        self.assertEqual(lease["records"], 2)
        self.assertEqual(lease["lease_numbers"], ["G36102"])
        self.assertEqual(lease["lease_summary"]["sample"][0]["Block"], "336")
        self.assertEqual(lease["current_owners"]["sample"][0]["Owner Company"], "Buyer Offshore")
        self.assertEqual(lease["current_owners"]["sample"][0]["Designated Operator"], "Operator LLC")
        self.assertEqual(lease["ownership_detail"]["sample"][0]["Owner Aliquot Description"], "All rights")
        self.assertEqual(lease["assignment_history"]["sample"][0]["Assignment Status"], "Current")
        self.assertIn("do not directly name legal buyer/seller pairs", lease["limitations"][0])

    def test_lease_owner_remarks_can_be_ranked_by_assignment_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            write_fixture(
                data_dir,
                "df_lease_owner_remarks.parquet",
                [
                    {"LEASE_NUMBER": "G1", "MMS_COMPANY_NUM": "1", "ASSIGNMENT_PCT": 25.0},
                    {"LEASE_NUMBER": "G2", "MMS_COMPANY_NUM": "2", "ASSIGNMENT_PCT": 75.0},
                ],
            )

            result = mod.build_ranked_dataset(
                data_dir=data_dir,
                table="lease_owner_remarks",
                rank_by="assignment_pct",
                limit=1,
            )

        self.assertEqual(result["rank_by"], "ASSIGNMENT_PCT")
        self.assertEqual(result["rank_unit"], "pct")
        self.assertEqual(result["sample"][0]["LEASE_NUMBER"], "G2")


if __name__ == "__main__":
    unittest.main()
