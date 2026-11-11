import wait_stack as ws


def full(**over):
    st = {s: ("running", "healthy", 0) for s in ws.LONG_RUNNING}
    st["otel-collector"] = ("running", "", 0)
    st.update({s: ("exited", "", 0) for s in ws.ONE_SHOT})
    st.update(over)
    return st


def test_complete_stack_has_no_problems():
    assert ws.problems(full()) == ([], [])


def test_empty_state_is_not_ready():
    failed, pending = ws.problems({})
    assert not failed and len(pending) == len(ws.LONG_RUNNING | ws.ONE_SHOT)


def test_one_healthy_service_alone_is_not_ready():
    assert ws.problems({"api": ("running", "healthy", 0)})[1]


def test_missing_service_is_pending_not_ok():
    st = full()
    del st["temporal"]
    assert ws.problems(st)[1] == ["temporal: missing"]


def test_failed_job_is_definitive_failure():
    assert ws.problems(full(**{"minio-init": ("exited", "", 1)}))[0] == ["minio-init: exited 1"]


def test_crashed_long_running_service_is_failure():
    assert ws.problems(full(minio=("exited", "", 137)))[0] == ["minio: exited"]


def test_unhealthy_service_is_pending():
    assert ws.problems(full(api=("running", "starting", 0)))[1] == ["api: running/starting"]


def test_timeout_returns_failure(monkeypatch):
    monkeypatch.setattr(ws, "state", lambda: {})
    monkeypatch.setattr(ws.time, "sleep", lambda _s: None)
    assert ws.main(timeout=-1) == 1
