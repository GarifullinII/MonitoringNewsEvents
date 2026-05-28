from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from monitoring_news_events.airtable import AirtablePublisher
from monitoring_news_events.config import load_project_config
from monitoring_news_events.models import GeoReport
from monitoring_news_events.pipeline import MonitoringPipeline


class FakeAirtableClient:
    def __init__(self) -> None:
        self.created: dict[str, list[dict]] = {}
        self.record_counter = 0

    def is_enabled(self) -> bool:
        return True

    def create_record(self, table_name: str, fields: dict) -> dict:
        return self.create_records(table_name, [fields])[0]

    def create_records(self, table_name: str, fields_list: list[dict]) -> list[dict]:
        records = self.created.setdefault(table_name, [])
        created_records: list[dict] = []
        for fields in fields_list:
            self.record_counter += 1
            record = {
                "id": f"rec{self.record_counter:04d}",
                "fields": fields,
            }
            records.append(record)
            created_records.append(record)
        return created_records

    def get_record(self, table_name: str, record_id: str) -> dict:
        if table_name != "Reports":
            raise AssertionError("Only Reports table should be polled for URL")
        return {
            "id": record_id,
            "fields": {
                "Document URL": "https://airtable.com/appDemo/pagDemo=rec0001",
            },
        }


class AirtablePublisherTestCase(unittest.TestCase):
    def test_publish_creates_report_and_child_records(self) -> None:
        config = load_project_config(ROOT / "tests" / "fixtures" / "test_config.toml")
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config.report_dir = temp_path / "reports"
            config.data_dir = temp_path / "data"

            pipeline = MonitoringPipeline(config)
            artifact = pipeline.run("fixture-geo", notify=False, force_disable_llm=True)
            report: GeoReport = artifact.report

            config.airtable.enabled = True
            config.airtable.base_id = "appDemo"
            config.airtable.report_link_field = "Document URL"

            fake_client = FakeAirtableClient()
            publisher = AirtablePublisher(config.airtable, client=fake_client)
            result = publisher.publish(
                report,
                {"markdown": artifact.markdown_path, "json": artifact.json_path},
            )

            self.assertEqual(result.report_record_id, "rec0001")
            self.assertEqual(
                result.report_url,
                "https://airtable.com/appDemo/pagDemo=rec0001",
            )
            self.assertEqual(len(fake_client.created["Reports"]), 1)
            self.assertEqual(
                len(fake_client.created["Inforeasons"]),
                len(report.raw_signals),
            )
            self.assertEqual(
                len(fake_client.created["Angles"]),
                len(report.angles),
            )
            self.assertEqual(
                len(fake_client.created["Headlines"]),
                len(report.headlines),
            )
            self.assertEqual(
                len(fake_client.created["Recommendations"]),
                len(report.recommendations),
            )
            self.assertEqual(
                len(fake_client.created["Risks"]),
                len(report.risks),
            )


if __name__ == "__main__":
    unittest.main()
