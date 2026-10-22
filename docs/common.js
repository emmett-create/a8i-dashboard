function escHtml(s) {
  return String(s).replace(/[&<>"']/g, m => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[m]));
}

function renderOutline(items) {
  if (!items || !items.length) return "";
  return `<ol class="outline">` + items.map(item => `
    <li class="outline-branch">
      <div class="leaf${item.question ? " q" : ""}">
        <span>${escHtml(item.text)}</span>
        ${item.annotation ? `<span class="annotation"><span class="avatar">${escHtml(item.annotation[0])}</span>${escHtml(item.annotation)}</span>` : ""}
      </div>
      ${renderOutline(item.children)}
    </li>
  `).join("") + `</ol>`;
}

// rows: [{ num, title, status ("focus"|"later"|undefined), note, items }]
function renderRowList(rows) {
  return `<div class="row-list">` + rows.map(r => `
    <div class="row-item">
      <div class="row-badge">${r.num}</div>
      <div>
        <h3>${escHtml(r.title)}${
          r.status === "focus" ? `<span class="status-pill focus"><span class="dot"></span>Current focus</span>` : ""
        }${
          r.status === "later" ? `<span class="status-pill later">Deprioritized</span>` : ""
        }</h3>
        ${r.note ? `<div class="row-note">${escHtml(r.note)}</div>` : ""}
        ${r.items && r.items.length ? renderOutline(r.items) : `<p class="leaf" style="color:var(--dim)">Nothing scoped here yet.</p>`}
      </div>
    </div>
  `).join("") + `</div>`;
}

function renderHeader({ onDark = true, back = null } = {}) {
  // Fixed-position header is inserted after this returns, so the listener
  // has to wait a frame before the element actually exists in the DOM.
  requestAnimationFrame(() => {
    const el = document.querySelector(".site-header");
    if (!el || el.dataset.stickyBound) return;
    el.dataset.stickyBound = "1";
    const hero = document.querySelector(".hero");
    const onScroll = () => {
      const pastHero = hero ? window.scrollY > hero.offsetHeight - 70 : false;
      el.classList.toggle("past-hero", pastHero);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });
    onScroll();
  });
  return `
    <header class="site-header ${onDark ? "on-dark" : ""}">
      ${back
        ? `<a class="back-link" href="${back}">&larr; A8I</a>`
        : `<a class="brand-mark" href="process.html"><img class="logo-mark" src="assets/symbol-horizontal-red.png" alt="Agency Eight"><span class="mark">AGENCY&nbsp;EIGHT &middot; A8I</span></a>`
      }
      <nav class="header-nav">
        <a href="process.html">Process</a>
        <a href="https://agency-eight.com" target="_blank" rel="noopener">Agency Eight &#8599;</a>
      </nav>
    </header>
  `;
}

// Shared order for the Previous/Next page nav — matches the "A8I · 0N"
// numbering already used in each area page's eyebrow.
const AREA_PAGES = [
  { id: "onboarding",       title: "Onboarding",       href: "onboarding.html" },
  { id: "sourcing",         title: "Sourcing",         href: "sourcing.html" },
  { id: "gifting",          title: "Gifting",          href: "gifting.html" },
  { id: "outreach",         title: "Outreach",         href: "outreach.html" },
  { id: "order-placement",  title: "Order Placement",  href: "order-placement.html" },
  { id: "content-tracking", title: "Content Tracking", href: "content-tracking.html" },
  { id: "reporting",        title: "Reporting",        href: "reporting.html" },
];

function renderPageNav(currentId) {
  const idx = AREA_PAGES.findIndex(p => p.id === currentId);
  if (idx === -1) return "";
  const prev = idx > 0 ? AREA_PAGES[idx - 1] : null;
  const next = idx < AREA_PAGES.length - 1 ? AREA_PAGES[idx + 1] : null;
  return `
    ${prev ? `<a class="page-nav page-nav-prev" href="${prev.href}"><span class="page-nav-arrow">&larr;</span><span class="page-nav-label">${escHtml(prev.title)}</span></a>` : ""}
    ${next ? `<a class="page-nav page-nav-next" href="${next.href}"><span class="page-nav-label">${escHtml(next.title)}</span><span class="page-nav-arrow">&rarr;</span></a>` : ""}
  `;
}

function getSessionId() {
  let id = localStorage.getItem("a8i_session_id");
  if (!id) {
    id = (crypto.randomUUID ? crypto.randomUUID() : (Date.now() + "-" + Math.random().toString(36).slice(2)));
    localStorage.setItem("a8i_session_id", id);
  }
  return id;
}

function renderFooter() {
  return `<footer class="site-footer">&copy; 2026 Agency Eight. A8I is built on the same system behind Agency Eight's full-service gifting programs.</footer>`;
}
