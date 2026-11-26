(() => {
  const totop = document.querySelector(".totop");
  if (totop) {
    const toggle = () => { totop.hidden = window.scrollY < 400; };
    toggle();
    window.addEventListener("scroll", toggle, { passive: true });
    totop.addEventListener("click", () => {
      const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      window.scrollTo({ top: 0, behavior: reduce ? "auto" : "smooth" });
    });
  }

  const zooms = document.querySelectorAll(".zoom");
  if (!zooms.length) return;

  const lb = document.createElement("div");
  lb.className = "lb";
  lb.hidden = true;
  lb.setAttribute("role", "dialog");
  lb.setAttribute("aria-modal", "true");
  lb.setAttribute("aria-label", "查看大图");
  lb.innerHTML = '<button type="button" class="lb__close" aria-label="关闭"><svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg></button><div class="lb__stage"><img class="lb__img" alt=""></div>';
  document.body.appendChild(lb);

  const stage = lb.querySelector(".lb__stage");
  const img = lb.querySelector(".lb__img");
  const closeBtn = lb.querySelector(".lb__close");
  let lastFocus = null;
  let scale = 1, tx = 0, ty = 0;
  const pointers = new Map();
  let lastDist = 0;
  let lastTap = 0;

  const apply = () => { img.style.transform = `translate(${tx}px, ${ty}px) scale(${scale})`; };
  const reset = () => { scale = 1; tx = 0; ty = 0; apply(); };

  const open = (src, alt) => {
    lastFocus = document.activeElement;
    img.src = src;
    img.alt = alt || "";
    reset();
    lb.hidden = false;
    document.body.classList.add("lb-open");
    closeBtn.focus();
  };
  const close = () => {
    if (lb.hidden) return;
    lb.hidden = true;
    document.body.classList.remove("lb-open");
    img.removeAttribute("src");
    reset();
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  };

  zooms.forEach((btn) => {
    btn.addEventListener("click", () => open(btn.getAttribute("data-full"), btn.getAttribute("aria-label") || ""));
  });
  closeBtn.addEventListener("click", (ev) => { ev.preventDefault(); ev.stopPropagation(); close(); });
  lb.addEventListener("click", (ev) => { if (ev.target === lb || ev.target === stage) close(); });
  document.addEventListener("keydown", (ev) => { if (!lb.hidden && ev.key === "Escape") close(); });

  stage.addEventListener("wheel", (ev) => {
    if (lb.hidden) return;
    ev.preventDefault();
    const next = Math.min(6, Math.max(1, scale * (ev.deltaY > 0 ? 0.9 : 1.11)));
    scale = next;
    if (scale === 1) { tx = 0; ty = 0; }
    apply();
  }, { passive: false });

  stage.addEventListener("pointerdown", (ev) => {
    if (lb.hidden) return;
    pointers.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });
    if (stage.setPointerCapture) stage.setPointerCapture(ev.pointerId);
    if (pointers.size === 2) {
      const [a, b] = [...pointers.values()];
      lastDist = Math.hypot(a.x - b.x, a.y - b.y);
    }
  });
  stage.addEventListener("pointermove", (ev) => {
    if (!pointers.has(ev.pointerId)) return;
    const prev = pointers.get(ev.pointerId);
    pointers.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });
    if (pointers.size === 2) {
      const [a, b] = [...pointers.values()];
      const dist = Math.hypot(a.x - b.x, a.y - b.y);
      if (lastDist) {
        scale = Math.min(6, Math.max(1, scale * (dist / lastDist)));
        apply();
      }
      lastDist = dist;
    } else if (pointers.size === 1 && scale > 1) {
      tx += ev.clientX - prev.x;
      ty += ev.clientY - prev.y;
      apply();
    }
  });
  const up = (ev) => {
    pointers.delete(ev.pointerId);
    if (pointers.size < 2) lastDist = 0;
    if (scale < 1.02) reset();
  };
  stage.addEventListener("pointerup", up);
  stage.addEventListener("pointercancel", up);

  stage.addEventListener("click", (ev) => {
    if (ev.target === closeBtn || closeBtn.contains(ev.target)) return;
    const now = Date.now();
    if (now - lastTap < 280) {
      ev.preventDefault();
      ev.stopPropagation();
      if (scale > 1) reset();
      else { scale = 2.5; apply(); }
    }
    lastTap = now;
  });
})();
