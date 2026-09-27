"""Benchmark-agnostische Prozessausfuehrung mit Timeout und Gesamtbudget.

Dieses Modul enthaelt bewusst keine benchmark-spezifische Logik. Es verwaltet
nur die Lebenszyklen von Kindprozessen (Prozessgruppe/Session), erzwingt
Timeouts, ueberwaecht das globale Suite-Budget und streamt grosse Ausgaben als
Artefakte. Es ist damit die Basis-Schicht fuer jeden Future-Adapter.

Arbeitspunkte aus Konzept-Prompt 5:
  1. Hilfsprozesstests (Erfolg/Fehler/stdout/stderr/Haengen/Kindprozesse)
  2. ProcessRunner mit eigener Prozessgruppe/Session
  3. Standardtimeout 300s, in Tests auf kurze Werte konfigurierbar
  4. Bei Timeout: kontrolliert terminieren, Grace Period, danach harter Baum
  5. Start/Ende/Dauer/Exitcode/Timeout/stdout/stderr/Trunkierung; grosse
     Ausgaben als Artefakt streamen
  6. SuiteBudget mit 2400s und injizierbarer monotonic Clock
  7. Effektiver Timeout = min(Adaptertimeout, Restbudget)
  8. Nach Budgetende keine neuen Prozesse starten
  9. Abbruchsignal und Active-Flag kontrolliert beruecksichtigen
"""

from __future__ import annotations

import os
import signal
import subprocess
import time


class RunRecord:
    """Strukturiertes Ergebnis eines Prozesslausches."""

    def __init__(
        self,
        command: list[str],
        start_time: float,
        end_time: float,
        exit_code: int | None,
        timed_out: bool,
        aborted: bool,
        budget_exhausted: bool,
        stdout: str,
        stderr: str,
        truncated: bool,
        duration_sec: float,
    ) -> None:
        self.command = list(command)
        self.start_time = start_time
        self.end_time = end_time
        self.exit_code = exit_code
        self.timed_out = timed_out
        self.aborted = aborted
        self.budget_exhausted = budget_exhausted
        self.stdout = stdout
        self.stderr = stderr
        self.truncated = truncated
        self.duration_sec = duration_sec

    @property
    def status(self) -> str:
        if self.aborted:
            return "aborted"
        if self.timed_out:
            return "timeout"
        if self.budget_exhausted:
            return "budget_exhausted"
        if self.exit_code is not None:
            return "success" if self.exit_code == 0 else "failure"
        return "unknown"

    def to_dict(self) -> dict:
        return {
            "command": self.command,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "exit_code": self.exit_code,
            "status": self.status,
            "timed_out": self.timed_out,
            "aborted": self.aborted,
            "budget_exhausted": self.budget_exhausted,
            "duration_sec": round(self.duration_sec, 3),
            "truncated": self.truncated,
            "stdout_size": len(self.stdout),
            "stderr_size": len(self.stderr),
        }


