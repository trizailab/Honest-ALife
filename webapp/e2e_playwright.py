"""
E2E-тест веб-приложения через Playwright (headless Chromium).
Запуск:  python3 webapp/e2e_playwright.py [URL]   (по умолчанию http://127.0.0.1)
Проверяет: загрузку, элементы, живой SSE-стрим, контроли (слайдеры/тумблер/сценарии),
и функциональный прогон «рецепта добра». Скриншоты -> /tmp/alife_*.png.
"""
import sys
import time
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1"
PASS, FAIL = [], []


def check(name, cond):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS ✅' if cond else 'FAIL ❌'}] {name}")
    return cond


def set_slider(page, sel, value):
    page.eval_on_selector(sel, """(el, v) => {
        el.value = v; el.dispatchEvent(new Event('input', {bubbles:true}));
    }""", value)


def num(page, sel):
    try:
        return float((page.text_content(sel) or "0").replace("—", "0"))
    except Exception:
        return 0.0


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1500, "height": 950})
        print(f"=== Открываю {URL} ===")
        page.goto(URL, wait_until="domcontentloaded", timeout=15000)

        # 1) Базовая загрузка и элементы
        print("1) Загрузка и элементы")
        check("заголовок про Honest ALife", "Honest ALife" in page.title())
        for sel in ["#soupCanvas", "#scenario", "#locToggle",
                    "#oradius", "#donate", "#dradius", "#divide", "#mut", "#speed",
                    "#sStep", "#sDef", "#sParas", "#phase", "#btnReseed"]:
            check(f"есть элемент {sel}", page.query_selector(sel) is not None)
        check("новый слайдер «радиус семьи» подписан",
              "радиус семьи" in (page.content()))

        # 2) Живой SSE-стрим: шаг растёт
        print("2) SSE-стрим обновляется")
        page.wait_for_timeout(1500)
        s0 = num(page, "#sStep")
        page.wait_for_timeout(3000)
        s1 = num(page, "#sStep")
        check(f"шаг растёт ({int(s0)} -> {int(s1)})", s1 > s0)
        check("популяция > 0", num(page, "#sPop") > 0)

        # 3) Слайдер «радиус семьи» меняет подпись
        print("3) Контрол: слайдер радиус семьи")
        set_slider(page, "#oradius", 18)
        page.wait_for_timeout(300)
        check("подпись радиуса семьи = 18", page.text_content("#vOradius") == "18")

        # 4) Тумблер локального размещения
        print("4) Контрол: тумблер локальности")
        page.click("#locToggle")
        page.wait_for_timeout(300)
        cls = page.get_attribute("#locSwitch", "class") or ""
        check("тумблер включился (класс on)", "on" in cls)

        # 5) Смена сценария на «предок» -> появляются паразиты со временем
        print("5) Сценарий «предок (паразитизм)»")
        page.select_option("#scenario", "ancestor")
        set_slider(page, "#mut", 0.03)
        set_slider(page, "#speed", 300)
        page.wait_for_timeout(6000)
        paras = num(page, "#sParas")
        cross = num(page, "#sCross")
        check(f"паразитизм измеряется (паразиты={int(paras)}, cross-exec={int(cross)})",
              cross > 0)
        page.screenshot(path="/tmp/alife_ancestor.png")

        # 6) Функциональный прогон «рецепта добра»: микс + плотные семьи + малый радиус доната
        print("6) Рецепт добра (микс, локальность, плотные семьи, малый радиус доната)")
        page.select_option("#scenario", "mix")
        page.wait_for_timeout(300)
        # включить локальность (после reset тумблер визуально мог слететь — выставим явно)
        if "on" not in (page.get_attribute("#locSwitch", "class") or ""):
            page.click("#locToggle")
        set_slider(page, "#oradius", 16)
        set_slider(page, "#dradius", 40)
        set_slider(page, "#divide", 320)
        set_slider(page, "#donate", 50)
        set_slider(page, "#mut", 0)
        set_slider(page, "#speed", 300)
        page.click("#btnReseed")          # свежий посев с этими настройками
        print("   гоняю ~25 c...")
        page.wait_for_timeout(25000)
        step = num(page, "#sStep")
        intact = num(page, "#sIntact")
        defec = num(page, "#sDef")
        phase = page.text_content("#phase")
        rr = page.text_content("#sR")
        tot = intact + defec
        fd = (defec / tot) if tot else None
        page.screenshot(path="/tmp/alife_good_recipe.png")
        print(f"   шаг={int(step)} кооп={int(intact)} предатели={int(defec)} "
              f"доля_предат={round(fd,2) if fd is not None else None} r={rr}")
        print(f"   фаза: {phase}")
        check("прогон отработал (шаг вырос)", step > 1000)
        check("есть зрелые организмы (кооп/предатели классифицируются)", tot > 0)

        browser.close()

    print("\n=== ИТОГ ===")
    print(f"PASS: {len(PASS)} | FAIL: {len(FAIL)}")
    if FAIL:
        print("Провалено:", FAIL)
    print("Скриншоты: /tmp/alife_ancestor.png, /tmp/alife_good_recipe.png")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
