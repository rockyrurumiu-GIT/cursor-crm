/**
 * CRM lightweight toast notifications.
 * No external UI library dependency.
 */
(function () {
  "use strict";

  var CONTAINER_ID = "crm-toast-container";
  var CONTAINER_ID_BR = "crm-toast-container-br";
  var DEFAULT_DURATION = 3000;

  function getContainer(opts) {
    opts = opts || {};
    var placement = opts.placement || "top-right";
    var id = placement === "bottom-right" ? CONTAINER_ID_BR : CONTAINER_ID;
    var c = document.getElementById(id);
    if (!c) {
      c = document.createElement("div");
      c.id = id;
      if (placement === "bottom-right") {
        c.style.cssText =
          "position:fixed;bottom:24px;right:24px;z-index:99999;display:flex;flex-direction:column-reverse;gap:10px;pointer-events:none;max-width:min(92vw,360px);";
      } else {
        c.style.cssText =
          "position:fixed;top:20px;right:20px;z-index:99999;display:flex;flex-direction:column;gap:8px;pointer-events:none;";
      }
      document.body.appendChild(c);
    }
    return c;
  }

  function successIcon() {
    var icon = document.createElement("span");
    icon.setAttribute("aria-hidden", "true");
    icon.style.cssText =
      "display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;width:20px;height:20px;border-radius:9999px;background:#22c55e;color:#fff;font-size:12px;font-weight:700;line-height:1;";
    icon.textContent = "✓";
    return icon;
  }

  function createToast(message, type, opts) {
    opts = opts || {};
    var el = document.createElement("div");
    var bottomRight = opts.placement === "bottom-right";
    var useIcon = !!opts.icon;

    if (bottomRight && type === "success" && useIcon) {
      el.style.cssText =
        "display:flex;align-items:center;gap:10px;padding:12px 16px;border-radius:10px;font-size:14px;line-height:1.5;" +
        "background:#ffffff;color:#24292f;border:1px solid #e5e7eb;" +
        "box-shadow:0 10px 24px rgba(15,23,42,.12);pointer-events:auto;" +
        "opacity:0;transform:translateX(calc(100% + 24px));transition:transform .28s ease,opacity .28s ease;" +
        "max-width:360px;word-break:break-word;";
      el.appendChild(successIcon());
      var text = document.createElement("span");
      text.textContent = message;
      el.appendChild(text);
      return el;
    }

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
   * @param {object} [opts] - { type, duration, placement: "top-right"|"bottom-right", icon: boolean }
   */
  function show(message, opts) {
    opts = opts || {};
    var type = opts.type || "info";
    var duration = opts.duration != null ? opts.duration : DEFAULT_DURATION;

    var container = getContainer(opts);
    var el = createToast(message, type, opts);
    container.appendChild(el);

    requestAnimationFrame(function () {
      if (opts.placement === "bottom-right" && opts.icon && type === "success") {
        el.style.opacity = "1";
        el.style.transform = "translateX(0)";
      } else {
        el.style.opacity = "1";
      }
    });

    if (duration > 0) {
      setTimeout(function () {
        dismiss(el, opts);
      }, duration);
    }

    return el;
  }

  function dismiss(el, opts) {
    opts = opts || {};
    if (opts.placement === "bottom-right" && opts.icon) {
      el.style.opacity = "0";
      el.style.transform = "translateX(calc(100% + 24px))";
    } else {
      el.style.opacity = "0";
    }
    setTimeout(function () {
      if (el.parentNode) {
        el.parentNode.removeChild(el);
      }
    }, 300);
  }

  function mergeOpts(opts, type) {
    var next = Object.assign({ type: type }, opts || {});
    return next;
  }

  function success(msg, opts) {
    return show(msg, mergeOpts(opts, "success"));
  }
  function error(msg, opts) {
    return show(msg, mergeOpts(opts, "error"));
  }
  function warning(msg, opts) {
    return show(msg, mergeOpts(opts, "warning"));
  }
  function info(msg, opts) {
    return show(msg, mergeOpts(opts, "info"));
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
