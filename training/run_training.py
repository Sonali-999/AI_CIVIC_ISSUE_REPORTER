"""
run_training.py
---------------
Supervisor for train_civic.py on a GPU that resets itself.

    python -m training.run_training              # same arguments as train_civic
    python -m training.run_training --epochs 20

WHY THIS EXISTS
===============
The target machine's MX450 intermittently trips the Windows display driver's
timeout-detection-and-recovery watchdog. When that happens the GPU is reset
underneath the training process: the CUDA context is destroyed and every
subsequent call raises "CUDA error: unknown error". There is no in-process
recovery - the only fix is a new process.

train_civic.py parks its full training state after every epoch, so a restart
loses at most one epoch. This script supplies the restart: it relaunches the
trainer until it exits cleanly or the retry budget runs out, and distinguishes
a driver reset (retry) from a real failure such as a bad argument (stop).
"""

import subprocess
import sys
import time

MAX_RESTARTS = 12
COOLDOWN_SECONDS = 20     # give the driver time to finish resetting

# Messages that mean "the GPU went away", as opposed to a bug in the code.
DRIVER_FAULTS = (
    "cuda error: unknown error",
    "cuda error: the launch timed out",
    "cuda error: illegal memory access",
    "cuda-capable device",
    "cudnn_status_execution_failed",
    "cuda driver",
)


def looks_like_driver_reset(output: str) -> bool:
    lowered = output.lower()
    return any(sig in lowered for sig in DRIVER_FAULTS)


def main() -> int:
    args = sys.argv[1:]
    command = [sys.executable, "-u", "-m", "training.train_civic", *args]

    for attempt in range(1, MAX_RESTARTS + 1):
        if attempt > 1:
            print(f"\n  [supervisor] restart {attempt - 1}/{MAX_RESTARTS} - "
                  f"resuming from the last completed epoch\n", flush=True)

        # The trainer's own output is the user-facing log, so it is streamed
        # through rather than captured - but a copy is kept to classify the
        # failure if it exits non-zero.
        tail: list[str] = []
        process = subprocess.Popen(command, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True,
                                   encoding="utf-8", errors="replace")
        for line in process.stdout:
            print(line, end="", flush=True)
            tail.append(line)
            del tail[:-60]

        code = process.wait()
        if code == 0:
            return 0

        recent = "".join(tail)
        if not looks_like_driver_reset(recent):
            print(f"\n  [supervisor] trainer exited with code {code} and this "
                  f"does not look like a GPU reset - not retrying.\n", flush=True)
            return code

        reason = ("process crashed (access violation)"
                  if code == EXIT_ACCESS_VIOLATION else "GPU reset detected")
        print(f"\n  [supervisor] {reason}. Cooling down "
              f"{COOLDOWN_SECONDS}s before restarting.", flush=True)
        time.sleep(COOLDOWN_SECONDS)

    print(f"\n  [supervisor] gave up after {MAX_RESTARTS} restarts.\n", flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
