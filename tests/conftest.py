"""
A silent skip is a FAIL (SCRUM-006).

A test that skips itself — a missing key, a missing file, a pytest.skip() left in — is turned
into a failure. A skip is allowed only when the test says why up front:

    @pytest.mark.expected_skip("needs a real Teams tenant; covered by SCRUM-013")
"""

from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "expected_skip(reason): this test may skip; the reason is reviewed in the PR"
    )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    outcome = yield
    report = outcome.get_result()
    if report.skipped and not getattr(report, "wasxfail", None) \
            and item.get_closest_marker("expected_skip") is None:
        reason = report.longrepr[2] if isinstance(report.longrepr, tuple) else report.longrepr
        report.outcome = "failed"
        report.longrepr = f"unexpected skip: {reason}\n(mark it @pytest.mark.expected_skip(reason) if intended)"
