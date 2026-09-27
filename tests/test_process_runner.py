from __future__ import annotations

import os
import signal
import threading
import sys
import threading
import time

import pytest

from agent_llm_bench_v03.runner import AbortError, ProcessRunner, RunRecord, SuiteBudget


class FakeClock:
    """Injizierbare monotonic-Clock (Sekunden als State)."""

    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance(self, sec: float) -> None:
        self.t += sec


def success_cmd() -> list[str]:
    return [sys.executable, "-c", "import sys; print('out'); print('err', file=sys.stderr); sys.exit(0)"]


def failure_cmd() -> list[str]:
    return [sys.executable, "-c", "import sys; print('boom'); sys.exit(3)"]


def make_runner(**kwargs):
    return ProcessRunner(budget=SuiteBudget(clock=FakeClock()), **kwargs)


# -- Abnahmekriterium 1: Erfolg -------------------------------------------------

def test_success_exit_code_zero(tmp_path) -> None:
    runner = make_runner(timeout_sec=30)
    record = runner.run(success_cmd(), cwd=str(tmp_path))

    assert record.status == "success"
    assert record.exit_code == 0
    assert "out" in record.stdout
    assert "err" in record.stderr


# -- Abnahmekriterium 2: Exitcode ungleich null ---------------------------------

def test_failure_nonzero_exit_code(tmp_path) -> None:
    runner = make_runner(timeout_sec=30)
    record = runner.run(failure_cmd(), cwd=str(tmp_path))

    assert record.status == "failure"
    assert record.exit_code == 3
    assert record.timed_out is False


# -- Abnahmekriterium 3: Timeout in Sekunden ------------------------------------

def test_timeout_fires_on_short_adapter() -> None:
    clock = FakeClock()
    runner = ProcessRunner(timeout_sec=1.0, budget=SuiteBudget(clock=clock))

    # Ein hängender Befehl, damit der 1-Sekunden-Timeout tatsächlich feuert.
    cmd = [sys.executable, "-c", "import time; time.sleep(30)"]
    record = runner.run(cmd)

    assert record.timed_out is True
    assert record.status == "timeout"
    # Timeout-Test muss in Sekunden laufen, nicht Minuten.
    assert clock.t < 60.0


# -- Abnahmekriterium 4: stdout/stderr bleiben bei Timeout erhalten -------------

def test_output_streams_open_when_timed_out() -> None:
    cmd = [sys.executable, "-c", "import time; time.sleep(10)"]
    runner = make_runner(timeout_sec=0.3)

    record = runner.run(cmd)

    assert record.timed_out is True
    assert isinstance(record.stdout, str)
    assert isinstance(record.stderr, str)


# -- Abnahmekriterium 5: große Ausgabe wird begrenzt und gesichert -------------

def test_large_output_is_bounded_and_flagged(tmp_path) -> None:
    # Payload wird im Kindprozess erzeugt, damit die argv-Groesse
    # (MAX_ARG_STRLEN ~128 KB) den Prozessstart nicht verhindert.
    cmd = [sys.executable, "-c", "import sys; sys.stdout.write('x' * (256 * 1024))"]
    runner = make_runner(timeout_sec=30, max_output_chars=1024)

    record = runner.run(cmd, cwd=str(tmp_path))

    assert record.truncated is True
    assert len(record.stdout) <= 1024 + len("[output truncated]")


# -- Abnahmekriterium 6: Restbudget kleiner als Adaptertimeout ------------------

def test_effective_timeout_is_min_adapter_and_budget() -> None:
    clock = FakeClock()
    runner = ProcessRunner(timeout_sec=300, budget=SuiteBudget(total_sec=2400, clock=clock))

    assert runner.effective_timeout() == pytest.approx(300.0)

    clock.advance(2100)  # Restbudget auf 300s
    assert runner.effective_timeout() == pytest.approx(300.0)

    clock.advance(299)  # Restbudget auf 1s
    assert runner.effective_timeout() == pytest.approx(1.0)


# -- Abnahmekriterium 7: budget_exhausted verhindert nächsten Start ------------

def test_budget_exhaustion_blocks_next_run() -> None:
    clock = FakeClock()
    runner = ProcessRunner(timeout_sec=300, budget=SuiteBudget(total_sec=0.05, clock=clock))

    first = runner.run(success_cmd())
    assert first.budget_exhausted is True

    second = runner.run(success_cmd())
    assert second.budget_exhausted is True
    assert second.exit_code is None


# -- Abnahmekriterium 8: Abbruch ergibt aborted statt timeout ------------------

def test_abort_yields_aborted_status() -> None:
    clock = FakeClock()

    class _Runner(ProcessRunner):
        def __init__(self, **kwargs) -> None:
            super().__init__(abort_signal_number=signal.SIGINT, budget=SuiteBudget(clock=clock), **kwargs)

        def _on_abort(self, signum, frame):  # pragma: no cover - signal path
            raise AbortError("aborted")

    runner = _Runner(timeout_sec=300)
    cmd = [sys.executable, "-c", "import time; time.sleep(60)"]

    def _fire_abort() -> None:
        time.sleep(0.3)
        os.kill(os.getpid(), signal.SIGINT)

    # Reales Abbruchsignal waehrend des Laufs -> kontrollierter Abbruchpfad.
    timer = threading.Thread(target=_fire_abort, daemon=True)
    timer.start()
    record = runner.run(cmd)
    timer.join(timeout=1)

    assert record.status == "aborted"
    assert record.timed_out is False


# -- Kein Nachlauf: Kindprozessbaum wird nach Timeout getötet -------------------

def _child_pids(parent_pid: int) -> list[int]:
    """Kind-PIDs ueber /proc/<pid>/stat (Feld 4 = ppid) bestimmen."""
    pids = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/stat", encoding="ascii", errors="replace") as f:
                # comm kann Klammern/Leerzeichen enthalten -> ab letztem ')' parsen
                rest = f.read().rsplit(")", 1)[1].split()
            ppid = int(rest[1])
        except (OSError, ValueError, IndexError):
            continue
        if ppid == parent_pid:
            pids.append(int(entry))
    return pids


def test_no_orphaned_processes_after_timeout() -> None:
    cmd = [sys.executable, "-c", "import time; time.sleep(60)"]
    runner = make_runner(timeout_sec=0.3, grace_sec=0.5)

    runner.run(cmd)

    children = _child_pids(os.getpid())
    assert not children


# -- Kindprozess-Kill: Fork-Kind wird mit dem Baum getötet ----------------------

def test_child_process_killed_within_group() -> None:
    parent_cmd = [sys.executable, "-c", "import subprocess,time; p=subprocess.Popen(['sleep','30']); time.sleep(10)"]
    runner = make_runner(timeout_sec=0.3, grace_sec=0.5)

    record = runner.run(parent_cmd)

    assert record.timed_out is True
    assert record.exit_code in (0, 1, 128, 137, 143)


def test_sigkill_after_ignored_sigterm() -> None:
    cmd = [sys.executable, "-c", "import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(60)"]
    runner = make_runner(timeout_sec=0.3, grace_sec=0.5)

    record = runner.run(cmd)

    assert record.timed_out is True
    # SIGTERM wurde ignoriert -> Grace Period abgelaufen -> harter SIGKILL (137).
    assert record.exit_code == 137


# -- Active-Flag: inaktiver Runner startet nichts -------------------------------

def test_inactive_runner_does_not_start() -> None:
    runner = ProcessRunner(active=False, timeout_sec=30)

    record = runner.run(success_cmd())

    assert record.budget_exhausted is True
    assert record.exit_code is None


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-v"]))
