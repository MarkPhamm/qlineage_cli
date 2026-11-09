(function () {
  "use strict";
  var root = document.querySelector(".qh");
  if (!root) return;
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function wait(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

  function onView(el, fn) {
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (e) {
        if (e.isIntersecting || e.boundingClientRect.bottom < 0) {
          io.unobserve(e.target);
          fn(e.target);
        }
      });
    }, { rootMargin: "0px 0px -12% 0px" });
    io.observe(el);
  }

  root.querySelectorAll(".qh-copy").forEach(function (button) {
    button.addEventListener("click", function () {
      if (!navigator.clipboard) return;
      var text = button.getAttribute("data-copy") || "";
      navigator.clipboard.writeText(text).then(function () {
        var previous = button.textContent;
        button.textContent = "Copied";
        setTimeout(function () { button.textContent = previous; }, 1200);
      }, function () {});
    });
  });

  root.querySelectorAll(".qh-tabs").forEach(function (box) {
    var bar = box.querySelector(".qh-tabs__bar");
    var tabs = [].slice.call(bar.querySelectorAll('[role="tab"]'));
    var panels = [].slice.call(box.querySelectorAll("pre.qh-code"));
    var ind = document.createElement("span");
    ind.className = "qh-tabs__ind";
    bar.appendChild(ind);
    bar.classList.add("qh-ind");
    function pick(k, focus) {
      tabs.forEach(function (t, j) {
        t.setAttribute("aria-selected", j === k ? "true" : "false");
        t.tabIndex = j === k ? 0 : -1;
        panels[j].classList.toggle("show", j === k);
      });
      var b = tabs[k];
      ind.style.transform = "translateX(" + b.offsetLeft + "px) scaleX(" + b.offsetWidth + ")";
      if (focus) b.focus();
    }
    tabs.forEach(function (t, k) {
      t.addEventListener("click", function () { pick(k); });
      t.addEventListener("keydown", function (e) {
        var n = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
        if (!n) return;
        e.preventDefault();
        pick((k + n + tabs.length) % tabs.length, true);
      });
    });
    pick(0);
  });

  root.querySelectorAll(".qh-col, .qh-box, .qh-card, .qh-tabs").forEach(function (c) {
    c.classList.add("qh-glow");
    c.addEventListener("pointermove", function (e) {
      var r = c.getBoundingClientRect();
      c.style.setProperty("--mx", (e.clientX - r.left) + "px");
      c.style.setProperty("--my", (e.clientY - r.top) + "px");
    });
  });

  if (reduce) return;

  function splitWords(h) {
    var i = 0;
    (function walk(n) {
      [].slice.call(n.childNodes).forEach(function (c) {
        if (c.nodeType === 3) {
          var frag = document.createDocumentFragment();
          c.textContent.split(/( +|\n+)/).forEach(function (w) {
            if (!w) return;
            if (!w.trim()) { frag.appendChild(document.createTextNode(w)); return; }
            var q = document.createElement("q-w");
            q.style.setProperty("--i", i++);
            q.textContent = w;
            frag.appendChild(q);
          });
          c.replaceWith(frag);
        } else if (c.nodeType === 1 && c.tagName !== "CODE") walk(c);
      });
    })(h);
    h.classList.add("qh-words");
  }

  function reveal(items, step) {
    items.forEach(function (el) { el.classList.add("qh-rv"); });
    void document.body.offsetWidth;
    items.forEach(function (el, k) {
      el.style.setProperty("--d", (step ? k * step : 0) + "s");
      onView(el, function () { el.classList.add("qh-in"); });
    });
  }

  var h1 = root.querySelector(".qh-hero h1");
  if (h1) splitWords(h1);
  root.querySelectorAll(".qh-section > h2, .qh-final > h2").forEach(function (h) {
    splitWords(h);
    onView(h, function () { h.classList.add("qh-in"); });
  });
  reveal([].slice.call(root.querySelectorAll(".qh-section > .qh-sub")));
  root.querySelectorAll(".qh-steps3, .qh-gallery").forEach(function (g) {
    reveal([].slice.call(g.children), 0.08);
  });
  var finalBlock = root.querySelector(".qh-final");
  if (finalBlock) {
    reveal([].slice.call(finalBlock.children).filter(function (c) { return c.tagName !== "H2"; }), 0.08);
  }

  var cmp = root.querySelector(".qh-compare");
  if (cmp) {
    cmp.classList.add("qh-anim");
    void cmp.offsetWidth;
    [].forEach.call(cmp.children, function (col, i) {
      col.style.setProperty("--d", i * 0.12 + "s");
      col.querySelectorAll("li").forEach(function (li, j) {
        li.style.setProperty("--d", (0.3 + i * 0.12 + j * 0.1) + "s");
      });
    });
    onView(cmp, function () { cmp.classList.add("qh-in"); });
  }

  var NS = "http://www.w3.org/2000/svg";
  function svgEl(tag, attrs) {
    var el = document.createElementNS(NS, tag);
    Object.keys(attrs).forEach(function (k) { el.setAttribute(k, attrs[k]); });
    return el;
  }
  var flow = root.querySelector(".qh-flow");
  if (flow) {
    var cols = flow.querySelectorAll(".qh-flow__col");
    cols[0].classList.add("qh-flow__ins");
    cols[2].classList.add("qh-flow__outs");
    var ins = [].slice.call(cols[0].children);
    var core = cols[1].querySelector(".qh-box");
    var outs = [].slice.call(cols[2].children);
    var small = core.querySelector("small");
    var parts = small.textContent.split(" · ");
    small.textContent = "";
    var words = parts.map(function (w, i) {
      if (i) small.appendChild(document.createTextNode(" · "));
      var s = document.createElement("span");
      s.textContent = w;
      return small.appendChild(s);
    });
    flow.classList.add("wired", "qh-anim");
    void flow.offsetWidth;
    ins.forEach(function (b, i) { b.style.setProperty("--d", i * 0.1 + "s"); });
    outs.forEach(function (b, i) { b.style.setProperty("--d", (1.5 + i * 0.1) + "s"); });
    core.style.setProperty("--d", ".7s");

    var svg = svgEl("svg", { "class": "qh-flow__wires", "aria-hidden": "true" });
    flow.insertBefore(svg, flow.firstChild);
    var wires = { in: [], out: [] };

    function box(b) {
      var x = b.offsetLeft + b.offsetParent.offsetLeft;
      var y = b.offsetTop + b.offsetParent.offsetTop;
      return { left: x, right: x + b.offsetWidth, mid: y + b.offsetHeight / 2 };
    }
    function draw() {
      while (svg.firstChild) svg.removeChild(svg.firstChild);
      wires = { in: [], out: [] };
      if (getComputedStyle(svg).display === "none") return;
      var c = box(core);
      function wire(kind, x1, y1, x2, y2) {
        var dx = (x2 - x1) * 0.55;
        var d = "M" + x1 + " " + y1 + " C" + (x1 + dx) + " " + y1 + " " + (x2 - dx) + " " + y2 + " " + x2 + " " + y2;
        var g = svgEl("g", {});
        var base = svgEl("path", { d: d, "class": "base" });
        g.appendChild(base);
        g.appendChild(svgEl("path", { d: d, "class": "flow" }));
        g.appendChild(svgEl("circle", { cx: x1, cy: y1, r: 3, "class": "dot" }));
        g.appendChild(svgEl("circle", { cx: x2, cy: y2, r: 3, "class": "dot" }));
        svg.appendChild(g);
        wires[kind].push({ g: g, base: base, d: d, len: base.getTotalLength() });
      }
      ins.forEach(function (b, i) {
        var r = box(b);
        wire("in", r.right, r.mid, c.left, c.mid + (i - (ins.length - 1) / 2) * 14);
      });
      outs.forEach(function (b, i) {
        var r = box(b);
        wire("out", c.right, c.mid + (i - (outs.length - 1) / 2) * 12, r.left, r.mid);
      });
    }
    draw();
    new ResizeObserver(function () { if (flow.isConnected) draw(); }).observe(flow);

    function drawIn(list, delay) {
      list.forEach(function (w, i) {
        w.base.animate(
          [{ strokeDasharray: w.len, strokeDashoffset: w.len }, { strokeDasharray: w.len, strokeDashoffset: 0 }],
          { duration: 520, delay: delay + i * 90, easing: "cubic-bezier(.65,0,.35,1)", fill: "backwards" }
        );
      });
    }
    function comet(w, ms) {
      var p = svgEl("path", { d: w.d, "class": "comet", "stroke-dasharray": "22 " + (w.len + 44) });
      svg.appendChild(p);
      p.animate([{ strokeDashoffset: 22 }, { strokeDashoffset: -w.len }], { duration: ms, easing: "cubic-bezier(.65,0,.35,1)" }).onfinish = function () { p.remove(); };
    }
    function ping(b) {
      b.classList.add("ping");
      setTimeout(function () { b.classList.remove("ping"); }, 650);
    }
    var turn = 0, hovering = false;
    async function pulse() {
      if (hovering || !wires.in.length) return;
      var i = turn++ % ins.length;
      ping(ins[i]);
      comet(wires.in[i], 700);
      await wait(650);
      ping(core);
      for (var k = 0; k < words.length; k++) {
        words[k].classList.add("on");
        await wait(160);
        words[k].classList.remove("on");
      }
      wires.out.forEach(function (w, j) { setTimeout(function () { comet(w, 650); }, j * 70); });
      await wait(560);
      outs.forEach(function (b, j) { setTimeout(function () { ping(b); }, j * 70); });
    }
    function light(on) {
      wires.in.concat(wires.out).forEach(function (w) { w.g.classList.toggle("lit", on.indexOf(w) >= 0); });
    }
    function hover(b, which) {
      b.addEventListener("mouseenter", function () { hovering = true; light(which()); });
      b.addEventListener("mouseleave", function () { hovering = false; light([]); });
    }
    ins.forEach(function (b, i) { hover(b, function () { return [wires.in[i]].concat(wires.out); }); });
    outs.forEach(function (b, i) { hover(b, function () { return wires.in.concat([wires.out[i]]); }); });
    hover(core, function () { return wires.in.concat(wires.out); });

    onView(flow, function () {
      flow.classList.add("qh-in");
      drawIn(wires.in, 350);
      setTimeout(function loop() {
        pulse().then(function () { if (flow.isConnected) setTimeout(loop, 1200); });
      }, 350 + 520 + ins.length * 90);
    });
  }

  var command = root.querySelector(".qh-final .qh-install code");
  if (command) {
    onView(command, function () {
      setTimeout(function () {
        var full = command.textContent;
        command.style.minWidth = command.offsetWidth + "px";
        command.textContent = "";
        var caret = document.createElement("q-caret");
        command.appendChild(caret);
        var k = 0;
        (function tick() {
          if (k < full.length) {
            caret.before(full[k++]);
            setTimeout(tick, 45);
          } else setTimeout(function () { caret.remove(); }, 1600);
        })();
      }, 400);
    });
  }
})();
