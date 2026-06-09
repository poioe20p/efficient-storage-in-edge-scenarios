import csv

for label, path in [
    ('Run A', '/home/testop/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics/20260608_131830_current_state_integrated_a/resource_stats.csv'),
    ('Run B', '/home/testop/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics/20260608_140225_current_state_integrated_b/resource_stats.csv'),
]:
    print(f'=== {label} — storage_count transitions ===')
    prev = None
    with open(path) as f:
        for row in csv.DictReader(f):
            sc = row.get('storage_count', '0')
            if sc != prev:
                print(f'  {row["timestamp"][:19]}  storage={prev} -> {sc}')
                prev = sc
    print(f'  END: storage={prev}')
    print()

# Check final container state
print('=== Current dynamic containers (running now) ===')
import subprocess
result = subprocess.run(['sudo', 'docker', 'ps', '--format', '{{.Names}}'], capture_output=True, text=True)
containers = result.stdout.strip().split('\n')
dyn = [c for c in containers if 'dyn' in c or 'sel_sync' in c]
print(f'  Dynamic containers still running: {len(dyn)}')
for c in sorted(dyn):
    print(f'    {c}')
