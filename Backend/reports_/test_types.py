"""Plain-English descriptions of each test type, used in the report."""
from __future__ import annotations

TEST_TYPES = {
    "load": {
        "name": "Load Test",
        "purpose": "checks how the API behaves under the number of users it is expected to handle day to day",
        "method": "Traffic was applied at the expected production level to confirm the API meets its response time and error targets under normal conditions.",
    },
    "stress": {
        "name": "Stress Test",
        "purpose": "pushes the API beyond its expected load to find the point where it slows down or starts to fail",
        "method": "Load was increased step by step beyond normal levels to find the API's breaking point and see how it behaves when overloaded.",
    },
    "soak": {
        "name": "Soak Test",
        "purpose": "runs a steady load for a long period to uncover problems that build up over time, such as memory leaks or slow degradation",
        "method": "A constant, realistic load was held for an extended period while response times and errors were watched for any gradual change.",
    },
    "spike": {
        "name": "Spike Test",
        "purpose": "hits the API with sudden bursts of traffic to see whether it survives and how quickly it recovers",
        "method": "Traffic was raised sharply in short bursts and then dropped, to observe how the API absorbs sudden demand and recovers afterwards.",
    },
    "smoke": {
        "name": "Smoke Test",
        "purpose": "is a short, light test that confirms the API works correctly before larger tests are run",
        "method": "A small number of requests were sent to confirm that the endpoints respond correctly and are ready for heavier testing.",
    },
}

DEFAULT = {"name": "Performance Test", "purpose": "measures how the API performs under load",
           "method": "Requests were sent to the API under controlled load while response times and errors were recorded."}


def get(test_type: str | None) -> dict:
    return TEST_TYPES.get((test_type or "").lower(), DEFAULT)