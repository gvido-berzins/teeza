from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from termlv.catalog import install_catalog
from termlv.db import add_concept, begin_release, connect, finish_release, initialize, rollback_source, upsert_source
from termlv.engine import TerminologyEngine
from termlv.importers import import_tbx, import_tei, import_tmx, import_wordforms
from termlv.updates import import_file, release_diff


class TerminologySystemTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = connect(Path(self.temp.name) / "test.sqlite")
        initialize(self.db)
        install_catalog(self.db)
        source = upsert_source(self.db, {
            "slug": "fixture-approved", "name": "Fixture approved terminology",
            "homepage": "https://example.invalid/terms", "authority": "approved_terminology",
            "redistribution": "test", "access_method": "fixture", "formats": ["tbx"],
        })
        self.release = begin_release(self.db, source, "1", "fixture")
        add_concept(self.db, self.release, {
            "en": [{"text": "penetration testing", "status": "recommended"}],
            "lv": [{"text": "ielaušanās testēšana", "status": "recommended"}],
        }, domain="cybersecurity", status="recommended", approval="approved")
        add_concept(self.db, self.release, {
            "en": [{"text": "vulnerability assessment", "status": "recommended"}],
            "lv": [{"text": "ievainojamības novērtēšana", "status": "recommended"}],
        }, domain="cybersecurity", status="recommended", approval="approved")
        add_concept(self.db, self.release, {
            "en": ["authentication"], "lv": ["autentifikācija"],
        }, domain="cybersecurity", status="recommended")
        add_concept(self.db, self.release, {
            "en": ["authorization"], "lv": ["autorizācija"],
        }, domain="cybersecurity", status="recommended")
        add_concept(self.db, self.release, {
            "en": ["privilege escalation"], "lv": ["privilēģiju eskalācija"],
        }, domain="cybersecurity", status="recommended")
        add_concept(self.db, self.release, {
            "en": ["lateral movement"], "lv": ["sānkustība"],
        }, domain="cybersecurity", status="unverified")
        add_concept(self.db, self.release, {
            "en": ["access type"], "lv": ["piekļuves tips"],
        }, domain="cybersecurity", status="recommended")
        add_concept(self.db, self.release, {
            "en": ["IS"], "lv": ["informācijas sistēma"],
        }, domain="cybersecurity", status="recommended")
        finish_release(self.db, self.release, 6)

        other = upsert_source(self.db, {
            "slug": "fixture-general", "name": "Fixture general", "homepage": "https://example.invalid/general",
            "authority": "reference", "redistribution": "test", "access_method": "fixture", "formats": ["csv"],
        })
        other_release = begin_release(self.db, other, "1", "fixture")
        add_concept(self.db, other_release, {"en": ["vulnerability assessment"],
                                             "lv": ["jutīguma novērtējums"]},
                    domain="environment", status="acceptable")
        finish_release(self.db, other_release, 1)
        self.db.commit()
        self.engine = TerminologyEngine(self.db)

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_english_latvian_accuracy(self):
        result = self.engine.translate_term("penetration testing", domain="cybersecurity")
        self.assertEqual("ielaušanās testēšana", result["selected"]["target_term"])
        self.assertEqual("approved", result["selected"]["approval"])

    def test_cybersecurity_terms(self):
        expected = {"authentication": "autentifikācija", "authorization": "autorizācija",
                    "privilege escalation": "privilēģiju eskalācija"}
        for source, target in expected.items():
            self.assertEqual(target, self.engine.translate_term(source)["selected"]["target_term"])

    def test_domain_disambiguation(self):
        security = self.engine.translate_term("vulnerability assessment", domain="cybersecurity")
        environment = self.engine.translate_term("vulnerability assessment", domain="environment")
        self.assertEqual("ievainojamības novērtēšana", security["selected"]["target_term"])
        self.assertEqual("jutīguma novērtējums", environment["selected"]["target_term"])

    def test_exact_prefix_and_fuzzy(self):
        self.assertTrue(self.engine.search_term("authentication", mode="exact"))
        self.assertTrue(self.engine.search_term("auth", mode="prefix"))
        self.assertEqual("autentifikācija", self.engine.search_term("authentcation", mode="fuzzy")[0]["target_term"])

    def test_fuzzy_lookup_does_not_substitute_a_different_multiword_term(self):
        self.assertIsNone(self.engine.translate_term("access token", domain="cybersecurity")["selected"])

    def test_review_ignores_stopwords_acronyms_and_technical_literals(self):
        result = self.engine.review_translation(
            "WebSite is implemented by PADIS API in findings-register.md.",
            "WebSite PADIS API implementācija ir aprakstīta findings-register.md.",
            domain="cybersecurity",
        )
        self.assertTrue(result["ok"], result["issues"])
        result = self.engine.review_translation(
            "Authentication and operation authorization are separate.",
            "Autentifikācija un operācijas autorizācija ir atsevišķas darbības.",
            domain="cybersecurity",
        )
        self.assertTrue(result["ok"], result["issues"])

    def test_multiword_longest_match_and_protection(self):
        result = self.engine.translate_text(
            "Penetration testing found privilege escalation in CVE-2026-12345 at https://x.test/a.",
            domain="cybersecurity",
        )
        self.assertIn("ielaušanās testēšana", result["draft"])
        self.assertIn("privilēģiju eskalācija", result["draft"])
        self.assertIn("CVE-2026-12345", result["draft"])
        self.assertIn("https://x.test/a", result["draft"])

    def test_user_override_has_priority(self):
        self.engine.add_override("lateral movement", "laterālā pārvietošanās", domain="cybersecurity")
        selected = self.engine.translate_term("lateral movement", domain="cybersecurity")["selected"]
        self.assertEqual("laterālā pārvietošanās", selected["target_term"])
        self.assertEqual("user_override", selected["authority"])

    def test_context_scoped_override_only_applies_when_matched(self):
        self.engine.add_override("authentication", "identitātes apliecināšana",
                                 domain="cybersecurity", context_pattern="legal agreement")
        ordinary = self.engine.translate_term("authentication", domain="cybersecurity")
        legal = self.engine.translate_term("authentication", domain="cybersecurity",
                                           context="This legal agreement defines authentication.")
        self.assertEqual("autentifikācija", ordinary["selected"]["target_term"])
        self.assertEqual("identitātes apliecināšana", legal["selected"]["target_term"])

    def test_target_side_preference_and_status_drive_selection(self):
        add_concept(self.db, self.release, {
            "en": [{"text": "target status fixture", "status": "recommended"}],
            "lv": [
                {"text": "novecojis variants", "status": "deprecated", "is_preferred": False},
                {"text": "ieteicamais variants", "status": "recommended", "is_preferred": True},
            ],
        }, domain="cybersecurity", status="recommended")
        self.db.commit()
        result = self.engine.translate_term("target status fixture", domain="cybersecurity")
        self.assertEqual("ieteicamais variants", result["selected"]["target_term"])
        self.assertEqual("recommended", result["selected"]["target_status"])

    def test_targetless_record_cannot_be_selected_as_translation(self):
        legal_source = upsert_source(self.db, {"slug": "lv-only", "name": "LV only",
                                              "homepage": "https://example.invalid/law",
                                              "authority": "legal_definition", "formats": ["csv"]})
        release = begin_release(self.db, legal_source, "1", "fixture")
        add_concept(self.db, release, {"lv": ["autentifikācija"], "en": []},
                    domain="cybersecurity", status="recommended")
        finish_release(self.db, release, 1)
        self.db.commit()
        result = self.engine.translate_term("autentifikācija", source_language="lv",
                                            target_language="en", domain="cybersecurity")
        self.assertEqual("authentication", result["selected"]["target_term"])

    def test_translation_history_records_choices(self):
        result = self.engine.translate_text("Authentication failed.", document_id="report-1",
                                            record_history=True)
        row = self.db.execute("SELECT document_id,choices_json FROM translation_history").fetchone()
        self.assertEqual("report-1", row["document_id"])
        self.assertIn("autentifikācija", row["choices_json"])
        self.assertIn("autentifikācija", result["draft"])

    def test_consistency_conflict(self):
        # Add a legitimate competing rendering to exercise document-level checks.
        add_concept(self.db, self.release, {"en": ["authentication"], "lv": ["identitātes pārbaude"]},
                    domain="cybersecurity", status="acceptable")
        self.db.commit()
        result = self.engine.check_consistency(
            "Authentication then authentication was required.",
            "Tika izmantota autentifikācija un identitātes pārbaude.", domain="cybersecurity")
        self.assertFalse(result["ok"])
        self.assertEqual("competing_translations", result["issues"][0]["type"])

    def test_review_reports_missing_term(self):
        result = self.engine.review_translation("Authorization failed.", "Pārbaude neizdevās.")
        self.assertFalse(result["ok"])
        self.assertEqual("missing_term", result["issues"][0]["type"])

    def test_term_count_uses_word_boundaries_and_counts_repetition(self):
        target = "autorizācija autorizācijas neautorizācija; autorizācija."
        self.assertEqual(2, self.engine._count_term(target, "autorizācija"))
        self.assertEqual(1, self.engine._count_term(target, "autorizācijas"))
        self.assertEqual(0, self.engine._count_term(target, "autoriz"))

    def test_offline_lookup_does_not_need_network(self):
        # A read-only local operation succeeds with a deliberately invalid source homepage.
        self.assertEqual("autorizācija", self.engine.translate_term("authorization")["selected"]["target_term"])

    def test_tbx_import_preserves_status_notes_and_ids(self):
        path = Path(self.temp.name) / "sample.tbx"
        path.write_text("""<?xml version='1.0'?><martif><text><body>
          <termEntry id='x-1'><langSet xml:lang='en'><ntig><termGrp><term>firewall</term></termGrp>
          <admin type='status'>approved</admin></ntig></langSet><langSet xml:lang='lv'><ntig>
          <termGrp><term>ugunsmūris</term></termGrp><admin type='status'>approved</admin>
          <termNote type='usageNote'>protocol 7</termNote></ntig></langSet></termEntry>
        </body></text></martif>""", encoding="utf-8")
        source = upsert_source(self.db, {"slug": "tbx-test", "name": "TBX", "homepage": "https://x.invalid",
                                        "authority": "approved_terminology", "formats": ["tbx"]})
        release = begin_release(self.db, source, "1", "tbx")
        self.assertEqual(1, import_tbx(self.db, release, path, domain="cybersecurity"))
        finish_release(self.db, release, 1)
        self.db.commit()
        result = self.engine.translate_term("firewall")["selected"]
        self.assertEqual("ugunsmūris", result["target_term"])
        self.assertEqual("x-1", result["source_record_id"])

    def test_tbx_parenthetical_deprecation_is_structured(self):
        path = Path(self.temp.name) / "deprecated.tbx"
        path.write_text("""<martif><text><body><termEntry id='x-deprecated'>
          <langSet xml:lang='en'><ntig><termGrp><term>old rate (deprecated)</term></termGrp>
          <admin type='status'>approved</admin></ntig><ntig><termGrp><term>current rate</term></termGrp>
          <admin type='status'>approved</admin></ntig></langSet>
          <langSet xml:lang='lv'><ntig><termGrp><term>pašreizējais ātrums</term></termGrp>
          <admin type='status'>approved</admin></ntig></langSet></termEntry></body></text></martif>""",
                        encoding="utf-8")
        source = upsert_source(self.db, {"slug": "deprecated-test", "name": "Deprecated TBX",
                                        "homepage": "https://x.invalid", "authority": "approved_terminology",
                                        "formats": ["tbx"]})
        release = begin_release(self.db, source, "1", "tbx")
        import_tbx(self.db, release, path, domain="networking")
        finish_release(self.db, release, 1)
        self.db.commit()
        result = self.engine.translate_term("old rate", domain="networking")
        self.assertEqual("deprecated", result["selected"]["source_status"])
        self.assertIn("lexical annotation: deprecated", result["selected"]["usage_note"])

    def test_tei_morphology_and_definition_import(self):
        path = Path(self.temp.name) / "sample.xml"
        path.write_text("""<TEI xmlns='http://www.tei-c.org/ns/1.0'><text><body><entry xml:id='lv-1'>
          <form type='lemma'><orth>ievainojamība</orth><gramGrp><iType>noun-4f</iType>
          <gram type='Dzimte'>Sieviešu</gram><gram type='Vārdšķira'>Lietvārds</gram></gramGrp></form>
          <sense><def>Sistēmas vājums.</def></sense></entry></body></text></TEI>""", encoding="utf-8")
        source = upsert_source(self.db, {"slug": "tei-test", "name": "TEI", "homepage": "https://x.invalid",
                                        "authority": "lexical_reference", "formats": ["tei"]})
        release = begin_release(self.db, source, "1", "tei")
        self.assertEqual(1, import_tei(self.db, release, path))
        finish_release(self.db, release, 1)
        self.db.commit()
        row = self.db.execute("SELECT grammatical_gender,part_of_speech FROM terms WHERE text='ievainojamība'").fetchone()
        self.assertEqual("Sieviešu", row["grammatical_gender"])
        self.assertEqual("Lietvārds", row["part_of_speech"])

    def test_tmx_import_and_retrieval(self):
        path = Path(self.temp.name) / "sample.tmx"
        path.write_text("""<tmx version='1.4'><body><tu tuid='d1'><tuv xml:lang='en'><seg>The risk is high.</seg></tuv>
          <tuv xml:lang='lv'><seg>Risks ir augsts.</seg></tuv></tu></body></tmx>""", encoding="utf-8")
        source = upsert_source(self.db, {"slug": "tmx-test", "name": "TMX", "homepage": "https://x.invalid",
                                        "authority": "translation_memory", "formats": ["tmx"]})
        release = begin_release(self.db, source, "1", "tmx")
        self.assertEqual(1, import_tmx(self.db, release, path))
        finish_release(self.db, release, 1)
        self.db.commit()
        self.assertEqual("Risks ir augsts.", self.engine.translation_memory("The risk was high")[0]["target_text"])

    def test_dgt_style_multifile_utf16_zip_import(self):
        archive_path = Path(self.temp.name) / "dgt.zip"
        template = """<?xml version='1.0' encoding='UTF-16'?><tmx version='1.1'><body><tu tuid='{id}'>
          <tuv xml:lang='EN'><seg>{en}</seg></tuv><tuv xml:lang='LV'><seg>{lv}</seg></tuv>
          </tu></body></tmx>"""
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr("doc1.tmx", template.format(id="1", en="Security control.", lv="Drošības kontrole.").encode("utf-16"))
            archive.writestr("nested/doc2.tmx", template.format(id="2", en="Network segment.", lv="Tīkla segments.").encode("utf-16"))
            archive.writestr("filelist.txt", "doc1 EN LV\n")
        source = upsert_source(self.db, {"slug": "dgt-test", "name": "DGT test",
                                        "homepage": "https://example.invalid/dgt",
                                        "authority": "translation_memory", "formats": ["tmx"]})
        release = begin_release(self.db, source, "1", "tmx")
        self.assertEqual(2, import_tmx(self.db, release, archive_path))
        finish_release(self.db, release, 2)
        self.db.commit()
        self.assertTrue(self.engine.translation_memory("Network segment"))

    def test_offline_wordform_import_and_lookup(self):
        path = Path(self.temp.name) / "forms.xml"
        path.write_text("""<TEI xmlns='http://www.tei-c.org/ns/1.0'><text><body><entry>
          <form type='lemma'><orth>ugunsmūris</orth></form>
          <form type='inflected'><orth>ugunsmūra</orth><gram type='Locījums'>Ģenitīvs</gram></form>
          </entry></body></text></TEI>""", encoding="utf-8")
        source = upsert_source(self.db, {"slug": "forms-test", "name": "Forms", "homepage": "https://x.invalid",
                                        "authority": "morphology_reference", "formats": ["wordforms"]})
        release = begin_release(self.db, source, "1", "wordforms")
        self.assertEqual(2, import_wordforms(self.db, release, path))
        finish_release(self.db, release, 2)
        self.db.commit()
        result = self.engine.morphology("ugunsmūra")
        self.assertEqual("ugunsmūris", result["wordforms"][0]["lemma"])
        self.assertEqual("Ģenitīvs", result["wordforms"][0]["attributes"]["Locījums"])
        add_concept(self.db, self.release, {"en": ["firewall"], "lv": ["ugunsmūris"]},
                    domain="cybersecurity", status="recommended")
        self.db.commit()
        review = self.engine.review_translation("The firewall configuration.", "Ugunsmūra konfigurācija.")
        self.assertTrue(review["ok"])

    def test_release_rollback(self):
        source = self.db.execute("SELECT id FROM sources WHERE slug='fixture-general'").fetchone()[0]
        second = begin_release(self.db, source, "2", "fixture")
        add_concept(self.db, second, {"en": ["risk"], "lv": ["risks"]}, status="recommended")
        finish_release(self.db, second, 1)
        self.db.commit()
        self.assertTrue(self.engine.search_term("risk", mode="exact"))
        result = rollback_source(self.db, "fixture-general")
        self.assertNotEqual(second, result["active_release_id"])
        self.assertFalse(self.engine.search_term("risk", mode="exact"))

    def test_release_update_change_summary(self):
        source = self.db.execute("SELECT id FROM sources WHERE slug='fixture-general'").fetchone()[0]
        old = self.db.execute("SELECT active_release_id FROM sources WHERE id=?", (source,)).fetchone()[0]
        new = begin_release(self.db, source, "2", "fixture")
        add_concept(self.db, new, {"en": ["risk"], "lv": ["risks"]}, status="recommended")
        finish_release(self.db, new, 1)
        self.db.commit()
        summary = release_diff(self.db, old, new)
        self.assertGreater(summary["added"], 0)
        self.assertGreater(summary["removed"], 0)

    def test_failed_import_rolls_back_release_and_active_pointer(self):
        before = self.db.execute(
            "SELECT active_release_id FROM sources WHERE slug='fixture-general'"
        ).fetchone()[0]
        release_count = self.db.execute("SELECT count(*) FROM source_releases").fetchone()[0]
        broken = Path(self.temp.name) / "broken.tbx"
        broken.write_text("<martif><termEntry>", encoding="utf-8")
        with self.assertRaises(Exception):
            import_file(self.db, source_slug="fixture-general", path=broken,
                        import_format="tbx", version="broken")
        after = self.db.execute(
            "SELECT active_release_id FROM sources WHERE slug='fixture-general'"
        ).fetchone()[0]
        self.assertEqual(before, after)
        self.assertEqual(release_count, self.db.execute("SELECT count(*) FROM source_releases").fetchone()[0])


if __name__ == "__main__":
    unittest.main()
