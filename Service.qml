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
  property bool busy: false
  property bool probed: false
  property bool hasCloudflared: false
  property bool hasQrencode: false
  property bool ready: false
  property var missing: []
  property bool setupRunning: false
  readonly property bool needsSetup: probed && !ready

  FileView {
    id: hostFile
    path: root.stateDir + "/host.json"
    watchChanges: true
    printErrors: false
    onFileChanged: reload()
    onLoaded: root.applyHost(text())
  }

  function applyHost(raw) {
    try {
      var data = JSON.parse(raw || "{}")
      root.on = !!data.on
      root.gateway = !!data.gateway || root.on
      root.magic = data.magic || ""
      root.qr = data.on ? (root.stateDir + "/qr.png#" + Date.now()) : ""
      root.error = data.error || ""
    } catch (e) {
      root.error = String(e)
    }
  }

  Process {
    id: runner
    onExited: function () {
      root.busy = false
      hostFile.reload()
    }
  }

  Process {
    id: depsProbe
    running: false
    stdout: StdioCollector {
      id: depsOut
      waitForEnd: true
    }
    onExited: root.applyDeps(depsOut.text)
  }

  function applyDeps(raw) {
    root.probed = true
    try {
      var data = JSON.parse(raw || "{}")
      root.hasCloudflared = !!data.cloudflared
      root.hasQrencode = !!data.qrencode
      root.missing = data.missing || []
      root.ready = !!data.ready
    } catch (e) {
      root.ready = false
    }
  }

  function probeDeps() {
    if (depsProbe.running)
      depsProbe.running = false
    depsProbe.command = [root.bin, "deps"]
    depsProbe.running = true
  }

  function tryStartSetup() {
    if (root.setupRunning)
      return false
    root.setupRunning = true
    return true
  }

  function finishSetup() {
    root.setupRunning = false
    probeDeps()
  }

  Component.onCompleted: probeDeps()

  function run(args) {
    root.busy = true
    runner.command = [root.bin].concat(args)
    runner.running = true
  }

  function toggle() {
    run(root.on ? ["host", "off"] : ["host", "on"])
  }
}