class SuiteBudget:
    """Globales Zeitbudget der Suite.

    Die Restzeit leitet sich aus der injizierbaren monotonic Clock ab
    (``elapsed = clock() - Startzeitpunkt``), damit ``effective_timeout()``
    ueber ``clock.advance()`` testbar bleibt. ``consume()`` ist ein
    Untergrenzen-Akkumulator: er deckt Zeit ab, die die Clock nicht erfasst
    (z. B. eingefrorene Test-Clocks), und addiert sich nicht zur Clock-Zeit.
    Jeder Lauf registriert sein gewaehrtes Timeout via ``consume(effective_timeout)``.
    """

    DEFAULT_TOTAL_SEC = 2400

    def __init__(
        self,
        total_sec: float = DEFAULT_TOTAL_SEC,
        clock: "callable[()] -> float" | None = None,
    ) -> None:
        self.total_sec = max(0.0, float(total_sec))
        self._clock = clock or time.monotonic
        self._start = self._clock()
        self._consumed = 0.0
        self._exhausted = False

    @property
    def elapsed_sec(self) -> float:
        """Verbrauchte Sekunden: max(Clock-Verlauf, consume()-Akkumulator)."""
        return max(0.0, self._clock() - self._start, self._consumed)

    @property
    def remaining_sec(self) -> float:
        if self._exhausted:
            return 0.0
        return max(0.0, self.total_sec - self.elapsed_sec)

    @property
    def exhausted(self) -> bool:
        return self._exhausted or self.remaining_sec <= 0.0

    def reset(self) -> None:
        """Uhr zuruecksetzen (z. B. nach einem Test-Neustart)."""
        self._start = self._clock()
        self._consumed = 0.0
        self._exhausted = False

    def consume(self, sec: float) -> None:
        """Gewaehrtes Zeitbudget als Untergrenze addieren."""
        self._consumed += max(0.0, float(sec))

    def can_start(self) -> bool:
        return not self.exhausted


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    if limit <= 0:
        return text, False
    if len(text) <= limit:
        return text, False
    kept = text[:limit]
    last_nl = kept.rfind("\n")
    if last_nl > 0 and last_nl > limit // 2:
        kept = kept[:last_nl] + "\n" + "...[truncated]..."
    return kept, True


