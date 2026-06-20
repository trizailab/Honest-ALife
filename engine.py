"""
Honest ALife engine — ядро эксперимента о «природе зла».

Честность (см. DESIGN.md):
  H4  защита записи: организм пишет только в свой выделенный блок; читает/исполняет везде.
  H5  provenance: owner[cell] = id организма-владельца; паразитизм ИЗМЕРЯЕТСЯ (cross_exec),
      а не оценивается на глаз.
  H6  детерминизм: вся случайность через self.rng (random.Random(seed)).

Фаза 1: VM + соус + template-addressing + рукописный предок. Контроль C1.
DONATE (фаза 5) пока определён как опкод, но инертен (no-op).
"""

import random

# ------------------------------------------------------------------ ISA --------
# Опкоды. EMPTY — маркер пустой ячейки супа (не опкод).
EMPTY = -1
(NOP0, NOP1, SEARCHB, SEARCHF, SUB_CX_BA,
 INCC, MAL, COPY, IFZ, JMPB, DIVIDE, DONATE) = range(12)
NUM_OPS = 12  # 0..11; mutation выбирает из этого диапазона

NAMES = {
    EMPTY: ".",
    NOP0: "0", NOP1: "1", SEARCHB: "b", SEARCHF: "f", SUB_CX_BA: "-",
    INCC: "+", MAL: "M", COPY: "C", IFZ: "?", JMPB: "J", DIVIDE: "D", DONATE: "$",
}
NAME2OP = {  # для ассемблера предка
    "NOP0": NOP0, "NOP1": NOP1, "SEARCHB": SEARCHB, "SEARCHF": SEARCHF,
    "SUB_CX_BA": SUB_CX_BA, "INCC": INCC, "MAL": MAL, "COPY": COPY,
    "IFZ": IFZ, "JMPB": JMPB, "DIVIDE": DIVIDE, "DONATE": DONATE,
}


def assemble(names):
    return [NAME2OP[n] for n in names]


# Предок: самокопирующийся организм (длина 41).
# Адресация — комплементарными шаблонами фиксированной длины TEMPLATE_LEN=4.
# Чтобы найти маркер M, операнд = complement(M); поиск ищет complement(операнда)=M.
ANCESTOR_SRC = [
    # --- T_BEGIN = 1111 (маркер начала) [0..3]
    "NOP1", "NOP1", "NOP1", "NOP1",
    # --- найти своё начало: SEARCHB, операнд 0000 -> ищет 1111 назад -> AX [4..8]
    "SEARCHB", "NOP0", "NOP0", "NOP0", "NOP0",
    # --- найти свой конец: SEARCHF, операнд 0001 -> ищет 1110 вперёд -> BX [9..13]
    "SEARCHF", "NOP0", "NOP0", "NOP0", "NOP1",
    # --- CX = BX - AX [14]
    "SUB_CX_BA",
    # --- CX += 4 (включить длину T_END в размер потомка) [15..18]
    "INCC", "INCC", "INCC", "INCC",
    # --- выделить CX ячеек -> DX = начало потомка; зарезервировать+owner [19]
    "MAL",
    # --- T_LOOP = 1101 (метка тела цикла) [20..23]
    "NOP1", "NOP1", "NOP0", "NOP1",
    # --- цикл копирования: COPY ; IFZ(skip-if-zero) ; JMPB к T_LOOP [24..30]
    "COPY",
    "IFZ",
    "JMPB", "NOP0", "NOP0", "NOP1", "NOP0",   # операнд 0010 -> compl 1101 = T_LOOP
    # --- закончили копирование -> породить потомка [31]
    "DIVIDE",
    # --- размножаться снова: JMPB к T_BEGIN (операнд 0000 -> compl 1111) [32..36]
    "JMPB", "NOP0", "NOP0", "NOP0", "NOP0",
    # --- T_END = 1110 (маркер конца) [37..40]
    "NOP1", "NOP1", "NOP1", "NOP0",
]
ANCESTOR = assemble(ANCESTOR_SRC)


