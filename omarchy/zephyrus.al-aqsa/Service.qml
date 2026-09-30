import QtQuick
import Quickshell
import Quickshell.Io

// Reads the status the Al-Aqsa background service writes to
// $XDG_RUNTIME_DIR/al-aqsa/bar.json (prayer times as timestamps) and does the
// per-second countdown here, so nothing has to run elsewhere every second.
Item {
  id: root

  property var shell: null
  property var status: null

  // Derived state, refreshed once a second by update()
  property var nextEvent: null      // next prayer (never sunrise)
  property var currentEvent: null   // latest event that has started (sunrise included)
  property int remainingSeconds: 0
  property real progress: 0
  property bool justStarted: false  // a prayer began in the last 15 min and isn't checked yet
  readonly property bool ready: status !== null && nextEvent !== null

  function pad(n) { return n < 10 ? "0" + n : String(n) }

  function countdown() {
    var s = Math.max(0, remainingSeconds)
    if (s < 600) return Math.floor(s / 60) + ":" + pad(s % 60)             // last 10 min: m:ss
    var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60)
    return h > 0 ? h + "h " + pad(m) + "m" : m + "m"
  }

  function clock(ms) { return Qt.formatTime(new Date(ms), "HH:mm") }

  function update() {
    var now = Date.now()
    var events = status && status.events ? status.events : []
    var next = null, current = null
    for (var i = 0; i < events.length; i++) {
      var e = events[i]
      if (e.at <= now) current = e
      else if (!next && e.prayer) next = e
    }
    nextEvent = next
    currentEvent = current
    remainingSeconds = next ? Math.ceil((next.at - now) / 1000) : 0
    progress = next && current ? Math.max(0, Math.min(1, (now - current.at) / (next.at - current.at))) : 0
    justStarted = !!(current && current.prayer && !current.prayed && now - current.at < 15 * 60 * 1000)
  }

  // Run al-aqsa without a shell interpreting the arguments; the login shell
  // gives it the user's PATH (~/.local/bin).
  function run(args) {
    Quickshell.execDetached(["bash", "-lc", 'exec "$@"', "bash"].concat(args))
  }

  function openApp() { run(["omarchy-launch-or-focus-tui", "al-aqsa"]) }
  function checkCurrent() { run(["al-aqsa", "--check-current"]) }
  function check(key, day) { run(["al-aqsa", "--check", String(key), String(day)]) }
  function toggleNotify() { run(["al-aqsa", "--notify", "toggle"]) }

  FileView {
    id: statusFile
    path: Quickshell.env("XDG_RUNTIME_DIR") + "/al-aqsa/bar.json"
    watchChanges: true
    printErrors: false
    onFileChanged: reload()
    onLoaded: {
      try { root.status = JSON.parse(text()) } catch (e) { root.status = null }
      root.update()
    }
    onLoadFailed: { root.status = null; root.update() }
  }

  Timer {
    interval: 1000
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: root.update()
  }

  // Safety net in case a file change is ever missed (e.g. the file was created late)
  Timer {
    interval: 60000
    running: true
    repeat: true
    onTriggered: statusFile.reload()
  }

  IpcHandler {
    target: "zephyrus.al-aqsa"

    function status(): string {
      return JSON.stringify({
        next: root.nextEvent ? root.nextEvent.name : null,
        remaining: root.remainingSeconds,
        display: root.ready ? root.countdown() : ""
      })
    }
  }
}
