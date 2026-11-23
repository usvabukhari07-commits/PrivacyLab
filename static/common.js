// Adds the CSRF-protection header to every request made by our own pages
(function () {
  const originalFetch = window.fetch;
  window.fetch = function (url, options) {
    options = options || {};
    options.headers = Object.assign({ "X-Requested-With": "PrivacyLab" }, options.headers || {});
    return originalFetch(url, options);
  };
})();