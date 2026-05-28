from tfdo._internal.core import failure_output


def test_is_plan_hard_failure() -> None:
    assert failure_output.is_plan_hard_failure(1)
    assert not failure_output.is_plan_hard_failure(2)
    assert not failure_output.is_plan_hard_failure(0)


def test_format_failure_stderr_tails_and_truncates() -> None:
    lines = [f"line-{index}" for index in range(50)]
    text = "\n".join(lines)
    formatted = failure_output.format_failure_stderr(text)
    assert formatted is not None
    assert formatted.startswith("line-10")
    assert formatted.endswith("line-49")

    huge_tail = "x" * 5000
    truncated = failure_output.format_failure_stderr(huge_tail)
    assert truncated is not None
    assert truncated.startswith("... (truncated,")
    assert "5000 chars total" in truncated
