import json
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
ENTRIES = {e['id']: e for e in json.loads((ROOT / 'runs/fe70_sequence_terms.json').read_text())['entries']}
STARTS = {'FRO01': 7, 'FRO04': 7, 'FRO06': 7, 'FRO25': 1,
          'LAN13': 7, 'LAN16': 8, 'LAN17': 8}


def run(job):
    sid, variant, start, terms = job
    name = f'{sid}_{variant}'
    destination = OUT / f'{name}.json'
    if destination.exists():
        json.loads(destination.read_text())
        print(f'SKIP {name}: saved result', flush=True)
        return
    command = [str(ROOT / '.venv/bin/oeis'), 'analyze', ','.join(map(str, terms)),
               '--deep', '--time-cap', '120', '--subsequence', '--json',
               '--show-terms', '60', '--show-formula']
    print(f'START {name}: index {start}, {len(terms)} terms', flush=True)
    began = time.monotonic()
    with (OUT / f'{name}.stderr.txt').open('w') as errors:
        result = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE,
                                stderr=errors, text=True, check=True)
    payload = json.loads(result.stdout)
    payload['fe70_input'] = {'id': sid, 'variant': variant, 'start_index': start,
                             'also_covers': ['LAN15'] if sid == 'LAN13' else [],
                             'command': command}
    destination.write_text(json.dumps(payload, indent=2) + '\n')
    counts = {key: len(payload.get(key, [])) for key in
              ('exact_matches', 'transform_matches', 'similarity', 'ranked_explanations')}
    print(f'DONE {name}: {time.monotonic() - began:.1f}s {counts}', flush=True)


if __name__ == '__main__':
    jobs = []
    for sid, start in STARTS.items():
        terms = ENTRIES[sid]['terms']
        jobs.append((sid, 'full', 1, terms))
        if start != 1:
            jobs.append((sid, 'tail', start, terms[start - 1:]))
        jobs.append((sid, 'window16', start, terms[start - 1:start + 15]))
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run, jobs))
    print(f'COMPLETE: {len(jobs)} Deep queries; LAN13 also covers LAN15.', flush=True)
