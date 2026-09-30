import QtQuick
import Quickshell
import qs.Commons
import qs.Ui

// The prayer popup: the next prayer as the hero, a rail from the last prayer
// to the next, then today's times as rows you can check off — click a row,
// or move with the arrow keys and press Enter / Space.
//
// Same composition and spacing as the clock's calendar popup, so the two sit
// side by side as one family. BarWidget.qml hands this panel the bar, the
// service and the button to anchor against.
Panel {
  id: root
  moduleName: hostWidget && hostWidget.moduleName ? hostWidget.moduleName : "zephyrus.al-aqsa"
  ipcTarget: "zephyrus.al-aqsa"
  manageIpc: false

  property var anchorItem: null
  property var hostWidget: null
  property var prayer: null
  readonly property var barIdentity: hostWidget || root

  readonly property color fg: bar ? bar.foreground : Color.foreground
  readonly property color dim: Qt.darker(fg, 1.5)
  readonly property color faint: Qt.darker(fg, 1.9)
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property color checkColor: Style.selectedStateColor(fg, Color.accent)

  readonly property var status: prayer ? prayer.status : null
  readonly property var rows: {
    var all = status && status.events ? status.events : []
    var out = []
    for (var i = 0; i < all.length; i++) if (all[i].today) out.push(all[i])
    return out
  }
  property int selected: -1

  readonly property int railWidth: Style.space(470)
  readonly property int rowHeight: Style.space(38)

  function open() {
    selectCurrent()
    root.controller.show()
    Qt.callLater(function() { if (root.opened) setCenterHoverRevealSuppressed(true) })
  }

  function close() {
    setCenterHoverRevealSuppressed(false)
    root.controller.hide()
  }

  function toggle() {
    if (root.opened) root.close()
    else root.open()
  }

  function switchPanel(direction) {
    if (root.bar && typeof root.bar.switchPanelFrom === "function")
      return root.bar.switchPanelFrom(root.barIdentity, direction)
    return false
  }

  function setCenterHoverRevealSuppressed(value) {
    if (root.bar && typeof root.bar.setCenterHoverRevealSuppressed === "function")
      root.bar.setCenterHoverRevealSuppressed(value)
    else if (root.bar && "centerHoverRevealSuppressed" in root.bar)
      root.bar.centerHoverRevealSuppressed = value
  }

  function isCurrent(e) {
    var c = prayer ? prayer.currentEvent : null
    return !!(c && e && c.key === e.key && c.day === e.day)
  }

  function isNext(e) {
    var n = prayer ? prayer.nextEvent : null
    return !!(n && e && n.key === e.key && n.day === e.day)
  }

  // Start on the prayer that's on now (or the next one before Fajr).
  function selectCurrent() {
    for (var i = 0; i < rows.length; i++) if (isCurrent(rows[i]) && rows[i].prayer) { selected = i; return }
    for (var j = 0; j < rows.length; j++) if (isNext(rows[j])) { selected = j; return }
    selected = 0
  }

  function moveSelection(delta) {
    if (rows.length === 0) return
    var i = selected
    do { i = (i + delta + rows.length) % rows.length } while (!rows[i].prayer && i !== selected)
    selected = i
  }

  function activate(index) {
    var e = rows[index]
    if (!e || !e.prayer || !prayer) return
    selected = index
    if (!e.locked) prayer.check(e.key, e.day)
  }

  function statusText(e) {
    if (!e.prayer) return "not a prayer"
    if (e.prayed) return "prayed"
    if (isCurrent(e)) return "now"
    if (isNext(e)) return "in " + prayer.countdown()
    if (e.at > Date.now()) return prayer.clock(e.at)
    return !e.locked ? "not yet checked" : "missed"
  }

  KeyboardPanel {
    id: panel
    anchorItem: root.anchorItem
    owner: root.barIdentity
    bar: root.bar
    open: root.opened
    centerOnBar: true
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(540))
    contentHeight: panel.fittedContentHeight(content.implicitHeight)

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onMoveRequested: function(dx, dy) { if (dy !== 0) root.moveSelection(dy) }
      onActivateRequested: root.activate(root.selected)
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }
      onTextKey: function(t) {
        if (t === " ") root.activate(root.selected)
        else if (t === "o" || t === "O") { root.prayer.openApp(); root.close() }
        else if (t === "n" || t === "N") root.prayer.toggleNotify()
        else if (t === "j") root.moveSelection(1)
        else if (t === "k") root.moveSelection(-1)
      }

      Column {
        id: content
        width: parent.width
        spacing: Style.space(8)

        // ---- Hero: the next prayer, or the one that has just begun.
        Item {
          width: parent.width
          height: heroRow.height

          Row {
            id: heroRow
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: Style.space(18)

            Text {
              anchors.baseline: heroName.baseline
              text: "󱠧"
              color: root.prayer && root.prayer.justStarted ? Color.accent : root.fg
              font.family: root.fontFamily
              font.pixelSize: 44
            }

            Text {
              id: heroName
              textFormat: Text.PlainText
              text: !root.prayer || !root.prayer.ready ? "Al-Aqsa"
                : (root.prayer.justStarted ? root.prayer.currentEvent.name : root.prayer.nextEvent.name)
              color: root.fg
              font.family: root.fontFamily
              font.pixelSize: 48
              font.bold: true
            }

            Text {
              anchors.baseline: heroName.baseline
              textFormat: Text.PlainText
              visible: !!(root.prayer && root.prayer.ready)
              text: root.prayer && root.prayer.justStarted ? "has started" : "in " + (root.prayer ? root.prayer.countdown() : "")
              color: root.prayer && (root.prayer.justStarted || root.prayer.remainingSeconds < 600) ? Color.accent : root.dim
              font.family: root.fontFamily
              font.pixelSize: 26
            }
          }
        }

        // ---- Rail: from the last prayer (or sunrise) to the next one.
        Item {
          width: parent.width
          height: rail.y + rail.height

          Item {
            id: rail
            y: Style.space(6)
            anchors.horizontalCenter: parent.horizontalCenter
            width: root.railWidth
            height: Math.max(railFrom.implicitHeight, Style.space(10))
            visible: !!(root.prayer && root.prayer.ready && root.prayer.currentEvent)

            Text {
              id: railFrom
              anchors.left: parent.left
              anchors.verticalCenter: parent.verticalCenter
              text: root.prayer && root.prayer.currentEvent
                ? root.prayer.currentEvent.name.toUpperCase() + "  " + root.prayer.clock(root.prayer.currentEvent.at) : ""
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
              font.letterSpacing: 1
            }

            Text {
              id: railTo
              anchors.right: parent.right
              anchors.verticalCenter: parent.verticalCenter
              text: root.prayer && root.prayer.nextEvent ? root.prayer.clock(root.prayer.nextEvent.at) : ""
              color: root.fg
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
            }

            Rectangle {
              anchors.left: railFrom.right
              anchors.right: railTo.left
              anchors.leftMargin: Style.space(12)
              anchors.rightMargin: Style.space(12)
              anchors.verticalCenter: parent.verticalCenter
              height: Style.space(6)
              radius: Style.cornerRadius > 0 ? height / 2 : 0
              color: Qt.rgba(root.fg.r, root.fg.g, root.fg.b, 0.12)

              Rectangle {
                width: Math.round(parent.width * (root.prayer ? root.prayer.progress : 0))
                height: parent.height
                radius: parent.radius
                color: root.checkColor
                Behavior on width { NumberAnimation { duration: 300; easing.type: Easing.OutCubic } }
              }
            }
          }
        }

        // ---- Today's prayers
        Column {
          anchors.horizontalCenter: parent.horizontalCenter
          width: root.railWidth
          topPadding: Style.space(14)
          spacing: Style.space(3)

          Item {
            width: parent.width
            height: Style.space(18)

            Text {
              anchors.left: parent.left
              anchors.leftMargin: Style.space(10)
              anchors.verticalCenter: parent.verticalCenter
              text: root.status ? (root.status.place + " · " + root.status.source).toUpperCase() : "TODAY"
              color: root.faint
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              font.letterSpacing: 1
              font.bold: true
              elide: Text.ElideRight
              width: parent.width * 0.7
            }

            Text {
              anchors.right: parent.right
              anchors.rightMargin: Style.space(10)
              anchors.verticalCenter: parent.verticalCenter
              text: root.status ? root.status.prayedToday + " / 5 PRAYED" : ""
              color: root.status && root.status.prayedToday === 5 ? root.checkColor : root.faint
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              font.letterSpacing: 1
              font.bold: true
            }
          }

          Repeater {
            model: root.rows

            Rectangle {
              id: row
              required property var modelData
              required property int index
              readonly property bool isPrayer: modelData.prayer
              readonly property bool can: isPrayer && !modelData.locked
              readonly property bool current: root.isCurrent(modelData) && isPrayer
              readonly property bool upcoming: modelData.at > Date.now() && !current
              readonly property color text: !isPrayer || (!can && !modelData.prayed) ? root.faint : root.fg

              width: parent.width
              height: root.rowHeight
              radius: Style.cornerRadius
              color: rowMouse.containsMouse && can
                ? Style.hoverFillFor(root.fg, Color.accent)
                : (index === root.selected && root.opened ? Qt.rgba(root.fg.r, root.fg.g, root.fg.b, 0.06) : "transparent")
              // The prayer that's on now is outlined, like today on the calendar
              border.width: current ? Style.spacing.hairline : 0
              border.color: Style.normalBorderFor(root.fg, Color.accent)

              Text {
                id: box
                anchors.left: parent.left
                anchors.leftMargin: Style.space(12)
                anchors.verticalCenter: parent.verticalCenter
                text: !row.isPrayer ? "󰖜" : (row.modelData.prayed ? "󰄲" : "󰄱")
                color: row.modelData.prayed ? root.checkColor : row.text
                font.family: root.fontFamily
                font.pixelSize: Style.font.body + 2
              }

              Text {
                anchors.left: parent.left
                anchors.leftMargin: Style.space(46)
                anchors.verticalCenter: parent.verticalCenter
                textFormat: Text.PlainText
                text: row.modelData.name
                color: row.text
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
                font.bold: row.current
              }

              Text {
                anchors.left: parent.left
                anchors.leftMargin: Style.space(176)
                anchors.verticalCenter: parent.verticalCenter
                textFormat: Text.PlainText
                text: root.prayer ? root.prayer.clock(row.modelData.at) : ""
                color: row.text
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
                font.bold: row.current
              }

              Text {
                anchors.left: parent.left
                anchors.leftMargin: Style.space(246)
                anchors.verticalCenter: parent.verticalCenter
                visible: !!row.modelData.iqama
                textFormat: Text.PlainText
                text: row.modelData.iqama && root.prayer ? "iqama " + root.prayer.clock(row.modelData.iqama) : ""
                color: root.faint
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
              }

              Text {
                anchors.right: parent.right
                anchors.rightMargin: Style.space(14)
                anchors.verticalCenter: parent.verticalCenter
                textFormat: Text.PlainText
                text: root.statusText(row.modelData)
                color: row.modelData.prayed ? root.checkColor
                  : (row.current ? Color.accent : root.faint)
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
                font.italic: !row.isPrayer
              }

              MouseArea {
                id: rowMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: row.can ? Qt.PointingHandCursor : Qt.ArrowCursor
                onClicked: root.activate(row.index)
              }

              PanelToolTip {
                visible: rowMouse.containsMouse && row.isPrayer && !row.can
                text: row.modelData.locked || ""
                fontFamily: root.fontFamily
              }
            }
          }
        }

        // ---- Footer rail: date and hijri date, notifications, open the app.
        Item {
          width: parent.width
          height: footer.height

          Item {
            id: footer
            anchors.horizontalCenter: parent.horizontalCenter
            width: root.railWidth
            height: footerLabel.implicitHeight + Style.space(18)

            PanelActionButton {
              anchors.left: parent.left
              anchors.leftMargin: -Style.space(8)
              anchors.verticalCenter: parent.verticalCenter
              iconText: root.status && root.status.notify ? "󰂚" : "󰂛"
              tooltipText: root.status && root.status.notify ? "Mute prayer notifications (n)" : "Turn on prayer notifications (n)"
              foreground: root.fg
              fontFamily: root.fontFamily
              onClicked: root.prayer.toggleNotify()
            }

            Text {
              id: footerLabel
              anchors.centerIn: parent
              textFormat: Text.PlainText
              text: root.status
                ? (Qt.formatDate(new Date(), "ddd d MMM") + (root.status.hijri ? "  ·  " + root.status.hijri : "")).toUpperCase()
                : ""
              color: Qt.darker(root.fg, 1.4)
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
              font.letterSpacing: 1
            }

            PanelActionButton {
              anchors.right: parent.right
              anchors.rightMargin: -Style.space(8)
              anchors.verticalCenter: parent.verticalCenter
              iconText: "󰏌"
              tooltipText: "Open Al-Aqsa (o)"
              foreground: root.fg
              fontFamily: root.fontFamily
              onClicked: { root.prayer.openApp(); root.close() }
            }
          }
        }
      }
    }
  }
}
