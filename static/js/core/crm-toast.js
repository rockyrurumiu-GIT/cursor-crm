/**
 * CRM lightweight toast notifications.
 * No external UI library dependency.
 */
(function () {
  "use strict";

  var CONTAINER_ID = "crm-toast-container";
  var DEFAULT_DURATION = 3000;

  function getContainer() {
    var c = document.getElementById(CONTAINER_ID);
    if (!c) {
      c = document.createElement("div");
      c.id = CONTAINER_ID;
      c.style.cssText =
        "position:fixed;top:20px;right:20px;z-index:99999;display:flex;flex-direction:column;gap:8px;pointer-events:none;";
      document.body.appendChild(c);
    }
    return c;
  }

  function createToast(message, type) {
    var el = document.createElement("div");
    el.style.cssText =
      "padding:10px 18px;border-radius:6px;font-size:14px;line-height:1.5;" +
      "box-shadow:0 4px 12px rgba(0,0,0,.15);pointer-events:auto;" +
      "opacity:0;transition:opacity .25s ease;max-width:360px;word-break:break-word;";

    switch (type) {
      case "success":
        el.style.background = "#f0fdf4";
        el.style.color = "#166534";
        el.style.border = "1px solid #bbf7d0";
        break;
      case "error":
        el.style.background = "#fef2f2";
        el.style.color = "#991b1b";
        el.style.border = "1px solid #fecaca";
        break;
      case "warning":
        el.style.background = "#fffbeb";
        el.style.color = "#92400e";
        el.style.border = "1px solid #fde68a";
        break;
      default:
        el.style.background = "#f8fafc";
        el.style.color = "#1e293b";
        el.style.border = "1px solid #e2e8f0";
    }

    el.textContent = message;
    return el;
  }

  /**
   * Show a toast message.
   * @param {string} message
   * @param {object} [opts] - { type: "success"|"error"|"warning"|"info", duration: ms }
   */
  function show(message, opts) {
    opts = opts || {};
    var type = opts.type || "info";
    var duration = opts.duration != null ? opts.duration : DEFAULT_DURATION;

    var container = getContainer();
    var el = createToast(message, type);
    container.appendChild(el);

    requestAnimationFrame(function () {
      el.style.opacity = "1";
    });

    if (duration > 0) {
      setTimeout(function () {
        dismiss(el);
      }, duration);
    }

    return el;
  }

  function dismiss(el) {
    el.style.opacity = "0";
    setTimeout(function () {
      if (el.parentNode) {
        el.parentNode.removeChild(el);
      }
    }, 300);
  }

  function success(msg, opts) {
    return show(msg, Object.assign({ type: "success" }, opts));
  }
  function error(msg, opts) {
    return show(msg, Object.assign({ type: "error" }, opts));
  }
  function warning(msg, opts) {
    return show(msg, Object.assign({ type: "warning" }, opts));
  }
  function info(msg, opts) {
    return show(msg, Object.assign({ type: "info" }, opts));
  }

  window.crmToast = {
    show: show,
    success: success,
    error: error,
    warning: warning,
    info: info,
    dismiss: dismiss,
  };
})();
