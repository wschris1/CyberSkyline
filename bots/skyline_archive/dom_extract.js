() => {
  // Read rendered DOM only. Never inspect React state, cookies, or network payloads.
  const text = (node) => (node?.textContent || "").trim();
  const escape = (value) => value.replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/([\\`*_{}\[\]()|#!])/g, "\\$1");
  function render(node) {
    if (node.nodeType === 3) return escape(node.textContent);
    if (node.nodeType !== 1) return "";
    const tag = node.tagName.toLowerCase();
    if (["input", "textarea", "select", "button", "script", "style", "iframe"].includes(tag)
        || node.getAttribute("role") === "listbox" || node.hidden
        || node.getAttribute("aria-hidden") === "true") return "";
    if (tag === "img") return node.closest("h4.ui.image.header") ? "" : "[Image in source challenge]";
    if (tag === "pre") {
      const value = text(node);
      const runs = value.match(/`+/g) || [];
      const fence = "`".repeat(Math.max(3, ...runs.map(r => r.length + 1)));
      return `\n\n${fence}\n${value}\n${fence}\n\n`;
    }
    if (tag === "code") {
      const value = text(node);
      const fence = "`".repeat(Math.max(1, ...(value.match(/`+/g) || []).map(r => r.length + 1)));
      return `${fence} ${value} ${fence}`;
    }
    const inner = Array.from(node.childNodes).map(render).join("");
    if (tag === "br") return "\n";
    if (tag === "li") return `\n- ${inner.trim()}\n`;
    if (tag === "a") {
      const href = node.getAttribute("href") || "";
      // Download URLs can be tied to a participant; publish only the filename.
      if (href.startsWith("/artifact/")) return inner;
      let url;
      try { url = new URL(href, "https://cyberskyline.com"); } catch { return inner; }
      if (!["http:", "https:"].includes(url.protocol)) return inner;
      url.search = ""; url.hash = ""; url.username = ""; url.password = "";
      return `[${inner || "Link"}](<${url.href}>)`;
    }
    if (tag === "tr") return `\n${inner}\n`;
    if (tag === "td" || tag === "th") return ` ${inner.trim()} |`;
    if (["p", "div", "section", "ul", "ol", "table", "h1", "h2", "h3", "h4"].includes(tag)) {
      return `\n\n${inner.trim()}\n\n`;
    }
    return inner;
  }
  // Keep whitespace inside code/ciphertext intact.
  const tidy = s => s.trim();
  const links = Array.from(document.querySelectorAll("a[href]")).map(a => ({
    href: a.getAttribute("href"),
    title: text(a.querySelector("h2")) || text(a.querySelector("h3")) || text(a),
  })).filter(a => /^\/(world|module)\/[a-f0-9/]+$/.test(a.href));
  const heading = document.querySelector("h1");
  const headingText = heading ? Array.from(heading.childNodes).filter(n => n.nodeType === 3)
    .map(n => n.textContent).join("").trim() || text(heading) : "";
  const result = {links, event: headingText, challenge: null, issue: null};
  const menus = Array.from(document.querySelectorAll('[role="listbox"].ui.inline.dropdown'));
  if (menus.length < 2) return result;
  const category = text(menus[0].querySelector('[role="alert"]'));
  const title = text(menus[1].querySelector('[role="alert"]'));
  result.category = category;
  result.title = title;
  const descriptions = Array.from(document.querySelectorAll(".ui.basic.segment.body:not(.fat)"));
  const tables = Array.from(document.querySelectorAll(".ui.basic.segment.fat.tall.body > table"));
  if (descriptions.length !== 1 || tables.length !== 1) {
    result.issue = "Expected one prompt and one question table.";
    return result;
  }
  const description = descriptions[0];
  const promptNodes = Array.from(description.children).filter(e =>
    e.tagName === "DIV" && e.style.padding === "0px");
  if (promptNodes.length !== 1) {
    result.issue = "The prompt layout was not recognized.";
    return result;
  }
  const table = tables[0];
  const rows = Array.from(table.querySelectorAll(":scope > tbody > tr[data-value]"));
  const headers = Array.from(table.querySelectorAll(":scope > thead > tr > th")).map(text);
  const questions = [];
  const questionIds = [];
  for (const row of rows) {
    const cells = Array.from(row.children).filter(e => e.tagName === "TD");
    // The final cell contains both saved answers and editable response controls.
    // Exclude the entire cell even when there is no input (completed questions).
    if (cells.length < 2 || cells.length > 3 || !cells.at(-1).classList.contains("center")
        || !cells.at(-1).classList.contains("aligned")) {
      result.issue = "Unrecognized question row; no response cells were exported.";
      return result;
    }
    const parts = cells.slice(0, -1).map((cell, index) => {
      const content = tidy(render(cell));
      return cells.length === 3 && headers[index] ? `**${escape(headers[index])}:** ${content}` : content;
    });
    questions.push(parts.join("\n\n"));
    questionIds.push(row.getAttribute("data-value"));
  }
  if (!title || !category || !questions.length || questions.some(q => !q)) {
    result.issue = "Question content is not ready or the layout has changed.";
    return result;
  }
  result.challenge = {
    title, category, prompt: tidy(render(promptNodes[0])), questions, question_ids: questionIds,
    attachments: Array.from(description.querySelectorAll('a[href^="/artifact/"]')).map(text),
    attachment_refs: Array.from(description.querySelectorAll('a[href^="/artifact/"]'))
      .map(a => ({name: text(a), url: new URL(a.getAttribute('href'), 'https://cyberskyline.com').href})),
  };
  return result;
}
