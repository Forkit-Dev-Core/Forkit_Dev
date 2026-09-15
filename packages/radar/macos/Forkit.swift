// Local app shell. The existing Python engine owns receipts and identities.
// No web server, account or project polling. A fixed count-only message handler
// accepts view/history intent after separate optional reporting consent.
import AppKit
import WebKit
import UniformTypeIdentifiers

final class ForkitApp: NSObject, NSApplicationDelegate, NSWindowDelegate, WKNavigationDelegate, WKDownloadDelegate, WKScriptMessageHandler {
    private var window: NSWindow!
    private var web: WKWebView!
    private var refreshButton: NSButton!
    private var captureButton: NSPopUpButton!
    private var passportButton: NSButton!
    private var progress: NSProgressIndicator!
    private var bridgeQueue = DispatchQueue(label: "dev.forkit.local-actions", qos: .userInitiated)
    private var watcher: DispatchSourceFileSystemObject?
    private var watchFingerprint = ""
    private var debounce: DispatchWorkItem?
    private var currentFile: URL?
    private var restoredState: Any?
    private var refreshing = false
    private var refreshAgain = false
    private var operationCount = 0
    private var controlOperations = 0
    private var installedReady = false
    private var firstActivation = true
    private var initialViewPending = true
    private var usageEnabled = false
    private var downloadDestinations: [ObjectIdentifier: URL] = [:]
    private var cancelledDownloads: Set<ObjectIdentifier> = []
    private let store: URL
    private let noSetup: Bool
    private let previewHome: URL?
    private let python: URL

