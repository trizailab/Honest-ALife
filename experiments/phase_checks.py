"""Быстрые проверки честности: C2 (детерминизм) и предпросмотр P1 (паразитизм по метрике)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine import World, Config, ANCESTOR


def control_C2(seed=7, steps=2000):
    """Один seed -> побитово один и тот же прогон."""
    def run():
        w = World(Config(copy_mut_rate=0.01, cosmic_rate=0.0001), seed=seed)
        w.inject(ANCESTOR, start=0, lineage=1)
        for _ in range(steps):
            w.step()
        return w.soup[:], w.stats()
    s1, st1 = run()
    s2, st2 = run()
    ok = (s1 == s2 and st1 == st2)
    print("=== Control C2 (детерминизм) ===")
    print("stats:", st1)
    print("C2:", "PASS ✅" if ok else "FAIL ❌")
    return ok


def preview_P1(seed=3, steps=30000, mut=0.018, cosmic=0.0):
    """Мутации on. Смотрим: возникает ли паразитизм (cross_exec по метрике) и дрейф длины генома."""
    w = World(Config(soup_size=4000, max_organisms=80,
                     copy_mut_rate=mut, cosmic_rate=cosmic), seed=seed)
    w.inject(ANCESTOR, start=0, lineage=1)
    print(f"=== Preview P1 (mutation={mut}, cosmic={cosmic}, seed={seed}) ===")
    print(f"{'step':>6} {'pop':>4} {'avg_len':>8} {'cross_exec':>11} {'max_cx/age':>11} {'births':>7}")
    for t in range(steps):
        w.step()
        if (t + 1) % 5000 == 0:
            orgs = w.organisms
            # доля исполнений в чужой памяти у самого «паразитического» из живых
            ratio = 0.0
            if orgs:
                ratio = max((o.cross_exec / o.age) if o.age else 0.0 for o in orgs)
            s = w.stats()
            print(f"{s['step']:>6} {s['pop']:>4} {s['avg_len']:>8} "
                  f"{s['cross_exec']:>11} {ratio:>11.3f} {s['births']:>7}")
            if not orgs:
                print("  -> вымирание")
                break


if __name__ == "__main__":
    control_C2()
    print()
    preview_P1()
