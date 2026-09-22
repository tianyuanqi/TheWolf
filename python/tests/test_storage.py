import os
import tempfile
import unittest

from pmi.storage import DEMO_DOCUMENT_ID, demo_research, document_evidence, initialize_demo_data


class StorageTests(unittest.TestCase):
    def test_demo_records_are_persistent_and_readable(self):
        with tempfile.TemporaryDirectory() as directory:
            previous = os.environ.get("WOLF_DATA_ROOT")
            os.environ["WOLF_DATA_ROOT"] = directory
            try:
                initialize_demo_data()
                initialize_demo_data()
                research = demo_research()
                evidence = document_evidence(DEMO_DOCUMENT_ID)
            finally:
                if previous is None:
                    os.environ.pop("WOLF_DATA_ROOT", None)
                else:
                    os.environ["WOLF_DATA_ROOT"] = previous

        self.assertEqual(research["trade_date"], "2026-09-18")
        self.assertEqual(research["currency"], "CNY")
        self.assertIsNotNone(evidence)
        self.assertEqual(evidence["evidence_page"], 1)