# Кооператор: предок + тег-«зелёная борода» T_KIN + шаг DONATE к носителям T_KIN.
# Layout B (тег ОТДЕЛЁН от поведения): дефектор может потерять DONATE, но сохранить тег
# -> продолжает ПОЛУЧАТЬ донации (классический falsebeard / зелёнобородый предатель).
# Та же длина и то же число тактов, что у дефектора (DONATE peek-not-consume) — P0.
COOPERATOR_SRC = [
    # T_BEGIN = 1111 [0..3]
    "NOP1", "NOP1", "NOP1", "NOP1",
    # find start: SEARCHB operand 0000 -> 1111 [4..8]
    "SEARCHB", "NOP0", "NOP0", "NOP0", "NOP0",
    # find end: SEARCHF operand 0001 -> 1110 [9..13]
    "SEARCHF", "NOP0", "NOP0", "NOP0", "NOP1",
    # CX = BX-AX [14]
    "SUB_CX_BA",
    # T_KIN = 1010 [15..18] — «борода»: обрамлён не-NOP (SUB_CX_BA / INCC) -> изолирован
    "NOP1", "NOP0", "NOP1", "NOP0",
    # CX += 4 [19..22]
    "INCC", "INCC", "INCC", "INCC",
    # MAL [23]
    "MAL",
    # T_LOOP = 1101 [24..27]
    "NOP1", "NOP1", "NOP0", "NOP1",
    # copy loop: COPY ; IFZ ; JMPB(operand 0010 -> 1101) [28..34]
    "COPY", "IFZ", "JMPB", "NOP0", "NOP0", "NOP1", "NOP0",
    # DIVIDE [35]
    "DIVIDE",
    # DONATE кин: operand 0101 -> target 1010 = T_KIN [36..40]
    "DONATE", "NOP0", "NOP1", "NOP0", "NOP1",
    # reproduce: JMPB к T_BEGIN (operand 0000 -> 1111) [41..45]
    "JMPB", "NOP0", "NOP0", "NOP0", "NOP0",
    # T_END = 1110 [46..49]
    "NOP1", "NOP1", "NOP1", "NOP0",
]
COOPERATOR = assemble(COOPERATOR_SRC)
COOP_LEN = len(COOPERATOR)        # 50

# Локусы для СТАТИЧЕСКОЙ классификации по генотипу (точечные мутации не сдвигают позиции).
DONATE_LOCUS = 36
DONATE_OPERAND = [NOP0, NOP1, NOP0, NOP1]   # [37..40] -> complement 1010 = T_KIN
TKIN_LOCUS = 15
TKIN_TAG = [NOP1, NOP0, NOP1, NOP0]         # [15..18] = 1010

# Дефектор = кооператор с точечной мутацией DONATE->NOP0 (ТА ЖЕ длина, то же число тактов).
DEFECTOR = list(COOPERATOR)
DEFECTOR[DONATE_LOCUS] = NOP0


def classify_genome(genome):
    """4 класса по статической структуре (P0): intact / defector(falsebeard) / tagless / both_lost.
    genome — список опкодов организма. Длина != COOP_LEN -> 'variant' (инделоподобный мутант)."""
    if len(genome) != COOP_LEN:
        return "variant"
    has_op = (genome[DONATE_LOCUS] == DONATE and
              genome[DONATE_LOCUS + 1:DONATE_LOCUS + 5] == DONATE_OPERAND)
    has_tag = genome[TKIN_LOCUS:TKIN_LOCUS + 4] == TKIN_TAG
    if has_op and has_tag:
        return "intact"        # кооператор: и отдаёт, и узнаваем
    if has_tag and not has_op:
        return "defector"      # falsebeard: тег сохранён, отдавать перестал -> получает даром
    if has_op and not has_tag:
        return "tagless"       # отдаёт, но не узнаётся (тег потерян)
    return "both_lost"


