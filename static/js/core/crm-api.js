/**
 * CRM API fetch wrapper.
 * - Attaches auth headers via window.crmAuthHeader().
 * - Uses credentials: "same-origin" for cookie-based sessions.
 * - Auto-sets Content-Type for JSON bodies.
 * - Surfaces 401/403 with clear errors (does not silently swallow).
 */
(function () {
  "use strict";

  function authHeaders() {
    return typeof window.crmAuthHeader === "function"
      ? window.crmAuthHeader()
      : {};
  }

  function buildHeaders(extra, hasBody) {
    var h = Object.assign({}, authHeaders(), extra || {});
    if (hasBody && !h["Content-Type"]) {
      h["Content-Type"] = "application/json";
    }
    return h;
  }

  function handleResponse(resp) {
    if (resp.status === 401) {
      return Promise.reject(new Error("认证失败 (401)，请重新登录"));
    }
    if (resp.status === 403) {
      return Promise.reject(new Error("无权限 (403)"));
    }
    if (!resp.ok) {
      return resp.text().then(function (t) {
        return Promise.reject(new Error("请求失败 (" + resp.status + "): " + t));
      });
    }
    var ct = resp.headers.get("content-type") || "";
    if (ct.indexOf("application/json") !== -1) {
      return resp.json();
    }
    return resp;
  }

  /**
   * GET request.
   * @param {string} url
   * @param {object} [opts] - { headers, params }
   */
  function get(url, opts) {
    opts = opts || {};
    if (opts.params) {
      var qs = new URLSearchParams(opts.params).toString();
      url += (url.indexOf("?") === -1 ? "?" : "&") + qs;
    }
    return fetch(url, {
      method: "GET",
      headers: buildHeaders(opts.headers, false),
      credentials: "same-origin",
    }).then(handleResponse);
  }

  /**
   * POST request (JSON body).
   * @param {string} url
   * @param {*} body - will be JSON.stringify'd unless opts.raw is set
   * @param {object} [opts] - { headers, raw }
   */
  function post(url, body, opts) {
    opts = opts || {};
    var payload = opts.raw ? body : JSON.stringify(body);
    var headers = buildHeaders(opts.headers, !opts.raw);
    if (opts.raw && headers["Content-Type"] === "application/json") {
      delete headers["Content-Type"];
    }
    return fetch(url, {
      method: "POST",
      headers: headers,
      credentials: "same-origin",
      body: payload,
    }).then(handleResponse);
  }

  /**
   * PUT request (JSON body).
   */
  function put(url, body, opts) {
    opts = opts || {};
    return fetch(url, {
      method: "PUT",
      headers: buildHeaders(opts.headers, true),
      credentials: "same-origin",
      body: JSON.stringify(body),
    }).then(handleResponse);
  }

  /**
   * PATCH request (JSON body).
   */
  function patch(url, body, opts) {
    opts = opts || {};
    return fetch(url, {
      method: "PATCH",
      headers: buildHeaders(opts.headers, true),
      credentials: "same-origin",
      body: JSON.stringify(body),
    }).then(handleResponse);
  }

  /**
   * DELETE request.
   */
  function del(url, opts) {
    opts = opts || {};
    return fetch(url, {
      method: "DELETE",
      headers: buildHeaders(opts.headers, false),
      credentials: "same-origin",
    }).then(handleResponse);
  }

  /**
   * POST with FormData (multipart, no manual Content-Type).
   */
  function postForm(url, formData, opts) {
    opts = opts || {};
    var headers = Object.assign({}, authHeaders(), opts.headers || {});
    return fetch(url, {
      method: "POST",
      headers: headers,
      credentials: "same-origin",
      body: formData,
    }).then(handleResponse);
  }

  window.crmApi = {
    get: get,
    post: post,
    put: put,
    patch: patch,
    del: del,
    postForm: postForm,
  };
})();
