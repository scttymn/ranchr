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

  Service { id: service }

  IpcHandler {
    target: root.ipcTarget
    function toggle(): string { root.toggle(); return "ok" }
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: "\uf6c0"
    active: service.on
    tooltipText: service.on ? "Ranchr · gate open" : "Ranchr · gate closed"
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
            width: parent.width
            title: "Ranchr"
            meta: service.busy ? "Working…" : (service.on ? "Gate open" : "Gate closed")
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
              enabled: service.on && !service.busy && service.notify !== "none"
              onClicked: service.resend()
            }
          }

          Text {
            width: parent.width
            wrapMode: Text.Wrap
            color: Color.foreground
            opacity: 0.7
            text: service.error !== "" ? service.error : (service.notified ? "Mailed: " + service.notified : (service.on ? "Scan the QR with your phone." : "Start the host to mint a magic link."))
            font.pixelSize: Style.font.bodySmall
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
            width: parent.width
            text: "Notify"
            color: Color.foreground
            font.pixelSize: Style.font.bodySmall
          }
          Row {
            spacing: Style.space(6)
            Repeater {
              model: ["none", "hey", "smtp"]
              Button {
                required property string modelData
                text: modelData
                highlighted: service.notify === modelData
                onClicked: service.setConfig("notify", modelData)
              }
            }
          }

          Column {
            visible: service.notify === "hey"
            width: parent.width
            spacing: Style.space(6)
            Text {
              text: "HEY to"
              color: Color.foreground
              opacity: 0.7
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
              echoMode: TextInput.Password
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
