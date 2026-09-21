/* ===========================================================================
   ВАЛЮТА АУЫСТЫРҒЫШ  ₸ ↔ $

   Қалай жұмыс істейді:
   1. Баға көрсетілетін әр элементте data-kzt="295000" атрибуты тұрады
   2. Түймені басқанда сан жаңа валютаға домалап өтеді
   3. Таңдау браузерде сақталады — келесі бетте де сол валюта

   Барлық есептеу ТЕҢГЕМЕН жүреді, доллар тек көрсету үшін.
   Сондықтан серверге әрқашан теңгедегі баға барады.
=========================================================================== */

window.Currency = (function () {

    var STORAGE_KEY = "mt-currency";

    var state = {
        code: "KZT",
        rate: 500
    };

    var reduced = window.matchMedia
        && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    /* ---------- сан пішімдеу ---------- */

    function spaced(value) {
        return Math.round(value)
            .toString()
            .replace(/\B(?=(\d{3})+(?!\d))/g, " ");
    }

    function format(kzt) {
        if (state.code === "USD") {
            var usd = kzt / state.rate;
            /* $1 000-нан асса — бүтін, азырақ болса ондыққа дейін */
            return "$" + (usd >= 1000 ? spaced(usd) : spaced(usd));
        }
        return spaced(kzt) + " ₸";
    }

    /* ---------- домалау анимациясы ---------- */

    function animate(el, fromKzt, toKzt) {
        if (!el) return;

        if (reduced || fromKzt === null || fromKzt === toKzt) {
            el.textContent = format(toKzt);
            return;
        }

        if (el._frame) cancelAnimationFrame(el._frame);

        var duration = 520;
        var started = null;

        function step(now) {
            if (started === null) started = now;

            var progress = Math.min((now - started) / duration, 1);
            var eased = 1 - Math.pow(1 - progress, 3);   /* easeOutCubic */

            el.textContent = format(fromKzt + (toKzt - fromKzt) * eased);

            if (progress < 1) {
                el._frame = requestAnimationFrame(step);
            }
        }

        el._frame = requestAnimationFrame(step);
    }

    /* ---------- элементтер ---------- */

    function elements() {
        return document.querySelectorAll("[data-kzt]");
    }

    function render(animated) {
        var list = elements();

        for (var i = 0; i < list.length; i++) {
            var el = list[i];
            var kzt = parseFloat(el.getAttribute("data-kzt")) || 0;

            if (!kzt) {
                el.textContent = "—";
                continue;
            }

            /* Валюта ауысқанда сан ескі КӨРСЕТІЛГЕН мәннен домалайды */
            var shown = el._shownKzt;
            el._shownKzt = kzt;

            if (animated && shown !== undefined) {
                animate(el, shown, kzt);
            } else if (animated) {
                animate(el, null, kzt);
            } else {
                el.textContent = format(kzt);
            }
        }
    }

    /* Валюта ауысқанда: сан бірдей, бірақ көрінісі басқа.
       Сондықтан ескі валютадағы мәннен жаңасына домалатамыз. */
    function switchTo(code, buttons) {
        if (code === state.code) return;

        var list = elements();
        var before = [];

        for (var i = 0; i < list.length; i++) {
            var kzt = parseFloat(list[i].getAttribute("data-kzt")) || 0;
            before.push(state.code === "USD" ? kzt / state.rate : kzt);
        }

        state.code = code;

        try {
            window.localStorage.setItem(STORAGE_KEY, code);
        } catch (error) {
            /* құпия режимде localStorage жабық болуы мүмкін */
        }

        for (var j = 0; j < list.length; j++) {
            var el = list[j];
            var target = parseFloat(el.getAttribute("data-kzt")) || 0;

            if (!target) {
                el.textContent = "—";
                continue;
            }

            /* Көрсетілетін бірлікте домалатамыз, сосын нақты мәнге қоямыз */
            animateDisplay(el, before[j], code === "USD" ? target / state.rate : target);
        }

        markButtons(buttons);
    }

    function animateDisplay(el, from, to) {
        var suffix = state.code === "USD" ? "" : " ₸";
        var prefix = state.code === "USD" ? "$" : "";

        if (reduced) {
            el.textContent = prefix + spaced(to) + suffix;
            return;
        }

        if (el._frame) cancelAnimationFrame(el._frame);

        var duration = 560;
        var started = null;

        function step(now) {
            if (started === null) started = now;

            var progress = Math.min((now - started) / duration, 1);
            var eased = 1 - Math.pow(1 - progress, 3);

            el.textContent = prefix + spaced(from + (to - from) * eased) + suffix;

            if (progress < 1) {
                el._frame = requestAnimationFrame(step);
            }
        }

        el._frame = requestAnimationFrame(step);
    }

    function markButtons(buttons) {
        if (!buttons) buttons = document.querySelectorAll("[data-currency]");

        for (var i = 0; i < buttons.length; i++) {
            var active = buttons[i].getAttribute("data-currency") === state.code;
            buttons[i].classList.toggle("is-active", active);
            buttons[i].setAttribute("aria-pressed", active ? "true" : "false");

            if (active) {
                var box = buttons[i].parentNode;
                var indicator = box && box.querySelector(".currency-indicator");
                if (indicator) {
                    indicator.style.width = buttons[i].offsetWidth + "px";
                    indicator.style.transform =
                        "translateX(" + buttons[i].offsetLeft + "px)";
                    indicator.classList.add("is-ready");
                }
            }
        }
    }

    /* ---------- сырттан бір бағаны жаңарту (booking беті) ---------- */

    function setValue(el, kzt) {
        if (!el) return;

        var previous = parseFloat(el.getAttribute("data-kzt"));
        el.setAttribute("data-kzt", kzt);

        var from = isNaN(previous) ? null : previous;

        if (state.code === "USD") {
            animateDisplay(el, from === null ? kzt / state.rate : from / state.rate,
                           kzt / state.rate);
        } else {
            animate(el, from, kzt);
        }
    }

    /* ---------- іске қосу ---------- */

    function init(options) {
        options = options || {};
        state.rate = options.rate || state.rate;

        try {
            var saved = window.localStorage.getItem(STORAGE_KEY);
            if (saved === "USD" || saved === "KZT") state.code = saved;
        } catch (error) {
            /* елемейміз */
        }

        render(false);

        var buttons = document.querySelectorAll("[data-currency]");

        for (var i = 0; i < buttons.length; i++) {
            buttons[i].addEventListener("click", function () {
                switchTo(this.getAttribute("data-currency"), buttons);
            });
        }

        markButtons(buttons);
        window.addEventListener("resize", function () { markButtons(buttons); });
    }

    /* Пакет ауысқанда: ескі бағадан жаңасына домалату.
       Екеуі де ТЕҢГЕМЕН беріледі, көрсету валютасын өзі есептейді. */
    function roll(el, fromKzt, toKzt) {
        if (!el) return;

        el.setAttribute("data-kzt", toKzt);

        var divide = state.code === "USD" ? state.rate : 1;
        animateDisplay(el, fromKzt / divide, toKzt / divide);
    }

    return {
        init: init,
        roll: roll,
        setValue: setValue,
        format: format,
        code: function () { return state.code; }
    };

})();