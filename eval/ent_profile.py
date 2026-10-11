"""Profile the EnterpriseRAG-Bench corpus: documents and content length per source type, plus a few samples.

    python -m eval.ent_profile [--samples 2] [--chars 700]

Writes eval/results/ent_profile.json. Chunking and access rules are designed from this output.
"""
import argparse
import json
import random
from collections import defaultdict

from core import config
from enterprise import data


def pct(xs, p):
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", type=int, default=2)
    ap.add_argument("--chars", type=int, default=700)
    a = ap.parse_args()

    lengths, samples, seen = defaultdict(list), defaultdict(list), defaultdict(int)
    rng = random.Random(0)
    for d in data.iter_documents():
        s = d["source_type"]
        lengths[s].append(len(d["content"] or ""))
        seen[s] += 1
        if len(samples[s]) < a.samples:  # reservoir sample so the examples are not just the first rows
            samples[s].append(d)
        elif rng.random() < a.samples / seen[s]:
            samples[s][rng.randrange(a.samples)] = d

    out = {}
    print(f"{'source':14}{'docs':>9}{'p50':>8}{'p90':>8}{'p99':>8}{'max':>9}{'total MB':>10}")
    for s, xs in sorted(lengths.items(), key=lambda kv: -len(kv[1])):
        xs.sort()
        out[s] = {"docs": len(xs), "chars_p50": pct(xs, 50), "chars_p90": pct(xs, 90), "chars_p99": pct(xs, 99),
                  "chars_max": xs[-1], "chars_total": sum(xs)}
        print(f"{s:14}{len(xs):>9}{pct(xs, 50):>8}{pct(xs, 90):>8}{pct(xs, 99):>8}{xs[-1]:>9}{sum(xs) / 1e6:>10.1f}")
    total = sum(v["chars_total"] for v in out.values())
    print(f"{'ALL':14}{sum(v['docs'] for v in out.values()):>9}{'':>33}{total / 1e6:>10.1f}")

    for s in out:
        for d in samples[s]:
            print(f"\n===== {s} | {d['doc_id']} | title: {d['title']!r} | {len(d['content'])} chars")
            print(d["content"][:a.chars])

    path = config.ROOT / "eval" / "results" / "ent_profile.json"
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
