/* TheInventoryManagementSystem - front-end behaviour (no frameworks) */
document.addEventListener("DOMContentLoaded", function () {
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
  var borrowForm = document.getElementById("borrow-form");
  if (borrowForm) {
    var borrowed = borrowForm.querySelector('[name="borrowed_date"]');
    var due = borrowForm.querySelector('[name="due_date"]');
    if (borrowed && !borrowed.value) {
      borrowed.value = new Date().toISOString().slice(0, 10);
    }
    if (due && !due.value && borrowed.value) {
      var plusWeek = new Date(borrowed.value + "T00:00:00");
      plusWeek.setDate(plusWeek.getDate() + 7);
      due.value = plusWeek.toISOString().slice(0, 10);
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
});
