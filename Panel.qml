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

  Service { id: service }

  IpcHandler {
    target: root.ipcTarget
    function toggle(): string { root.toggle(); return "ok" }
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    active: service.on
    tooltipText: service.on ? "Ranchr · gate open" : "Ranchr · gate closed"
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
      if (buttonCode === Qt.RightButton)
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
            meta: service.busy ? "Working…" : (service.on ? "Gate open" : "Gate closed")
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
                checked: service.on
                busy: service.busy
                foreground: hero.foreground
                onToggled: service.toggle()
              }
            }
          }

          Text {
            width: parent.width
            wrapMode: Text.Wrap
            color: service.error !== "" ? (bar ? bar.urgent : Color.urgent) : root.foreground
            opacity: service.error !== "" ? 1.0 : 0.7
            text: service.error !== ""
              ? service.error
              : (service.notified
                  ? "Mailed: " + service.notified
                  : (service.on ? "Scan the QR with your phone." : "Start the host to mint a magic link."))
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
          }

          Row {
            spacing: Style.space(8)
            Button {
              text: service.on ? "Stop host" : "Start host"
              enabled: !service.busy
              onClicked: service.toggle()
            }
            Button {
              text: "Resend mail"
              visible: service.on && service.notify !== "none"
              enabled: !service.busy
              onClicked: service.resend()
            }
          }

          Image {
            visible: service.on && service.qr !== ""
            width: Math.min(parent.width, 240)
            height: width
            fillMode: Image.PreserveAspectFit
            source: service.qr !== "" ? "file://" + service.qr : ""
            cache: false
          }

          Text {
            visible: service.on && service.magic !== ""
            width: parent.width
            wrapMode: Text.WrapAnywhere
            text: service.magic
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
          }

          PanelSeparator { width: parent.width }

          PanelSectionHeader {
            width: parent.width
            text: "Notify"
          }

          ButtonGroup {
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
            visible: service.notify === "hey"
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
            visible: service.notify === "smtp"
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
