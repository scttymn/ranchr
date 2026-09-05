import QtQuick
import Quickshell
import Quickshell.Io

Item {
  id: root
  visible: false

  readonly property string home: Quickshell.env("HOME") || ""
  readonly property string stateDir: (Quickshell.env("XDG_STATE_HOME") || home + "/.local/state") + "/ranchr"
  readonly property string pluginDir: {
    var u = Qt.resolvedUrl(".").toString()
    if (u.indexOf("file://") === 0)
      u = u.substring(7)
    return u.replace(/\/$/, "")
  }
  readonly property string bin: pluginDir + "/bin/ranchr"

  property bool on: false
  property bool gateway: false
  property string magic: ""
  property string qr: ""
  property string error: ""
  property string notified: ""
  property string notify: "none"
  property string heyTo: ""
  property string smtpHost: ""
  property string smtpPort: "587"
  property string smtpUser: ""
  property string smtpPassword: ""
  property string smtpFrom: ""
  property string smtpTo: ""
  property bool busy: false

  FileView {
    id: hostFile
    path: root.stateDir + "/host.json"
    watchChanges: true
    printErrors: false
    onFileChanged: reload()
    onLoaded: root.applyHost(text())
  }

  FileView {
    id: configFile
    path: (Quickshell.env("XDG_CONFIG_HOME") || root.home + "/.config") + "/ranchr/config.json"
    watchChanges: true
    printErrors: false
    onFileChanged: reload()
    onLoaded: root.applyConfig(text())
  }

  function applyHost(raw) {
    try {
      var data = JSON.parse(raw || "{}")
      root.on = !!data.on
      root.gateway = !!data.gateway || root.on
      root.magic = data.magic || ""
      root.qr = data.on ? (root.stateDir + "/qr.png#" + Date.now()) : ""
      root.error = data.error || ""
      root.notified = data.notified || ""
    } catch (e) {
      root.error = String(e)
    }
  }

  function applyConfig(raw) {
    try {
      var data = JSON.parse(raw || "{}")
      root.notify = data.notify || "none"
      root.heyTo = data.hey_to || ""
      root.smtpHost = data.smtp_host || ""
      root.smtpPort = String(data.smtp_port || 587)
      root.smtpUser = data.smtp_user || ""
      root.smtpPassword = data.smtp_password || ""
      root.smtpFrom = data.smtp_from || ""
      root.smtpTo = data.smtp_to || ""
    } catch (e) {}
  }

  Process {
    id: runner
    onExited: function () {
      root.busy = false
      hostFile.reload()
      configFile.reload()
    }
  }

  function run(args) {
    root.busy = true
    runner.command = [root.bin].concat(args)
    runner.running = true
  }

  function toggle() {
    run(root.on ? ["host", "off"] : ["host", "on"])
  }

  function resend() {
    run(["host", "notify"])
  }

  function setConfig(key, value) {
    run(["config", "set", key, value])
  }
}
