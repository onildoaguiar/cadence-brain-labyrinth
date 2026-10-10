"""Hall of fame only records a name after every challenge on this brain."""

import json
import tempfile
import unittest
from pathlib import Path

from hall import Hall, clean_name
from race import CHALLENGES, Race


class HallTests(unittest.TestCase):
    def test_name_rules(self):
        self.assertEqual(clean_name("  Ada  Lovelace "), "Ada Lovelace")
        for bad in ("", "   ", "<script>", "way too long for a plaque name"):
            with self.assertRaises(ValueError):
                clean_name(bad)

    def test_save_only_after_every_challenge(self):
        race = Race()
        self.assertFalse(race.fame_ready())
        for item in CHALLENGES:
            race.achievements[item["id"]] = True
        self.assertTrue(race.fame_ready())
        with tempfile.TemporaryDirectory() as directory:
            hall = Hall(Path(directory) / "hall-of-fame.json")
            hall.add("Ada", level=9, wins=6, heats=11)
            race.enshrine()
            self.assertFalse(race.fame_ready())
            public = hall.public()
            self.assertEqual(public[0]["name"], "Ada")
            race.hatch()
            self.assertFalse(race.fame_ready())
            self.assertFalse(any(race.achievements.values()))
            again = Hall(Path(directory) / "hall-of-fame.json")
            self.assertEqual(again.public()[0]["name"], "Ada")
            raw = json.loads((Path(directory) / "hall-of-fame.json").read_text())
            self.assertEqual(raw[0]["wins"], 6)


if __name__ == "__main__":
    unittest.main()
