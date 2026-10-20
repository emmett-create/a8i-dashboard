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
  return `
    <header class="site-header ${onDark ? "on-dark" : ""}">
      ${back
        ? `<a class="back-link" href="${back}">&larr; a8i</a>`
        : `<a class="brand-mark" href="index.html"><span class="dot">A</span><span class="mark">AGENCY&nbsp;EIGHT &middot; a8i</span></a>`
      }
      <nav class="header-nav">
        <a href="index.html">Process</a>
        <a href="big-questions.html">Big Questions</a>
      </nav>
    </header>
  `;
}

function renderFooter() {
  return `<footer class="site-footer">Rough visual skeleton as of the 2026-10-20 working session — content mirrors the live "Our Process" Notion page. Not a functional build yet.</footer>`;
}