# ----------------------------------------------------------------- Config ------
class Config:
    def __init__(self, **kw):
        self.soup_size = 4000        # L — размер супа (тор)
        self.max_organisms = 60      # лимит популяции -> Жнец
        self.template_len = 4        # фикс. длина шаблона (содержимое эволюционирует, длина — нет)
        self.search_limit = 512      # радиус поиска шаблона
        self.min_genome = 4
        self.max_genome = 256
        self.alloc_probes = 80       # попыток найти свободный блок при MAL
        self.copy_mut_rate = 0.0     # мутация при COPY (фаза 3+)
        self.cosmic_rate = 0.0       # фоновое повреждение ячеек (фаза 3+)
        # Жнец: очередь смерти, управляемая ошибками (аутентичный Tierra).
        # Рождение -> в середину очереди; ошибка -> ближе к смерти; косим с головы.
        self.reaper_fault_bump = 8   # на сколько позиций ошибка двигает к смерти
        self.reaper_lost_bump = 1    # bump за исполнение пустой ячейки (потерянный IP)
        # Смертность: постоянный риск (экспоненц. продолжительность жизни). Убирает и
        # бессмертных «зомби», и синхронные когорты. Линия выживает, только если
        # размножается быстрее, чем умирает; коллапс = честное вымирание.
        self.mortality_rate = 1.0 / 8000   # вероятность смерти за такт
        self.max_age = None                # необязательный жёсткий потолок (None=выкл)
        # Метаболизм (фаза 4): энергия — ЦЕЛОЧИСЛЕННЫЙ ресурс (точное сохранение, C4).
        # Выкл -> энергия не влияет (C1/C2 и чистые тесты остаются такими же).
        self.metabolism = False
        self.start_energy = 100       # энергия впрыснутого организма
        self.energy_income = 1        # «свет»: прибавка за такт, ОДИНАКОВА для всех
        self.energy_max = 2000        # потолок (высокий -> не cap-saturated режим)
        self.divide_cost = 100        # стоимость деления (платит родитель)
        self.child_init_energy = 20   # стартовая энергия потомка (берётся из divide_cost)
        # DONATE (фаза 5): нейтральный примитив переноса энергии.
        self.donate_amount = 40       # сколько энергии переносит (sweep)
        self.donate_cost = 0          # сжигается при акте доната (sweep)
        self.donate_radius = 200      # радиус поиска получателя (ОТДЕЛЬНО от локальности)
        # Локальность потомства = ассортативность r (ОТДЕЛЬНО от donate_radius).
        self.offspring_local = False  # True -> потомок рядом с родителем (высокая r)
        self.offspring_radius = 120   # радиус размещения потомка при offspring_local
        for k, v in kw.items():
            if not hasattr(self, k):
                raise KeyError(f"unknown config key: {k}")
            setattr(self, k, v)


# --------------------------------------------------------------- Organism ------
class Organism:
    __slots__ = ("id", "start", "length", "ip", "ax", "bx", "cx", "dx",
                 "daughter_start", "daughter_size", "age", "offspring",
                 "fault", "illegal_write", "cross_exec", "cross_read",
                 "parent_id", "lineage", "jumped", "energy",
                 "donated", "received", "donate_events")

    def __init__(self, oid, start, length, ip, parent_id=-1, lineage=0, energy=0.0):
        self.id = oid
        self.start = start
        self.length = length
        self.ip = ip
        self.ax = self.bx = self.cx = self.dx = 0
        self.daughter_start = None
        self.daughter_size = 0
        self.age = 0
        self.offspring = 0
        self.fault = 0            # некорректные операции (плохой размер, нет памяти и т.п.)
        self.illegal_write = 0   # попытки записи вне своего блока (H4)
        self.cross_exec = 0      # шаги исполнения в чужой памяти (метрика паразитизма, H5)
        self.cross_read = 0      # чтения чужих ячеек при COPY (вторичная метрика)
        self.parent_id = parent_id
        self.lineage = lineage   # тег линии (наследуется; для генеалогии)
        self.jumped = False
        self.energy = energy
        self.donated = 0.0       # сколько энергии отдал (фаза 5)
        self.received = 0.0      # сколько энергии получил (фаза 5)
        self.donate_events = 0   # сколько раз успешно исполнил DONATE (классификация кооператора)


