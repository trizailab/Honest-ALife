"""
Фазовый sweep (DESIGN.md): репортим КАЖДУЮ ячейку. Колонка donate_amount=0 — нулевой контроль
(C5) в каждой строке. Гипотеза Гамильтона проверяется по ИЗМЕРЕННЫМ r,B,C, не по ручкам.

Выход: experiments/sweep.jsonl (по строке на ячейку) + сводная таблица в stdout.
"""
import os
import sys
import json
import itertools
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine import World, Config, COOPERATOR, DEFECTOR

BASE = dict(metabolism=True, soup_size=8000, max_organisms=80,
            energy_income=1, child_init_energy=10, energy_max=600,
            donate_cost=0, offspring_radius=150)

GRID = dict(
    offspring_local=[False, True],
    donate_radius=[150, 600],
    donate_amount=[0, 30, 60],     # 0 = нулевой контроль (C5) в каждой строке
    divide_cost=[280, 340],
)
SEEDS = list(range(16))
STEPS = 25000
N = 8                              # 8 coop + 8 def, interleaved


def run_cell(job):
    cell, seed = job
    cfg = Config(offspring_local=cell["offspring_local"], donate_radius=cell["donate_radius"],
                 donate_amount=cell["donate_amount"], divide_cost=cell["divide_cost"],
                 copy_mut_rate=0.0, **BASE)
    w = World(cfg, seed=seed)
    spacing = cfg.soup_size // (2 * N)
    for i in range(2 * N):
        w.inject(COOPERATOR if i % 2 == 0 else DEFECTOR, i * spacing,
                 lineage=1 if i % 2 == 0 else 2)
    r_samples, e_samples = [], []
    for t in range(STEPS):
        w.step()
        if t in (STEPS // 4, STEPS // 2, 3 * STEPS // 4):
            r = w.realized_r()
            if r is not None:
                r_samples.append(r)
            o = w.organisms
            if o:
                e_samples.append(sum(x.energy for x in o) / len(o))
    comp = w.composition(mature_only=True)
    tot = comp["intact"] + comp["defector"]
    avg_e = sum(e_samples) / len(e_samples) if e_samples else 0.0
    return {**cell, "seed": seed,
            "intact": comp["intact"], "defector": comp["defector"],
            "frac_def": (comp["defector"] / tot) if tot else None,
            "pop": len(w.organisms), "donations": w.donations_made,
            "realized_r": (sum(r_samples) / len(r_samples)) if r_samples else None,
            "avg_energy": round(avg_e, 1),
            "c4_ok": w.energy_check()}


def main():
    cells = [dict(zip(GRID, vals)) for vals in itertools.product(*GRID.values())]
    jobs = [(c, s) for c in cells for s in SEEDS]
    print(f"sweep: {len(cells)} ячеек × {len(SEEDS)} seeds = {len(jobs)} прогонов × {STEPS} шагов")
    procs = min(8, os.cpu_count() or 1)
    with mp.Pool(procs) as pool:
        results = pool.map(run_cell, jobs)

    path = os.path.join(os.path.dirname(__file__), "sweep.jsonl")
    with open(path, "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")

    # сводка по ячейкам
    print(f"\n{'loc':>5} {'dRad':>5} {'A':>3} {'D':>4} | {'mean_fd':>7} {'inv':>3} {'rep':>3} "
          f"{'cox':>3} {'ext':>3} | {'r':>6} {'avgE':>5} {'don':>6} c4")
    by = {}
    for r in results:
        k = (r["offspring_local"], r["donate_radius"], r["donate_amount"], r["divide_cost"])
        by.setdefault(k, []).append(r)
    for k in sorted(by):
        rs = by[k]
        fr = [x["frac_def"] for x in rs if x["frac_def"] is not None]
        ext = sum(1 for x in rs if x["pop"] == 0)
        rr = [x["realized_r"] for x in rs if x["realized_r"] is not None]
        mfd = round(sum(fr) / len(fr), 2) if fr else None
        inv = sum(1 for x in fr if x >= 0.9)
        rep = sum(1 for x in fr if x <= 0.1)
        cox = len(fr) - inv - rep
        mr = round(sum(rr) / len(rr), 2) if rr else None
        avgE = round(sum(x["avg_energy"] for x in rs) / len(rs))
        don = round(sum(x["donations"] for x in rs) / len(rs))
        c4 = all(x["c4_ok"] for x in rs)
        loc = "L" if k[0] else "G"
        print(f"{loc:>5} {k[1]:>5} {k[2]:>3} {k[3]:>4} | {str(mfd):>7} {inv:>3} {rep:>3} "
              f"{cox:>3} {ext:>3} | {str(mr):>6} {avgE:>5} {don:>6} {'ok' if c4 else 'XX'}")
    print(f"\nJSONL -> {path}")


if __name__ == "__main__":
    main()
