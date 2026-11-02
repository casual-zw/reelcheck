import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import collect
from factcheck_seeds import canonical_video


class CollectionTests(unittest.TestCase):
    def test_only_video_links_are_accepted(self):
        for url in ["https://youtube.com/@NASA/shorts", "https://youtube.com/playlist?list=ABC", "https://youtube.com.attacker.example/watch?v=abcdefghijk", "https://tiktok.com/@someone"]:
            self.assertIsNone(canonical_video(url))
        self.assertEqual(canonical_video("https://youtu.be/abcdefghijk?t=4")[1], "abcdefghijk")
        self.assertEqual(canonical_video("https://www.tiktok.com/@creator/video/123456789?x=y")[1], "123456789")

    def test_sampler_is_balanced_deterministic_and_deduplicates_leads(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(collect, "DATA", Path(directory)):
            rows = [{"platform": "youtube", "video_id": f"{cat}{creator}{i}", "sampling_category": cat,
                     "source_handle": creator} for cat in ["a", "b"] for creator in ["x", "y"] for i in range(10)]
            collect.write_jsonl(collect.DATA / "candidates.jsonl", rows)
            collect.write_jsonl(collect.DATA / "factcheck_candidates.jsonl", [rows[0]])
            args = argparse.Namespace(count=11, seed=42, factcheck_count=1)
            collect.select(args)
            first = collect.read_jsonl(collect.DATA / "selected.jsonl")
            collect.select(args)
            self.assertEqual(first, collect.read_jsonl(collect.DATA / "selected.jsonl"))
            self.assertEqual(len(first), 11)
            self.assertEqual(len({r["video_id"] for r in first}), 11)
            self.assertEqual(sum(r["sampling_category"] == "a" for r in first), 6)
            self.assertEqual({r["source_handle"] for r in first}, {"x", "y"})


if __name__ == "__main__":
    unittest.main()
