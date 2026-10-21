/* TheInventoryManagementSystem - front-end behaviour (no frameworks) */
document.addEventListener("DOMContentLoaded", function () {
  /* -------------------------------------------------------- FAQ assistant */
  var qetiWidget = document.querySelector("[data-faq-chat]");
  if (qetiWidget) {
    var qetiPanel = qetiWidget.querySelector("[data-chat-panel]");
    var qetiToggle = qetiWidget.querySelector("[data-chat-toggle]");
    var qetiClose = qetiWidget.querySelector("[data-chat-close]");
    var qetiForm = qetiWidget.querySelector("[data-chat-form]");
    var qetiInput = qetiWidget.querySelector("#faq-chat-input");
    var qetiMessages = qetiWidget.querySelector("[data-chat-messages]");
    var qetiSessionList = qetiWidget.querySelector("[data-chat-session-list]");
    var qetiNewChatButton = qetiWidget.querySelector("[data-chat-new]");
    var qetiStorageError = qetiWidget.querySelector("[data-chat-storage-error]");
    var qetiStorageKey = "ims.qeti.chats.v1." + encodeURIComponent(qetiWidget.dataset.user || "guest");
    var qetiSessions = [];
    var qetiActiveSessionId = null;
    var qetiStorageUsable = true;
    var qetiWelcomeMessage = "Hi! I’m Qeti. Ask me how to use the inventory system. Please don’t share passwords or secrets.";

    function addChatMessage(text, type) {
      var message = document.createElement("p");
      message.className = "faq-chat-message faq-chat-" + type;
      message.textContent = text;
      qetiMessages.appendChild(message);
      qetiMessages.scrollTop = qetiMessages.scrollHeight;
      return message;
    }
    function setChatOpen(open) {
      qetiPanel.hidden = !open;
      qetiToggle.setAttribute("aria-expanded", String(open));
      if (open && qetiInput && !qetiInput.disabled) qetiInput.focus();
    }

    function showStorageError(text) {
      qetiStorageError.textContent = text;
      qetiStorageError.hidden = !text;
    }

    function saveSessions() {
      if (!qetiStorageUsable) return;
      try {
        localStorage.setItem(qetiStorageKey, JSON.stringify(qetiSessions));
        showStorageError("");
      } catch (error) {
        qetiStorageUsable = false;
        showStorageError("Qeti cannot save chat history here. Chats will remain only until this page is closed.");
      }
    }

    function requestAnswer(question, sessionId, failedItem) {
      var chatSession = qetiSessions.find(function (item) { return item.id === sessionId; });
      if (!chatSession) return;
      if (failedItem) {
        chatSession.messages = chatSession.messages.filter(function (item) {
          return item !== failedItem;
        });
        saveSessions();
        renderMessages();
      }

      var pending =       qetiActiveSessionId === sessionId
        ? addChatMessage("Thinking...", "answer")
        : null;
      var replyText = "";
      var qetiSendButton = qetiForm.querySelector("button[type='submit']");
      qetiInput.disabled = true;
      qetiSendButton.disabled = true;
      var controller = new AbortController();
      var timedOut = false;
      var requestTimer = window.setTimeout(function () {
        timedOut = true;
        controller.abort();
      }, 70000);

      fetch(qetiWidget.dataset.endpoint, {
        method: "POST",
        credentials: "same-origin",
        signal: controller.signal,
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": qetiWidget.dataset.csrf
        },
        body: JSON.stringify({
          message: question,
          history: chatSession.messages
            .filter(function (item) {
              return !item.failed &&
                (item.role === "user" || item.role === "assistant") &&
                typeof item.text === "string";
            })
            .slice(-20)
            .map(function (item) {
              return { role: item.role, text: item.text };
            })
        })
      }).then(function (response) {
        if (!response.ok) {
          return response.json().then(function (body) {
            throw new Error(body.error || "The assistant could not respond.");
          });
        }
        if (!response.body || !response.body.getReader) {
          throw new Error("This browser cannot display streamed Qeti replies.");
        }
        var reader = response.body.getReader();
        var decoder = new TextDecoder();
        var buffer = "";
        function readNext() {
          return reader.read().then(function (result) {
            buffer += decoder.decode(result.value || new Uint8Array(), {
              stream: !result.done
            });
            var lines = buffer.split("\n");
            buffer = lines.pop();
            lines.forEach(function (line) {
              if (!line.trim()) return;
              var event = JSON.parse(line);
              if (event.error) throw new Error(event.error);
              if (typeof event.text === "string") {
                replyText += event.text;
                if (pending && pending.isConnected) {
                  pending.textContent = replyText;
                  qetiMessages.scrollTop = qetiMessages.scrollHeight;
                }
              }
            });
            if (result.done) {
              if (buffer.trim()) {
                var finalEvent = JSON.parse(buffer);
                if (finalEvent.error) throw new Error(finalEvent.error);
                if (typeof finalEvent.text === "string") replyText += finalEvent.text;
              }
              if (!replyText.trim()) throw new Error("Qeti returned an empty reply. Please try again.");
              return;
            }
            return readNext();
          });
        }
        return readNext();
      }).then(function (body) {
        persistMessage("assistant", replyText.trim(), sessionId);
        if (qetiActiveSessionId === sessionId) renderMessages();
      }).catch(function (error) {
        var errorText = timedOut
          ? "Qeti took too long to respond. Please try again."
          : (error.message || "The assistant is temporarily unavailable.");
        persistMessage("assistant", errorText, sessionId, {
          failed: true,
          question: question,
        });
        if (qetiActiveSessionId === sessionId) renderMessages();
      }).finally(function () {
        window.clearTimeout(requestTimer);
        qetiInput.disabled = false;
        qetiSendButton.disabled = false;
        if (qetiPanel.hidden === false) qetiInput.focus();
      });
    }

    function renderMessages() {
      qetiMessages.textContent = "";
      addChatMessage(qetiWelcomeMessage, "answer");
      var active = qetiSessions.find(function (item) { return item.id === qetiActiveSessionId; });
      if (!active) return;
      active.messages.forEach(function (item) {
        var message = addChatMessage(
          item.text,
          item.role === "user" ? "question" : (item.failed ? "error" : "answer")
        );
        if (item.failed) {
          var retry = document.createElement("button");
          retry.type = "button";
          retry.className = "faq-chat-retry";
          retry.textContent = "Retry";
          retry.addEventListener("click", function () {
            requestAnswer(item.question, active.id, item);
          });
          message.appendChild(retry);
        }
      });
    }

    function renderSessions() {
      qetiSessionList.textContent = "";
      qetiSessions.forEach(function (item) {
        var row = document.createElement("li");
        row.className = "faq-chat-session" + (item.id === qetiActiveSessionId ? " is-active" : "");
        var select = document.createElement("button");
        select.type = "button";
        select.className = "faq-chat-session-select";
        select.textContent = item.title;
        select.setAttribute("aria-current", item.id === qetiActiveSessionId ? "true" : "false");
        select.addEventListener("click", function () {
          qetiActiveSessionId = item.id;
          renderSessions();
          renderMessages();
        });
        var remove = document.createElement("button");
        remove.type = "button";
        remove.className = "faq-chat-session-delete";
        remove.textContent = "Delete";
        remove.setAttribute("aria-label", "Delete chat: " + item.title);
        remove.addEventListener("click", function () {
          customConfirm("Are you sure do you want to delete this session? This cannot be undone.", "Delete")
            .then(function (confirmed) {
              if (!confirmed) return;
              qetiSessions = qetiSessions.filter(function (session) { return session.id !== item.id; });
              if (qetiActiveSessionId === item.id) {
                qetiActiveSessionId = qetiSessions.length ? qetiSessions[0].id : null;
              }
              if (!qetiSessions.length) createSession();
              saveSessions();
              renderSessions();
              renderMessages();
            });
        });
        row.appendChild(select);
        row.appendChild(remove);
        qetiSessionList.appendChild(row);
      });
    }

    function createSession() {
      var id = Date.now().toString(36) + "-" + Math.random().toString(36).slice(2);
      var item = { id: id, title: "New chat", updatedAt: Date.now(), messages: [] };
      qetiSessions.unshift(item);
      qetiActiveSessionId = id;
      saveSessions();
      renderSessions();
      renderMessages();
    }

    function persistMessage(role, text, sessionId, extra) {
      var active = qetiSessions.find(function (item) {
        return item.id === (sessionId || qetiActiveSessionId);
      });
      if (!active) return;
      var message = { role: role, text: text };
      if (extra) Object.keys(extra).forEach(function (key) { message[key] = extra[key]; });
      active.messages.push(message);
      if (role === "user" && active.title === "New chat") {
        active.title = text.length > 32 ? text.slice(0, 29) + "..." : text;
      }
      active.updatedAt = Date.now();
      qetiSessions.sort(function (a, b) { return b.updatedAt - a.updatedAt; });
      saveSessions();
      renderSessions();
    }

    try {
      var savedSessions = JSON.parse(localStorage.getItem(qetiStorageKey) || "[]");
      if (!Array.isArray(savedSessions)) throw new Error("Invalid chat history.");
      qetiSessions = savedSessions.filter(function (item) {
        return item && typeof item.id === "string" &&
          typeof item.title === "string" && Array.isArray(item.messages) &&
          item.messages.every(function (message) {
            return message && (message.role === "user" || message.role === "assistant") &&
              typeof message.text === "string";
          });
      });
    } catch (error) {
      qetiSessions = [];
      qetiStorageUsable = false;
      showStorageError("Qeti could not read saved chats. New chats will remain only until this page is closed.");
    }
    var recoveredUnansweredChat = false;
    qetiSessions.forEach(function (item) {
      var lastMessage = item.messages[item.messages.length - 1];
      if (lastMessage && lastMessage.role === "user") {
        item.messages.push({
          role: "assistant",
          text: "Qeti did not save a reply for this question. Try again.",
          failed: true,
          question: lastMessage.text,
        });
        recoveredUnansweredChat = true;
      }
    });
    if (recoveredUnansweredChat) saveSessions();
    if (qetiSessions.length) {
      qetiSessions.sort(function (a, b) { return (b.updatedAt || 0) - (a.updatedAt || 0); });
      qetiActiveSessionId = qetiSessions[0].id;
    } else {
      createSession();
    }
    renderSessions();
    renderMessages();

    qetiToggle.addEventListener("click", function () {
      setChatOpen(qetiPanel.hidden);
    });
    qetiClose.addEventListener("click", function () {
      setChatOpen(false);
      qetiToggle.focus();
    });
    qetiNewChatButton.addEventListener("click", createSession);
    qetiForm.addEventListener("submit", function (event) {
      event.preventDefault();
      var question = qetiInput.value.trim();
      if (!question) return;
      var requestSessionId = qetiActiveSessionId;
      addChatMessage(question, "question");
      persistMessage("user", question, requestSessionId);
      qetiInput.value = "";
      requestAnswer(question, requestSessionId);
    });
  }

  /* ---------------------------------------------------- flash messages */
  document.querySelectorAll(".flash-x").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var flash = btn.closest(".flash");
      if (flash) flash.remove();
    });
  });

  /* ---------------------------------------------------- custom confirm modal */
  /* In-page confirmation instead of window.confirm(): a suppressed or blocked
     native dialog silently cancels the action. Returns a Promise that resolves
     true when the user confirms. Shared by every page. */
  function customConfirm(message, okLabel) {
    return new Promise(function (resolve) {
      var overlay = document.createElement("div");
      overlay.className = "confirm-overlay";
      var box = document.createElement("div");
      box.className = "confirm-box";
      var text = document.createElement("div");
      text.textContent = message || "Are you sure?";
      var actions = document.createElement("div");
      actions.className = "confirm-actions";
      var cancel = document.createElement("button");
      cancel.className = "btn btn-ghost btn-sm";
      cancel.type = "button";
      cancel.textContent = "Cancel";
      var ok = document.createElement("button");
      ok.className = "btn btn-danger btn-sm";
      ok.type = "button";
      ok.textContent = okLabel || "Delete";
      actions.appendChild(cancel);
      actions.appendChild(ok);
      box.appendChild(text);
      box.appendChild(actions);
      overlay.appendChild(box);
      document.body.appendChild(overlay);

      function cleanup(result) {
        if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
        document.removeEventListener("keydown", escHandler);
        resolve(result);
      }
      cancel.addEventListener("click", function () { cleanup(false); });
      ok.addEventListener("click", function () { cleanup(true); });
      overlay.addEventListener("click", function (e) {
        if (e.target === overlay) cleanup(false);
      });
      var escHandler = function (e) {
        if (e.key === "Escape") cleanup(false);
      };
      document.addEventListener("keydown", escHandler);
      ok.focus();
    });
  }

  /* Send a form the way the clicked button would have, without re-entering the
     submit event and without letting HTML5 validation block the request. */
  function submitAction(button) {
    var target = button.form;
    if (!target) return false;
    var marker = document.createElement("input");
    marker.type = "hidden";
    marker.name = button.name || "action";
    marker.value = button.value == null ? "" : button.value;
    target.appendChild(marker);
    target.noValidate = true;
    target.submit();
    return true;
  }

  /* ---------------------------------------------------- confirmations */
  document.querySelectorAll("[data-confirm]").forEach(function (el) {
    el.addEventListener("click", function (event) {
      event.preventDefault();
      var isDelete = el.value === "delete" || /delete/i.test(el.getAttribute("data-confirm"));
      customConfirm(el.getAttribute("data-confirm"), isDelete ? "Delete" : "Confirm")
        .then(function (ok) {
          if (ok) submitAction(el);
        });
    });
  });

  /* ---------------------------------------------------- equipment form */
  var form = document.getElementById("equipment-form");
  if (form) {
    var idField = form.querySelector("#f-id");
    var chip = document.getElementById("edit-chip");
    var deleteBtn = document.getElementById("btn-delete");
    var newBtn = document.getElementById("btn-new");
    var closeBtn = document.getElementById("btn-close");
    var drawer = document.getElementById("form-drawer");
    var more = form.querySelector("details.more");

    /* The confirm dialog lives at the top of this file (shared by all pages). */

    function openDrawer() {
      if (drawer) drawer.hidden = false;
    }

    function closeDrawer() {
      if (drawer) drawer.hidden = true;
    }

    var FIELDS = ["model", "brand", "assigned_to", "warranty_expiry", "asset_tag",
                  "category", "serial_no", "location", "status", "condition",
                  "purchase_date", "notes"];

    function dataAttr(field) {
      return "data-" + field.replace(/_/g, "-");
    }

    function enterEdit(row) {
      openDrawer();
      FIELDS.forEach(function (field) {
        var input = form.querySelector('[name="' + field + '"]');
        if (input) input.value = row.getAttribute(dataAttr(field)) || "";
      });
      idField.value = row.getAttribute("data-id") || "";
      if (chip) {
        chip.hidden = false;
        chip.textContent = "Editing " + (row.getAttribute("data-asset-tag") || "record");
      }
      if (deleteBtn) deleteBtn.disabled = false;
      if (more && (row.getAttribute("data-category") || row.getAttribute("data-notes") ||
                   row.getAttribute("data-serial-no"))) {
        more.open = true;
      }
      document.querySelectorAll("[data-equipment-row]").forEach(function (r) {
        r.classList.remove("row-active");
      });
      row.classList.add("row-active");
      if (window.innerWidth > 980) {
        form.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
    }

    function resetForm(skipFocus) {
      form.reset();
      idField.value = "";
      if (chip) chip.hidden = true;
      if (deleteBtn) deleteBtn.disabled = true;
      document.querySelectorAll("[data-equipment-row]").forEach(function (r) {
        r.classList.remove("row-active");
      });
      var model = form.querySelector('[name="model"]');
      if (model && !skipFocus) model.focus();
    }

    document.querySelectorAll("[data-edit]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        enterEdit(btn.closest("[data-equipment-row]"));
      });
    });
    document.querySelectorAll(".row-marker").forEach(function (btn) {
      btn.addEventListener("click", function () {
        enterEdit(btn.closest("[data-equipment-row]"));
      });
    });
    /* A row-level delete (trash icon) must bypass the form's HTML5 validation:
       Model is required, and the form is never filled in for that path, so a
       plain button click is blocked by the browser and the request would never
       leave the page. form.submit() skips validation and the submit event, so
       the delete request always goes out. */
    function submitDelete() {
      var marker = form.querySelector('input[name="action"][value="delete"]');
      if (!marker) {
        marker = document.createElement("input");
        marker.type = "hidden";
        marker.name = "action";
        marker.value = "delete";
        form.appendChild(marker);
      }
      form.noValidate = true;
      form.submit();
    }

    function askThenDelete() {
      customConfirm("Delete this equipment record? This cannot be undone.").then(function (ok) {
        if (ok) submitDelete();
      });
    }

    document.querySelectorAll("[data-quick-delete]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var row = btn.closest("[data-equipment-row]");
        if (!row) return;
        idField.value = row.getAttribute("data-id") || "";
        if (deleteBtn) deleteBtn.disabled = false;
        askThenDelete();
      });
    });

    if (newBtn) newBtn.addEventListener("click", function () {
      openDrawer();
      resetForm();
    });
    if (closeBtn) closeBtn.addEventListener("click", function () {
      resetForm(true);
      closeDrawer();
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && drawer && !drawer.hidden) {
        resetForm(true);
        closeDrawer();
      }
    });

    form.addEventListener("submit", function (event) {
      var submitter = event.submitter || null;
      var fAction = form.querySelector("#f-action");
      var deleting = submitter ? submitter.value === "delete"
                               : !!(fAction && fAction.value === "delete");
      if (deleting) {
        /* Stop the browser's own submit first, then send the delete ourselves
           once the confirmation is answered. An async handler that awaited the
           confirm let the raw, unconfirmed submit through. */
        event.preventDefault();
        askThenDelete();
        return;
      }
      var modelInput = form.querySelector('[name="model"]');
      if (modelInput && !modelInput.value.trim()) {
        window.alert("MODEL is required.");
        event.preventDefault();
      }
    });
  }

  /* ---------------------------------------------------- borrow form dates */
  /* The server already fills these in PHT (today / +7); this stays as a
     fallback for browsers using a different local timezone. */
  function philippineISO(d) {
    var parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Manila",
      year: "numeric",
      month: "2-digit",
      day: "2-digit"
    }).formatToParts(d);
    var values = {};
    parts.forEach(function (part) {
      if (part.type !== "literal") values[part.type] = part.value;
    });
    return values.year + "-" + values.month + "-" + values.day;
  }
  function addDaysISO(value, days) {
    var parts = value.split("-").map(Number);
    var d = new Date(Date.UTC(parts[0], parts[1] - 1, parts[2] + days));
    return d.toISOString().slice(0, 10);
  }
  var borrowForm = document.getElementById("borrow-form");
  if (borrowForm) {
    var borrowed = borrowForm.querySelector('[name="borrowed_date"]');
    var due = borrowForm.querySelector('[name="due_date"]');
    if (borrowed && !borrowed.value) {
      borrowed.value = philippineISO(new Date());
    }
    if (due && !due.value && borrowed.value) {
      due.value = addDaysISO(borrowed.value, 7);
    }
    /* Row-level deletes on this page (data-confirm) are handled by the shared
       confirm dialog at the top of this file. */
  }

  /* ---------------------------------------------------- location cards */
  /* Opening one location shows only that location's devices: every other card
     closes, so two tables can never be on screen at the same time. */
  var locCards = document.querySelectorAll(".loc-grid .loc-card");
  if (locCards.length) {
    locCards.forEach(function (card) {
      card.addEventListener("toggle", function () {
        if (!card.open) return;
        locCards.forEach(function (other) {
          if (other !== card && other.open) other.open = false;
        });
      });
    });
  }

  /* ------------------------------ borrow + maintenance form open and close */
  /* Same drawer behaviour as the equipment page: the toolbar button opens the
     form, the X (or Escape) closes it. The equipment page has its own block
     above, so this one only runs on the pages that use borrow/maintenance. */
  (function () {
    var panel = document.getElementById("borrow-form") ||
                document.getElementById("maintenance-form");
    var drawer = document.getElementById("form-drawer");
    if (!panel || !drawer || !drawer.contains(panel)) return;

    var openBtn = document.getElementById("btn-new");
    var closeBtn = document.getElementById("btn-close");

    function closeDrawer() {
      panel.reset();
      drawer.hidden = true;
    }

    if (openBtn) {
      openBtn.addEventListener("click", function () {
        drawer.hidden = false;
        var first = panel.querySelector("select, input:not([type=hidden]), textarea");
        if (first) first.focus();
      });
    }
    if (closeBtn) closeBtn.addEventListener("click", closeDrawer);
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && !drawer.hidden) closeDrawer();
    });

    panel.addEventListener("submit", async function (event) {
      var submitter = event.submitter || null;
      var deleting = submitter ? submitter.value === "delete" : false;
      if (deleting) {
        var ok = await customConfirm("Delete this record? This cannot be undone.");
        if (!ok) {
          event.preventDefault();
          return;
        }
      }
    });
  })();

  /* --------------------------------------------------- about poster auto-fit */
  /* The About page is a fixed-format poster: on a short window (a small laptop
     screen) the last credits and the footer used to fall below the fold. Scale
     the whole card down until it fits the space under the top bar, using CSS
     zoom so the layout box shrinks too and the page stops scrolling. Runs only
     on the About page - every other page keeps its normal size. */
  (function () {
    var page = document.querySelector(".about-page");
    if (!page) return;
    if (!window.CSS || !CSS.supports("zoom", "0.9")) return;

    var MIN = 0.62;   /* below this it would be unreadable - scroll instead */
    var timer = null;

    function fit() {
      page.style.zoom = "";
      var rect = page.getBoundingClientRect();
      var parent = page.parentElement;
      var pad = parent ? (parseFloat(getComputedStyle(parent).paddingBottom) || 0) : 0;
      var room = window.innerHeight - rect.top - pad;
      if (room <= 0 || !rect.height) return;
      var scale = Math.min(1, room / rect.height);
      if (scale < MIN) scale = MIN;
      if (scale < 0.995) page.style.zoom = String(Math.round(scale * 1000) / 1000);
    }

    fit();
    window.addEventListener("resize", function () {
      clearTimeout(timer);
      timer = setTimeout(fit, 120);
    });
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(fit);
  })();

  /* ------------------------------------------------- report preview mode */
  /* "Print Report" previews the whole report in place - the page keeps its
     state and nothing navigates. preview-mode hides the app chrome, shows the
     report bar (Save as PDF / Print / Close preview) and a report header, so
     the screen matches what prints. Escape leaves the preview. */
  (function () {
    var opener = document.querySelector('[data-report-open]');
    if (!opener) return;
    var bar = document.querySelector('[data-report-bar]');

    function enter() {
      document.body.classList.add('preview-mode');
      window.scrollTo(0, 0);
      if (bar) bar.focus({ preventScroll: true });
    }
    function exit() {
      document.body.classList.remove('preview-mode');
    }

    opener.addEventListener('click', function (e) {
      e.preventDefault();
      enter();
    });
    Array.prototype.forEach.call(
      document.querySelectorAll('[data-report-close]'),
      function (el) { el.addEventListener('click', exit); });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') exit();
    });
    var print = document.querySelector('[data-report-print]');
    if (print) {
      print.addEventListener('click', function () { window.print(); });
    }
  })();

  /* ------------------------------------ save the PDF: paper, then destination
     "Save as PDF" (a plain link to /report.pdf) runs two steps in the user's
     order: first an in-page picker for the sheet - paper size *and* the way
     round it goes ("add options of any paper size before saving", then "add
     options of Portrait and Landscape") - and only then the save destination
     dialog, so the file is laid out for the sheet they picked. The choices
     travel as ?paper=<key>&orientation=<portrait|landscape> and the server
     scales the whole report to them (PAPER_SIZES/ORIENTATIONS in
     backend/report_pdf.py - keep the keys in step with PAPERS below).

     The destination step needs Chromium's File System Access API: the PDF is
     fetched and the bytes written to the handle from a real OS save dialog
     (folder + file name). Everywhere else - Firefox, Safari, phones, a
     non-secure origin such as http://192.168.x.x, or a cancelled/refused
     dialog - the chooser still runs and the plain download then carries the
     same ?paper= choice, so the picked sheet is honoured either way. */
  (function () {
    var link = document.querySelector('[data-report-pdf]');
    if (!link) return;

    /* The sheets offered before saving. First entry is the default (landscape
       A4, the size the report is designed on). */
    var PAPERS = [
      ['a4', 'A4', '210 x 297 mm (Default)'],
      ['letter', 'Letter', '8.5 x 11 in'],
      ['legal', 'Legal', '8.5 x 14 in'],
      ['a3', 'A3', '297 x 420 mm'],
      ['tabloid', 'Tabloid', '11 x 17 in'],
      ['a5', 'A5', '148 x 210 mm'],
    ];

    /* Which way round the sheet goes. Landscape is the default (the report is
       designed on a landscape A4 sheet); the values are the ORIENTATIONS keys
       in backend/report_pdf.py. */
    var ORIENTATIONS = [
      ['portrait', 'Portrait', 'Tall'],
      ['landscape', 'Landscape', 'Wide (Default)'],
    ];

    function el(tag, className, text) {
      var node = document.createElement(tag);
      if (className) node.className = className;
      if (text != null) node.textContent = text;
      return node;
    }

    /* One radio + name + note row, shared by both groups. */
    function option(group, value, name, note, checked, radios) {
      var radio = document.createElement('input');
      radio.type = 'radio';
      radio.name = group;
      radio.value = value;
      radio.checked = checked;
      radios.push(radio);
      var label = el('label', 'paper-option');
      label.appendChild(radio);
      label.appendChild(el('span', 'paper-name', name));
      if (note) label.appendChild(el('span', 'paper-dim', note));
      return label;
    }

    /* Step 1 - the sheet: paper size, then orientation. Resolves with
       {paper, orientation}, or null when the user cancels (Cancel, Escape, or
       a click outside the box). */
    function pickPaper() {
      return new Promise(function (resolve) {
        var overlay = el('div', 'confirm-overlay');
        overlay.setAttribute('role', 'dialog');
        overlay.setAttribute('aria-label', 'Paper size and orientation');
        var box = el('div', 'paper-box');
        var title = el('div', 'paper-title', 'Paper size');
        var hint = el('div', 'paper-hint',
          'Choose the PDF paper size, then select where to save it');

        var list = el('div', 'paper-list');
        var radios = [];
        var orientRadios = [];
        var done = false;

        function finish(value) {
          if (done) return;          // Cancel + Escape + backdrop must not fire twice
          done = true;
          document.removeEventListener('keydown', onKey);
          overlay.remove();
          resolve(value);
        }
        function picked(from, fallback) {
          for (var i = 0; i < from.length; i++) {
            if (from[i].checked) return from[i].value;
          }
          return fallback;
        }
        function onKey(e) {
          if (e.key === 'Escape') { e.preventDefault(); finish(null); }
        }

        PAPERS.forEach(function (paper, i) {
          // landscape A4 is the default
          list.appendChild(
            option('report-paper', paper[0], paper[1], paper[2], i === 0, radios));
        });

        var sub = el('div', 'paper-sub', 'Orientation');
        var orient = el('div', 'paper-orient');
        ORIENTATIONS.forEach(function (o) {
          orient.appendChild(option('report-orient', o[0], o[1], o[2],
            o[0] === 'landscape', orientRadios));
        });

        var actions = el('div', 'paper-actions');
        var cancel = el('button', 'btn btn-ghost btn-sm', 'Cancel');
        cancel.type = 'button';
        var save = el('button', 'btn btn-solid btn-sm', 'Save as PDF');
        save.type = 'button';
        cancel.addEventListener('click', function () { finish(null); });
        save.addEventListener('click', function () {
          finish({ paper: picked(radios, PAPERS[0][0]),
                   orientation: picked(orientRadios, 'landscape') });
        });
        actions.appendChild(cancel);
        actions.appendChild(save);

        box.appendChild(title);
        box.appendChild(hint);
        box.appendChild(list);
        box.appendChild(sub);
        box.appendChild(orient);
        box.appendChild(actions);
        overlay.appendChild(box);
        overlay.addEventListener('click', function (e) {
          if (e.target === overlay) finish(null);
        });
        document.addEventListener('keydown', onKey);
        document.body.appendChild(overlay);
        radios[0].focus({ preventScroll: true });
      });
    }

    /* Step 2a - no File System Access API: an ordinary download, still carrying
       the paper the user just picked. */
    function download(url) {
      var a = document.createElement('a');
      a.href = url;
      document.body.appendChild(a);
      a.click();
      a.remove();
    }

    /* Step 2b - the OS save dialog (folder + file name), then the bytes. */
    function save(url) {
      var name = 'inventory-report.pdf';
      fetch(url, { credentials: 'same-origin' })
        .then(function (res) {
          if (!res.ok) throw new Error('HTTP ' + res.status);
          var cd = res.headers.get('Content-Disposition') || '';
          var m = /filename\*?=(?:UTF-8''|")?([^";]+)/i.exec(cd);
          if (m) {
            try { name = decodeURIComponent(m[1].replace(/"/g, '')); }
            catch (err) { /* keep the default name */ }
          }
          return res.blob();
        })
        .then(function (blob) {
          return window
            .showSaveFilePicker({
              suggestedName: name,
              types: [{ description: 'PDF document', accept: { 'application/pdf': ['.pdf'] } }],
            })
            .then(function (handle) { return handle.createWritable(); })
            .then(function (writable) {
              return writable.write(blob).then(function () { return writable.close(); });
            });
        })
        .catch(function (err) {
          if (err && err.name === 'AbortError') return;  // user closed the dialog
          download(url);                                 // API refused - plain download
        });
    }

    link.addEventListener('click', function (e) {
      e.preventDefault();
      pickPaper().then(function (sheet) {
        if (!sheet) return;                            // cancelled: save nothing
        var url = link.href + (link.href.indexOf('?') < 0 ? '?' : '&') +
          'paper=' + encodeURIComponent(sheet.paper) +
          '&orientation=' + encodeURIComponent(sheet.orientation);
        if (typeof window.showSaveFilePicker !== 'function') download(url);
        else save(url);
      });
    });
  })();
});
