import csv, json

BASE = '/home/testop/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics'

for run_name, run_dir in [('Run A', f'{BASE}/20260608_131830_current_state_integrated_a'),
                           ('Run B', f'{BASE}/20260608_140225_current_state_integrated_b')]:
    print(f'=== {run_name}: Compute container lifecycle ===')
    compute_events = []
    with open(f'{run_dir}/container_events.csv') as f:
        for row in csv.DictReader(f):
            name = row['container']
            if 'edge_server_lan' in name or 'edge_server_n' in name:
                compute_events.append(row)
    
    for e in compute_events:
        print(f'  {e["timestamp_iso"][:19]}  {e["event"]:15s}  {e["container"]:35s}  phase={e["phase"]}')
    
    adds = [e for e in compute_events if e['event'] == 'added' and 'dyn' in e['container']]
    rems = [e for e in compute_events if e['event'] == 'removed' and 'dyn' in e['container']]
    print(f'  Dynamic compute adds: {len(adds)}, removes: {len(rems)}')
    
    # Check if removes happened during demand_drop (cleanup phase)
    demand_removes = [e for e in rems if e['phase'] == 'demand_drop']
    final_removes = [e for e in rems if e['event'] == 'final']
    print(f'  Removes during demand_drop: {len(demand_removes)}')
    finals = [e for e in compute_events if e['event'] == 'final']
    print(f'  Final-state entries: {len(finals)}')
    print()

# Check if server_count 0 means compute scaled down
print('=== Server count = 0 periods ===')
for run_name, run_dir in [('Run A', f'{BASE}/20260608_131830_current_state_integrated_a'),
                           ('Run B', f'{BASE}/20260608_140225_current_state_integrated_b')]:
    with open(f'{run_dir}/resource_stats.csv') as f:
        zero_periods = []
        for row in csv.DictReader(f):
            if row.get('server_count', '1') == '0':
                zero_periods.append(row['timestamp'][:19])
        print(f'{run_name}: server_count=0 at {len(zero_periods)} sample points')
        if zero_periods:
            print(f'  First: {zero_periods[0]}, Last: {zero_periods[-1]}')