# ----------------------------------------------------------------- World -------
class World:
    def __init__(self, config=None, seed=0):
        self.cfg = config or Config()
        self.L = self.cfg.soup_size
        self.seed = seed
        # Независимые RNG-потоки из master seed (C9): смена ассортативности не должна
        # сдвигать историю мутаций. placement / mutation / cosmic — раздельно.
        master = random.Random(seed)
        self.rng_place = random.Random(master.randint(0, 2**31 - 1))
        self.rng_mut = random.Random(master.randint(0, 2**31 - 1))
        self.rng_cosmic = random.Random(master.randint(0, 2**31 - 1))
        self.rng_death = random.Random(master.randint(0, 2**31 - 1))
        self.soup = [EMPTY] * self.L
        self.owner = [-1] * self.L     # provenance: id организма-владельца ячейки
        self.organisms = []
        self.by_id = {}                # id -> Organism (для DONATE и учёта)
        self.queue = []                # очередь смерти (index 0 = next to die)
        self._next_id = 0
        self.step_count = 0
        # глобальные метрики
        self.births = 0
        self.deaths = 0
        self.cross_exec_total = 0
        self.cross_read_total = 0
        self.illegal_write_total = 0
        # энергетический реестр (C4): sum(alive.energy) == energy_in - energy_out
        self.energy_in = 0
        self.energy_out = 0
        # учёт донаций (C14) и причин смерти по типам (C7)
        self.donations_made = 0
        self.energy_donated = 0
        self.self_deal_blocked = 0
        self.cross_exec_donations = 0   # донации, исполненные в чужой памяти
        self.deaths_by = {"starv": 0, "age": 0, "reap": 0}

    # --- helpers -------------------------------------------------------------
    def _new_id(self):
        i = self._next_id
        self._next_id += 1
        return i

    def _wrap(self, a):
        return a % self.L

    def inject(self, genome, start, lineage=0):
        """Поместить геном в суп и создать организм (owner = новый организм)."""
        e = self.cfg.start_energy if self.cfg.metabolism else 0
        org = Organism(self._new_id(), start, len(genome), ip=start,
                       lineage=lineage, energy=e)
        self.energy_in += e
        for k, op in enumerate(genome):
            a = self._wrap(start + k)
            self.soup[a] = op
            self.owner[a] = org.id
        self.organisms.append(org)
        self.by_id[org.id] = org
        self._queue_insert(org)
        return org

    # --- death queue ---------------------------------------------------------
    def _queue_insert(self, org):
        self.queue.insert(len(self.queue) // 2, org)  # новички — в середину

    def _bump_death(self, org, amt):
        try:
            idx = self.queue.index(org)
        except ValueError:
            return
        new = max(0, idx - amt)
        if new != idx:
            self.queue.pop(idx)
            self.queue.insert(new, org)

    def genome_at(self, start, length):
        return [self.soup[self._wrap(start + k)] for k in range(length)]

    # --- template matching ---------------------------------------------------
    def _read_template(self, ip):
        """Прочитать TEMPLATE_LEN ячеек после ip как шаблон, вернуть target=complement."""
        tlen = self.cfg.template_len
        target = []
        for k in range(tlen):
            p = self.soup[self._wrap(ip + 1 + k)]
            target.append((1 - p) if p in (0, 1) else None)  # None => шаблон испорчен
        return target

    def _match(self, a, target):
        for k, t in enumerate(target):
            if t is None:
                return False
            if self.soup[self._wrap(a + k)] != t:
                return False
        return True

    def _search(self, ip, target, backward):
        R = self.cfg.search_limit
        for d in range(1, R + 1):
            a = self._wrap(ip - d) if backward else self._wrap(ip + d)
            if self._match(a, target):
                return a
        return None

    # --- instructions --------------------------------------------------------
    def _do_search(self, org, backward):
        target = self._read_template(org.ip)
        found = self._search(org.ip, target, backward)
        if backward:
            org.ax = found if found is not None else org.ip
        else:
            org.bx = found if found is not None else org.ip
        org.ip = self._wrap(org.ip + 1 + self.cfg.template_len)
        org.jumped = True

    def _free_range(self, oid, base, ln):
        for k in range(ln):
            a = self._wrap(base + k)
            if self.owner[a] == oid:
                self.owner[a] = -1
                self.soup[a] = EMPTY

    def _do_mal(self, org):
        # освободить ранее зарезервированный, но не использованный блок потомка (от утечки)
        if org.daughter_start is not None:
            self._free_range(org.id, org.daughter_start, org.daughter_size)
            org.daughter_start = None
        size = org.cx
        if size < self.cfg.min_genome or size > self.cfg.max_genome:
            org.fault += 1
            self._bump_death(org, self.cfg.reaper_fault_bump)
            org.daughter_start = None
            return
        start = self._find_free(size, near=org.start)
        if start is None:
            org.fault += 1
            self._bump_death(org, self.cfg.reaper_fault_bump)
            org.daughter_start = None
            return
        for k in range(size):
            self.owner[self._wrap(start + k)] = org.id
        org.daughter_start = start
        org.daughter_size = size
        org.dx = start  # dest-указатель для COPY (src = AX)

    def _block_free(self, s, size):
        for k in range(size):
            if self.owner[self._wrap(s + k)] != -1:
                return False
        return True

    def _find_free(self, size, near=None):
        """Свободный блок длины size. near != None и offspring_local -> рядом с родителем
        (высокая ассортативность r); иначе глобально-случайно. Поток rng_place (C9).
        Фолбэк-скан гарантирует размещение, если место вообще есть (нет фрагментац. вымирания)."""
        L = self.L
        local = self.cfg.offspring_local and near is not None
        rad = self.cfg.offspring_radius
        for _ in range(self.cfg.alloc_probes):
            if local:
                s = self._wrap(near + self.rng_place.randint(-rad, rad))
            else:
                s = self.rng_place.randint(0, L - 1)
            if self._block_free(s, size):
                return s
        if local:
            # фолбэк В ЛОКАЛЬНОМ режиме: ближайший к родителю свободный блок (семьи плотные,
            # высокая r), а не глобальное рассеивание — иначе ассортативность разрушается.
            for d in range(1, L):
                for s in (self._wrap(near + d), self._wrap(near - d)):
                    if self._block_free(s, size):
                        return s
        else:
            base = self.rng_place.randint(0, L - 1)   # глоб. скан от случайной базы
            for off in range(L):
                s = self._wrap(base + off)
                if self._block_free(s, size):
                    return s
        return None

    def _do_copy(self, org):
        if org.daughter_start is None:
            org.fault += 1
            return
        src = org.ax
        dest = org.dx
        ds, sz = org.daughter_start, org.daughter_size
        within = (dest - ds) % self.L < sz
        if not within or self.owner[dest] != org.id:  # H4 защита записи
            org.illegal_write += 1
            self.illegal_write_total += 1
            self._bump_death(org, self.cfg.reaper_fault_bump)
            return
        val = self.soup[src]
        if self.owner[src] != -1 and self.owner[src] != org.id:  # вторичная метрика
            org.cross_read += 1
            self.cross_read_total += 1
        if self.cfg.copy_mut_rate and self.rng_mut.random() < self.cfg.copy_mut_rate:
            val = self.rng_mut.randint(0, NUM_OPS - 1)
        self.soup[dest] = val
        self.owner[dest] = org.id
        org.ax = self._wrap(org.ax + 1)
        org.dx = self._wrap(org.dx + 1)
        org.cx = self._wrap(org.cx - 1)

    def _do_jmpb(self, org):
        target = self._read_template(org.ip)
        found = self._search(org.ip, target, backward=True)
        if found is not None:
            org.ip = found
        else:
            org.ip = self._wrap(org.ip + 1 + self.cfg.template_len)
        org.jumped = True

    def _search_nearest_foreign(self, org, target, radius):
        """Ближайшая ЧУЖАЯ ячейка (owner != self, != -1), совпадающая с шаблоном.
        Двусторонний поиск по тору; tie-break: вперёд раньше назад (детерминированно)."""
        for d in range(1, radius + 1):
            for a in (self._wrap(org.ip + d), self._wrap(org.ip - d)):
                o = self.owner[a]
                if o != -1 and o != org.id and self._match(a, target):
                    return a
        return None

    def _do_donate(self, org):
        """Нейтральный перенос энергии кин-носителю. peek-not-consume: IP += 1 как у NOP,
        чтобы рабочий и замутированный (в NOP) DONATE стоили одинаковое число тактов (P0)."""
        if not self.cfg.metabolism:
            return
        target = self._read_template(org.ip)          # complement(operand) = что ищем (T_KIN)
        found = self._search_nearest_foreign(org, target, self.cfg.donate_radius)
        if found is None:
            return                                     # неуспех — no-op, НЕ наказывается
        recip = self.by_id.get(self.owner[found])
        if recip is None:
            return
        if recip.id == org.id:                         # self-deal невозможен (уже отфильтрован)
            self.self_deal_blocked += 1
            return
        give = min(self.cfg.donate_amount, org.energy - self.cfg.donate_cost)
        if give <= 0:
            return                                     # не хватает энергии — no-op
        org.energy -= (give + self.cfg.donate_cost)
        recip.energy += give                           # БЕЗ потолка -> энергия не уничтожается
        self.energy_out += self.cfg.donate_cost        # сожжённая стоимость акта -> реестр
        org.donated += give
        recip.received += give
        org.donate_events += 1
        self.donations_made += 1
        self.energy_donated += give
        if self.owner[org.ip] != -1 and self.owner[org.ip] != org.id:
            self.cross_exec_donations += 1             # паразит исполнил DONATE хозяина

    def _do_divide(self, org):
        if org.daughter_start is None:
            org.fault += 1
            self._bump_death(org, self.cfg.reaper_fault_bump)
            return
        # энергетический шлюз: деление стоит энергии (фаза 4)
        if self.cfg.metabolism and org.energy < self.cfg.divide_cost:
            # не хватает энергии — не ошибка; освободить блок и ждать накопления
            self._free_range(org.id, org.daughter_start, org.daughter_size)
            org.daughter_start = None
            return
        ds, sz = org.daughter_start, org.daughter_size
        if self.cfg.metabolism:
            child_e = self.cfg.child_init_energy
            org.energy -= self.cfg.divide_cost                 # родитель платит
            # из divide_cost: child_e -> потомку (перенос), остаток сгорает (метаб. тепло)
            self.energy_out += (self.cfg.divide_cost - child_e)
        else:
            child_e = 0
        child = Organism(self._new_id(), ds, sz, ip=ds,
                         parent_id=org.id, lineage=org.lineage, energy=child_e)
        for k in range(sz):
            self.owner[self._wrap(ds + k)] = child.id  # передать владение потомку
        self.organisms.append(child)
        self.by_id[child.id] = child
        self._queue_insert(child)
        self.births += 1
        org.offspring += 1
        org.daughter_start = None
        org.daughter_size = 0

    # --- one instruction -----------------------------------------------------
    def _execute(self, org):
        ip = org.ip
        op = self.soup[ip]
        o = self.owner[ip]
        if o != -1 and o != org.id:          # H5: исполнение в чужой памяти
            org.cross_exec += 1
            self.cross_exec_total += 1
        org.jumped = False

        if op == NOP0 or op == NOP1 or op == EMPTY:
            if op == EMPTY:                  # потерянный IP блуждает по пустоте
                org.fault += 1
                self._bump_death(org, self.cfg.reaper_lost_bump)
        elif op == DONATE:
            self._do_donate(org)             # peek-not-consume: IP += 1 (тайм-нейтрально)
        elif op == SEARCHB:
            self._do_search(org, backward=True)
        elif op == SEARCHF:
            self._do_search(org, backward=False)
        elif op == SUB_CX_BA:
            org.cx = (org.bx - org.ax) % self.L
        elif op == INCC:
            org.cx = self._wrap(org.cx + 1)
        elif op == MAL:
            self._do_mal(org)
        elif op == COPY:
            self._do_copy(org)
        elif op == IFZ:
            if org.cx == 0:                  # пропустить следующую ячейку
                org.ip = self._wrap(org.ip + 2)
                org.jumped = True
        elif op == JMPB:
            self._do_jmpb(org)
        elif op == DIVIDE:
            self._do_divide(org)

        if not org.jumped:
            org.ip = self._wrap(org.ip + 1)
        org.age += 1

    # --- reaper --------------------------------------------------------------
    def _free(self, victim):
        # организм владеет только своим телом + зарезервированным блоком потомка
        ranges = [(victim.start, victim.length)]
        if victim.daughter_start is not None:
            ranges.append((victim.daughter_start, victim.daughter_size))
        for base, ln in ranges:
            for k in range(ln):
                a = self._wrap(base + k)
                if self.owner[a] == victim.id:
                    self.owner[a] = -1
                    self.soup[a] = EMPTY

    def _kill(self, victim, cause):
        """Единый путь смерти: учёт причины (C7), возврат энергии в реестр (C4)."""
        removed = False
        try:
            self.organisms.remove(victim)
            removed = True
        except ValueError:
            pass
        try:
            self.queue.remove(victim)
        except ValueError:
            pass
        self.by_id.pop(victim.id, None)
        if removed:
            self.energy_out += victim.energy   # энергия мёртвого покидает систему
            self._free(victim)
            self.deaths += 1
            self.deaths_by[cause] += 1
        return removed

    def _mortality(self):
        cfg = self.cfg
        if cfg.mortality_rate > 0:        # постоянный риск -> нет синхронных когорт
            r = cfg.mortality_rate
            rng = self.rng_death
            for victim in [o for o in self.organisms if rng.random() < r]:
                self._kill(victim, "age")
        if cfg.max_age is not None:
            for victim in [o for o in self.organisms if o.age > cfg.max_age]:
                self._kill(victim, "age")

    def _reap(self):
        # косим с головы очереди смерти, пока pop превышает лимит
        while len(self.organisms) > self.cfg.max_organisms and self.queue:
            self._kill(self.queue[0], "reap")

    def _starvation(self):
        for victim in [o for o in self.organisms if o.energy <= 0]:
            self._kill(victim, "starv")

    # --- step ----------------------------------------------------------------
    def step(self):
        cfg = self.cfg
        # Порядок шага (пред-регистрация, P1): космос -> приток -> исполнение
        #  -> голод -> возраст -> Жнец.
        if cfg.cosmic_rate:
            for i in range(self.L):
                if self.rng_cosmic.random() < cfg.cosmic_rate:
                    if self.rng_cosmic.random() < 0.5:
                        self.soup[i] = self.rng_cosmic.randint(0, NUM_OPS - 1)
                    else:
                        self.soup[i] = EMPTY
        if cfg.metabolism:
            inc, cap = cfg.energy_income, cfg.energy_max
            for org in self.organisms:
                add = min(inc, cap - org.energy)  # потолок: излишек не «впрыскивается»
                if add > 0:
                    org.energy += add
                    self.energy_in += add
        for org in list(self.organisms):
            self._execute(org)
        if cfg.metabolism:
            self._starvation()
        self._mortality()
        self._reap()
        self.step_count += 1

    def energy_check(self):
        """C4: точное сохранение энергии (целые числа)."""
        live = sum(o.energy for o in self.organisms)
        return live == self.energy_in - self.energy_out

    # --- classification & relatedness ----------------------------------------
    def classify_org(self, org):
        return classify_genome(self.genome_at(org.start, org.length))

    def composition(self, mature_only=False):
        counts = {"intact": 0, "defector": 0, "tagless": 0,
                  "both_lost": 0, "variant": 0}
        for o in self.organisms:
            if mature_only and o.offspring < 1:   # C15: исключить не-цикливших
                continue
            counts[self.classify_org(o)] += 1
        return counts

    def _torus_dist(self, a, b):
        d = abs(self._wrap(a - b))
        return min(d, self.L - d)

    def realized_r(self, radius=None):
        """Генеалогическая ассортативность кооператорного генотипа (G=1 если 'intact').
        r = Cov(G_focal, G_neigh)/Var(G_focal) по всем парам в радиусе. Считается из
        байтов генома, НЕЗАВИСИМО от событий доната (C10). None если мономорфно/мало пар."""
        radius = radius if radius is not None else self.cfg.donate_radius
        orgs = self.organisms
        if len(orgs) < 2:
            return None
        G = {o.id: (1.0 if self.classify_org(o) == "intact" else 0.0) for o in orgs}
        fo, ne = [], []
        for f in orgs:
            for n in orgs:
                if n.id == f.id:
                    continue
                if self._torus_dist(n.start, f.start) <= radius:
                    fo.append(G[f.id])
                    ne.append(G[n.id])
        m = len(fo)
        if m == 0:
            return None
        mean = sum(fo) / m
        var = sum((x - mean) ** 2 for x in fo) / m
        if var == 0:
            return None
        cov = sum((fo[i] - mean) * (ne[i] - mean) for i in range(m)) / m
        return cov / var

    # --- summary -------------------------------------------------------------
    def stats(self):
        orgs = self.organisms
        n = len(orgs)
        avg_len = sum(o.length for o in orgs) / n if n else 0.0
        max_age = max((o.age for o in orgs), default=0)
        avg_e = sum(o.energy for o in orgs) / n if n else 0.0
        comp = self.composition()
        return {
            "step": self.step_count,
            "pop": n,
            "avg_len": round(avg_len, 3),
            "max_age": max_age,
            "births": self.births,
            "deaths": self.deaths,
            "cross_exec": self.cross_exec_total,
            "illegal_write": self.illegal_write_total,
            "avg_energy": round(avg_e, 2),
            "intact": comp["intact"],
            "defector": comp["defector"],
            "tagless": comp["tagless"],
            "both_lost": comp["both_lost"],
            "variant": comp["variant"],
            "donations": self.donations_made,
            "energy_ok": self.energy_check(),
            "deaths_by": dict(self.deaths_by),
        }


# --------------------------------------------------------------- self-test -----
def _control_C1(verbose=True):
    """C1: mutation=0, cosmic=0 -> побитовая репликация, ноль паразитизма/незаконных записей."""
    cfg = Config(soup_size=4000, max_organisms=60, copy_mut_rate=0.0, cosmic_rate=0.0)
    w = World(cfg, seed=1)
    w.inject(ANCESTOR, start=0, lineage=1)

    # шагаем до первого деления и сразу (пока потомок жив) сверяем его геном с предком
    first_birth = None
    identical = False
    child0 = None
    for _ in range(6000):
        w.step()
        if first_birth is None and w.births >= 1:
            first_birth = w.step_count
            child0 = next((o for o in w.organisms if o.id == 1), None)
            if child0:
                identical = (w.genome_at(child0.start, child0.length) == ANCESTOR)

    s = w.stats()
    if verbose:
        print("=== Control C1 (mutation=0) ===")
        print(f"первое деление на шаге: {first_birth}")
        print(f"итог: {s}")
        if child0:
            print(f"первый потомок id=1: start={child0.start} len={child0.length} "
                  f"identical_to_ancestor={identical}")
    ok = (
        s["births"] >= 2 and
        s["cross_exec"] == 0 and
        s["illegal_write"] == 0 and
        identical
    )
    print("C1:", "PASS ✅" if ok else "FAIL ❌")
    return ok


if __name__ == "__main__":
    _control_C1()
