/* ===========================================================================
   СКРОЛЛДА ШЫҒУ

   Элемент экранға кірген сәтте астынан көтеріліп, айқындалады.
   Бір рет қана — жоғары-төмен жүргенде қайталанбайды.

   Қауіпсіздігі: анимация тек JS жүктелгенде қосылады. Скрипт
   істемесе, бәрі бұрынғыдай көрініп тұрады (CSS .reveal-ready
   класына байланған, ал оны JS қояды).
=========================================================================== */

(function () {

    "use strict";

    var reduced = window.matchMedia
        && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    /* Анимация қолданылатын элементтер.
       Жаңа бөлім қосқың келсе, осы тізімге селектор қосасың. */
    var GROUPS = [
        { selector: ".section-top",    stagger: 0   },
        { selector: ".tour-card",      stagger: 80  },
        { selector: ".benefit",        stagger: 70  },
        { selector: ".gallery-slot",   stagger: 90  },
        { selector: ".map-container",  stagger: 0   },
        { selector: ".review-card",    stagger: 0   },
        { selector: ".detail-block",   stagger: 90  },
        { selector: ".overview-item",  stagger: 70  },
        { selector: ".routes-list li", stagger: 60  }
    ];

    if (reduced || !("IntersectionObserver" in window)) {
        return;                      /* бәрі әдеттегідей көрінеді */
    }

    var items = [];

    GROUPS.forEach(function (group) {
        var found = document.querySelectorAll(group.selector);

        for (var i = 0; i < found.length; i++) {
            /* Бір элемент екі топқа кірмесін */
            if (found[i].dataset.revealBound) continue;

            found[i].dataset.revealBound = "1";
            found[i].classList.add("reveal");

            /* Қатардағы орнына қарай кідіріс: 1-і бірден, 2-і кейін */
            found[i].style.setProperty("--reveal-delay", (i % 6) * group.stagger + "ms");

            items.push(found[i]);
        }
    });

    if (!items.length) return;

    /* Класс қосылғаннан кейін ғана элементтер жасырылады —
       сондықтан JS істемесе, ештеңе жоғалмайды */
    document.documentElement.classList.add("reveal-ready");

    var observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
            if (!entry.isIntersecting) return;

            entry.target.classList.add("is-visible");
            observer.unobserve(entry.target);      /* бір рет қана */
        });
    }, {
        /* Элемент экранның төменгі шетінен 12% көтерілгенде басталады */
        rootMargin: "0px 0px -12% 0px",
        threshold: 0.05
    });

    items.forEach(function (item) {
        observer.observe(item);
    });

    /* Бет ашылған сәтте экранда тұрғандар бірден көрінсін */
    window.setTimeout(function () {
        items.forEach(function (item) {
            var box = item.getBoundingClientRect();
            if (box.top < window.innerHeight * 0.9) {
                item.classList.add("is-visible");
                observer.unobserve(item);
            }
        });
    }, 60);

})();