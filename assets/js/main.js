/* WirelessMathBench-XL project page (v6) — vanilla JS, progressive enhancement.
   Everything on the page is readable without this file (a static sample problem,
   a list of the explorer pool, all four mask-ladder rungs); it only adds math
   rendering, the problem explorer, the mask-ladder slider, tabs, the MCQ checker,
   copy buttons and the scrollytelling diagram states. */
(function () {
  "use strict";
  var root = document.documentElement;
  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------- KaTeX ---------- */
  function renderMath(el) {
    if (typeof window.renderMathInElement !== "function") return;
    window.renderMathInElement(el || document.body, {
      delimiters: [
        { left: "$$", right: "$$", display: true },
        { left: "\\[", right: "\\]", display: true },
        { left: "$", right: "$", display: false },
        { left: "\\(", right: "\\)", display: false }
      ],
      ignoredTags: ["script", "noscript", "style", "textarea", "pre", "code", "option"],
      ignoredClasses: ["no-math"],
      throwOnError: false
    });
  }

  /* ---------- tabs (results + fill-in rungs) ---------- */
  function initTabs(list) {
    var tabs = Array.prototype.slice.call(list.querySelectorAll('[role="tab"]'));
    function select(tab, focus) {
      tabs.forEach(function (t) {
        var on = t === tab;
        t.setAttribute("aria-selected", on ? "true" : "false");
        t.tabIndex = on ? 0 : -1;
        var panel = document.getElementById(t.getAttribute("aria-controls"));
        if (panel) panel.hidden = !on;
      });
      if (focus) tab.focus();
    }
    tabs.forEach(function (t, i) {
      t.addEventListener("click", function () { select(t, false); });
      t.addEventListener("keydown", function (e) {
        var k = e.key, j = null;
        if (k === "ArrowRight" || k === "ArrowDown") j = (i + 1) % tabs.length;
        else if (k === "ArrowLeft" || k === "ArrowUp") j = (i - 1 + tabs.length) % tabs.length;
        else if (k === "Home") j = 0;
        else if (k === "End") j = tabs.length - 1;
        if (j !== null) { e.preventDefault(); select(tabs[j], true); }
      });
    });
    var initial = tabs.filter(function (t) { return t.getAttribute("aria-selected") === "true"; })[0] || tabs[0];
    select(initial, false);
  }

  /* ---------- MCQ checker ---------- */
  function initMCQ(block) {
    if (!block || block._mcq) return;
    block._mcq = true;
    var answer = block.getAttribute("data-answer");
    var fb = block.querySelector(".feedback");
    var opts = Array.prototype.slice.call(block.querySelectorAll(".opt"));
    opts.forEach(function (btn) {
      btn.addEventListener("click", function () {
        var letter = btn.getAttribute("data-letter");
        opts.forEach(function (b) { b.removeAttribute("data-state"); b.setAttribute("aria-pressed", "false"); b.querySelector(".verdict").textContent = ""; });
        btn.setAttribute("aria-pressed", "true");
        if (letter === answer) {
          btn.setAttribute("data-state", "right");
          btn.querySelector(".verdict").textContent = "Correct";
          fb.className = "feedback ok";
          fb.textContent = "Correct: option " + answer + " matches the verifier-facing ground truth.";
        } else {
          btn.setAttribute("data-state", "wrong");
          btn.querySelector(".verdict").textContent = "Not this one";
          fb.className = "feedback no";
          fb.textContent = "Option " + letter + " is not the ground truth. Try again, or reveal the answer below.";
        }
      });
    });
  }

  /* ---------- problem explorer (Chapter 2) ---------- */
  /* <card-template> — also run by the build step that writes the static first card and the no-JS list */
  var CARD = (function () {
    function esc(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;"); }
    var FMT = {
      MCQ: { badge: "MCQ", cls: "p-mcq", title: "Multiple choice", short: "MCQ" },
      fill_blank_25: { badge: "Fill-in", cls: "p-fill", title: "Fill-in · 25% of components masked", short: "Fill-in 25%" },
      fill_blank_50: { badge: "Fill-in", cls: "p-fill", title: "Fill-in · 50% of components masked", short: "Fill-in 50%" },
      fill_blank_75: { badge: "Fill-in", cls: "p-fill", title: "Fill-in · 75% of components masked", short: "Fill-in 75%" },
      fill_blank_100: { badge: "FEC", cls: "p-fec", title: "Full Equation Completion", short: "FEC" }
    };
    var I_PAPER = '<svg class="ci" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 2.8h8.5l4.7 4.7v13.7H6z M14.5 2.8v4.7h4.7" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><path d="M9 13h7M9 17h5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>';
    var I_ZERO = '<svg class="ci" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M8 12.4l2.7 2.6L16 9.6" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    var I_TALLY = '<svg class="ci" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 5v14M10 5v14M14 5v14M18 5v14M3.5 16.5l17-9" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>';
    function maskEq(eq, fill) {
      var n = (eq.match(/\[MASK\]/g) || []).length, k = 0;
      return eq.replace(/\[MASK\]/g, function () {
        k++;
        if (fill) return "\\boxed{\\color{#00706c}{" + fill[k - 1] + "}}";
        return "\\boxed{\\,\\color{#b3401c}{" + (n === 1 ? "?" : "?_{" + k + "}") + "}\\,}";
      });
    }
    function hint(p) {
      if (p.type === "MCQ") return "Distractors are built to violate an implicit constraint";
      if (p.type === "fill_blank_100") return "Every component masked; only definitions and assumptions remain";
      var n = (p.equation.match(/\[MASK\]/g) || []).length;
      return n + (n === 1 ? " blank" : " blanks") + " in the equation";
    }
    function auditChip(c) {
      if (c.in_S0) return '<span class="chip audit">' + I_ZERO + "RedPajama-arXiv 13-gram hits: 0 · in S<sub>0</sub></span>";
      return '<span class="chip audit flag">' + I_TALLY + "RedPajama-arXiv 13-gram hits: " + c.hits_total + " · docs: " + c.docs_total +
        " · not in S<sub>0</sub>" + (c.in_S1 ? " · in S<sub>1</sub>" : "") + "</span>";
    }
    function overlap(c) {
      if (c.in_S0 || !c.matched_ngrams_capped || !c.matched_ngrams_capped.length) return "";
      return '<div class="overlap h-coral"><div class="ov-head"><svg class="il" viewBox="0 0 34 34" aria-hidden="true"><circle cx="17" cy="17" r="16" class="f-as"/>' +
        '<rect x="7" y="9" width="20" height="16" rx="4" class="f-paper"/><rect x="7" y="9" width="20" height="16" rx="4" class="ln-t"/>' +
        '<path d="M12 13v8M15.5 13v8M19 13v8M22.5 13v8" class="ln-t"/><path d="M10 19.5l14.5-5" class="ln-a"/></svg>' +
        "<p><b>Detected overlap on the audit channel.</b> Released matched 13-grams (normalised, capped):</p></div>" +
        '<ul class="grams">' + c.matched_ngrams_capped.map(function (g) { return '<li><code class="no-math">' + esc(g) + "</code></li>"; }).join("") + "</ul>" +
        '<p class="fine">From the record’s <code class="no-math">contamination.matched_ngrams_capped</code> field: prompt-surface strings that matched RedPajama-arXiv on the one fixed channel the audit covers (13-gram lexical overlap). They are not answers.</p></div>';
    }
    function card(p, headingId) {
      var f = FMT[p.type], mcq = p.type === "MCQ", c = p.contamination, hid = headingId || "ex-title", q, ans;
      q = '<p class="p-label">Question</p><p class="p-q">' + esc(p.question_text) + "</p>" + (p.equation ? '<div class="eq">' + esc(maskEq(p.equation)) + "</div>" : "");
      if (mcq) {
        q += '<ul class="options" aria-label="Answer options">' + ["A", "B", "C", "D"].filter(function (L) { return p.options[L]; }).map(function (L) {
          return '<li><button type="button" class="opt" data-letter="' + L + '" aria-pressed="false"><span class="letter" aria-hidden="true">' + L +
            '</span><span class="opt-math"><span class="sr-only">Option ' + L + ": </span>" + esc(p.options[L]) + '</span><span class="verdict" aria-hidden="true"></span></button></li>';
        }).join("") + '</ul><p class="feedback" aria-live="polite"></p>';
        ans = "<p>Ground truth: <strong>option " + esc(p.correct_answer) + "</strong></p>" +
          (p.equation ? '<div class="eq">' + esc(maskEq(p.equation, [p.options[p.correct_answer].trim().replace(/^\$|\$$/g, "")])) + "</div>" : "") +
          "<p>MCQ distractors are constraint-violating by construction (for example matrix-dimension mismatches, operator-order errors, or sign violations), so the format probes implicit constraints rather than surface plausibility.</p>";
      } else {
        var parts = p._answer_parts;
        ans = parts.length === 1 ? "<p>Ground truth: $" + esc(parts[0]) + "$</p>" :
          "<p>Ground truth: " + parts.map(function (x, i) { return "$?_{" + (i + 1) + "} = " + esc(x) + "$"; }).join(", ") + "</p>";
        ans += '<div class="eq">' + esc(maskEq(p.equation, parts)) + "</div>" +
          "<p>Open-form answers are graded by deterministic match, then LaTeX canonicalisation, then a bounded LLM-judge fallback (GPT-4.1-mini) for residual semantic equivalence.</p>";
      }
      q += '<details class="reveal"><summary>Reveal answer</summary><div class="answer">' + ans + "</div></details>";
      return '<article class="problem ' + f.cls + '" aria-labelledby="' + hid + '" data-id="' + esc(p.id) + '">' +
        '<div class="problem-head"><div class="fmt"><span class="badge">' + f.badge + '</span><h3 id="' + hid + '" tabindex="-1">' + f.title +
        '<span class="rec"> · record #' + esc(p.id) + '</span></h3></div><span class="hint">' + hint(p) + "</span></div>" +
        '<div class="problem-body' + (mcq ? ' mcq" data-answer="' + esc(p.correct_answer) + '"' : '"') + ">" +
        '<div><p class="p-label">Background</p><p class="p-bg">' + esc(p.background) + "</p></div><div>" + q + "</div></div>" +
        overlap(c) +
        '<div class="provenance"><span class="credit">' + I_PAPER + 'Derived from <a href="https://arxiv.org/abs/' + esc(p.paper_id) + '">arXiv:' + esc(p.paper_id) + "</a></span>" +
        '<span class="chip">record #' + esc(p.id) + '</span><span class="chip">type <code class="no-math">' + esc(p.type) + '</code></span><span class="chip">' + esc(p.split) + " split</span>" +
        '<a class="chip lic" href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>' + auditChip(c) + "</div></article>";
    }
    function listItem(p) {
      var c = p.contamination;
      return '<li><b>#' + esc(p.id) + "</b> · " + FMT[p.type].short + " · " + esc(p.split) + ' · <a href="https://arxiv.org/abs/' + esc(p.paper_id) + '">arXiv:' + esc(p.paper_id) + "</a> · " +
        (c.in_S0 ? "0 hits (S<sub>0</sub>)" : c.hits_total + (c.hits_total === 1 ? " hit" : " hits") + " (not in S<sub>0</sub>)") + "</li>";
    }
    return { esc: esc, FMT: FMT, maskEq: maskEq, card: card, listItem: listItem };
  })();
  /* </card-template> */

  function initSeg(group, onChange) {
    var btns = Array.prototype.slice.call(group.querySelectorAll("button"));
    btns.forEach(function (b) {
      b.addEventListener("click", function () {
        btns.forEach(function (x) { x.setAttribute("aria-pressed", x === b ? "true" : "false"); });
        onChange(b);
      });
    });
    return {
      set: function (pred) { btns.forEach(function (x) { x.setAttribute("aria-pressed", pred(x) ? "true" : "false"); }); },
      buttons: btns
    };
  }

  var explorerAPI = null;
  function initExplorer() {
    var box = document.getElementById("explorer");
    if (!box) return;
    var cardEl = document.getElementById("ex-card"), status = document.getElementById("ex-status"), shuffleBtn = document.getElementById("ex-shuffle");
    var first = cardEl.querySelector(".problem");
    var state = { fmt: "all", audit: "all" }, pool = null, current = first ? first.getAttribute("data-id") : null, deck = [];
    var fmtSeg, audSeg;
    function matches(p, fmt, aud) {
      if (fmt !== "all" && p.type !== fmt) return false;
      if (aud === "s0" && !p.contamination.in_S0) return false;
      if (aud === "hit" && p.contamination.in_S0) return false;
      return true;
    }
    function list() { return pool.filter(function (p) { return matches(p, state.fmt, state.audit); }); }
    function counts() {
      fmtSeg.buttons.forEach(function (b) {
        var n = pool.filter(function (p) { return matches(p, b.getAttribute("data-val"), state.audit); }).length;
        b.querySelector(".ct").textContent = n;
        b.disabled = n === 0;
      });
      audSeg.buttons.forEach(function (b) {
        var n = pool.filter(function (p) { return matches(p, state.fmt, b.getAttribute("data-val")); }).length;
        b.querySelector(".ct").textContent = n;
        b.disabled = n === 0;
      });
    }
    function show(p, focus) {
      current = p.id;
      cardEl.innerHTML = CARD.card(p);
      renderMath(cardEl);
      initMCQ(cardEl.querySelector(".mcq"));
      var l = list(), idx = l.indexOf(p);
      status.textContent = "Showing record #" + p.id + " (" + CARD.FMT[p.type].short + ", derived from arXiv:" + p.paper_id + ")" +
        (idx >= 0 ? ": " + (idx + 1) + " of " + l.length + (l.length === 1 ? " record matches" : " records match") + " the filters." : ".");
      if (focus) { var h = document.getElementById("ex-title"); if (h) h.focus({ preventScroll: true }); }
    }
    /* draw without replacement: every matching record appears once before any repeats */
    function next() {
      var l = list();
      if (!l.length) { status.textContent = "No problems in the pool match these filters."; return; }
      deck = deck.filter(function (p) { return l.indexOf(p) >= 0 && p.id !== current; });
      if (!deck.length) {
        deck = l.filter(function (p) { return p.id !== current; });
        for (var i = deck.length - 1; i > 0; i--) { var j = Math.floor(Math.random() * (i + 1)), t = deck[i]; deck[i] = deck[j]; deck[j] = t; }
        if (!deck.length) deck = l.slice();
      }
      show(deck.shift(), false);
    }
    function onFilter() {
      counts();
      deck = [];
      var cur = pool.filter(function (p) { return p.id === current; })[0];
      if (cur && matches(cur, state.fmt, state.audit)) show(cur, false); else next();
    }
    fetch("assets/data/problems.json").then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); }).then(function (data) {
      pool = data.problems;
      fmtSeg = initSeg(box.querySelector('[data-filter="fmt"]'), function (b) { state.fmt = b.getAttribute("data-val"); onFilter(); });
      audSeg = initSeg(box.querySelector('[data-filter="audit"]'), function (b) { state.audit = b.getAttribute("data-val"); onFilter(); });
      counts();
      shuffleBtn.addEventListener("click", next);
      status.textContent = "Pool of " + pool.length + " CC BY 4.0 records loaded. Showing record #" + current + ".";
      explorerAPI = {
        showById: function (id) {
          var p = pool.filter(function (x) { return x.id === id; })[0];
          if (!p) return;
          state.fmt = "all"; state.audit = "all"; deck = [];
          fmtSeg.set(function (x) { return x.getAttribute("data-val") === "all"; });
          audSeg.set(function (x) { return x.getAttribute("data-val") === "all"; });
          counts(); show(p, true);
          box.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
        }
      };
    }).catch(function () {
      status.textContent = "The problem pool could not be loaded here, so one sample record is shown.";
      Array.prototype.forEach.call(box.querySelectorAll(".ex-bar button"), function (b) { b.disabled = true; });
    });
    Array.prototype.forEach.call(document.querySelectorAll("[data-show-problem]"), function (b) {
      b.addEventListener("click", function () { if (explorerAPI) explorerAPI.showById(b.getAttribute("data-show-problem")); });
    });
  }

  /* ---------- mask ladder slider ---------- */
  function initLadder() {
    var slider = document.getElementById("mask-slider");
    if (!slider) return;
    var ladder = document.getElementById("ladder");
    var panels = Array.prototype.slice.call(ladder.querySelectorAll(".rung-panel"));
    var art = Array.prototype.slice.call(ladder.querySelectorAll(".lad-rung"));
    var ticks = Array.prototype.slice.call(ladder.querySelectorAll(".mask-ticks button"));
    var out = document.getElementById("mask-out");
    var labels = ["25%", "50%", "75%", "100% (FEC)"], blanks = ["1 blank", "2 blanks", "4 blanks", "the whole right-hand side"];
    function set(i) {
      panels.forEach(function (p, j) { p.hidden = j !== i; });
      art.forEach(function (g) { g.classList.toggle("on", +g.getAttribute("data-rung") === i); });
      ticks.forEach(function (t, j) { t.classList.toggle("on", j === i); });
      out.textContent = labels[i];
      slider.style.setProperty("--p", (i / 3 * 100) + "%");
      slider.setAttribute("aria-valuetext", labels[i] + " masked, " + blanks[i]);
    }
    slider.addEventListener("input", function () { set(+slider.value); });
    ticks.forEach(function (t, j) { t.addEventListener("click", function () { slider.value = j; set(j); }); });
    set(+slider.value);
  }

  /* ---------- copy buttons ---------- */
  function initCopy(btn) {
    btn.addEventListener("click", function () {
      var target = document.getElementById(btn.getAttribute("data-copy"));
      if (!target) return;
      var text = target.innerText.replace(/ /g, " ");
      var done = function () {
        var old = btn.textContent;
        btn.textContent = "Copied";
        setTimeout(function () { btn.textContent = old; }, 1600);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, function () { fallbackCopy(text); done(); });
      } else { fallbackCopy(text); done(); }
    });
  }
  function fallbackCopy(text) {
    var ta = document.createElement("textarea");
    ta.value = text; ta.setAttribute("readonly", ""); ta.style.position = "absolute"; ta.style.left = "-9999px";
    document.body.appendChild(ta); ta.select();
    try { document.execCommand("copy"); } catch (e) { /* ignore */ }
    document.body.removeChild(ta);
  }

  /* ---------- scrollytelling: reverse-probe audit ---------- */
  function initScrolly() {
    var svg = document.getElementById("probe-svg");
    var steps = Array.prototype.slice.call(document.querySelectorAll(".scrolly .step"));
    var label = document.getElementById("probe-step-label");
    if (!svg || !steps.length) return;
    var FULL = svg.getAttribute("viewBox").split(/\s+/).map(Number);
    var narrow = window.matchMedia("(max-width: 900px)");
    var current = FULL.slice(), raf = null;
    function setVB(target) {
      if (raf) cancelAnimationFrame(raf);
      if (reduceMotion) { current = target.slice(); svg.setAttribute("viewBox", current.join(" ")); return; }
      var from = current.slice(), t0 = null, dur = 520;
      function tick(ts) {
        if (!t0) t0 = ts;
        var p = Math.min(1, (ts - t0) / dur);
        var e = p < .5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2;
        current = from.map(function (v, i) { return v + (target[i] - v) * e; });
        svg.setAttribute("viewBox", current.map(function (v) { return v.toFixed(2); }).join(" "));
        if (p < 1) raf = requestAnimationFrame(tick);
      }
      raf = requestAnimationFrame(tick);
    }
    /* On narrow screens the sticky diagram zooms into the region of the active step
       so labels stay legible; on wide screens the whole pipeline stays in view. */
    function frameFor(step) {
      var vb = step.getAttribute("data-vb");
      return narrow.matches && vb ? vb.split(/\s+/).map(Number) : FULL;
    }
    var active = steps[0];
    if (narrow.addEventListener) narrow.addEventListener("change", function () { setVB(frameFor(active)); });
    function activate(step) {
      var n = step.getAttribute("data-step");
      active = step;
      setVB(frameFor(step));
      svg.setAttribute("data-step", n);
      steps.forEach(function (s) { s.classList.toggle("is-active", s === step); });
      if (label) label.textContent = "Step " + n + " of " + steps.length;
    }
    activate(steps[0]);
    if (!("IntersectionObserver" in window)) return;
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) { if (en.isIntersecting) activate(en.target); });
    }, { rootMargin: narrow.matches ? "-64% 0px -30% 0px" : "-50% 0px -45% 0px", threshold: 0 });
    steps.forEach(function (s) { io.observe(s); });
  }

  /* ---------- chapter rail + top nav + progress ---------- */
  function initProgress() {
    var chapters = Array.prototype.slice.call(document.querySelectorAll("section.chapter[id]"));
    var links = Array.prototype.slice.call(document.querySelectorAll(".rail a, .topnav a.chap-link"));
    var bar = document.querySelector(".progress");
    if ("IntersectionObserver" in window) {
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) {
          if (!en.isIntersecting) return;
          var id = en.target.id;
          links.forEach(function (a) {
            a.setAttribute("aria-current", a.getAttribute("href") === "#" + id ? "true" : "false");
          });
        });
      }, { rootMargin: "-40% 0px -55% 0px" });
      chapters.forEach(function (c) { io.observe(c); });
    }
    if (bar) {
      var ticking = false;
      var update = function () {
        var h = document.documentElement.scrollHeight - window.innerHeight;
        var p = h > 0 ? Math.min(1, Math.max(0, window.scrollY / h)) : 0;
        bar.style.transform = "scaleX(" + p.toFixed(4) + ")";
        ticking = false;
      };
      window.addEventListener("scroll", function () {
        if (!ticking) { ticking = true; window.requestAnimationFrame(update); }
      }, { passive: true });
      update();
    }
  }

  /* ---------- theme toggle (system default; explicit choice remembered) ---------- */
  function initTheme() {
    var btn = document.querySelector(".theme-toggle");
    if (!btn) return;
    var mq = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
    function effective() {
      var t = root.getAttribute("data-theme");
      if (t === "dark" || t === "light") return t;
      return mq && mq.matches ? "dark" : "light";
    }
    function label() {
      var next = effective() === "dark" ? "light" : "dark";
      btn.setAttribute("aria-label", "Switch to " + next + " theme");
      btn.setAttribute("title", "Switch to " + next + " theme");
    }
    btn.addEventListener("click", function () {
      var next = effective() === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try { localStorage.setItem("wmbxl-theme", next); } catch (e) { /* storage unavailable */ }
      label();
    });
    if (mq && mq.addEventListener) mq.addEventListener("change", label);
    label();
  }

  /* ---------- pause hero ambient motion while off-screen ---------- */
  function initHeroMotion() {
    var art = document.querySelector(".hero-svg");
    if (!art || reduceMotion || !("IntersectionObserver" in window)) return;
    new IntersectionObserver(function (entries) {
      entries.forEach(function (en) { art.classList.toggle("paused", !en.isIntersecting); });
    }).observe(art);
  }

  function init() {
    initTheme();
    initHeroMotion();
    renderMath();
    Array.prototype.forEach.call(document.querySelectorAll('[role="tablist"]'), initTabs);
    Array.prototype.forEach.call(document.querySelectorAll(".mcq"), initMCQ);
    initExplorer();
    initLadder();
    Array.prototype.forEach.call(document.querySelectorAll(".copy"), initCopy);
    initScrolly();
    initProgress();
    if (reduceMotion) root.classList.add("reduced-motion");
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
