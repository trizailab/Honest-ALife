"""
Веб-визуализация honest-ALife в реальном времени. Чистый stdlib (http.server + SSE).
Запуск:  python3 webapp/server.py   ->  открыть http://localhost:8000

Симуляция крутится в фоновом потоке; состояние стримится в браузер через Server-Sent Events.
Контроли (donate_amount, локальность размещения, divide_cost, мутации, скорость, seed, сценарий)
меняются на лету — видно фазовый переход «зло побеждает / добро выживает» вживую.
"""
import os
import sys
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine import (World, Config, COOPERATOR, DEFECTOR, ANCESTOR, EMPTY, NAMES,
                    classify_genome)

HERE = os.path.dirname(os.path.abspath(__file__))

# класс организма -> символ для раскраски ячеек
CLASS_CHAR = {"intact": "C", "defector": "D", "tagless": "T",
              "both_lost": "B", "variant": "V"}


class Sim:
    """Обёртка над World с потокобезопасным управлением и снапшотами для стрима."""
    def __init__(self):
        self.lock = threading.Lock()
        self.params = dict(
            scenario="mix",            # mix | pure_coop | ancestor
            soup_size=8000, max_organisms=80,
            donate_amount=40, offspring_local=False, donate_radius=600,
            offspring_radius=40,       # «радиус семьи»: меньше -> плотнее -> выше r
            divide_cost=300, energy_income=1, copy_mut_rate=0.0,
            mortality_rate=1.0 / 8000, seed=1,
        )
        self.speed = 60               # шагов за тик стрима (скорость)
        self.paused = False
        self.world = None
        self._build()

    def _build(self):
        p = self.params
        cfg = Config(metabolism=True, soup_size=p["soup_size"],
                     max_organisms=p["max_organisms"], energy_income=p["energy_income"],
                     divide_cost=p["divide_cost"], child_init_energy=10, energy_max=600,
                     donate_amount=p["donate_amount"], donate_cost=0,
                     donate_radius=p["donate_radius"], offspring_local=p["offspring_local"],
                     offspring_radius=p["offspring_radius"], copy_mut_rate=p["copy_mut_rate"],
                     mortality_rate=p["mortality_rate"])
        w = World(cfg, seed=p["seed"])
        sc = p["scenario"]
        if sc == "ancestor":
            w.inject(ANCESTOR, p["soup_size"] // 2, lineage=0)
        elif sc == "pure_coop":
            n = 8
            for i in range(n):
                w.inject(COOPERATOR, i * (p["soup_size"] // n), lineage=1)
        else:  # mix
            n = 8
            sp = p["soup_size"] // (2 * n)
            for i in range(2 * n):
                w.inject(COOPERATOR if i % 2 == 0 else DEFECTOR, i * sp,
                         lineage=1 if i % 2 == 0 else 2)
        self.world = w

    def set_params(self, upd):
        with self.lock:
            rebuild_keys = {"scenario", "soup_size", "max_organisms", "seed"}
            need_rebuild = any(k in upd and upd[k] != self.params.get(k) for k in rebuild_keys)
            for k, v in upd.items():
                if k == "speed":
                    self.speed = max(1, min(400, int(v)))
                elif k == "paused":
                    self.paused = bool(v)
                elif k in self.params:
                    self.params[k] = v
            if need_rebuild:
                self._build()
            elif self.world:                     # живое применение к текущему миру
                c = self.world.cfg
                c.donate_amount = self.params["donate_amount"]
                c.offspring_local = self.params["offspring_local"]
                c.donate_radius = self.params["donate_radius"]
                c.offspring_radius = self.params["offspring_radius"]
                c.divide_cost = self.params["divide_cost"]
                c.energy_income = self.params["energy_income"]
                c.copy_mut_rate = self.params["copy_mut_rate"]
                c.mortality_rate = self.params["mortality_rate"]

    def reset(self):
        with self.lock:
            self._build()

    def step_batch(self):
        with self.lock:
            if self.paused or self.world is None:
                return
            for _ in range(self.speed):
                self.world.step()
                if not self.world.organisms:
                    break

    def snapshot(self):
        with self.lock:
            w = self.world
            if w is None:
                return {}
            # класс каждого организма (по генотипу) -> символ
            id_char = {}
            for o in w.organisms:
                id_char[o.id] = CLASS_CHAR.get(classify_genome(w.genome_at(o.start, o.length)), "V")
            soup, owner = w.soup, w.owner
            cells = []
            for i in range(w.L):
                oid = owner[i]
                if oid == -1:
                    cells.append("." if soup[i] == EMPTY else "x")  # x: ничей код (космос)
                else:
                    ch = id_char.get(oid, "V")
                    cells.append(ch if soup[i] != EMPTY else ch.lower())  # lower = резерв
            ips = [o.ip for o in w.organisms]
            comp = w.composition(mature_only=True)
            r = w.realized_r()
            s = w.stats()
            # паразиты: организмы, исполняющие >=30% инструкций в ЧУЖОЙ памяти (cross_exec)
            parasites = sum(1 for o in w.organisms
                            if o.age > 0 and o.cross_exec / o.age >= 0.3)
            return {
                "cells": "".join(cells),
                "ips": ips,
                "L": w.L,
                "stats": {
                    "step": s["step"], "pop": s["pop"], "births": s["births"],
                    "deaths": s["deaths"], "donations": s["donations"],
                    "avg_len": s["avg_len"], "avg_energy": s["avg_energy"],
                    "cross_exec": s["cross_exec"], "energy_ok": s["energy_ok"],
                    "parasites": parasites,
                    "intact": comp["intact"], "defector": comp["defector"],
                    "tagless": comp["tagless"], "both_lost": comp["both_lost"],
                    "variant": comp["variant"],
                    "realized_r": (round(r, 3) if r is not None else None),
                    "deaths_by": s["deaths_by"],
                },
                "params": dict(self.params, speed=self.speed, paused=self.paused),
            }


SIM = Sim()


def sim_loop():
    while True:
        SIM.step_batch()
        time.sleep(0.05)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if body:
            self.wfile.write(body if isinstance(body, bytes) else body.encode())

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                self._send(200, "text/html; charset=utf-8", f.read())
        elif self.path == "/stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            try:
                while True:
                    frame = SIM.snapshot()
                    self.wfile.write(b"data: " + json.dumps(frame).encode() + b"\n\n")
                    self.wfile.flush()
                    time.sleep(0.08)
            except (BrokenPipeError, ConnectionResetError):
                return
        else:
            self._send(404, "text/plain", "not found")

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(n) if n else b"{}"
        try:
            data = json.loads(body or b"{}")
        except Exception:
            data = {}
        if self.path == "/control":
            SIM.set_params(data)
            self._send(200, "application/json", b'{"ok":true}')
        elif self.path == "/reset":
            if data:
                SIM.set_params(data)
            SIM.reset()
            self._send(200, "application/json", b'{"ok":true}')
        else:
            self._send(404, "text/plain", "not found")


def _ips():
    """Адреса, по которым доступен сервер (для подключения по IP)."""
    import socket
    found = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))            # ничего не шлёт, лишь выясняет исходящий IP
        found.append(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    try:
        for ip in os.popen("hostname -I").read().split():
            if ":" not in ip and ip not in found:
                found.append(ip)
    except Exception:
        pass
    return found


def main():
    threading.Thread(target=sim_loop, daemon=True).start()
    port = int(os.environ.get("PORT", "8000"))
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print("=" * 52)
    print("  Honest-ALife webapp запущен (слушает 0.0.0.0)")
    print(f"  локально:   http://localhost:{port}")
    for ip in _ips():
        print(f"  по IP:      http://{ip}:{port}")
    print("=" * 52)
    print("  Ctrl+C — остановить")
    srv.serve_forever()


if __name__ == "__main__":
    main()
