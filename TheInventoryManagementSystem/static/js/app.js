/* TheInventoryManagementSystem - front-end behaviour (no frameworks) */
document.addEventListener("DOMContentLoaded", function () {
  /* ---------------------------------------------------- flash messages */
  document.querySelectorAll(".flash-x").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var flash = btn.closest(".flash");
      if (flash) flash.remove();
    });
  });

  /* ---------------------------------------------------- confirmations */
  document.querySelectorAll("[data-confirm]").forEach(function (el) {
    el.addEventListener("click", function (event) {
      if (!window.confirm(el.getAttribute("data-confirm"))) {
        event.preventDefault();
      }
    });
  });

  /* ---------------------------------------------------- equipment form */
  var form = document.getElementById("equipment-form");
  if (form) {
    var idField = form.querySelector("#f-id");
    var chip = document.getElementById("edit-chip");
    var deleteBtn = document.getElementById("btn-delete");
    var cancelBtn = document.getElementById("btn-cancel");
    var newBtn = document.getElementById("btn-new");
    var more = form.querySelector("details.more");
    var skipConfirm = false;

    var FIELDS = ["model", "brand", "assigned_to", "warranty_expiry", "asset_tag",
                  "category", "serial_no", "location", "status", "condition",
                  "purchase_date", "notes"];

    function dataAttr(field) {
      return "data-" + field.replace(/_/g, "-");
    }

    function enterEdit(row) {
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
      if (cancelBtn) cancelBtn.hidden = false;
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

    function resetForm() {
      form.reset();
      idField.value = "";
      if (chip) chip.hidden = true;
      if (deleteBtn) deleteBtn.disabled = true;
      if (cancelBtn) cancelBtn.hidden = true;
      document.querySelectorAll("[data-equipment-row]").forEach(function (r) {
        r.classList.remove("row-active");
      });
      var model = form.querySelector('[name="model"]');
      if (model) model.focus();
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
    document.querySelectorAll("[data-quick-delete]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        if (!window.confirm("Delete this equipment record? This cannot be undone.")) return;
        var row = btn.closest("[data-equipment-row]");
        idField.value = row.getAttribute("data-id") || "";
        if (deleteBtn) {
          deleteBtn.disabled = false;
          skipConfirm = true;
          deleteBtn.click();
        } else {
          form.submit();
        }
      });
    });

    if (newBtn) newBtn.addEventListener("click", resetForm);
    if (cancelBtn) cancelBtn.addEventListener("click", resetForm);

    form.addEventListener("submit", function (event) {
      var submitter = event.submitter || null;
      var deleting = submitter ? submitter.value === "delete"
                               : form.querySelector("#f-action").value === "delete";
      if (deleting && !skipConfirm) {
        if (!window.confirm("Delete this equipment record? This cannot be undone.")) {
          event.preventDefault();
          return;
        }
      }
      skipConfirm = false;
      if (!deleting) {
        var modelInput = form.querySelector('[name="model"]');
        if (modelInput && !modelInput.value.trim()) {
          window.alert("MODEL is required.");
          event.preventDefault();
        }
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
  }
});
