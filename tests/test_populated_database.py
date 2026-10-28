from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path

from termlv.engine import TerminologyEngine


DB_PATH = Path(__file__).resolve().parents[1] / "data" / "termlv.sqlite3"


@unittest.skipUnless(DB_PATH.exists(), "populated database is not present")
class PopulatedDatabaseSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        cls.db.row_factory = sqlite3.Row
        cls.engine = TerminologyEngine(cls.db)

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_integrity_and_population(self):
        self.assertEqual("ok", self.db.execute("PRAGMA integrity_check").fetchone()[0])
        self.assertGreater(self.db.execute("SELECT count(*) FROM concepts").fetchone()[0], 400_000)
        self.assertGreater(self.db.execute("SELECT count(*) FROM terms").fetchone()[0], 500_000)

    def test_real_ittea_penetration_testing(self):
        result = self.engine.translate_term("penetration testing", domain="cybersecurity")
        self.assertEqual("ielaušanās testēšana", result["selected"]["target_term"])
        self.assertEqual("approved", result["selected"]["approval"])

    def test_reverse_lookup_prefers_actual_translation_over_lv_only_law_record(self):
        result = self.engine.translate_term("ievainojamība", source_language="lv",
                                            target_language="en", domain="cybersecurity")
        self.assertEqual("vulnerability", result["selected"]["target_term"])

    def test_real_tbx_deprecation_annotation(self):
        result = self.engine.translate_term("bit error rate", domain="networking")
        self.assertEqual("deprecated", result["selected"]["source_status"])
        self.assertEqual("deprecated", result["selected"]["status"])

    def test_exact_cybersecurity_tm_suggestion(self):
        source = "Penetration testing identified a privilege-escalation vulnerability in the API."
        result = self.engine.translate_text(source, domain="cybersecurity")
        self.assertEqual(
            "Ielaušanās testēšanā tika atklāta API ievainojamība, kas ļauj paaugstināt privilēģijas.",
            result["sentence_suggestion"],
        )


if __name__ == "__main__":
    unittest.main()
