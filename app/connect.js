// Persist the magic-link ranch before the rest of the app loads, and publish a
// manifest whose start_url still contains host+token. iOS Add to Home Screen
// uses that start_url and does not share Safari localStorage with the icon.
(function () {
  var STORE_HOST = "ranchr.host";
  var STORE_TOKEN = "ranchr.token";
  var COOKIE_HOST = "ranchr_host";
  var COOKIE_TOKEN = "ranchr_token";

  function cookiePath() {
    return new URL("./", location.href).pathname;
  }

  function writeCookie(name, value) {
    if (!value) return;
    var secure = location.protocol === "https:" ? "; Secure" : "";
    document.cookie =
      name +
      "=" +
      encodeURIComponent(value) +
      "; Max-Age=" +
      60 * 60 * 24 * 180 +
      "; Path=" +
      cookiePath() +
      "; SameSite=Lax" +
      secure;
  }

  function readCookie(name) {
    var parts = document.cookie.split(";");
    for (var i = 0; i < parts.length; i++) {
      var p = parts[i].trim();
      var eq = p.indexOf("=");
      if (eq < 0) continue;
      if (p.slice(0, eq) === name) {
        try {
          return decodeURIComponent(p.slice(eq + 1));
        } catch (e) {
          return p.slice(eq + 1);
        }
      }
    }
    return "";
  }

  function storeGet(key) {
    try {
      return localStorage.getItem(key) || "";
    } catch (e) {
      return "";
    }
  }

  function storeSet(key, value) {
    if (!value) return;
    try {
      localStorage.setItem(key, value);
    } catch (e) {}
  }

  var q = new URLSearchParams(location.search);
  var host = (q.get("host") || "").trim().replace(/\/$/, "");
  var token = (q.get("t") || "").trim();
  if (host) {
    storeSet(STORE_HOST, host);
    writeCookie(COOKIE_HOST, host);
  }
  if (token) {
    storeSet(STORE_TOKEN, token);
    writeCookie(COOKIE_TOKEN, token);
  }
  if (!host) host = (storeGet(STORE_HOST) || readCookie(COOKIE_HOST)).replace(/\/$/, "");
  if (!token) token = storeGet(STORE_TOKEN) || readCookie(COOKIE_TOKEN);

  var start = new URL(location.pathname, location.origin);
  if (host) start.searchParams.set("host", host);
  if (token) start.searchParams.set("t", token);
  var scope = new URL("./", location.href);
  var manifest = {
    name: "Ranchr",
    short_name: "Ranchr",
    description: "Remote client for the agents on this PC",
    start_url: start.href,
    scope: scope.href,
    display: "standalone",
    background_color: "#0b0d11",
    theme_color: "#0b0d11",
    icons: [
      {
        src: new URL("./icon.svg", location.href).href,
        sizes: "any",
        type: "image/svg+xml",
        purpose: "any",
      },
    ],
  };
  var link = document.createElement("link");
  link.rel = "manifest";
  link.href = "data:application/manifest+json," + encodeURIComponent(JSON.stringify(manifest));
  document.head.appendChild(link);
})();
