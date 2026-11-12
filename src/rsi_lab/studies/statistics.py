"""Root-level estimands and paired percentile bootstrap, with explicit missingness."""
import random
from statistics import mean


def interval(values, *, seed=0, samples=2000):
    known = [v for v in values if v is not None]
    result = {"mean": mean(known) if known else None, "n": len(known),
              "missing": len(values) - len(known), "ci95": None,
              "unit": "independent_root", "bootstrap_samples": samples}
    if len(known) >= 2:
        rng = random.Random(seed)
        estimates = sorted(mean(rng.choices(known, k=len(known))) for _ in range(samples))
        result["ci95"] = [estimates[int(.025 * (samples - 1))], estimates[int(.975 * (samples - 1))]]
    return result


def summarize(rows, *, seed=0, samples=2000, references=None):
    groups = {}
    for row in rows:
        key = (row["method"], row["arm"], row["benchmark"])
        groups.setdefault(key, []).append(row)
    estimates, contrasts = [], []
    for (method, arm, benchmark), group in sorted(groups.items()):
        metrics = sorted({k for row in group for k in row["estimates"]})
        estimates.append({"method": method, "arm": arm, "benchmark": benchmark,
                          "metrics": {m: interval([r["estimates"].get(m) for r in group], seed=seed, samples=samples)
                                      for m in metrics}})
        reference_method = (references or {}).get(method, "frozen")
        reference = groups.get((method, "native_only", benchmark)) if arm != "native_only" else groups.get((reference_method, "native_only", benchmark))
        if reference is None or method == "frozen" and arm == "native_only":
            continue
        by_seed = {r["seed"]: r for r in reference}
        differences = {}
        for metric in metrics:
            values = []
            for row in group:
                ref = by_seed.get(row["seed"], {})
                a, b = row["estimates"].get(metric), ref.get("estimates", {}).get(metric)
                values.append(a - b if a is not None and b is not None else None)
            differences[metric] = interval(values, seed=seed, samples=samples)
        contrasts.append({"method": method, "arm": arm, "benchmark": benchmark,
                          "reference": "native_only" if arm != "native_only" else reference_method,
                          "direction": "treatment_minus_reference", "pairing": "seed;whole_roots_resampled",
                          "metrics": differences})
    return {"estimates": estimates, "contrasts": contrasts,
            "inference": "exploratory percentile bootstrap; no episode-level replication or significance claim"}
