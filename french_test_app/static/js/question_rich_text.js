/* Visual rich-text editor + toggleable French guillemets for teacher forms. */
(function () {
  function makeToolbar(actions) {
    var bar = document.createElement("div");
    bar.className = "rich-text-toolbar";
    bar.setAttribute("role", "toolbar");
    bar.setAttribute("aria-label", "Mise en forme");
    actions.forEach(function (item) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "rich-text-toolbar__btn";
      btn.title = item.title;
      btn.setAttribute("aria-label", item.title);
      btn.innerHTML = item.label;
      btn.addEventListener("click", function (event) {
        event.preventDefault();
        item.run();
      });
      bar.appendChild(btn);
    });
    return bar;
  }

  function normalizeEditorHtml(html) {
    var tmp = document.createElement("div");
    tmp.innerHTML = html || "";
    Array.prototype.slice.call(tmp.querySelectorAll("div, p")).forEach(function (block) {
      var br = document.createElement("br");
      block.parentNode.insertBefore(br, block);
      while (block.firstChild) {
        block.parentNode.insertBefore(block.firstChild, block);
      }
      block.remove();
    });
    Array.prototype.slice
      .call(tmp.querySelectorAll("b, i, em, strong, span"))
      .forEach(function (el) {
        if (!el.textContent || !el.textContent.trim()) {
          el.remove();
          return;
        }
        if (el.tagName === "STRONG") {
          var bold = document.createElement("b");
          while (el.firstChild) bold.appendChild(el.firstChild);
          el.replaceWith(bold);
          return;
        }
        if (el.tagName === "EM") {
          var italic = document.createElement("i");
          while (el.firstChild) italic.appendChild(el.firstChild);
          el.replaceWith(italic);
          return;
        }
        if (el.tagName === "SPAN") {
          while (el.firstChild) el.parentNode.insertBefore(el.firstChild, el);
          el.remove();
        }
      });
    return tmp.innerHTML
      .replace(/^(<br\s*\/?>)+|(<br\s*\/?>)+$/gi, "")
      .replace(/(<br\s*\/?>\s*){3,}/gi, "<br><br>");
  }

  function placeCaretInNode(node, offset) {
    var selection = window.getSelection();
    if (!selection) return;
    var range = document.createRange();
    range.setStart(node, offset);
    range.collapse(true);
    selection.removeAllRanges();
    selection.addRange(range);
  }

  function stripOuterGuillemets(text) {
    var match = String(text || "").match(/^«\s*([\s\S]*?)\s*»$/);
    return match ? match[1] : null;
  }

  function replaceRangeWithText(range, text) {
    range.deleteContents();
    var node = document.createTextNode(text);
    range.insertNode(node);
    return node;
  }

  function unwrapGuillemetsInTextNode(textNode, caretOffset) {
    var text = textNode.data;
    var open = text.lastIndexOf("«", Math.max(0, caretOffset - 1));
    if (open < 0) return false;
    var close = text.indexOf("»", caretOffset);
    if (close < 0) return false;
    var chunk = text.slice(open, close + 1);
    var inner = stripOuterGuillemets(chunk);
    if (inner === null) return false;
    textNode.data = text.slice(0, open) + inner + text.slice(close + 1);
    placeCaretInNode(textNode, open + inner.length);
    return true;
  }

  function applyGuillemets(editor) {
    editor.focus();
    var selection = window.getSelection();
    if (!selection || !selection.rangeCount) {
      var fallback = document.createTextNode("«  »");
      editor.appendChild(fallback);
      placeCaretInNode(fallback, 2);
      return;
    }
    var range = selection.getRangeAt(0);
    if (!editor.contains(range.commonAncestorContainer)) {
      var outside = document.createTextNode("«  »");
      editor.appendChild(outside);
      placeCaretInNode(outside, 2);
      return;
    }

    if (!selection.isCollapsed) {
      var selected = selection.toString();
      var unwrapped = stripOuterGuillemets(selected.trim());
      if (unwrapped !== null) {
        // Toggle off: « mot » → mot
        var kept = replaceRangeWithText(range, unwrapped);
        placeCaretInNode(kept, unwrapped.length);
        return;
      }
      // Toggle on: keep formatting inside the selection.
      var contents = range.extractContents();
      var open = document.createTextNode("« ");
      var close = document.createTextNode(" »");
      var frag = document.createDocumentFragment();
      frag.appendChild(open);
      frag.appendChild(contents);
      frag.appendChild(close);
      range.insertNode(frag);
      var endRange = document.createRange();
      endRange.setStartAfter(close);
      endRange.collapse(true);
      selection.removeAllRanges();
      selection.addRange(endRange);
      return;
    }

    // Collapsed caret: unwrap surrounding « … » if present, else insert empty pair.
    var node = range.startContainer;
    if (node.nodeType === Node.TEXT_NODE && unwrapGuillemetsInTextNode(node, range.startOffset)) {
      return;
    }
    var empty = document.createTextNode("«  »");
    range.insertNode(empty);
    placeCaretInNode(empty, 2);
  }

  function attachVisualEditor(textarea, opts) {
    if (!textarea || textarea.dataset.richEditor === "1") return;
    opts = opts || {};
    textarea.dataset.richEditor = "1";
    textarea.classList.add("rich-text-source");
    textarea.setAttribute("tabindex", "-1");
    textarea.setAttribute("aria-hidden", "true");

    var form = textarea.form;
    var editor = document.createElement("div");
    editor.className =
      "rich-text-editor form-control" + (opts.compact ? " rich-text-editor--compact" : "");
    editor.contentEditable = "true";
    editor.setAttribute("role", "textbox");
    editor.setAttribute("aria-multiline", "true");
    editor.setAttribute("aria-label", opts.label || "Texte");
    editor.innerHTML = textarea.value || "";

    function sync() {
      textarea.value = normalizeEditorHtml(editor.innerHTML);
    }

    var bar = makeToolbar([
      {
        label: "<strong>G</strong>",
        title: "Gras",
        run: function () {
          editor.focus();
          document.execCommand("bold", false, null);
          sync();
        },
      },
      {
        label: "<em>I</em>",
        title: "Italique",
        run: function () {
          editor.focus();
          document.execCommand("italic", false, null);
          sync();
        },
      },
      {
        label: "« »",
        title: "Guillemets français (ajouter / retirer)",
        run: function () {
          applyGuillemets(editor);
          sync();
        },
      },
    ]);

    editor.addEventListener("input", sync);
    editor.addEventListener("blur", sync);
    if (form) form.addEventListener("submit", sync);

    textarea.parentNode.insertBefore(bar, textarea);
    textarea.parentNode.insertBefore(editor, textarea);
    sync();
  }

  function initQuestionRichText(root) {
    var scope = root || document;
    var questionText = scope.querySelector("#id_question_text");
    if (!questionText) return;
    attachVisualEditor(questionText, { label: "Énoncé de la question" });
    [
      ["#id_option_1", "Option 1", true],
      ["#id_option_2", "Option 2", true],
      ["#id_option_3", "Option 3", true],
      ["#id_option_4", "Option 4", true],
      ["#id_option_a", "Option A", true],
      ["#id_option_t", "Option T", true],
      ["#id_explanation", "Explication", false],
      ["#id_reference_text", "Texte de référence", false],
    ].forEach(function (item) {
      var field = scope.querySelector(item[0]);
      if (field) {
        attachVisualEditor(field, { label: item[1], compact: item[2] });
      }
    });
  }

  window.initQuestionRichText = initQuestionRichText;
  document.addEventListener("DOMContentLoaded", function () {
    initQuestionRichText(document);
  });
})();
