# Resilient worker execution

The distributed worker treats a control-plane job as a durable intent and each local CONN run as a replaceable attempt. The remote job ID remains stable when a machine or process interruption forces MATLAB to start again.

## Invariants

- The worker recovers durable local intent before it asks the control plane for new work.
- One CONN project owns the local execution slot. `parallel_jobs` controls CONN's internal MATLAB workers.
- A live MATLAB process is never stopped during reconciliation.
- A local row is declared orphaned only after process inspection positively finds no matching worker or MATLAB process.
- Infrastructure interruption does not complete the remote job as failed. A new local attempt is created for the same remote job.
- Result publication and completion are repeatable. Artifact keys derive from content hashes and repeated registrations return the existing artifact.

## Durable records

Each claimed job stores these atomic files under `work/remote/<remote-job-id>/`:

- `remote-job.json`: the complete execution request needed to restart without first contacting the control plane.
- `worker-state.json`: the current remote-to-local attempt mapping.
- `recovery-state.json`: lifecycle state (`running`, `publishing`, `completed`, or `permanent_failed`), local attempt ID, restart count, and last interruption.

Second-level recalculations use the same pattern under `work/second-level/<run-id>/`.

The local jobs database uses SQLite WAL mode with full synchronous writes. JSON state files are flushed and atomically replaced.

## Recovery behavior

| Interruption | Behavior after service returns |
| --- | --- |
| Internet unavailable while MATLAB runs | MATLAB continues locally. Network calls retry until the control plane returns, then status and results synchronize. |
| Supervisor exits while MATLAB runs | The Windows task restarts the supervisor. It reads the journal and re-associates the live local attempt. |
| Power loss or reboot | The supervisor starts at boot, reads the journal, marks the vanished local attempt interrupted, and starts a clean local attempt for the same remote job. |
| Power loss while uploading results | The succeeded local attempt is reused. Upload and completion repeat safely without duplicate artifact records. |
| Corrupt mapping file | A single live local process is re-associated. A single dead local attempt is cleared. Ambiguous process state blocks new claims instead of corrupting the queue. |
| Scientific or input error | The remote job finishes as failed with the exact error; it is not retried indefinitely. |

The dashboard reads the recovery journal and reports `Recuperando ejecución` plus the restart count while a replacement local attempt is being created.
