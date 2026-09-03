# Task: Run Bundled Evaluation Using Existing `run_eval.py` (No New Code)

## Context

Working directory:
```
cmu-agentic-ai-program-2026/cmu-capstone/agent/
```

`evaluation/run_eval.py` already supports everything needed to run the 22 benchmark
cases in independent bundles:

- `--case-ids a,b,c` — comma-separated, explicit case IDs
- `--output PATH` — write results to a custom path instead of the default
- `--no-live` / `--live` — fixture vs live Angular server
- `--worktree` — isolated git worktree per case (optional)

---

## The 7 Bundles (do not change)

| Bundle | Case IDs | Count |
|--------|----------|-------|
| 1 | case-01, case-02, case-03, case-04 | 4 |
| 2 | case-05, case-06, case-07 | 3 |
| 3 | case-08, case-09, case-10 | 3 |
| 4 | case-11, case-12, case-13 | 3 |
| 5 | case-14, case-15, case-16 | 3 |
| 6 | case-17, case-18, case-19 | 3 |
| 7 | case-20, case-21, case-22 | 3 |
| **Total** | | **22** |

Verify against `evaluation/benchmark_cases.json` (22 entries, case-01 through case-22).

---

## Step 1 — Run each bundle

```bash
cd /Users/dks0721706/dev/cmu-agentic-ai-program-2026/cmu-capstone/agent
source /Users/dks0721706/dev/cmu-agentic-ai-program-2026/CMU/bin/activate

mkdir -p evaluation/results/bundles

python -m evaluation.run_eval --case-ids case-01,case-02,case-03,case-04 \
  --output evaluation/results/bundles/bundle_1_summary.json --no-live

python -m evaluation.run_eval --case-ids case-05,case-06,case-07 \
  --output evaluation/results/bundles/bundle_2_summary.json --no-live

python -m evaluation.run_eval --case-ids case-08,case-09,case-10 \
  --output evaluation/results/bundles/bundle_3_summary.json --no-live

python -m evaluation.run_eval --case-ids case-11,case-12,case-13 \
  --output evaluation/results/bundles/bundle_4_summary.json --no-live

python -m evaluation.run_eval --case-ids case-14,case-15,case-16 \
  --output evaluation/results/bundles/bundle_5_summary.json --no-live

python -m evaluation.run_eval --case-ids case-17,case-18,case-19 \
  --output evaluation/results/bundles/bundle_6_summary.json --no-live

python -m evaluation.run_eval --case-ids case-20,case-21,case-22 \
  --output evaluation/results/bundles/bundle_7_summary.json --no-live
```

Run these one at a time (sequentially, in separate terminal invocations, or however
is convenient). If one bundle's command fails or times out, move on to the next —
each bundle is independent and writes its own file. Re-run just the failed bundle
later; it will overwrite its own output file only.

Swap `--no-live` for `--live` if you want live PR delivery for that run.

---

## Step 2 — Merge the 7 bundle files into `results_summary.json`

No wrapper script — a single inline `python -c` command, run once after all (or as
many as exist) bundle files are present:

```bash
cd /Users/dks0721706/dev/cmu-agentic-ai-program-2026/cmu-capstone/agent
python -c "
import json, glob, sys

bundle_files = sorted(glob.glob('evaluation/results/bundles/bundle_*_summary.json'))
if not bundle_files:
    sys.exit('No bundle files found in evaluation/results/bundles/')

bundle_summaries = [json.loads(open(f).read()) for f in bundle_files]
print('Loaded:', [f.split('/')[-1] for f in bundle_files])

all_cases = []
for b in bundle_summaries:
    all_cases.extend(b.get('cases', []))

total = len(all_cases)
if total == 0:
    sys.exit('No cases found in any bundle file')

cleared = sum(1 for c in all_cases if c.get('cleared'))
errors = sum(1 for c in all_cases if c.get('error'))
escalated = sum(1 for c in all_cases if c.get('route') == 'human')
total_latency = sum(c.get('latency_seconds', 0) or 0 for c in all_cases)

by_rule = {}
for c in all_cases:
    rule = c.get('rule', 'unknown')
    by_rule.setdefault(rule, {'total': 0, 'cleared': 0})
    by_rule[rule]['total'] += 1
    if c.get('cleared'):
        by_rule[rule]['cleared'] += 1

weighted_brier = weighted_ece = 0.0
for b in bundle_summaries:
    s = b.get('summary', {})
    n = s.get('total_cases', 0)
    weighted_brier += s.get('brier_score', 0.0) * n
    weighted_ece += s.get('expected_calibration_error', 0.0) * n

merged = {
    'summary': {
        'total_cases': total,
        'violation_clearance_rate': cleared / total,
        'human_escalation_rate': escalated / total,
        'error_rate': errors / total,
        'mean_latency_seconds': total_latency / total,
        'brier_score': weighted_brier / total,
        'expected_calibration_error': weighted_ece / total,
        'by_rule': by_rule,
    },
    'cases': all_cases,
}

with open('evaluation/results/results_summary.json', 'w') as f:
    json.dump(merged, f, indent=2)

s = merged['summary']
print(f'Wrote evaluation/results/results_summary.json')
print(f'{s[\"total_cases\"]} cases, {s[\"violation_clearance_rate\"]:.1%} cleared, '
      f'{s[\"error_rate\"]:.1%} errors, mean latency {s[\"mean_latency_seconds\"]:.1f}s')
"
```

This is safe to re-run at any point (e.g. after only 3 of 7 bundles have finished) —
it merges whatever bundle files currently exist and overwrites `results_summary.json`.

---

## Step 3 — Verify the merged file

```bash
python -c "
import json
d = json.loads(open('evaluation/results/results_summary.json').read())
assert 'summary' in d and 'cases' in d
s = d['summary']
for k in ['total_cases','violation_clearance_rate','human_escalation_rate',
          'error_rate','mean_latency_seconds','brier_score','by_rule']:
    assert k in s, f'missing key: {k}'
print(f'✅ valid — {s[\"total_cases\"]} cases, {s[\"violation_clearance_rate\"]:.1%} cleared')
"
```

Expect `total_cases: 22` once all 7 bundles have run successfully.
