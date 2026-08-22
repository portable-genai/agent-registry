"""The offline eval gate passes on the local adapter and reports per-metric scores.

It must also fail closed on an evaluation that measured nothing. ``EvalReport.passed`` was
``all(m.passed for m in self.metrics)``; ``all(())`` is vacuously True, and ``main()`` returns
``0`` on ``passed``, so a run that scored nothing certified a promotion. This repo is the
registry that verifies releases, which is the worst possible place for that verdict.

The three ``NOTHING``/``no_metric``/``zero_cards`` tests were RED against that form before the
fix landed, which is the only reason they are worth keeping. The rest pin the behaviour that
must not change: a real evaluation still passes, and one failing metric still fails.
"""

from __future__ import annotations

import sys
from pathlib import Path

_EVAL_DIR = Path(__file__).resolve().parents[1] / "eval"
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

import run_eval  # noqa: E402


def _row(metric: str = "resolve_accuracy", *, passed: bool = True) -> run_eval.MetricResult:
    return run_eval.MetricResult(metric=metric, score=1.0 if passed else 0.0, threshold=1.0)


def test_eval_report_passes() -> None:
    report = run_eval.evaluate()
    assert report.passed, [(m.metric, m.score) for m in report.metrics if not m.passed]


def test_eval_main_exits_zero() -> None:
    assert run_eval.main() == 0


def test_eval_covers_all_thresholds() -> None:
    report = run_eval.evaluate()
    assert {m.metric for m in report.metrics} == set(run_eval.THRESHOLDS)


def test_a_report_that_scored_NOTHING_does_not_pass_the_gate() -> None:
    """The exact fail-open: no metrics, no cards, and the old form said PASSED."""
    assert run_eval.EvalReport(metrics=[], n_examples=0).passed is False


def test_cards_evaluated_but_no_metric_computed_does_not_pass() -> None:
    """A run that loaded the golden set and produced no metric proves nothing."""
    assert run_eval.EvalReport(metrics=[], n_examples=4).passed is False


def test_metric_rows_over_zero_cards_do_not_pass() -> None:
    """Rows synthesised over an empty golden set are not evidence."""
    assert run_eval.EvalReport(metrics=[_row()], n_examples=0).passed is False


def test_a_real_passing_evaluation_still_passes() -> None:
    assert run_eval.EvalReport(metrics=[_row()], n_examples=4).passed is True


def test_one_failing_metric_still_fails() -> None:
    report = run_eval.EvalReport(
        metrics=[_row(), _row("roundtrip_fidelity", passed=False)], n_examples=4
    )
    assert report.passed is False


def test_the_real_evaluation_counts_the_cards_it_scored() -> None:
    """The count must come from the golden set, not from a constant nobody rechecks."""
    report = run_eval.evaluate()
    assert report.n_examples == len(run_eval._golden_cards())
    assert report.n_examples > 0
