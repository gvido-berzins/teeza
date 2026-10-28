from __future__ import annotations

import unittest

from termlv.text import overlaps, protected_spans


class ProtectedSpanTests(unittest.TestCase):
    def test_overlap_boundaries_use_half_open_intervals(self) -> None:
        protected = [(10, 20), (30, 40)]
        self.assertFalse(overlaps((0, 10), protected))
        self.assertTrue(overlaps((9, 11), protected))
        self.assertTrue(overlaps((10, 20), protected))
        self.assertTrue(overlaps((19, 30), protected))
        self.assertFalse(overlaps((20, 30), protected))
        self.assertFalse(overlaps((40, 50), protected))

    def test_protected_spans_are_sorted_and_non_overlapping(self) -> None:
        spans = protected_spans(
            "See CVE-2026-12345 in `Service.svc.cs:10` at https://example.invalid/a."
        )
        self.assertEqual(spans, sorted(spans))
        self.assertTrue(all(left[1] <= right[0]
                            for left, right in zip(spans, spans[1:])))

    def test_large_span_set_finds_predecessor_overlap(self) -> None:
        protected = [(index * 4, index * 4 + 2) for index in range(100_000)]
        self.assertTrue(overlaps((399_997, 399_999), protected))
        self.assertFalse(overlaps((399_998, 400_000), protected))


if __name__ == "__main__":
    unittest.main()
