from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from monitoring_news_events.config import load_project_config
from monitoring_news_events.pipeline import MonitoringPipeline


class PipelineTestCase(unittest.TestCase):
    def test_generates_report_from_local_fixture(self) -> None:
        config = load_project_config(ROOT / "tests" / "fixtures" / "test_config.toml")
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config.report_dir = temp_path / "reports"
            config.data_dir = temp_path / "data"

            pipeline = MonitoringPipeline(config)
            artifact = pipeline.run("fixture-geo", notify=False, force_disable_llm=True)

            self.assertGreaterEqual(len(artifact.report.raw_signals), 3)
            self.assertGreaterEqual(len(artifact.report.angles), 4)
            self.assertGreaterEqual(len(artifact.report.headlines), 6)
            self.assertTrue(artifact.markdown_path.exists())
            self.assertTrue(artifact.json_path.exists())
            self.assertIn("fixture-geo", artifact.json_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
