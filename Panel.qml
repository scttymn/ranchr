import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

Panel {
  id: root
  moduleName: "scttymn.ranchr"
  ipcTarget: "ranchr"
  manageIpc: false

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  readonly property color foreground: bar ? bar.foreground : Color.foreground
  readonly property color dim: Qt.darker(foreground, 1.55)
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property string setupCommand: "omarchy pkg add cloudflared qrencode"
  property bool didPromptSetup: false

  Service { id: service }

  IpcHandler {
    target: root.ipcTarget
    function toggle(): string { root.toggle(); return "ok" }
    function setupFinished(): void {
      service.finishSetup()
    }
  }

  Connections {
    target: service
    function onNeedsSetupChanged() {
      if (service.needsSetup && !root.didPromptSetup) {
        root.didPromptSetup = true
        root.open()
      }
    }
  }

  function launchSetup() {
    if (!bar || !service.tryStartSetup())
      return
    var inner = "trap 'omarchy-shell -q ranchr setupFinished' EXIT; " + root.setupCommand
    bar.run("omarchy-launch-floating-terminal-with-presentation " + Util.shellQuote(inner))
    root.close()
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    active: service.on
    tooltipText: service.needsSetup
      ? "Ranchr · setup needed"
      : (service.on ? "Ranchr · gate open" : "Ranchr · gate closed")
    iconComponent: Component {
      Item {
        RanchrIcon {
          anchors.centerIn: parent
          iconSize: parent.width
          color: service.on ? (root.bar ? root.bar.urgent : Color.urgent) : root.foreground
        }
      }
    }
    onPressed: function (buttonCode) {
      if (service.needsSetup)
        root.toggle()
      else if (buttonCode === Qt.RightButton)
        service.toggle()
      else
        root.toggle()
    }
  }

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(420))
    contentHeight: panel.fittedContentHeight(column.implicitHeight, Style.space(640))

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onCloseRequested: root.close()
      onTabRequested: function (direction) { root.switchPanel(direction) }

      Flickable {
        id: panelFlick
        anchors.fill: parent
        contentWidth: width
        contentHeight: column.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.VerticalFlick
        interactive: contentHeight > height
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        Column {
          id: column
          width: panelFlick.width
          spacing: Style.space(12)

          PanelHero {
            id: hero
            width: parent.width
            title: "Ranchr"
            meta: service.needsSetup
              ? "Setup needed"
              : (service.busy ? "Working…" : (service.on ? "Gate open" : "Gate closed"))
            foreground: service.error !== "" ? (bar ? bar.urgent : Color.urgent) : root.foreground
            fontFamily: root.fontFamily
            iconOpacity: service.on ? 1.0 : 0.5
            iconComponent: Component {
              RanchrIcon {
                iconSize: Style.font.display
                color: root.foreground
              }
            }
            trailingControl: Component {
              ToggleSwitch {
                id: hostSwitch
                visible: !service.needsSetup
                checked: service.on
                busy: service.busy
                foreground: hero.foreground
                onToggled: service.toggle()
              }
            }
          }

          Column {
            visible: service.needsSetup
            width: parent.width
            spacing: Style.space(10)

            Text {
              width: parent.width
              wrapMode: Text.Wrap
              color: root.foreground
              text: !service.hasCloudflared && !service.hasQrencode
                ? "Ranchr needs cloudflared to open a tunnel and qrencode to draw the QR."
                : (!service.hasCloudflared
                    ? "Install cloudflared to open a magic-link tunnel from this PC."
                    : "Install qrencode so the widget can show a QR for your phone.")
              font.family: root.fontFamily
              font.pixelSize: Style.font.body
            }

            Button {
              text: service.setupRunning ? "Installing…" : "Install missing tools…"
              enabled: !service.setupRunning
              bordered: true
              onClicked: root.launchSetup()
            }

            Text {
              width: parent.width
              wrapMode: Text.Wrap
              color: root.dim
              text: "or run: " + root.setupCommand
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
            }
          }

          Text {
            visible: !service.needsSetup
            width: parent.width
            wrapMode: Text.Wrap
            color: service.error !== "" ? (bar ? bar.urgent : Color.urgent) : root.foreground
            opacity: service.error !== "" ? 1.0 : 0.7
            text: service.error !== ""
              ? service.error
              : (service.notified
                  ? "Mailed: " + service.notified
                  : (service.on ? "Scan the QR with your phone." : "Turn the switch on to mint a magic link."))
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
          }

          Button {
            text: "Resend mail"
            visible: !service.needsSetup && service.on && service.notify !== "none"
            enabled: !service.busy
            onClicked: service.resend()
          }

          Image {
            visible: !service.needsSetup && service.on && service.qr !== ""
            width: Math.min(parent.width, 240)
            height: width
            fillMode: Image.PreserveAspectFit
            source: service.qr !== "" ? "file://" + service.qr : ""
            cache: false
          }

          Text {
            visible: !service.needsSetup && service.on && service.magic !== ""
            width: parent.width
            wrapMode: Text.WrapAnywhere
            text: service.magic
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
          }

          PanelSeparator {
            visible: !service.needsSetup
            width: parent.width
          }

          PanelSectionHeader {
            visible: !service.needsSetup
            width: parent.width
            text: "Notify"
          }

          ButtonGroup {
            visible: !service.needsSetup
            width: parent.width
            value: service.notify
            foreground: root.foreground
            fontFamily: root.fontFamily
            fontSize: Style.font.caption
            focusable: false
            options: [
              { value: "none", label: "None" },
              { value: "hey", label: "HEY" },
              { value: "smtp", label: "SMTP" }
            ]
            onChanged: function (v) { service.setConfig("notify", v) }
          }

          Column {
            visible: !service.needsSetup && service.notify === "hey"
            width: parent.width
            spacing: Style.space(6)
            Text {
              text: "HEY to"
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
            }
            TextField {
              width: parent.width
              text: service.heyTo
              placeholderText: "you@hey.com"
              onEditingFinished: service.setConfig("hey_to", text)
            }
          }

          Column {
            visible: !service.needsSetup && service.notify === "smtp"
            width: parent.width
            spacing: Style.space(6)
            TextField {
              width: parent.width
              text: service.smtpHost
              placeholderText: "SMTP host"
              onEditingFinished: service.setConfig("smtp_host", text)
            }
            TextField {
              width: parent.width
              text: service.smtpPort
              placeholderText: "587"
              onEditingFinished: service.setConfig("smtp_port", text)
            }
            TextField {
              width: parent.width
              text: service.smtpUser
              placeholderText: "SMTP user"
              onEditingFinished: service.setConfig("smtp_user", text)
            }
            TextField {
              width: parent.width
              password: true
              text: service.smtpPassword
              placeholderText: "SMTP password"
              onEditingFinished: service.setConfig("smtp_password", text)
            }
            TextField {
              width: parent.width
              text: service.smtpFrom
              placeholderText: "From"
              onEditingFinished: service.setConfig("smtp_from", text)
            }
            TextField {
              width: parent.width
              text: service.smtpTo
              placeholderText: "To"
              onEditingFinished: service.setConfig("smtp_to", text)
            }
          }
        }
      }
    }
  }
}
