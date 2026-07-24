---
description: "Operational lessons learned during edge-platform experiments. Applies to experiment runner and analyzer agents to avoid repeating known mistakes."
applyTo: ".github/agents/experiment-runner-edge.agent.md,.github/agents/edge-experiment-analyzer.agent.md"
---

# Edge Platform — Lessons Learned

*Record operational lessons discovered during experiments to avoid repeating mistakes.*

## SSH Keepalive

The cloud VM's SSH server kills idle connections after ~5 min. **Always use
`ssh -o ServerAliveInterval=60`** for any `ssh` command that needs to stay open
longer than a quick check. This includes `mode=async` experiment launches,
mid-run status checks, and file sync operations.

Discovered on 2026-06-29 during `rq1_v2_push_1` attempts — SSH dropped
mid-settle, causing premature run termination. The 10+ min of accumulated
settle time from the two prior failed attempts was a fortunate side-effect, not
a reliable fallback.

## CRLF Line Endings from Windows `scp`

`scp` from Windows preserves CRLF line endings which break bash scripts on the
cloud VM. Always run `sed -i 's/\r$//'` on any `.sh` file synced from Windows
before using it. Also fix the local file's line endings to prevent recurrence.

When copying run artifacts or scripts back from the cloud VM for local
analysis, be aware that Windows tools may add CRLF if files are later
re-synced. Always verify shell scripts have Unix line endings before
re-deploying. Fix: `sed -i 's/\r$//'` on the cloud VM, or use `dos2unix` if
available.

Discovered on 2026-07-03 during `rq1_v2final_push_1` launch —
`build_network_setup.sh` synced with CRLF caused `set: pipefail: invalid option`
and make failed immediately.

## Long-Run Monitoring (Open Investigation)

Runs can take 40+ minutes. The current approach (`mode=async` terminal +
`ServerAliveInterval=60`) works but has failure modes:

- **SSH keepalive gaps**: If the VM is slow to respond, the keepalive may not
  prevent a dropped connection on a 40-minute run.
- **No progress visibility**: The runner has no mid-run signal beyond
  `current_phase.txt` — if the run silently stalls, detection is delayed until
  the terminal exits (or doesn't).
- **Investigation needed**: Evaluate alternatives such as `nohup` +
  detached execution with periodic phase-polling from a separate SSH session,
  or a lightweight watchdog script on the cloud VM that writes heartbeat
  timestamps the runner can check independently.
