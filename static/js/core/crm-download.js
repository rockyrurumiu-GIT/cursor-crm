/**
 * CRM file download helper.
 * Fetches a URL as blob and triggers browser download.
 * Does not modify backend export logic.
 */
(function () {
  "use strict";

  function authHeaders() {
    return typeof window.crmAuthHeader === "function"
      ? window.crmAuthHeader()
      : {};
  }

  /**
   * Download a file from the given URL.
   * @param {string} url - API endpoint that returns a file
   * @param {string} [filename] - override filename; if omitted, extracts from Content-Disposition or URL
   * @param {object} [opts] - { method, headers, body }
   */
  function download(url, filename, opts) {
    opts = opts || {};
    var method = opts.method || "GET";
    var headers = Object.assign({}, authHeaders(), opts.headers || {});

    return fetch(url, {
      method: method,
      headers: headers,
      credentials: "same-origin",
      body: opts.body || undefined,
    }).then(function (resp) {
      if (resp.status === 401) {
        return Promise.reject(new Error("认证失败 (401)，请重新登录"));
      }
      if (resp.status === 403) {
        return Promise.reject(new Error("无权限 (403)"));
      }
      if (!resp.ok) {
        return resp.text().then(function (t) {
          return Promise.reject(new Error("下载失败 (" + resp.status + "): " + t));
        });
      }

      var name = filename || extractFilename(resp) || guessFilename(url);
      return resp.blob().then(function (blob) {
        triggerDownload(blob, name);
      });
    });
  }

  function extractFilename(resp) {
    var cd = resp.headers.get("content-disposition");
    if (!cd) return null;
    var match = cd.match(/filename\*=UTF-8''([^;]+)/i);
    if (match) return decodeURIComponent(match[1]);
    match = cd.match(/filename="?([^";]+)"?/i);
    return match ? match[1] : null;
  }

  function guessFilename(url) {
    var parts = url.split("/");
    var last = parts[parts.length - 1].split("?")[0];
    return last || "download";
  }

  function triggerDownload(blob, filename) {
    var a = document.createElement("a");
    var objUrl = URL.createObjectURL(blob);
    a.href = objUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    setTimeout(function () {
      document.body.removeChild(a);
      URL.revokeObjectURL(objUrl);
    }, 100);
  }

  window.crmDownload = {
    download: download,
  };
})();
