import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

// 󱠧 Fajr 4h 47m — styled like the rest of the bar. Left click opens the prayer
// panel, right click checks off the prayer that's on now, middle click opens
// the Al-Aqsa app.
BarWidget {
  id: root
  moduleName: "zephyrus.al-aqsa"

  readonly property var prayer: bar && bar.shell ? bar.shell.serviceFor(moduleName) : null
  readonly property bool ready: prayer ? prayer.ready : false
  readonly property bool highlight: ready && (prayer.justStarted || prayer.remainingSeconds < 600)

  readonly property string label: {
    if (!ready) return "󱠧"
    var name = prayer.justStarted ? prayer.currentEvent.name : prayer.nextEvent.name
    var when = prayer.justStarted ? "now" : prayer.countdown()
    return vertical ? "󱠧\n" + when : "󱠧  " + name + " " + when
  }

  // ---- Panel contract (open/close/opened on the bar-widget root), as the clock does it
  readonly property bool opened: panelLoader.item ? panelLoader.item.opened === true : false
  readonly property real openPanelIndicatorWidth: labelMeasure.implicitWidth
  readonly property real openPanelIndicatorHeight: Math.max(Style.space(10), Math.round(Style.bar.iconSlot * 0.55))
  readonly property bool popoutSwitchClosing: panelLoader.item ? panelLoader.item.popoutSwitchClosing === true : false

  function open() { if (panelLoader.item) panelLoader.item.open() }
  function close() { if (panelLoader.item) panelLoader.item.close() }
  function togglePanel() { if (panelLoader.item) panelLoader.item.toggle() }
  function closeForPopoutSwitch() { if (panelLoader.item) panelLoader.item.closeForPopoutSwitch() }

  function injectPanel() {
    var target = panelLoader.item
    if (!target) return
    if ("bar" in target) target.bar = root.bar
    if ("settings" in target) target.settings = root.settings
    if ("anchorItem" in target) target.anchorItem = button
    if ("hostWidget" in target) target.hostWidget = root
    if ("prayer" in target) target.prayer = root.prayer
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  onBarChanged: injectPanel()
  onSettingsChanged: injectPanel()
  onPrayerChanged: injectPanel()

  Loader {
    id: panelLoader
    active: true
    source: Qt.resolvedUrl("Panel.qml")
    visible: false
    onLoaded: {
      root.injectPanel()
      Qt.callLater(root.injectPanel)
    }
  }

  IpcHandler {
    target: "zephyrus.al-aqsa.panel"
    function open(): void { root.open() }
    function close(): void { root.close() }
    function toggle(): void { root.togglePanel() }
  }

  Text {
    id: labelMeasure
    visible: false
    text: root.label
    font.family: button.fontFamily
    font.pixelSize: button.fontSize
  }

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.label
    foreground: root.highlight ? Color.accent : (root.bar ? root.bar.barForeground : Color.foreground)
    horizontalMargin: 8.75
    verticalPadding: 8.75
    tooltipText: root.opened ? "" : "Prayer times\nLeft: panel   Right: check off current prayer   Middle: open Al-Aqsa"

    onPressed: function(b) {
      if (!root.prayer) return
      if (b === Qt.RightButton) root.prayer.checkCurrent()
      else if (b === Qt.MiddleButton) root.prayer.openApp()
      else root.togglePanel()
    }
  }
}