    override init() {
        let args = CommandLine.arguments
        let configuredStore = args.firstIndex(of: "--store").flatMap { i in i + 1 < args.count ? args[i + 1] : nil }
        let preview = args.firstIndex(of: "--preview-home").flatMap { i in i + 1 < args.count ? args[i + 1] : nil }
        previewHome = preview.map { URL(fileURLWithPath: $0, isDirectory: true) }
        store = configuredStore.map { URL(fileURLWithPath: $0, isDirectory: true) }
            ?? (previewHome ?? FileManager.default.homeDirectoryForCurrentUser).appendingPathComponent(".forkit-radar", isDirectory: true)
        // Isolated preview never alters user-level hooks. This is not a product default.
        noSetup = args.contains("--no-setup")
        python = Bundle.main.resourceURL!.resolvingSymlinksInPath().appendingPathComponent("runtime/bin/python3.11")
        super.init()
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        let appMenu = NSMenu()
        let menu = NSMenuItem(); appMenu.addItem(menu)
        let items = NSMenu(); menu.submenu = items
        items.addItem(withTitle: "About Forkit", action: #selector(about), keyEquivalent: "")
        items.addItem(withTitle: "Optional usage counts…", action: #selector(usageSettings), keyEquivalent: "")
        items.addItem(withTitle: "Repair installation", action: #selector(repairInstallation), keyEquivalent: "")
        items.addItem(withTitle: "Restore previous version…", action: #selector(restorePrevious), keyEquivalent: "")
        items.addItem(withTitle: "Remove Forkit…", action: #selector(removeInstallation), keyEquivalent: "")
        items.addItem(.separator())
        items.addItem(withTitle: "Quit Forkit", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        // Native text fields and the local WebView retain standard clipboard shortcuts.
        let edit = NSMenuItem(title: "Edit", action: nil, keyEquivalent: "")
        let editMenu = NSMenu(title: "Edit"); edit.submenu = editMenu
        editMenu.addItem(withTitle: "Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        editMenu.addItem(withTitle: "Paste", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        editMenu.addItem(withTitle: "Select All", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        appMenu.addItem(edit); NSApp.mainMenu = appMenu

        let config = WKWebViewConfiguration()
        config.websiteDataStore = .nonPersistent()
        config.userContentController.add(self, name: "forkitUsage")
        web = WKWebView(frame: .zero, configuration: config)
        web.navigationDelegate = self
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1120, height: 850),
            styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = noSetup || previewHome != nil ? "Forkit Session Receipt — Local validation" : "Forkit Session Receipt"
        window.minSize = NSSize(width: 720, height: 540)
        window.delegate = self; window.isReleasedWhenClosed = false
        refreshButton = NSButton(title: "Refresh", target: self, action: #selector(refreshClicked))
        refreshButton.toolTip = "Refresh saved history"
        captureButton = NSPopUpButton(frame: .zero, pullsDown: true)
        captureButton.addItems(withTitles: ["Capture", "Set up / resume", "Pause capture", "Recover session…"])
        captureButton.target = self; captureButton.action = #selector(captureClicked)
        passportButton = NSButton(title: "Passport…", target: self, action: #selector(passportClicked))
        passportButton.toolTip = "Optional local identity for future sessions"
        progress = NSProgressIndicator(); progress.style = .spinning; progress.controlSize = .small
        progress.isDisplayedWhenStopped = false
        let local = NSTextField(labelWithString: noSetup || previewHome != nil ? "Local validation · No account" : "Local · No account")
        local.textColor = .secondaryLabelColor; local.font = .systemFont(ofSize: 12)
        let spacer = NSView(); spacer.setContentHuggingPriority(.defaultLow, for: .horizontal)
        let bar = NSStackView(views: [refreshButton, captureButton, passportButton, spacer, progress, local])
        bar.orientation = .horizontal; bar.spacing = 10
        bar.edgeInsets = NSEdgeInsets(top: 9, left: 16, bottom: 9, right: 16)
        let content = NSView(); window.contentView = content
        for view in [bar, web!] { view.translatesAutoresizingMaskIntoConstraints = false; content.addSubview(view) }
        NSLayoutConstraint.activate([
            bar.topAnchor.constraint(equalTo: content.topAnchor), bar.leadingAnchor.constraint(equalTo: content.leadingAnchor),
            bar.trailingAnchor.constraint(equalTo: content.trailingAnchor), bar.heightAnchor.constraint(equalToConstant: 48),
            web.topAnchor.constraint(equalTo: bar.bottomAnchor), web.leadingAnchor.constraint(equalTo: content.leadingAnchor),
            web.trailingAnchor.constraint(equalTo: content.trailingAnchor), web.bottomAnchor.constraint(equalTo: content.bottomAnchor),
            progress.widthAnchor.constraint(equalToConstant: 16), progress.heightAnchor.constraint(equalToConstant: 16)
        ])
        window.center(); window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true)
        refreshHistory()
        if !noSetup {
            prepareInstallation()
        }
    }

    func applicationDidBecomeActive(_ notification: Notification) {
        if firstActivation { firstActivation = false; return }
        // Returning from Finder must not replace an unchanged page under a click.
        if web != nil && fingerprint() != watchFingerprint { refreshHistory() }
        loadUsagePreference()
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
    func applicationWillTerminate(_ notification: Notification) { watcher?.cancel(); debounce?.cancel() }

    @objc private func about() {
        message("Forkit Session Receipt", "Local development build · Apple Silicon\nYour receipts stay on this Mac. No signup or upload.\nCodex hooks require review in /hooks. Claude Code and Cursor are experimental.")
    }
    private func message(_ title: String, _ text: String) {
        let alert = NSAlert(); alert.messageText = title; alert.informativeText = text
        alert.addButton(withTitle: "OK"); alert.beginSheetModal(for: window)
    }
    private func loadUsagePreference(countOpening: Bool = false) {
        guard !noSetup, previewHome == nil else { return }
        action("usage-status", quiet: true) { result in
            self.usageEnabled = result?["state"] as? String == "enabled" && result?["consent"] as? String == "usage-v3"
            if countOpening && result?["has_receipt"] as? Bool == true { self.countUsage("view") }
        }
    }
    private func countUsage(_ kind: String) {
        guard usageEnabled, !noSetup, previewHome == nil else { return }
        action("engagement", data: ["action": kind], quiet: true) { _ in }
    }
    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard message.name == "forkitUsage", message.frameInfo.isMainFrame,
            let expected = currentFile, let source = message.frameInfo.request.url, source.isFileURL,
            source.path == expected.path, web.url?.path == expected.path, window.isKeyWindow,
            let kind = message.body as? String, ["view", "history"].contains(kind) else { return }
        countUsage(kind)
    }
    @objc private func usageSettings() {
        guard !noSetup, previewHome == nil else {
            message("Local validation", "Validation windows do not enable community reporting."); return
        }
        action("usage-status") { result in
            guard let result = result else { return }
            let enabled = result["state"] as? String == "enabled"
            let alert = NSAlert(); alert.messageText = "Help improve Forkit with counts"
            alert.informativeText = "Optional. All local features stay free. After consent, counts of receipts, scans, Passport creation, days you view results/history and card exports may be sent once a day. No prompts, code, filenames or Passport IDs. A random reporting profile links updates; the service sees connection metadata. Read the operator’s privacy notice first. Disabling stops future reports; use forkit-radar usage withdraw to remove a sent contribution."
            alert.addButton(withTitle: enabled ? "Keep current setting" : "Keep off")
            if enabled {
                alert.addButton(withTitle: "Disable reporting")
                alert.beginSheetModal(for: self.window) { response in
                    if response == .alertSecondButtonReturn {
                        self.action("usage-disable") { _ in self.usageEnabled = false }
                    }
                }
                return
            }
            guard result["has_receipt"] as? Bool == true else {
                self.message("Get your first receipt", "Optional counts are available after your first completed session."); return
            }
            alert.addButton(withTitle: "Enable these counts")
            let endpoint = NSTextField(frame: NSRect(x: 0, y: 0, width: 440, height: 24))
            endpoint.placeholderString = "HTTPS collector supplied by the beta operator"
            alert.accessoryView = endpoint
            alert.beginSheetModal(for: self.window) { response in
                if response == .alertSecondButtonReturn {
                    self.action("usage-enable", data: ["endpoint": endpoint.stringValue, "consent": "usage-v3"]) { answer in
                        if answer != nil {
                            self.usageEnabled = true
                            self.message("Preference saved", "Nothing sent by this action. Future normal use may report counts. No previous activity was imported.")
                        }
                    }
                }
            }
        }
    }
    private func setBusy(_ change: Int, blocksControls: Bool) {
        operationCount += change
        if blocksControls { controlOperations += change }
        // A focus-triggered history refresh must not swallow the user's click.
        refreshButton.isEnabled = controlOperations == 0
        captureButton.isEnabled = controlOperations == 0; passportButton.isEnabled = controlOperations == 0
        if operationCount > 0 { progress.startAnimation(nil) } else { progress.stopAnimation(nil) }
    }
    // Only fixed actions from native controls. No user input becomes a command,
    // import path or executable. Each isolated child has bounded output and life.
    private func action(_ name: String, data: [String: Any] = [:], quiet: Bool = false, completion: @escaping ([String: Any]?) -> Void) {
        let blocks = !["render", "usage-status", "engagement"].contains(name)
        setBusy(1, blocksControls: blocks)
        let executable = python, root = store
        let overrideHome = previewHome
        bridgeQueue.async {
            var answer: [String: Any]?
            do {
                let task = Process(), output = Pipe(), input = Pipe()
                task.executableURL = executable
                task.arguments = ["-I", "-B", "-m", "forkit_radar.desktop", name, "--store", root.path]
                let inherited = ProcessInfo.processInfo.environment
                var env = ["HOME": (overrideHome ?? FileManager.default.homeDirectoryForCurrentUser).path,
                    "PATH": FileManager.default.homeDirectoryForCurrentUser.path + "/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
                    "LANG": "en_US.UTF-8", "TMPDIR": NSTemporaryDirectory()]
                for key in ["CODEX_HOME", "CLAUDE_CONFIG_DIR"] { if let value = inherited[key] { env[key] = value } }
                if let home = overrideHome {
                    env["CODEX_HOME"] = home.appendingPathComponent(".codex").path
                    env["CLAUDE_CONFIG_DIR"] = home.appendingPathComponent(".claude").path
                }
                task.environment = env; task.currentDirectoryURL = executable.deletingLastPathComponent()
                task.standardOutput = output; task.standardInput = input
                task.standardError = FileHandle(forWritingAtPath: "/dev/null")
                try task.run()
                let timeout = DispatchWorkItem { if task.isRunning { task.terminate() } }
                DispatchQueue.global().asyncAfter(deadline: .now() + 60, execute: timeout)
                try input.fileHandleForWriting.write(contentsOf: JSONSerialization.data(withJSONObject: data))
                try input.fileHandleForWriting.close()
                var bytes = Data()
                while true {
                    let part = output.fileHandleForReading.readData(ofLength: 16_384)
                    if part.isEmpty { break }
                    bytes.append(part)
                    if bytes.count > 1_048_576 { task.terminate(); break }
                }
                task.waitUntilExit(); timeout.cancel()
                if task.terminationStatus == 0 || task.terminationStatus == 1 {
                    answer = try JSONSerialization.jsonObject(with: bytes) as? [String: Any]
                }
            } catch { /* Only a fixed actionable message reaches the UI. */ }
            DispatchQueue.main.async {
                self.setBusy(-1, blocksControls: blocks)
                if answer?["ok"] as? Bool == true {
                    completion(answer?["result"] as? [String: Any])
                } else {
                    if !quiet { self.message("Forkit needs attention", answer?["error"] as? String ?? "The local action could not finish. Your saved receipts are preserved. Check file access, then try again.") }
                    completion(nil)
                }
            }
        }
    }
    @objc private func refreshClicked() { refreshHistory() }
    private func refreshHistory() {
        if refreshing { refreshAgain = true; return }
        refreshing = true
        let requestedFingerprint = fingerprint()
        web.evaluateJavaScript("window.forkitViewState ? window.forkitViewState() : null") { state, _ in
            self.restoredState = state
            self.action("render") { result in
                guard let path = result?["file"] as? String else { self.refreshing = false; return }
                let file = URL(fileURLWithPath: path).standardizedFileURL
                // A response cannot broaden WebKit file access beyond this one snapshot.
                guard file.deletingLastPathComponent() == self.store.standardizedFileURL,
                    file.lastPathComponent.range(of: "^history-[0-9a-f-]{36}\\.html$", options: .regularExpression) != nil
                else { self.refreshing = false; return }
                self.currentFile = file
                self.web.loadFileURL(file, allowingReadAccessTo: file)
                self.beginWatching()
                // The first watcher starts after rendering. A receipt saved
                // during that first snapshot must still schedule a fresh view.
                if self.fingerprint() != requestedFingerprint { self.refreshAgain = true }
            }
        }
    }
    private func fingerprint() -> String {
        let names = ["sessions.sqlite3", "sessions.sqlite3-wal", "automatic-capture.json", "session-associations.json",
            "capture-status-codex.json", "capture-status-claude-code.json", "capture-status-cursor.json"]
        return names.map { name in
            guard let value = try? FileManager.default.attributesOfItem(atPath: store.appendingPathComponent(name).path) else { return name + ":missing" }
            let modified = (value[.modificationDate] as? Date)?.timeIntervalSince1970 ?? 0
            return name + ":" + String(modified) + ":" + String(describing: value[.size]) + ":" + String(describing: value[.systemFileNumber])
        }.joined(separator: "|")
    }
    private func beginWatching() {
        // Directory notifications only; generated HTML does not trigger a loop.
        if watcher != nil { return }
        watchFingerprint = fingerprint()
        let fd = open(store.path, O_EVTONLY | O_NOFOLLOW)
        if fd < 0 { return }
        let source = DispatchSource.makeFileSystemObjectSource(fileDescriptor: fd, eventMask: [.write, .rename, .delete], queue: .main)
        source.setEventHandler { [weak self] in
            guard let self = self else { return }
            self.debounce?.cancel()
            let work = DispatchWorkItem {
                let next = self.fingerprint()
                if next != self.watchFingerprint { self.watchFingerprint = next; self.refreshHistory() }
            }
            self.debounce = work; DispatchQueue.main.asyncAfter(deadline: .now() + 0.25, execute: work)
        }
        source.setCancelHandler { close(fd) }
        watcher = source; source.resume()
    }
    private func prepareInstallation() {
        action("app-status") { result in
            guard let result = result, result["app"] is String else { return }
            if result["recovery_pending"] as? Bool == true {
                self.message("Finish the interrupted update", "Use Repair installation in the Forkit menu. Your saved receipts remain here.")
                return
            }
            if result["running_from_installation"] as? Bool == true {
                self.action("app-install") { installed in
                    if installed != nil {
                        self.installedReady = true
                        self.action("onboard") { _ in self.refreshHistory() }
                    }
                }
                return
            }
            let alert = NSAlert()
            let updating = result["installed"] as? Bool == true
            alert.messageText = updating ? "Update Forkit on this Mac?" : "Install Forkit on this Mac?"
            alert.informativeText = updating
                ? "Finish coding sessions and quit the installed Forkit app first. This update keeps your receipts and a recoverable previous version."
                : "Forkit will live in your Applications folder with everything it needs. Receipts stay on this Mac. No account is required."
            alert.addButton(withTitle: updating ? "Update" : "Install"); alert.addButton(withTitle: "Not now")
            alert.beginSheetModal(for: self.window) { response in
                if response == .alertFirstButtonReturn {
                    self.action("app-install") { installed in
                        if let path = installed?["app"] as? String { self.openInstalled(path) }
                    }
                }
            }
        }
    }
    private func openInstalled(_ path: String) {
        let expected = (previewHome ?? FileManager.default.homeDirectoryForCurrentUser)
            .appendingPathComponent("Applications/Forkit Session Receipt.app").standardizedFileURL
        let target = URL(fileURLWithPath: path).standardizedFileURL
        guard target == expected else { return }
        let configuration = NSWorkspace.OpenConfiguration()
        configuration.createsNewApplicationInstance = true
        if let home = previewHome { configuration.arguments = ["--preview-home", home.path] }
        NSWorkspace.shared.openApplication(at: target, configuration: configuration) { _, error in
            DispatchQueue.main.async {
                if error == nil { NSApp.terminate(nil) }
                else { self.message("Forkit is installed", "Open Forkit Session Receipt from your Applications folder to continue.") }
            }
        }
    }
    @objc private func repairInstallation() {
        if noSetup { message("Isolated preview", "Installation changes are disabled in this preview."); return }
        action("app-repair") { result in
            if result != nil { self.prepareInstallation() }
        }
    }
    @objc private func restorePrevious() {
        if noSetup || !installedReady { message("Installed app required", "Open the installed Forkit app to restore its previous version."); return }
        let alert = NSAlert(); alert.messageText = "Restore the previous Forkit app?"
        alert.informativeText = "Finish coding sessions first. Your saved history stays here. Changed hook commands may need review in your coding tool."
        alert.addButton(withTitle: "Restore"); alert.addButton(withTitle: "Cancel")
        alert.beginSheetModal(for: window) { response in
            if response == .alertFirstButtonReturn {
                self.action("app-rollback") { result in
                    if let path = result?["app"] as? String { self.openInstalled(path) }
                }
            }
        }
    }
    @objc private func removeInstallation() {
        if noSetup || !installedReady { message("Installed app required", "Open the installed Forkit app to remove it safely."); return }
        let alert = NSAlert(); alert.messageText = "Remove Forkit from this Mac?"
        alert.informativeText = "Finish coding sessions first. Forkit will remove its capture hooks and command, move its app and previous version to Trash, and keep your local receipts."
        alert.addButton(withTitle: "Remove Forkit"); alert.addButton(withTitle: "Cancel")
        alert.beginSheetModal(for: window) { response in
            if response == .alertFirstButtonReturn {
                self.action("app-remove") { result in
                    if result?["removed"] as? Bool == true { NSApp.terminate(nil) }
                }
            }
        }
    }
    @objc private func captureClicked() {
        switch captureButton.indexOfSelectedItem {
        case 1:
            if noSetup || !installedReady { message("Install Forkit first", "Tool setup uses the stable installed app. It is disabled in this preview."); return }
            action("setup") { result in
                self.refreshHistory()
                if result != nil { self.message("Capture settings updated", "Codex: review Forkit in /hooks, then start a new session. Claude Code and Cursor remain experimental. The capture status shows any action still needed.") }
            }
        case 2:
            if noSetup || !installedReady { message("Isolated preview", "Tool settings cannot be changed from this preview."); return }
            let alert = NSAlert(); alert.messageText = "Pause capture?"
            alert.informativeText = "Saved history stays here. A session already in progress may need recovery if its end arrives while capture is paused."
            alert.addButton(withTitle: "Pause"); alert.addButton(withTitle: "Cancel")
            alert.beginSheetModal(for: window) { response in
                if response == .alertFirstButtonReturn { self.action("pause") { _ in self.refreshHistory() } }
            }
        case 3: recover()
        default: break
        }
    }
    private func recover() {
        action("status") { result in
            guard let active = result?["active"] as? [[String: Any]] else { return }
            if active.isEmpty { self.message("No incomplete session", "All saved sessions have ended."); return }
            let alert = NSAlert(); alert.messageText = "Recover an unfinished session"
            alert.informativeText = "Use this only after coding has stopped. The receipt will be marked recovered; Forkit will not invent its end time."
            let picker = NSPopUpButton(frame: NSRect(x: 0, y: 0, width: 380, height: 30), pullsDown: false)
            for item in active {
                let started = item["started"] as? [String: Any] ?? [:]
                picker.addItem(withTitle: "\(started["tool"] as? String ?? "Session") · \(started["started_at"] as? String ?? "Unknown start")")
            }
            alert.accessoryView = picker; alert.addButton(withTitle: "Recover"); alert.addButton(withTitle: "Cancel")
            alert.beginSheetModal(for: self.window) { response in
                if response == .alertFirstButtonReturn,
                    let start = active[picker.indexOfSelectedItem]["started"] as? [String: Any],
                    let id = start["session_id"] as? String {
                    self.action("recover", data: ["session_id": id]) { _ in self.refreshHistory() }
                }
            }
        }
    }
    @objc private func passportClicked() {
        action("projects") { result in
            guard let projects = result?["projects"] as? [[String: Any]] else { return }
            if projects.isEmpty { self.message("Passport is optional", "Finish your first coding session, then choose a local Passport for that project. No account or connection is required."); return }
            let alert = NSAlert(); alert.messageText = "Local Passport"
            alert.informativeText = "Choose an identity for future sessions. Existing receipts keep their original identity. Finish an active session before changing its Passport."
            let picker = NSPopUpButton(frame: NSRect(x: 0, y: 0, width: 420, height: 30), pullsDown: false)
            let associations = (result?["associations"] as? [String: Any])?["projects"] as? [String: Any] ?? [:]
            for project in projects {
                let chosen = associations[project["project_id"] as? String ?? ""] as? [String: Any]
                let selection = chosen?["selection"] as? [String: Any]
                let passport = selection?["passport_id"] as? String
                let label = (project["name"] as? String ?? "Local project") + (passport.map { " · Passport " + $0.prefix(12) + "…" } ?? " · No Passport selected")
                picker.addItem(withTitle: label); picker.lastItem?.toolTip = project["path"] as? String
            }
            alert.accessoryView = picker
            for label in ["Create…", "Use existing…", "Clear selection", "Cancel"] { alert.addButton(withTitle: label) }
            alert.beginSheetModal(for: self.window) { response in
                guard let id = projects[picker.indexOfSelectedItem]["project_id"] as? String else { return }
                switch response.rawValue {
                case NSApplication.ModalResponse.alertFirstButtonReturn.rawValue: self.createPassport(id)
                case NSApplication.ModalResponse.alertSecondButtonReturn.rawValue: self.selectPassport(id)
                case NSApplication.ModalResponse.alertThirdButtonReturn.rawValue:
                    self.action("clear-passport", data: ["project_id": id]) { _ in self.refreshHistory() }
                default: break
                }
            }
        }
    }
    private func createPassport(_ projectID: String) {
        let alert = NSAlert(); alert.messageText = "Create a local Passport"
        alert.informativeText = "Local declarations for a custom code assistant. Use versions such as 1.0.0. Model task: code generation; architecture: other. These details do not prove which model ran."
        let entries = [("name", "Agent name"), ("version", "Agent version"), ("creator", "Creator name"),
            ("model_name", "Model name"), ("model_version", "Model version")]
        var inputs: [String: NSTextField] = [:]
        let stack = NSStackView(); stack.orientation = .vertical; stack.alignment = .leading; stack.spacing = 5
        for (key, label) in entries {
            let field = NSTextField(string: key == "version" || key == "model_version" ? "1.0.0" : "")
            field.placeholderString = label; field.setAccessibilityLabel(label)
            field.widthAnchor.constraint(equalToConstant: 380).isActive = true
            stack.addArrangedSubview(NSTextField(labelWithString: label)); stack.addArrangedSubview(field); inputs[key] = field
        }
        stack.frame = NSRect(x: 0, y: 0, width: 380, height: 280)
        alert.accessoryView = stack; alert.addButton(withTitle: "Create"); alert.addButton(withTitle: "Cancel")
        alert.buttons[0].isEnabled = false
        let validation = NotificationCenter.default.addObserver(forName: NSControl.textDidChangeNotification, object: nil, queue: .main) { _ in
            alert.buttons[0].isEnabled = inputs.values.allSatisfy {
                let value = $0.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
                return !value.isEmpty && value.count <= 160 && value.rangeOfCharacter(from: .controlCharacters) == nil
            } && ["version", "model_version"].allSatisfy {
                let count = inputs[$0]!.stringValue.components(separatedBy: ".").count
                return count == 2 || count == 3
            }
        }
        alert.beginSheetModal(for: window) { response in
            NotificationCenter.default.removeObserver(validation)
            if response == .alertFirstButtonReturn {
                var data: [String: Any] = ["project_id": projectID]
                for (key, field) in inputs { data[key] = field.stringValue }
                self.action("create-passport", data: data) { result in
                    self.refreshHistory()
                    if let id = result?["passport_id"] as? String { self.message("Passport saved locally", "Selected for future sessions.\n\(id)") }
                }
            }
        }
    }
    private func selectPassport(_ projectID: String, registry: String? = nil) {
        action("passport-options", data: ["registry": registry as Any? ?? NSNull()]) { result in
            guard let choices = result?["passports"] as? [[String: String]] else { return }
            let alert = NSAlert(); alert.messageText = "Use existing Passport"
            alert.informativeText = choices.isEmpty
                ? "No usable Passport found here. Create one locally or choose another registry."
                : "Choose a saved local identity for future sessions."
            if (result?["skipped"] as? Int ?? 0) + (result?["unavailable_registries"] as? Int ?? 0) > 0 {
                alert.informativeText += " Some entries could not be checked."
            }
            let picker = NSPopUpButton(frame: NSRect(x: 0, y: 0, width: 460, height: 30), pullsDown: false)
            for item in choices {
                picker.addItem(withTitle: "\(item["name"] ?? "Passport") · v\(item["version"] ?? "") · \((item["id"] ?? "").prefix(12))…")
                picker.lastItem?.toolTip = item["registry"]
            }
            alert.accessoryView = picker
            for title in ["Select", "Other registry…", "Cancel"] { alert.addButton(withTitle: title) }
            alert.buttons[0].isEnabled = !choices.isEmpty
            alert.beginSheetModal(for: self.window) { answer in
                if answer == .alertFirstButtonReturn && !choices.isEmpty {
                    let chosen = choices[picker.indexOfSelectedItem]
                    self.action("select-passport", data: ["project_id": projectID, "registry": chosen["registry"]!, "passport_id": chosen["id"]!]) { _ in self.refreshHistory() }
                } else if answer == .alertSecondButtonReturn {
                    self.chooseRegistry(projectID, current: registry)
                }
            }
        }
    }
    private func chooseRegistry(_ projectID: String, current: String?) {
        let alert = NSAlert(); alert.messageText = "Open a local registry"
        alert.informativeText = "Enter the folder containing your existing agents and models."
        let field = NSTextField(string: current ?? "~/.forkit/registry")
        field.frame = NSRect(x: 0, y: 0, width: 460, height: 26); field.setAccessibilityLabel("Registry folder")
        alert.accessoryView = field; alert.addButton(withTitle: "Open"); alert.addButton(withTitle: "Cancel")
        alert.beginSheetModal(for: window) { response in
            if response == .alertFirstButtonReturn { self.selectPassport(projectID, registry: field.stringValue) }
        }
    }
    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = navigationAction.request.url else { decisionHandler(.cancel); return }
        if navigationAction.shouldPerformDownload && url.scheme == "blob" { decisionHandler(.download); return }
        if url.isFileURL, let current = currentFile,
            url.path == current.path { decisionHandler(.allow); return }
        // The private viewer has no remote content or external navigation.
        decisionHandler(.cancel)
    }
    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        if let state = restoredState, JSONSerialization.isValidJSONObject(state),
            let bytes = try? JSONSerialization.data(withJSONObject: state), let json = String(data: bytes, encoding: .utf8) {
            webView.evaluateJavaScript("window.forkitRestoreView(\(json))", completionHandler: nil)
        }
        restoredState = nil; refreshing = false
        if initialViewPending {
            initialViewPending = false
            loadUsagePreference(countOpening: window.isKeyWindow)
        }
        if refreshAgain { refreshAgain = false; refreshHistory() }
    }
    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) { refreshing = false }
    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        refreshing = false; message("History could not open", "Your saved receipts are preserved. Use Refresh to try again.")
    }
    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) { download.delegate = self }
    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse, suggestedFilename: String, completionHandler: @escaping (URL?) -> Void) {
        // One click saves to a private local folder. Never reuse a filename or
        // silently write into a cloud-backed Documents/Downloads preference.
        do {
            let directory = store.appendingPathComponent("exports", isDirectory: true)
            let manager = FileManager.default
            if !manager.fileExists(atPath: directory.path) {
                try manager.createDirectory(at: directory, withIntermediateDirectories: false,
                    attributes: [.posixPermissions: 0o700])
            }
            var info = stat()
            guard lstat(directory.path, &info) == 0, info.st_mode & S_IFMT == S_IFDIR,
                info.st_uid == geteuid(), info.st_mode & 0o077 == 0
            else { throw CocoaError(.fileWriteNoPermission) }
            let isJSON = suggestedFilename.hasSuffix(".json")
            let name = (isJSON ? "forkit-private-receipt-" : "forkit-session-card-")
                + UUID().uuidString.lowercased() + (isJSON ? ".json" : ".html")
            let destination = directory.appendingPathComponent(name)
            downloadDestinations[ObjectIdentifier(download)] = destination
            completionHandler(destination)
        } catch {
            cancelledDownloads.insert(ObjectIdentifier(download))
            exportStatus("Export could not be saved. Check access to Forkit’s local data folder, then try again.")
            completionHandler(nil)
        }
    }
    func downloadDidFinish(_ download: WKDownload) {
        let destination = downloadDestinations.removeValue(forKey: ObjectIdentifier(download))
        if let destination = destination {
            do { try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: destination.path) }
            catch { exportStatus("Export saved in the private folder; file permissions need attention."); return }
        }
        self.exportStatus(destination?.pathExtension == "json" ? "Private receipt saved locally." : "Saved locally. Open the card to save PNG or SVG.")
        if destination?.pathExtension == "html" { countUsage("card") }
        if let destination = destination { NSWorkspace.shared.activateFileViewerSelecting([destination]) }
    }
    func download(_ download: WKDownload, didFailWithError error: Error, resumeData: Data?) {
        let id = ObjectIdentifier(download)
        downloadDestinations.removeValue(forKey: id)
        if cancelledDownloads.remove(id) == nil { exportStatus("Export did not finish. Try again.") }
    }
    private func exportStatus(_ message: String) {
        if let data = try? JSONSerialization.data(withJSONObject: [message]), let json = String(data: data, encoding: .utf8) {
            web.evaluateJavaScript("window.forkitExportStatus(\(json)[0])", completionHandler: nil)
        }
    }
}

let app = NSApplication.shared
let delegate = ForkitApp()
app.delegate = delegate
app.run()
