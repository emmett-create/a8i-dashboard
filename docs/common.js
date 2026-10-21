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
    const onScroll = () => el.classList.toggle("scrolled", window.scrollY > 40);
    window.addEventListener("scroll", onScroll, { passive: true });
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
