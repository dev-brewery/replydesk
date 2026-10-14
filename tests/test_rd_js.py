"""T21a tests for docs/rd.js — node-driven port of the paste-parse suite.

Runs node (offline) on a driver script that loads rd.js and asserts the same
synthetic cases as tests/test_paste_parse.py. Skips cleanly if node is absent
so the suite still runs offline in environments without it.
"""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RD_JS = REPO / "docs" / "rd.js"

GOOGLE_DUMP = """\
Riverside Coffee Bar
4.2
1,048 reviews
Coffee shop \u00b7 Open until 6 PM

Jordyn Ellis
12 reviews\u00b76 friends
\u2605\u2605\u2605\u2605\u2605
2 days ago
The cortado here is the best in town and the baristas remember my order.

Marcus Hale
3 reviews
\u2605\u2605\u2605
a week ago
Waited twenty minutes on a Tuesday and the milk was scorched twice.

Priya Nair
81 reviews\u00b7140 friends
\u2605\u2605\u2605\u2605
October 12
Great pastries and the back patio is quiet in the mornings.
Owner responded
Response from the owner
Thanks for the kind words about our afternoon staff, Priya!
See more
Like
Share
"""

YELP_DUMP = """\
Riverside Coffee Bar
4.2 star rating
1048 reviews

Sasha B.
Elite 2024
Portland, OR
4/5
10/2/2024
Solid drip coffee and the staff fixed my order without any fuss.

Devon K.
2 friends
12 reviews
3/5
Updated review: still a solid latte, though the line moves slowly at 8am.
"""

# Driver: reads JSON cases from stdin, runs rd.parsePaste on each, prints
# JSON results. Keeps the JS-side logic minimal; assertions live in Python.
DRIVER_JS = """\
const fs = require('fs');
require(process.argv[2]);
const cases = JSON.parse(fs.readFileSync(0, 'utf8'));
const out = cases.map((text) => rd.parsePaste(text).reviews);
process.stdout.write(JSON.stringify(out));
"""


def run_node(cases: list[str]) -> list[dict]:
    if shutil.which("node") is None:
        raise unittest.SkipTest("node not available on this machine")
    with tempfile.TemporaryDirectory() as tmp:
        driver = Path(tmp) / "driver.js"
        driver.write_text(DRIVER_JS, encoding="utf-8")
        proc = subprocess.run(
            ["node", str(driver), str(RD_JS)],
            input=json.dumps(cases), capture_output=True, text=True,
            encoding="utf-8", timeout=60,
        )
    if proc.returncode != 0:
        raise AssertionError(f"node driver failed:\n{proc.stderr}")
    return json.loads(proc.stdout)


class RdJsPortTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = run_node([text for _, text in PORT_CASES])

    def test_matches_expected(self):
        self.assertEqual(EXPECTED, self.results)


# Each case is (label, paste text); expectations are built alongside in
# EXPECTED below so a single node round-trip covers the whole ported suite.
PORT_CASES = [
    ("manual", "5 | great coffee\n2 | my order was cold"),
    ("google", GOOGLE_DUMP),
    ("yelp", YELP_DUMP),
    ("rated-form", "Rated 4 out of 5.\nGood service, quick fix."),
    ("half-star", "Reviewer A\n\u2605\u2605\u2605\u00bd\na day ago\nHalf-star floors down to three, and this text is the body."),
    ("garbage-prose", "hello world\nno stars here"),
    ("garbage-mixed", "\u2605\u2606 3.9"),
    ("garbage-digits", "12345"),
    ("garbage-dashes", "---"),
    ("empty", ""),
    ("blank", "  \n \n"),
    ("anchor-no-text", "\u2605\u2605\u2605\u2605\u2605\n2 days ago"),
    ("anchor-without-text-keeps-others",
     "Ann Lee\n\u2605\u2605\u2605\u2605\n3 days ago\nLovely staff.\n\u2605\u2605\nQuick service but cramped."),
    ("empty-star-run", "\u2606\u2606\u2606\njust decoration text"),
    ("pua-five", "Reviewer One\n12 reviews\n\ue838\ue838\ue838\ue838\ue838\n2 days ago\nGreat coffee and quick service."),
    ("pua-filler-four", "Reviewer Two\n\ue8dc\ue80d\ue5d4\ue88e\ue838\ue838\ue838\ue838\na week ago\nNice pastries."),
    ("pua-mixed", "Reviewer Three\n\u2605\u2605\ue838\ue838\nOctober 12\nQuiet patio."),
    ("pua-filler-only", "\ue8dc\ue80d\ue5d4\ue88e\njust decoration text"),
    ("pua-reviews-photos-meta",
     "Jordyn Ellis\n12 reviews \u00b7 3 photos\n\ue838\ue838\ue838\ue838\ue838\n2 days ago\nThe cortado is great."),
]

R = lambda sid, stars, text: {"review_id": sid, "stars": stars, "text": text}

EXPECTED = [
    [R("r1", 5, "great coffee"), R("r2", 2, "my order was cold")],
    [R("p1", 5, "The cortado here is the best in town and the baristas remember my order."),
     R("p2", 3, "Waited twenty minutes on a Tuesday and the milk was scorched twice."),
     R("p3", 4, "Great pastries and the back patio is quiet in the mornings.")],
    [R("p1", 4, "Solid drip coffee and the staff fixed my order without any fuss."),
     R("p2", 3, "Updated review: still a solid latte, though the line moves slowly at 8am.")],
    [R("p1", 4, "Good service, quick fix.")],
    [R("p1", 3, "Half-star floors down to three, and this text is the body.")],
    [], [], [], [],
    [], [],
    [],
    [R("p1", 4, "Lovely staff."), R("p2", 2, "Quick service but cramped.")],
    [],
    [R("p1", 5, "Great coffee and quick service.")],
    [R("p1", 4, "Nice pastries.")],
    [R("p1", 4, "Quiet patio.")],
    [],
    [R("p1", 5, "The cortado is great.")],
]


if __name__ == "__main__":
    unittest.main()
