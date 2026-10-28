from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

from termlv.catalog import install_catalog
from termlv.db import add_concept, begin_release, connect, finish_release, initialize, upsert_source
from termlv.server import create_server


class FrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.temp.name) / "frontend.sqlite"
        db = connect(cls.path)
        initialize(db)
        install_catalog(db)
        source = upsert_source(db, {"slug": "ui-fixture", "name": "UI fixture",
                                    "homepage": "https://example.invalid/ui",
                                    "authority": "approved_terminology", "formats": ["tbx"]})
        release = begin_release(db, source, "1", "fixture")
        add_concept(db, release, {"en": [{"text": "penetration testing", "status": "recommended"}],
                                  "lv": [{"text": "ielaušanās testēšana", "status": "recommended"}]},
                    domain="cybersecurity", status="recommended", approval="approved")
        finish_release(db, release, 1)
        db.commit()
        db.close()
        cls.server = create_server("127.0.0.1", 0, cls.path)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)
        cls.temp.cleanup()

    def get(self, path: str):
        with urllib.request.urlopen(self.base + path, timeout=5) as response:
            return response, response.read()

    def post(self, path: str, body: dict):
        request = urllib.request.Request(self.base + path, method="POST",
                                         data=json.dumps(body).encode("utf-8"),
                                         headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.load(response)

    def test_static_frontend_and_security_headers(self):
        response, body = self.get("/")
        self.assertIn(b"TermLV", body)
        self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])
        self.assertEqual("nosniff", response.headers["X-Content-Type-Options"])

    def test_search_api(self):
        _, body = self.get("/api/search?q=penetration%20testing&domain=cybersecurity")
        results = json.loads(body)
        self.assertEqual("ielaušanās testēšana", results[0]["target_term"])

    def test_translation_and_override_apis(self):
        translated = self.post("/api/translate-text", {"text": "Penetration testing.",
                                                        "domain": "cybersecurity"})
        self.assertIn("ielaušanās testēšana", translated["draft"])
        saved = self.post("/api/override", {"source": "lateral movement",
                                            "target": "laterālā pārvietošanās",
                                            "domain": "cybersecurity"})
        self.assertEqual("user-approved", saved["status"])
        _, body = self.get("/api/search?q=lateral%20movement&domain=cybersecurity")
        self.assertEqual("laterālā pārvietošanās", json.loads(body)[0]["target_term"])


if __name__ == "__main__":
    unittest.main()
