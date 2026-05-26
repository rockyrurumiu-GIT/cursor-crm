/**
 * CRM DOM helpers.
 * - escapeHTML to prevent XSS when inserting user content.
 * - setText for safely setting element text without innerHTML.
 */
(function () {
  "use strict";

  var escapeMap = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  };
  var escapeRe = /[&<>"']/g;

  /**
   * Escape HTML special characters.
   * @param {string} str
   * @returns {string}
   */
  function escapeHTML(str) {
    if (str == null) return "";
    return String(str).replace(escapeRe, function (ch) {
      return escapeMap[ch];
    });
  }

  /**
   * Safely set text content of an element (no HTML parsing).
   * @param {HTMLElement|string} el - element or selector
   * @param {string} text
   */
  function setText(el, text) {
    if (typeof el === "string") {
      el = document.querySelector(el);
    }
    if (el) {
      el.textContent = text != null ? String(text) : "";
    }
  }

  /**
   * Create an element with attributes and text.
   * @param {string} tag
   * @param {object} [attrs]
   * @param {string} [text]
   * @returns {HTMLElement}
   */
  function createElement(tag, attrs, text) {
    var el = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        el.setAttribute(k, attrs[k]);
      });
    }
    if (text != null) {
      el.textContent = String(text);
    }
    return el;
  }

  window.crmDom = {
    escapeHTML: escapeHTML,
    setText: setText,
    createElement: createElement,
  };
})();
