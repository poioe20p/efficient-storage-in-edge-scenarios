# Run Matrix - Storage Reserve Load Sweep

Shared fixed settings for every run in this matrix:

- `PHASES_CONFIG=testing/phases_experiment_storage_reserve_shared.json`
- `DEVICES=600 NODES=100`
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
- `SCALEUP_STORAGE_BASE_THRESHOLD=0.12`
- `SCALEUP_STORAGE_REQUIRED=2`
- `SCALEUP_STORAGE_WINDOW_SIZE=5`
- `SCALEUP_STORAGE_COOLDOWN_S=120`

Only `CLIENTS` changes across the three candidate runs below.

Fixed threshold: **t12 (0.12)** — chosen from the threshold sweep as the highest threshold that still activates under this workload. The override file is `testing/controller_env_overrides/storage_reserve_threshold_t12.env`.

| Run label | `CLIENTS` | Intended interpretation |
| --- | ---: | --- |
| `reserve_load_c08` | `8` | Anchor candidate. Matches the use-validation and threshold-sweep sizing. Run first. |
| `reserve_load_c06` | `6` | Lower-load candidate. Run this next if `c08` activates and you want a lighter reproducible setting. |
| `reserve_load_c10` | `10` | Heavier fallback. Run this next if `c08` misses or cycles. |

Concrete launch sequence per run:

1. Keep `OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/storage_reserve_threshold_t12.env` fixed for the whole sweep.
2. Run `c08` first.
3. If `c08` activates stably, run `c06` next. If `c08` misses or cycles, run `c10` next.
4. Use the third run only if the first two still leave the lightest acceptable load unresolved.
5. Do not edit [osken-controller.env](../../../../../../source/scripts/osken-controller.env) in place.

```bash
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/storage_reserve_threshold_t12.env \
  RUN_LABEL=reserve_load_c08 \
  PHASES_CONFIG=testing/phases_experiment_storage_reserve_shared.json \
  CLIENTS=8 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1

sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/storage_reserve_threshold_t12.env \
  RUN_LABEL=reserve_load_c06 \
  PHASES_CONFIG=testing/phases_experiment_storage_reserve_shared.json \
  CLIENTS=6 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1

sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/storage_reserve_threshold_t12.env \
  RUN_LABEL=reserve_load_c10 \
  PHASES_CONFIG=testing/phases_experiment_storage_reserve_shared.json \
  CLIENTS=10 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

Preferred analysis order: `c08` first, then only the candidate that answers the next question. Most campaigns should stop after 2 runs, with a third only when the result is still ambiguous.
