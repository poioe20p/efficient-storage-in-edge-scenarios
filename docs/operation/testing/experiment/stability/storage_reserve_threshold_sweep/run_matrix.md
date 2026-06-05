# Run Matrix - Storage Reserve Threshold Sweep

Shared fixed settings for every run in this matrix:

- `PHASES_CONFIG=testing/phases_experiment_storage_reserve_shared.json`
- `CLIENTS=8 DEVICES=600 NODES=100`
- `STORAGE_PERSISTENT_RESERVE_ENABLED=1`
- `SS_ENABLED=0`
- `MAX_DYNAMIC_COMPUTE=0`
- `MAX_DYNAMIC_STORAGE=5`
- `SCALEUP_W_STORAGE_CPU=0.60`
- `SCALEUP_W_T_DB=0.40`
- `SCALEUP_STORAGE_CPU_FLOOR=1.5`
- `SCALEUP_STORAGE_CPU_SPAN=5`
- `SCALEUP_T_DB_FLOOR=60`
- `SCALEUP_T_DB_SPAN=250`
- `SCALEUP_STORAGE_REQUIRED=2`
- `SCALEUP_STORAGE_WINDOW_SIZE=5`
- `SCALEUP_STORAGE_COOLDOWN_S=120`

Only `SCALEUP_STORAGE_BASE_THRESHOLD` changes across the candidate runs below.

**Known boundaries** (from [use-validation results](../storage_reserve_use_validation/results.md)):
- `t08` (0.08): activates reliably but cycles (3 full reserve cycles in 10 min on control, 2 on rebind) — unacceptable for stable operation.
- `t20` (0.20): stayed waiting-only in a prior run — does not activate under this probe workload.

**Primary candidates** (unexplored range):

| Run label | `SCALEUP_STORAGE_BASE_THRESHOLD` | Intended interpretation |
| --- | ---: | --- |
| `reserve_threshold_t15` | `0.15` | **Start here.** Highest unexplored candidate. If stable-activating, this is the preferred operating point. |
| `reserve_threshold_t12` | `0.12` | Fallback if `t15` misses activation or cycles. |
| `reserve_threshold_t10` | `0.10` | Last-resort fallback if `t12` still cycles. Closest to the proven `t08` anchor without being `t08` itself. |

**Optional stretch** (only if `t15` is stable-activating and you want to push higher):

| Run label | `SCALEUP_STORAGE_BASE_THRESHOLD` | Intended interpretation |
| --- | ---: | --- |
| `reserve_threshold_t18` | `0.18` | Stretch candidate. Only run after `t15` succeeds, to test whether an even less aggressive threshold still activates. |

Concrete launch sequence per run:

1. Use the matching `OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/storage_reserve_threshold_tXX.env` shown below.
2. Run the matching command below.
3. Do not edit [osken-controller.env](../../../../../../source/scripts/osken-controller.env) in place between runs. The shared base env stays fixed and only the per-run override file changes.
4. **Execution order**: `t15` → evaluate → `t12` (if t15 missed or cycled) → `t10` (if t12 cycled). Optionally `t18` after `t15` if you want to stretch higher. Most campaigns should stop after 1–2 runs.

```bash
# Run 1 — t15 (primary, start here)
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/storage_reserve_threshold_t15.env \
  RUN_LABEL=reserve_threshold_t15 \
  PHASES_CONFIG=testing/phases_experiment_storage_reserve_shared.json \
  CLIENTS=8 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1

# Run 2 — t12 (fallback if t15 missed or cycled)
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/storage_reserve_threshold_t12.env \
  RUN_LABEL=reserve_threshold_t12 \
  PHASES_CONFIG=testing/phases_experiment_storage_reserve_shared.json \
  CLIENTS=8 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1

# Run 3 — t10 (last-resort fallback if t12 still cycles)
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/storage_reserve_threshold_t10.env \
  RUN_LABEL=reserve_threshold_t10 \
  PHASES_CONFIG=testing/phases_experiment_storage_reserve_shared.json \
  CLIENTS=8 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1

# Optional stretch — t18 (only if t15 was stable-activating)
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/storage_reserve_threshold_t18.env \
  RUN_LABEL=reserve_threshold_t18 \
  PHASES_CONFIG=testing/phases_experiment_storage_reserve_shared.json \
  CLIENTS=8 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

Preferred analysis order: start at `t15`. If stable-activating, optionally test `t18`; otherwise stop at `t15`. If `t15` misses or cycles, move to `t12`. If `t12` cycles, fall back to `t10`. Stop once a stable-activating threshold is found. Use the third run only if the first two are both unacceptable.
