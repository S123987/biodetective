/* BioDetective browser interface. User content is rendered as text or sanitized Markdown. */
(function () {
  "use strict";

  const STORAGE_KEY = "biodetective.web.conversations.v1";
  const THEME_KEY = "biodetective.web.theme.v1";
  const PREFERENCES_KEY = "biodetective.web.preferences.v1";
  const DEFAULT_PREFERENCES = {
    model: "gemini-3.8-flash",
    reasoning_effort: "medium",
    style: "balanced",
    web_search: true,
    custom_instructions: "",
  };
  const MODEL_LABELS = {
    "gemini-3.8-flash": "Gemini 3.8 Flash",
    "gemini-3.5-flash": "Gemini 3.5 Flash",
    "gemini-3.5-flash-lite": "Gemini 3.5 Flash-Lite",
    "gemini-3.1-flash-lite": "Gemini 3.1 Flash-Lite",
  };
  const MAX_FILES = 5;
  const MAX_FILE_BYTES = 12 * 1024 * 1024;
  const byId = function (id) { return document.getElementById(id); };
  const elements = {
    sidebar: byId("sidebar"), scrim: byId("sidebarScrim"), conversationList: byId("conversationList"),
    historyContextMenu: byId("historyContextMenu"), deleteHistoryButton: byId("deleteHistoryButton"),
    welcome: byId("welcomeView"), messageView: byId("messageView"), messages: byId("messages"),
    prompt: byId("promptInput"), send: byId("sendButton"), fileInput: byId("fileInput"), attachmentList: byId("attachmentList"),
    voice: byId("voiceButton"), recordingLabel: byId("recordingLabel"), toast: byId("toast"),
    connectionDot: byId("connectionDot"), connectionLabel: byId("connectionLabel"), modelLabel: byId("modelLabel"),
    modeHint: byId("modeHint"), modal: byId("modalBackdrop"),
  };

  let conversations = readConversations();
  let activeId = null;
  let mode = "chat";
  let pendingFiles = [];
  let busy = false;
  let recorder = null;
  let recordingTimer = null;
  let toastTimer = null;
  let searchInput = null;
  let searchTerm = "";
  let contextConversationId = null;
  let contextMenuAnchor = null;
  let preferences = readPreferences();

  function readConversations() {
    try {
      const value = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
      return Array.isArray(value) ? value.filter(function (item) { return item && Array.isArray(item.messages); }) : [];
    } catch (_error) {
      return [];
    }
  }

  function readPreferences() {
    try {
      const saved = JSON.parse(localStorage.getItem(PREFERENCES_KEY) || "{}");
      if (!saved || typeof saved !== "object") return Object.assign({}, DEFAULT_PREFERENCES);
      return {
        model: Object.prototype.hasOwnProperty.call(MODEL_LABELS, saved.model) ? saved.model : DEFAULT_PREFERENCES.model,
        reasoning_effort: ["low", "medium", "high"].includes(saved.reasoning_effort) ? saved.reasoning_effort : DEFAULT_PREFERENCES.reasoning_effort,
        style: ["concise", "balanced", "detailed"].includes(saved.style) ? saved.style : DEFAULT_PREFERENCES.style,
        web_search: saved.web_search !== false,
        custom_instructions: typeof saved.custom_instructions === "string" ? saved.custom_instructions.slice(0, 1500) : "",
      };
    } catch (_error) {
      return Object.assign({}, DEFAULT_PREFERENCES);
    }
  }

  function updateModelLabel() {
    elements.modelLabel.textContent = MODEL_LABELS[preferences.model] || MODEL_LABELS[DEFAULT_PREFERENCES.model];
  }

  function openSettings() {
    byId("modelSelect").value = preferences.model;
    byId("reasoningSelect").value = preferences.reasoning_effort;
    byId("styleSelect").value = preferences.style;
    byId("webSearchToggle").checked = preferences.web_search;
    byId("customInstructions").value = preferences.custom_instructions;
    byId("settingsBackdrop").classList.remove("hidden");
    byId("modelSelect").focus();
  }

  function closeSettings() {
    byId("settingsBackdrop").classList.add("hidden");
  }

  function saveSettings(next) {
    preferences = Object.assign({}, DEFAULT_PREFERENCES, next || {
      model: byId("modelSelect").value,
      reasoning_effort: byId("reasoningSelect").value,
      style: byId("styleSelect").value,
      web_search: byId("webSearchToggle").checked,
      custom_instructions: byId("customInstructions").value.slice(0, 1500).trim(),
    });
    try { localStorage.setItem(PREFERENCES_KEY, JSON.stringify(preferences)); } catch (_error) { /* Preferences still apply until the page closes. */ }
    updateModelLabel();
    closeSettings();
    showToast("Preferences saved in this browser.", false);
  }

  function persist() {
    conversations = conversations.slice(0, 40);
    const compact = conversations.map(function (conversation) {
      return Object.assign({}, conversation, {
        messages: conversation.messages.slice(-40).map(function (message) {
          const saved = Object.assign({}, message);
          if (saved.investigation && Array.isArray(saved.investigation.articles)) {
            saved.investigation = Object.assign({}, saved.investigation, {
              articles: saved.investigation.articles.map(function (article) {
                const copy = Object.assign({}, article);
                delete copy.abstract;
                return copy;
              }),
            });
          }
          return saved;
        }),
      });
    });
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(compact)); } catch (_error) { /* Browser storage may be full or disabled. */ }
  }

  function currentConversation() {
    return conversations.find(function (item) { return item.id === activeId; }) || null;
  }

  function createConversation() {
    const id = "chat-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 8);
    const conversation = { id: id, title: "New chat", messages: [], updated: Date.now() };
    conversations.unshift(conversation);
    activeId = id;
    return conversation;
  }

  function truncate(value, max) {
    const text = String(value || "").replace(/\s+/g, " ").trim();
    return text.length > max ? text.slice(0, max - 1) + "…" : text;
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, function (char) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char];
    });
  }

  function safeUrl(value) {
    try {
      const parsed = new URL(value);
      return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.href : "";
    } catch (_error) { return ""; }
  }

  function inlineMarkdown(value) {
    let text = escapeHtml(value);
    text = text.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, function (_match, label, url) {
      const safe = safeUrl(url.replace(/&amp;/g, "&"));
      return safe ? '<a href="' + escapeHtml(safe) + '" target="_blank" rel="noopener noreferrer">' + label + "</a>" : label;
    });
    text = text.replace(/`([^`]+)`/g, "<code>$1</code>");
    text = text.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    text = text.replace(/(^|[^*])\*([^*]+)\*/g, "$1<em>$2</em>");
    return text;
  }

  function markdownHtml(markdown) {
    const lines = String(markdown || "").replace(/\r/g, "").split("\n");
    const output = [];
    let paragraph = [];
    let list = "";
    let code = false;
    let codeLines = [];
    function flushParagraph() {
      if (paragraph.length) {
        output.push("<p>" + paragraph.map(inlineMarkdown).join("<br>") + "</p>");
        paragraph = [];
      }
    }
    function closeList() {
      if (list) { output.push("</" + list + ">"); list = ""; }
    }
    lines.forEach(function (line) {
      if (/^\s*```/.test(line)) {
        flushParagraph(); closeList();
        if (code) {
          output.push("<pre><code>" + escapeHtml(codeLines.join("\n")) + "</code></pre>");
          codeLines = [];
        }
        code = !code;
        return;
      }
      if (code) { codeLines.push(line); return; }
      if (!line.trim()) { flushParagraph(); closeList(); return; }
      const heading = line.match(/^(#{1,3})\s+(.+)$/);
      if (heading) {
        flushParagraph(); closeList();
        const level = Math.min(heading[1].length + 1, 4);
        output.push("<h" + level + ">" + inlineMarkdown(heading[2]) + "</h" + level + ">");
        return;
      }
      const bullet = line.match(/^\s*[-*]\s+(.+)$/);
      const numbered = line.match(/^\s*\d+[.)]\s+(.+)$/);
      if (bullet || numbered) {
        flushParagraph();
        const nextList = bullet ? "ul" : "ol";
        if (list !== nextList) { closeList(); output.push("<" + nextList + ">"); list = nextList; }
        output.push("<li>" + inlineMarkdown((bullet || numbered)[1]) + "</li>");
        return;
      }
      closeList(); paragraph.push(line);
    });
    flushParagraph(); closeList();
    if (codeLines.length) output.push("<pre><code>" + escapeHtml(codeLines.join("\n")) + "</code></pre>");
    return output.join("");
  }

  function addSourceStrip(parent, citations) {
    if (!Array.isArray(citations) || !citations.length) return;
    const strip = document.createElement("div");
    strip.className = "source-strip";
    citations.slice(0, 8).forEach(function (citation) {
      const url = safeUrl(citation.url || "");
      if (!url) return;
      const link = document.createElement("a");
      link.className = "source-chip";
      link.href = url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      const dot = document.createElement("i");
      const label = document.createElement("span");
      label.textContent = truncate(citation.title || new URL(url).hostname, 42);
      link.append(dot, label);
      strip.appendChild(link);
    });
    if (strip.childElementCount) parent.appendChild(strip);
  }

  function textElement(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    node.textContent = text == null ? "" : String(text);
    return node;
  }

  function makeStat(number, label, extraClass) {
    const card = document.createElement("div");
    card.className = "evidence-stat" + (extraClass ? " " + extraClass : "");
    card.append(textElement("strong", "", number), textElement("span", "", label));
    return card;
  }

  function buildRelationshipGraph(relationships) {
    if (!relationships.length) return null;
    const ns = "http://www.w3.org/2000/svg";
    const rowHeight = 58;
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("class", "mini-graph");
    svg.setAttribute("viewBox", "0 0 660 " + (relationships.length * rowHeight + 8));
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", "Proposed biological relationships with mapped evidence counts");
    const theme = getComputedStyle(document.documentElement);
    const lineColor = theme.getPropertyValue("--line-strong").trim();
    const textColor = theme.getPropertyValue("--text").trim();
    const mutedColor = theme.getPropertyValue("--text-faint").trim();
    const surfaceColor = theme.getPropertyValue("--surface").trim();
    const accentColor = theme.getPropertyValue("--accent").trim();
    const markerId = "graph-arrow-" + Math.random().toString(36).slice(2, 8);
    const defs = document.createElementNS(ns, "defs");
    const marker = document.createElementNS(ns, "marker");
    marker.setAttribute("id", markerId); marker.setAttribute("markerWidth", "7"); marker.setAttribute("markerHeight", "7");
    marker.setAttribute("refX", "5"); marker.setAttribute("refY", "3.5"); marker.setAttribute("orient", "auto");
    const arrow = document.createElementNS(ns, "path"); arrow.setAttribute("d", "M0,0 L7,3.5 L0,7 Z"); arrow.setAttribute("fill", accentColor);
    marker.appendChild(arrow); defs.appendChild(marker); svg.appendChild(defs);

    relationships.slice(0, 10).forEach(function (relationship, index) {
      const y = 6 + index * rowHeight;
      const source = truncate(relationship.source || "Unresolved source", 21);
      const target = truncate(relationship.target || "Unresolved target", 21);
      const label = truncate(relationship.relation || "proposed link", 17);
      const edge = document.createElementNS(ns, "line");
      edge.setAttribute("x1", "188"); edge.setAttribute("y1", String(y + 21)); edge.setAttribute("x2", "469"); edge.setAttribute("y2", String(y + 21));
      edge.setAttribute("stroke", lineColor); edge.setAttribute("stroke-width", "1.5"); edge.setAttribute("marker-end", "url(#" + markerId + ")"); svg.appendChild(edge);

      [[10, source], [476, target]].forEach(function (node) {
        const box = document.createElementNS(ns, "rect");
        box.setAttribute("x", String(node[0])); box.setAttribute("y", String(y + 5)); box.setAttribute("width", "174"); box.setAttribute("height", "32");
        box.setAttribute("rx", "8"); box.setAttribute("fill", surfaceColor); box.setAttribute("stroke", lineColor); svg.appendChild(box);
        const text = document.createElementNS(ns, "text");
        text.setAttribute("x", String(node[0] + 12)); text.setAttribute("y", String(y + 25)); text.setAttribute("fill", textColor); text.setAttribute("font-size", "11"); text.setAttribute("font-family", "DM Sans, sans-serif");
        text.textContent = node[1]; svg.appendChild(text);
      });

      const relation = document.createElementNS(ns, "text");
      relation.setAttribute("x", "328"); relation.setAttribute("y", String(y + 15)); relation.setAttribute("text-anchor", "middle");
      relation.setAttribute("fill", accentColor); relation.setAttribute("font-size", "9"); relation.setAttribute("font-family", "DM Sans, sans-serif"); relation.textContent = label; svg.appendChild(relation);
      const counts = document.createElementNS(ns, "text");
      counts.setAttribute("x", "328"); counts.setAttribute("y", String(y + 34)); counts.setAttribute("text-anchor", "middle");
      counts.setAttribute("fill", mutedColor); counts.setAttribute("font-size", "8"); counts.setAttribute("font-family", "DM Sans, sans-serif");
      counts.textContent = "+" + (relationship.supporting || 0) + " support   −" + (relationship.contradicting || 0) + " conflict   ·   " + (relationship.linked_records || 0) + " mapped";
      svg.appendChild(counts);
    });
    return svg;
  }

  function downloadReport(markdown, claim) {
    const blob = new Blob([String(markdown || "")], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    const filename = String(claim || "biology-claim").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 48) || "biology-claim";
    anchor.href = url; anchor.download = "biodetective-" + filename + ".md";
    document.body.appendChild(anchor); anchor.click(); anchor.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  }

  function renderInvestigation(parent, data, report) {
    if (!data || typeof data !== "object") return;
    const panel = document.createElement("section");
    panel.className = "investigation-panel";
    const header = document.createElement("div");
    header.className = "investigation-header";
    header.appendChild(textElement("strong", "", "Investigation snapshot"));
    const headerActions = document.createElement("div"); headerActions.className = "investigation-header-actions";
    headerActions.appendChild(textElement("span", "research-stamp", "Source-linked review"));
    const exportButton = textElement("button", "download-report", "↓ Report");
    exportButton.type = "button"; exportButton.addEventListener("click", function () { downloadReport(report, data.claim); });
    headerActions.appendChild(exportButton); header.appendChild(headerActions);
    panel.appendChild(header);

    const evidence = data.bes || {};
    const stats = document.createElement("div");
    stats.className = "evidence-stats";
    stats.append(makeStat(evidence.supporting || 0, "Potential support", "support"), makeStat(evidence.contradicting || 0, "Potential conflict", "conflict"), makeStat(evidence.insufficient || 0, "Insufficient"));
    panel.appendChild(stats);

    const score = Number.isFinite(evidence.score) ? evidence.score : null;
    const scoreLine = document.createElement("div");
    scoreLine.className = "score-line";
    scoreLine.append(textElement("strong", "", "Pilot evidence share"), textElement("span", "", score === null ? "Not scored" : score + " / 100"));
    panel.appendChild(scoreLine);
    const track = document.createElement("div"); track.className = "score-track";
    const fill = document.createElement("div"); fill.className = "score-fill"; fill.style.width = (score === null ? 0 : Math.max(0, Math.min(100, score))) + "%";
    track.appendChild(fill); panel.appendChild(track);
    panel.appendChild(textElement("p", "uncalibrated-note", "Weighted share among retrieved records classified as supporting or contradictory. It is uncalibrated and is not a probability that the claim is true."));

    const relationships = Array.isArray(data.relationship_assessments) ? data.relationship_assessments : [];
    if (relationships.length) {
      panel.appendChild(textElement("div", "panel-section-title", "Evidence graph · proposed claim relationships"));
      const graphViewport = document.createElement("div"); graphViewport.className = "mini-graph-scroll";
      const graph = buildRelationshipGraph(relationships);
      if (graph) graphViewport.appendChild(graph);
      panel.appendChild(graphViewport);
      const list = document.createElement("div"); list.className = "relationship-list";
      relationships.slice(0, 6).forEach(function (relationship) {
        const row = document.createElement("div"); row.className = "relationship-item";
        row.append(textElement("span", "relation-end", relationship.source || "?"), textElement("span", "relationship-arrow", "→"), textElement("span", "relation-end", relationship.target || "?"), textElement("span", "relationship-count", (relationship.linked_records || 0) + " sources"));
        list.appendChild(row);
      });
      panel.appendChild(list);
    }

    const hypotheses = data.analysis && Array.isArray(data.analysis.hypotheses) ? data.analysis.hypotheses : [];
    if (hypotheses.length) {
      panel.appendChild(textElement("div", "panel-section-title", "Competing hypotheses"));
      const list = document.createElement("div"); list.className = "hypothesis-list";
      hypotheses.forEach(function (hypothesis) {
        const card = document.createElement("article"); card.className = "hypothesis-card";
        card.appendChild(textElement("strong", "", (hypothesis.id || "H") + " · " + (hypothesis.label || "Candidate explanation")));
        card.appendChild(textElement("p", "", hypothesis.description || ""));
        list.appendChild(card);
      });
      panel.appendChild(list);
    }

    const articles = Array.isArray(data.articles) ? data.articles : [];
    if (articles.length) {
      panel.appendChild(textElement("div", "panel-section-title", "Evidence cards · " + articles.length + " retrieved records"));
      const list = document.createElement("div"); list.className = "evidence-card-list";
      articles.forEach(function (article, index) {
        const card = document.createElement("article"); card.className = "evidence-card";
        const titleRow = document.createElement("div"); titleRow.className = "evidence-card-title";
        const link = document.createElement("a");
        const articleUrl = safeUrl(article.url || "");
        link.textContent = "[" + (index + 1) + "] " + (article.title || "Untitled source");
        if (articleUrl) { link.href = articleUrl; link.target = "_blank"; link.rel = "noopener noreferrer"; }
        const polarity = article.evidence && article.evidence.polarity || "insufficient";
        titleRow.append(link, textElement("span", "polarity-badge " + polarity, polarity));
        card.appendChild(titleRow);
        const meta = [article.year, article.journal, (article.source_catalogs || []).join(" · ")].filter(Boolean).join(" · ");
        card.appendChild(textElement("p", "evidence-meta", meta || "Metadata only"));
        card.appendChild(textElement("p", "", article.evidence && article.evidence.finding_summary || "No finding summary available."));
        list.appendChild(card);
      });
      panel.appendChild(list);
    }
    parent.appendChild(panel);
  }

  function renderMessage(message) {
    const row = document.createElement("article");
    row.className = "message-row " + (message.role === "user" ? "user" : "assistant");
    if (message.role !== "user") row.appendChild(textElement("div", "assistant-mark", "B"));
    const body = document.createElement("div"); body.className = "message-body";
    if (message.role !== "user") body.appendChild(textElement("div", "message-author", "BioDetective"));
    const content = document.createElement("div"); content.className = "message-text";
    content.innerHTML = markdownHtml(message.content || "");
    body.appendChild(content);
    if (Array.isArray(message.files) && message.files.length) {
      const files = document.createElement("div"); files.className = "message-files";
      message.files.forEach(function (name) { files.appendChild(textElement("span", "message-file-pill", "▧ " + name)); });
      body.appendChild(files);
    }
    if (message.role !== "user") {
      addSourceStrip(body, message.citations);
      renderInvestigation(body, message.investigation, message.content);
    }
    row.appendChild(body);
    return row;
  }

  function renderMessages() {
    const conversation = currentConversation();
    const hasMessages = Boolean(conversation && conversation.messages.length);
    elements.welcome.classList.toggle("hidden", hasMessages);
    elements.messageView.classList.toggle("hidden", !hasMessages);
    if (!hasMessages) return;
    elements.messages.replaceChildren();
    conversation.messages.forEach(function (message) { elements.messages.appendChild(renderMessage(message)); });
    elements.messageView.scrollTop = elements.messageView.scrollHeight;
  }

  function renderConversationList() {
    elements.conversationList.replaceChildren();
    const matches = conversations.filter(function (conversation) {
      return conversation.messages.length && (!searchTerm || conversation.title.toLowerCase().includes(searchTerm.toLowerCase()));
    });
    matches.slice(0, 40).forEach(function (conversation) {
      const button = document.createElement("button");
      button.className = "history-item" + (conversation.id === activeId ? " active" : "");
      button.type = "button";
      button.appendChild(textElement("span", "history-chat-icon", ""));
      button.appendChild(textElement("span", "", conversation.title || "New chat"));
      button.addEventListener("click", function () {
        activeId = conversation.id;
        renderConversationList(); renderMessages(); closeSidebar();
      });
      button.addEventListener("contextmenu", function (event) {
        openHistoryContextMenu(event, conversation, button);
      });
      button.addEventListener("keydown", function (event) {
        if (event.key === "ContextMenu" || (event.shiftKey && event.key === "F10")) {
          const bounds = button.getBoundingClientRect();
          openHistoryContextMenu({
            preventDefault: function () {},
            clientX: Math.min(bounds.right - 8, window.innerWidth - 8),
            clientY: Math.min(bounds.bottom, window.innerHeight - 8),
          }, conversation, button);
        }
      });
      elements.conversationList.appendChild(button);
    });
    if (!matches.length && searchTerm) elements.conversationList.appendChild(textElement("div", "empty-search", "No matching chats"));
  }

  function openHistoryContextMenu(event, conversation, anchor) {
    event.preventDefault();
    contextConversationId = conversation.id;
    contextMenuAnchor = anchor;
    const menu = elements.historyContextMenu;
    menu.hidden = false;
    menu.style.left = "0px";
    menu.style.top = "0px";
    const bounds = menu.getBoundingClientRect();
    const left = Math.max(8, Math.min(event.clientX, window.innerWidth - bounds.width - 8));
    const top = Math.max(8, Math.min(event.clientY, window.innerHeight - bounds.height - 8));
    menu.style.left = left + "px";
    menu.style.top = top + "px";
    elements.deleteHistoryButton.focus({ preventScroll: true });
  }

  function closeHistoryContextMenu(restoreFocus) {
    elements.historyContextMenu.hidden = true;
    contextConversationId = null;
    if (restoreFocus && contextMenuAnchor && contextMenuAnchor.isConnected) contextMenuAnchor.focus();
    contextMenuAnchor = null;
  }

  function deleteContextConversation() {
    const conversationId = contextConversationId;
    closeHistoryContextMenu(false);
    const conversation = conversations.find(function (item) { return item.id === conversationId; });
    if (!conversation) return;
    if (!window.confirm("Delete this chat and its saved history? This cannot be undone.")) return;
    conversations = conversations.filter(function (item) { return item.id !== conversationId; });
    if (activeId === conversationId) activeId = null;
    persist();
    renderConversationList();
    renderMessages();
    showToast("Chat deleted.", false);
  }

  function updateMode(nextMode) {
    mode = nextMode === "investigate" ? "investigate" : "chat";
    document.querySelectorAll(".mode-tab").forEach(function (button) {
      const selected = button.dataset.mode === mode;
      button.classList.toggle("active", selected);
      button.setAttribute("aria-selected", selected ? "true" : "false");
    });
    elements.prompt.placeholder = mode === "investigate" ? "Describe the biological claim you want to investigate" : "Ask anything about biology";
    elements.modeHint.textContent = mode === "investigate" ? "Decompose · search papers · assess · identify what's missing" : "Ask biology · search scholarly sources";
    updateModelLabel();
  }

  function setTheme(theme) {
    const next = theme === "dark" ? "dark" : "light";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem(THEME_KEY, next); } catch (_error) { /* Theme still applies for this page view. */ }
    const label = next === "dark" ? "Light appearance" : "Dark appearance";
    byId("themeLabel").textContent = label;
    byId("themeIcon").textContent = next === "dark" ? "☼" : "◐";
    byId("topThemeToggle").textContent = next === "dark" ? "☼" : "◐";
    document.querySelector('meta[name="theme-color"]').content = next === "dark" ? "#212121" : "#ffffff";
  }

  function showToast(message, isError) {
    elements.toast.textContent = message;
    elements.toast.classList.toggle("error", Boolean(isError));
    elements.toast.classList.add("visible");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { elements.toast.classList.remove("visible"); }, 4200);
  }

  function renderFileChips() {
    elements.attachmentList.replaceChildren();
    pendingFiles.forEach(function (file, index) {
      const chip = document.createElement("div"); chip.className = "file-chip";
      chip.appendChild(textElement("span", "", file.name));
      const remove = textElement("button", "", "×"); remove.type = "button"; remove.setAttribute("aria-label", "Remove " + file.name);
      remove.addEventListener("click", function () { pendingFiles.splice(index, 1); renderFileChips(); });
      chip.appendChild(remove); elements.attachmentList.appendChild(chip);
    });
  }

  function queueFiles(fileList) {
    const allowed = [".pdf", ".docx", ".txt", ".md", ".csv"];
    Array.from(fileList || []).forEach(function (file) {
      const suffix = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
      if (!allowed.includes(suffix)) { showToast(file.name + " is not a supported file type.", true); return; }
      if (file.size > MAX_FILE_BYTES) { showToast(file.name + " is larger than the 12 MB limit.", true); return; }
      if (pendingFiles.some(function (item) { return item.name === file.name && item.size === file.size; })) return;
      if (pendingFiles.length >= MAX_FILES) { showToast("Attach up to five files at a time.", true); return; }
      pendingFiles.push(file);
    });
    renderFileChips();
  }

  function loadingMessage(text) {
    const row = document.createElement("article"); row.className = "message-row assistant loading-row";
    row.appendChild(textElement("div", "assistant-mark", "B"));
    const body = document.createElement("div"); body.className = "message-body";
    body.appendChild(textElement("div", "message-author", "BioDetective"));
    const indicator = document.createElement("div"); indicator.className = "thinking-indicator";
    indicator.append(document.createElement("i"), document.createElement("i"), document.createElement("i"), textElement("span", "", text));
    body.appendChild(indicator); row.appendChild(body); elements.messages.appendChild(row);
    elements.messageView.scrollTop = elements.messageView.scrollHeight;
    return row;
  }

  async function readError(response) {
    try { const data = await response.json(); return data.detail || "The request could not be completed."; }
    catch (_error) { return "The request could not be completed."; }
  }

  async function sendMessage() {
    if (busy) return;
    const text = elements.prompt.value.trim();
    if (!text && !pendingFiles.length) return;
    const conversation = currentConversation() || createConversation();
    const userMessage = text || "Please review the attached file and summarize its biological content.";
    const history = conversation.messages.filter(function (item) { return item.role === "user" || item.role === "assistant"; }).slice(-12).map(function (item) {
      return { role: item.role, content: item.content };
    });
    const filesToSend = pendingFiles.slice();
    const requestSettings = Object.assign({}, preferences);
    const fileNames = filesToSend.map(function (file) { return file.name; });
    conversation.messages.push({ role: "user", content: userMessage, mode: mode, files: fileNames });
    if (conversation.messages.length === 1) conversation.title = truncate(userMessage, 54);
    conversation.updated = Date.now();
    activeId = conversation.id;
    elements.prompt.value = ""; resizePrompt();
    pendingFiles = []; renderFileChips();
    busy = true; elements.send.disabled = true;
    renderConversationList(); renderMessages();
    const waiting = loadingMessage(mode === "investigate" ? "Searching papers and mapping evidence" : "Looking across biology sources");
    const form = new FormData();
    form.append("payload", JSON.stringify({ message: userMessage, history: history, settings: requestSettings }));
    filesToSend.forEach(function (file) { form.append("files", file, file.name); });
    try {
      let response;
      if (mode === "investigate") {
        const researchForm = new FormData();
        researchForm.append("claim", userMessage);
        researchForm.append("settings", JSON.stringify(requestSettings));
        filesToSend.forEach(function (file) { researchForm.append("files", file, file.name); });
        response = await fetch("/api/investigate", { method: "POST", body: researchForm });
      } else {
        response = await fetch("/api/chat", { method: "POST", body: form });
      }
      if (!response.ok) throw new Error(await readError(response));
      const data = await response.json();
      waiting.remove();
      conversation.messages.push({
        role: "assistant", content: data.reply || "No response was returned.", citations: data.citations || [],
        investigation: data.investigation || null, files: data.files || [], mode: mode,
      });
      conversation.updated = Date.now();
    } catch (error) {
      waiting.remove();
      conversation.messages.push({ role: "assistant", content: "I couldn’t complete that request. " + (error && error.message ? error.message : "Check your connection and try again."), error: true });
    } finally {
      busy = false; elements.send.disabled = false;
      persist(); renderConversationList(); renderMessages(); elements.prompt.focus();
    }
  }

  function resizePrompt() {
    elements.prompt.style.height = "auto";
    elements.prompt.style.height = Math.min(elements.prompt.scrollHeight, 180) + "px";
  }

  function startNewChat() {
    if (recorder && recorder.state === "recording") stopRecording();
    activeId = null; pendingFiles = []; renderFileChips();
    elements.prompt.value = ""; resizePrompt();
    renderConversationList(); renderMessages(); closeSidebar(); elements.prompt.focus();
  }

  function openSidebar() { elements.sidebar.classList.add("open"); elements.scrim.classList.add("visible"); }
  function closeSidebar() { elements.sidebar.classList.remove("open"); elements.scrim.classList.remove("visible"); }

  function toggleSearch() {
    if (searchInput) { searchInput.focus(); return; }
    searchInput = document.createElement("input");
    searchInput.className = "history-search-input";
    searchInput.type = "search";
    searchInput.placeholder = "Search recent chats";
    searchInput.setAttribute("aria-label", "Search recent chats");
    elements.conversationList.before(searchInput);
    searchInput.addEventListener("input", function () { searchTerm = searchInput.value.trim(); renderConversationList(); });
    searchInput.addEventListener("keydown", function (event) {
      if (event.key === "Escape") { searchInput.remove(); searchInput = null; searchTerm = ""; renderConversationList(); }
    });
    searchInput.focus();
  }

  function showModal() { elements.modal.classList.remove("hidden"); }
  function hideModal() { elements.modal.classList.add("hidden"); }

  async function checkHealth() {
    try {
      const response = await fetch("/api/health");
      const data = await response.json();
      if (data.ai_configured) {
        elements.connectionLabel.textContent = "Gemini key set";
        elements.connectionDot.className = "connection-dot ready";
      } else {
        elements.connectionLabel.textContent = "Gemini setup needed";
        elements.connectionDot.className = "connection-dot error";
      }
      updateModelLabel();
    } catch (_error) {
      elements.connectionLabel.textContent = "Offline";
      elements.connectionDot.className = "connection-dot error";
    }
  }

  async function toggleRecording() {
    if (recorder && recorder.state === "recording") { stopRecording(); return; }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || typeof MediaRecorder === "undefined") {
      showToast("Voice input needs a browser with microphone recording support, such as Chrome or Edge.", true); return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const types = ["audio/webm;codecs=opus", "audio/mp4", "audio/webm", "audio/ogg;codecs=opus"];
      const mime = types.find(function (type) { return MediaRecorder.isTypeSupported(type); });
      recorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
      const chunks = [];
      recorder.addEventListener("dataavailable", function (event) { if (event.data && event.data.size) chunks.push(event.data); });
      recorder.addEventListener("stop", async function () {
        stream.getTracks().forEach(function (track) { track.stop(); });
        clearTimeout(recordingTimer);
        const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
        elements.voice.classList.remove("recording");
        elements.recordingLabel.classList.add("hidden");
        elements.voice.setAttribute("aria-label", "Start voice input");
        if (!blob.size) { showToast("No audio was recorded.", true); return; }
        showToast("Transcribing your question…");
        const ext = blob.type.includes("mp4") ? "mp4" : blob.type.includes("ogg") ? "ogg" : "webm";
        const form = new FormData(); form.append("audio", blob, "voice." + ext);
        try {
          const response = await fetch("/api/transcribe", { method: "POST", body: form });
          if (!response.ok) throw new Error(await readError(response));
          const data = await response.json();
          const current = elements.prompt.value.trim();
          elements.prompt.value = current ? current + " " + data.text : data.text;
          resizePrompt(); elements.prompt.focus(); showToast("Voice input is ready. Review it, then send.");
        } catch (error) { showToast(error.message || "Transcription failed.", true); }
      });
      recorder.start();
      elements.voice.classList.add("recording");
      elements.voice.setAttribute("aria-label", "Stop voice recording");
      elements.recordingLabel.classList.remove("hidden");
      recordingTimer = setTimeout(stopRecording, 45000);
    } catch (error) {
      showToast(error && error.name === "NotAllowedError" ? "Allow microphone access in your browser to use voice input." : "Could not open the microphone.", true);
    }
  }

  function stopRecording() {
    if (recorder && recorder.state === "recording") recorder.stop();
  }

  document.querySelectorAll(".mode-tab").forEach(function (button) { button.addEventListener("click", function () { updateMode(button.dataset.mode); }); });
  document.querySelectorAll(".suggestion-card").forEach(function (button) {
    button.addEventListener("click", function () {
      updateMode(button.dataset.mode);
      elements.prompt.value = button.dataset.prompt || "";
      resizePrompt(); elements.prompt.focus();
    });
  });
  byId("newChatButton").addEventListener("click", startNewChat);
  elements.deleteHistoryButton.addEventListener("click", deleteContextConversation);
  document.addEventListener("click", function (event) {
    if (!elements.historyContextMenu.contains(event.target)) closeHistoryContextMenu(false);
  });
  elements.conversationList.addEventListener("scroll", function () { closeHistoryContextMenu(false); });
  window.addEventListener("resize", function () { closeHistoryContextMenu(false); });
  byId("searchChatsButton").addEventListener("click", toggleSearch);
  byId("themeToggle").addEventListener("click", function () { setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"); });
  byId("topThemeToggle").addEventListener("click", function () { setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"); });
  byId("aboutButton").addEventListener("click", showModal);
  byId("privacyButton").addEventListener("click", showModal);
  byId("settingsButton").addEventListener("click", openSettings);
  byId("settingsTopButton").addEventListener("click", openSettings);
  byId("settingsClose").addEventListener("click", closeSettings);
  byId("settingsSave").addEventListener("click", function () { saveSettings(); });
  byId("settingsReset").addEventListener("click", function () { saveSettings(Object.assign({}, DEFAULT_PREFERENCES)); });
  byId("settingsBackdrop").addEventListener("click", function (event) { if (event.target === byId("settingsBackdrop")) closeSettings(); });
  byId("modalClose").addEventListener("click", hideModal);
  byId("modalDone").addEventListener("click", hideModal);
  elements.modal.addEventListener("click", function (event) { if (event.target === elements.modal) hideModal(); });
  byId("mobileMenu").addEventListener("click", openSidebar);
  byId("sidebarClose").addEventListener("click", closeSidebar);
  elements.scrim.addEventListener("click", closeSidebar);
  byId("attachButton").addEventListener("click", function () { elements.fileInput.click(); });
  elements.fileInput.addEventListener("change", function () { queueFiles(elements.fileInput.files); elements.fileInput.value = ""; });
  elements.voice.addEventListener("click", toggleRecording);
  elements.send.addEventListener("click", sendMessage);
  elements.prompt.addEventListener("input", resizePrompt);
  elements.prompt.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); sendMessage(); }
  });
  document.addEventListener("keydown", function (event) {
    const mod = event.ctrlKey || event.metaKey;
    if (mod && event.key.toLowerCase() === "k") { event.preventDefault(); startNewChat(); }
    if (mod && event.key.toLowerCase() === "j") { event.preventDefault(); toggleSearch(); }
    if (event.key === "Escape") { closeHistoryContextMenu(true); hideModal(); closeSettings(); closeSidebar(); }
  });

  let savedTheme = "light";
  try { savedTheme = localStorage.getItem(THEME_KEY) || "light"; } catch (_error) { /* Keep the default theme. */ }
  setTheme(savedTheme);
  updateModelLabel();
  updateMode("chat");
  renderConversationList();
  renderMessages();
  checkHealth();
}());