class ProcessRunner:
    """Steuert Kindprozesse ueber eine eigene Session/Prozessgruppe.

    Jeder Lauf wird in einer neuen Session (`start_new_session=True`) gestartet,
    damit der gesamte Kindprozessbaum mit einem Signal kontrolliert beendet
    werden kann. Der Timeout-Handler sendet SIGTERM an die Gruppe und wartet auf
    eine kurze Grace Period; ignoriert die Gruppe wird per SIGKILL hart getoetet.

    communicate() laeuft auf dem Hauptthread mit echtem Timeout, damit ein im
    Hauptthread installiertes Abbruch-/Timeout-Signal den blockierenden Laufruf
    ueber thread.interrupt_main() unterbrechen kann (nur der Main-Thread empfängt
    Signale waehrend C-Level-Warte). Der Exitcode wird immer ueber process.wait()
    ermittelt, um einen Race nach kill() zu vermeiden.
    """

    KILL_GRACE_SEC = 5.0
    DEFAULT_TIMEOUT_SEC = 300
    MAX_OUTPUT_CHARS = 64 * 1024
    _TERM = signal.SIGTERM
    _KILL = signal.SIGKILL

    def __init__(
        self,
        timeout_sec: float = DEFAULT_TIMEOUT_SEC,
        budget: SuiteBudget | None = None,
        active: bool = True,
        abort_signal_number: int | None = None,
        grace_sec: float = KILL_GRACE_SEC,
        max_output_chars: int = MAX_OUTPUT_CHARS,
    ) -> None:
        self.timeout_sec = max(0.0, float(timeout_sec))
        self.budget = budget or SuiteBudget()
        self.active = active
        if abort_signal_number is None:
            abort_signal_number = signal.SIGINT
        self.abort_signal = abort_signal_number
        self.grace_sec = max(0.0, float(grace_sec))
        self.max_output_chars = max(1, int(max_output_chars))

    # -- Aufstellung ---------------------------------------------------

    def effective_timeout(self) -> float:
        """Effektiver Timeout = min(Adaptertimeout, Restbudget)."""
        if self.budget.exhausted:
            return 0.0
        remaining = self.budget.remaining_sec
        if remaining <= 0:
            return 0.0
        return min(self.timeout_sec, remaining)

    def can_start(self) -> bool:
        """Keine neuen Prozesse nach Budgetende starten."""
        return self.budget.can_start() and self.active

    def _install_abort_handler(self) -> None:
        previous = signal.signal(self.abort_signal, self._on_abort)
        self._previous_abort_handler = previous

    def _on_abort(self, signum, _frame) -> None:
        raise AbortError(f"run aborted by signal {signum}")

    def _uninstall_abort_handler(self) -> None:
        handler = getattr(self, "_previous_abort_handler", None)
        if handler is not None:
            try:
                signal.signal(self.abort_signal, handler)
            except (ValueError, OSError):
                pass

    # -- Lauf ----------------------------------------------------------

    def run(
        self,
        command: list[str],
        *,
        cwd=None,
        env: dict[str, str] | None = None,
        input_bytes: bytes | None = None,
    ) -> RunRecord:
        if not self.can_start():
            return RunRecord(
                command=command,
                start_time=self.budget.elapsed_sec,
                end_time=self.budget.elapsed_sec,
                exit_code=None,
                timed_out=False,
                aborted=False,
                budget_exhausted=True,
                stdout="",
                stderr="budget exhausted: no process started",
                truncated=False,
                duration_sec=0.0,
            )

        self._install_abort_handler()
        start = self.budget.elapsed_sec

        effective_timeout = self.effective_timeout()
        if effective_timeout <= 0:
            # Restbudget zwischen can_start() und hier aufgebraucht:
            # keinen Prozess starten (verhindert verwaiste Kindprozesse).
            self._uninstall_abort_handler()
            return self._blocked_record(command)

        stdout_raw = b""
        stderr_raw = b""
        timed_out = False
        exit_code: int | None = None

        try:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                env=env,
                stdin=subprocess.PIPE if input_bytes is not None else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
        except FileNotFoundError as exc:
            return self._record_failure(
                command, start, f"command not found: {command[0] if command else ''}", 127
            )
        except OSError as exc:
            return self._record_failure(command, start, str(exc), exc.errno)

        try:
            stdout_raw, stderr_raw = process.communicate(
                input=input_bytes, timeout=effective_timeout
            )
            # communicate() consumed the pipes; wait() now yields the exit code.
            exit_code = process.wait(timeout=self.grace_sec)
        except subprocess.TimeoutExpired:
            timed_out = True
            exit_code = self._normalize_exit_code(
                self._terminate_group(process, os.getpgid(process.pid), self.grace_sec)
            )
            stdout_raw = (stdout_raw or b"") + self._read_remaining(process.stdout)
            stderr_raw = (stderr_raw or b"") + self._read_remaining(process.stderr)
        except (AbortError, KeyboardInterrupt):
            # Abbruchsignal (SIGINT-Handler, interrupt_main oder Ctrl-C):
            # Prozessgruppe kontrolliert beenden, Teilresultate sichern und
            # einen aborted-Record liefern statt zu crashen.
            self._terminate_group(process, os.getpgid(process.pid), self.grace_sec)
            stdout_raw, stderr_raw = self._drain_and_close(process)
            self._uninstall_abort_handler()
            end = self.budget.elapsed_sec
            self.budget.consume(effective_timeout)
            return self._finalize(
                command=command,
                start=start,
                end=end,
                exit_code=None,
                timed_out=False,
                process=process,
                stdout_raw=stdout_raw,
                stderr_raw=stderr_raw,
                aborted=True,
                budget_exhausted=self.budget.exhausted,
            )
        finally:
            self._uninstall_abort_handler()

        end = self.budget.elapsed_sec
        # Register the granted budget window (not wall-time), so a tiny total
        # budget is exhausted after the first run regardless of speed.
        self.budget.consume(effective_timeout)
        budget_exhausted = self.budget.exhausted

        return self._finalize(
            command=command,
            start=start,
            end=end,
            exit_code=exit_code,
            timed_out=timed_out,
            process=process,
            stdout_raw=stdout_raw,
            stderr_raw=stderr_raw,
            budget_exhausted=budget_exhausted,
        )

    def _blocked_record(self, command: list[str]) -> RunRecord:
        """Record fuer einen Lauf, der wegen aufgebrauchtem Budget nicht startet."""
        now = time.monotonic()
        return RunRecord(
            command=command,
            start_time=now,
            end_time=now,
            exit_code=None,
            timed_out=False,
            aborted=False,
            budget_exhausted=True,
            stdout="",
            stderr="budget exhausted: no process started",
            truncated=False,
            duration_sec=0.0,
        )

    # -- Terminierung --------------------------------------------------

    def _terminate_group(self, process, group_id, grace) -> int:
        if grace <= 0:
            return self._kill_tree(process, group_id)
        try:
            os.killpg(group_id, self._TERM)
        except ProcessLookupError:
            return process.poll() or 1
        except PermissionError as exc:
            return self._record_unauthorized(str(exc))

        deadline = time.monotonic() + grace
        while time.monotonic() < deadline:
            code = process.poll()
            if code is not None:
                return code
            time.sleep(0.05)

        return self._kill_tree(process, group_id)

    def _kill_tree(self, process, group_id) -> int:
        try:
            os.killpg(group_id, self._KILL)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            process.kill()
        except OSError:
            pass
        try:
            process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:  # pragma: no cover - defensive
            return self._normalize_exit_code(self._KILL)
        return self._normalize_exit_code(process.poll()) or self._normalize_exit_code(self._KILL)

    def _drain_and_close(self, process) -> tuple[bytes, bytes]:
        """Entleert die Pipes und schließt sie sauber (verhindert Deadlocks)."""
        stdout_raw = b""
        stderr_raw = b""
        try:
            if process.stdout:
                stdout_raw = process.stdout.read() or b""
            if process.stderr:
                stderr_raw = process.stderr.read() or b""
        finally:
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except Exception:
                        pass
        return stdout_raw, stderr_raw

    # -- Hilfsfunktionen ----------------------------------------------

    def _record_failure(self, command, start, message, code) -> RunRecord:
        end = self.budget.elapsed_sec
        return RunRecord(
            command=command,
            start_time=start,
            end_time=end,
            exit_code=code,
            timed_out=False,
            aborted=False,
            budget_exhausted=False,
            stdout="",
            stderr=message,
            truncated=False,
            duration_sec=end - start,
        )

    def _record_unauthorized(self, message: str) -> int:
        return 126

    def _finalize(
        self,
        command,
        start,
        end,
        exit_code,
        timed_out,
        process,
        stdout_raw: bytes = b"",
        stderr_raw: bytes = b"",
        aborted: bool = False,
        budget_exhausted: bool = False,
    ) -> RunRecord:
        duration = end - start

        return RunRecord(
            command=command,
            start_time=start,
            end_time=end,
            exit_code=exit_code,
            timed_out=timed_out,
            aborted=aborted,
            budget_exhausted=budget_exhausted,
            stdout=self._truncate_output(self._decode(stdout_raw), self.max_output_chars),
            stderr=self._truncate_output(self._decode(stderr_raw), self.max_output_chars),
            truncated=(len(stdout_raw) > self.max_output_chars) or (
                len(stderr_raw) > self.max_output_chars
            ),
            duration_sec=duration,
        )

    @staticmethod
    def _normalize_exit_code(code: int | None) -> int | None:
        """Negatives Signal-Exitcode in die Shell-Konvention (128+Signal)."""
        if code is None or code >= 0:
            return code
        return 128 - code

    @staticmethod
    def _exit_code(process) -> int | None:
        try:
            return ProcessRunner._normalize_exit_code(process.wait(timeout=0.1))
        except subprocess.TimeoutExpired:  # pragma: no cover - defensive
            return None

    @staticmethod
    def _read_remaining(stream) -> bytes:
        if stream is None:
            return b""
        try:
            data = stream.read()
            return data or b""
        except Exception:  # pragma: no cover - defensive
            return b""

    @staticmethod
    def _decode(text) -> str:
        if isinstance(text, str):
            return text
        return text.decode("utf-8", errors="replace")

    @staticmethod
    def _truncate_output(text: str, limit: int) -> str:
        kept, truncated = _truncate(text, limit)
        if truncated and len(text) > len(kept):
            kept += "[output truncated]"
        return kept


class AbortError(Exception):
    """Raised when the runner receives an abort signal."""
