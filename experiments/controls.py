"""
Решающие контроли честности (DESIGN.md, фаза 5). Гейт перед любым выводом — C5.

  C4  — сохранение энергии каждый шаг при активных DONATE + смерти + Жнец.
  C5  — donate_amount=0, length/tick-matched: НЕТ систематического вторжения дефектора
        при низкой r и НЕТ коллапса при высокой r (среднее по N seeds ≈ дрейф 0.5).
  C5b — mutation-off 50/50, donate>0: дефектор побеждает -> это ОТБОР (а не мутац. давление).
  C12 — mutation=0 чистые кооператоры: все зрелые 'intact', реализованных донаций > 0.
"""
import os
import sys
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine import World, Config, COOPERATOR, DEFECTOR

# Репродукционно-лимитированный, связывающий по энергии базовый режим.
BASE = dict(
    metabolism=True, soup_size=8000, max_organisms=80,
    energy_income=1, divide_cost=300, child_init_energy=10, energy_max=600,
    donate_cost=0, donate_radius=600, offspring_radius=150,
)


def run_competition(p):
    """Один прогон конкуренции кооператоров vs дефекторов. p — dict параметров + seed."""
    cfg = Config(donate_amount=p["donate_amount"],
                 offspring_local=p["offspring_local"],
                 copy_mut_rate=p.get("copy_mut_rate", 0.0),
                 **BASE)
    w = World(cfg, seed=p["seed"])
    n = p["n"]
    # чередуем coop/def -> пространственная симметрия типов (нет позиционного перекоса)
    spacing = cfg.soup_size // (2 * n)
    for i in range(2 * n):
        g = COOPERATOR if (i % 2 == 0) else DEFECTOR
        lin = 1 if (i % 2 == 0) else 2
        w.inject(g, i * spacing, lineage=lin)
    c4_ok = True
    check_every = p.get("check_c4", 0)
    for t in range(p["steps"]):
        w.step()
        if check_every and (t % check_every == 0) and not w.energy_check():
            c4_ok = False
    comp = w.composition(mature_only=True)
    tot = comp["intact"] + comp["defector"]
    frac_def = (comp["defector"] / tot) if tot else None
    return {
        "seed": p["seed"], "intact": comp["intact"], "defector": comp["defector"],
        "frac_def": frac_def, "pop": w.stats()["pop"], "donations": w.donations_made,
        "c4_ok": (c4_ok and w.energy_check()),
    }


def _pool_map(fn, jobs):
    procs = min(8, os.cpu_count() or 1)
    with mp.Pool(procs) as pool:
        return pool.map(fn, jobs)


def _summary(results):
    fr = [r["frac_def"] for r in results if r["frac_def"] is not None]
    ext = sum(1 for r in results if r["pop"] == 0)
    if not fr:
        return {"n": len(results), "extinct": ext, "mean_frac_def": None}
    mean = sum(fr) / len(fr)
    inv = sum(1 for x in fr if x >= 0.9)
    rep = sum(1 for x in fr if x <= 0.1)
    return {"n": len(results), "extinct": ext, "mean_frac_def": round(mean, 3),
            "invaded(>=.9)": inv, "repelled(<=.1)": rep,
            "coexist": len(fr) - inv - rep,
            "min": round(min(fr), 2), "max": round(max(fr), 2)}


def control_C4(seeds=range(6)):
    print("=== C4 — сохранение энергии (DONATE + мутации + все смерти) ===")
    jobs = [dict(donate_amount=40, offspring_local=(s % 2 == 0), copy_mut_rate=0.02,
                 n=8, seed=s, steps=20000, check_c4=1) for s in seeds]
    res = _pool_map(run_competition, jobs)
    ok = all(r["c4_ok"] for r in res)
    print(f"  все {len(res)} прогонов: energy_check каждый шаг = {ok}")
    print("  C4:", "PASS ✅" if ok else "FAIL ❌")
    return ok


def control_C5(N=24, steps=50000):
    print("=== C5 (DECISIVE) — нулевые ставки donate_amount=0, length/tick-matched ===")
    out = {}
    for loc, name in [(False, "global (низкая r)"), (True, "local (высокая r)")]:
        jobs = [dict(donate_amount=0, offspring_local=loc, copy_mut_rate=0.0,
                     n=8, seed=s, steps=steps) for s in range(N)]
        res = _pool_map(run_competition, jobs)
        s = _summary(res)
        out[loc] = s
        print(f"  {name}: {s}")
    # PASS: среднее ≈ 0.5 (дрейф), нет систематического перекоса к дефектору/коллапса
    ok = True
    for loc, s in out.items():
        if s["mean_frac_def"] is None:
            ok = False
        elif not (0.30 <= s["mean_frac_def"] <= 0.70):
            ok = False
    print("  Ожидание: среднее frac_def ≈ 0.5 (нейтральный дрейф), без систематич. вторжения.")
    print("  C5:", "PASS ✅" if ok else "FAIL ❌  (остаточная асимметрия = подстройка!)")
    return ok, out


def control_C5b(N=24, steps=50000):
    print("=== C5b — mutation-off 50/50, donate>0: отбор vs мутац. давление ===")
    for loc, name in [(False, "global (низкая r)"), (True, "local (высокая r)")]:
        jobs = [dict(donate_amount=40, offspring_local=loc, copy_mut_rate=0.0,
                     n=8, seed=s, steps=steps) for s in range(N)]
        res = _pool_map(run_competition, jobs)
        print(f"  {name}: {_summary(res)}")
    print("  (mutation OFF -> любой перекос = чистый ОТБОР, не мутационное давление)")


def control_C12(seeds=range(6), steps=40000):
    print("=== C12 — mutation=0 чистые кооператоры: все зрелые 'intact', донаций > 0 ===")
    def run_pure(seed):
        cfg = Config(donate_amount=40, offspring_local=True, copy_mut_rate=0.0, **BASE)
        w = World(cfg, seed=seed)
        n = 8
        sp = cfg.soup_size // n
        for i in range(n):
            w.inject(COOPERATOR, i * sp, lineage=1)
        for _ in range(steps):
            w.step()
        c = w.composition(mature_only=True)
        bad = c["defector"] + c["tagless"] + c["both_lost"]
        return (bad == 0 and c["intact"] > 0, w.donations_made, c)
    res = [run_pure(s) for s in seeds]
    ok = all(r[0] for r in res) and all(r[1] > 0 for r in res)
    print(f"  прогоны: {[(r[2]['intact'], 'don=' + str(r[1])) for r in res]}")
    print("  C12:", "PASS ✅" if ok else "FAIL ❌")
    return ok


if __name__ == "__main__":
    c4 = control_C4()
    print()
    c12 = control_C12()
    print()
    c5, _ = control_C5()
    print()
    control_C5b()
    print()
    print("ГЕЙТ C5:", "ОТКРЫТ ✅ (можно делать выводы)" if c5 else "ЗАКРЫТ ❌ (сначала убрать асимметрию)")
