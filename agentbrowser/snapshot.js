// Builds a compact, LLM-friendly view of the page: readable text plus a numbered
// list of interactive elements. Each element gets a stable ref (e1, e2, ...) stored
// on the DOM node, so the agent can say "click e3" instead of guessing selectors.
(opts) => {
  const maxText = (opts && opts.maxText) || 4000;
  const INTERACTIVE = [
    'a[href]', 'button', 'input:not([type=hidden])', 'select', 'textarea', 'summary',
    '[role=button]', '[role=link]', '[role=checkbox]', '[role=radio]', '[role=tab]',
    '[role=menuitem]', '[role=option]', '[role=switch]', '[contenteditable=true]', '[onclick]'
  ].join(',');

  const visible = (el) => {
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) return false;
    const s = getComputedStyle(el);
    return s.visibility !== 'hidden' && s.display !== 'none' && s.opacity !== '0';
  };

  const roleOf = (el) => {
    const explicit = el.getAttribute('role');
    if (explicit) return explicit;
    const tag = el.tagName.toLowerCase();
    if (tag === 'a') return 'link';
    if (tag === 'button' || tag === 'summary') return 'button';
    if (tag === 'select') return 'combobox';
    if (tag === 'textarea') return 'textbox';
    if (tag === 'input') {
      const t = (el.getAttribute('type') || 'text').toLowerCase();
      if (['submit', 'button', 'reset', 'image'].includes(t)) return 'button';
      if (t === 'checkbox' || t === 'radio') return t;
      return 'textbox';
    }
    return tag;
  };

  const labelOf = (el) => {
    const aria = el.getAttribute('aria-label');
    if (aria) return aria;
    if (el.id) {
      const lab = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (lab && lab.innerText.trim()) return lab.innerText;
    }
    const tag = el.tagName.toLowerCase();
    if (tag === 'input' && ['submit', 'button'].includes(el.type)) return el.value || '';
    return el.innerText || el.placeholder || el.title || el.getAttribute('name') || el.alt || '';
  };

  let next = window.__abNext || 1;
  const elements = [];
  document.querySelectorAll(INTERACTIVE).forEach((el) => {
    if (!visible(el) || el.disabled) return;
    let ref = el.getAttribute('data-ab-ref');
    if (!ref) {
      ref = 'e' + next++;
      el.setAttribute('data-ab-ref', ref);
    }
    const item = {
      ref,
      role: roleOf(el),
      name: String(labelOf(el)).trim().replace(/\s+/g, ' ').slice(0, 80),
    };
    const tag = el.tagName.toLowerCase();
    if (tag === 'input' || tag === 'textarea') {
      if (el.type === 'checkbox' || el.type === 'radio') item.checked = el.checked;
      else if (el.type !== 'password' && el.value) item.value = el.value.slice(0, 40);
    }
    if (tag === 'select') item.value = el.value;
    if (tag === 'a') item.href = el.getAttribute('href');
    elements.push(item);
  });
  window.__abNext = next;

  const text = (document.body ? document.body.innerText : '')
    .replace(/[ \t]+/g, ' ')
    .replace(/\n\s*\n\s*\n+/g, '\n\n')
    .trim();

  return {
    url: location.href,
    title: document.title,
    text: text.slice(0, maxText),
    truncated: text.length > maxText,
    elements,
  };
}
