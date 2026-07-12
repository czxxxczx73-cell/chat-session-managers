import AppKit
import Foundation
import WebKit

enum HostError: LocalizedError {
    case pythonMissing
    case serverFailed(String)

    var errorDescription: String? {
        switch self {
        case .pythonMissing:
            return "Python 3.9 or later is required. Install Python from python.org or Homebrew, then reopen the App."
        case .serverFailed(let message):
            return "The local session service could not start.\n\n\(message)"
        }
    }
}

final class NavigationGuard: NSObject, WKNavigationDelegate {
    func webView(
        _ webView: WKWebView,
        decidePolicyFor navigationAction: WKNavigationAction,
        decisionHandler: @escaping (WKNavigationActionPolicy) -> Void
    ) {
        guard let url = navigationAction.request.url else {
            decisionHandler(.cancel)
            return
        }
        let localFile = url.isFileURL
        let localHTTP = ["127.0.0.1", "localhost"].contains(url.host ?? "")
        decisionHandler(localFile || localHTTP ? .allow : .cancel)
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var window: NSWindow!
    private var webView: WKWebView!
    private var server: Process?
    private let navigationGuard = NavigationGuard()

    private var productName: String {
        Bundle.main.localizedInfoDictionary?["CFBundleDisplayName"] as? String
            ?? Bundle.main.object(forInfoDictionaryKey: "CFBundleDisplayName") as? String
            ?? "Chat Session Manager"
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .nonPersistent()
        webView = WKWebView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = navigationGuard

        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 1180, height: 800),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        window.title = productName
        window.minSize = NSSize(width: 820, height: 560)
        window.center()
        window.contentView = webView
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        installMenu()
        showLoading()

        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            self?.startLocalService()
        }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    func applicationWillTerminate(_ notification: Notification) {
        server?.terminate()
        if server?.isRunning == true {
            Thread.sleep(forTimeInterval: 0.1)
            server?.interrupt()
        }
    }

    private func startLocalService() {
        do {
            let python = try findPython()
            let port = try freePort(using: python)
            let resources = Bundle.main.resourceURL!
            let script = resources.appendingPathComponent("server.py")
            let process = Process()
            process.executableURL = URL(fileURLWithPath: python)
            process.arguments = [script.path]
            var environment = ProcessInfo.processInfo.environment
            environment["PORT"] = String(port)
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            environment["PYTHONUNBUFFERED"] = "1"
            environment["SESSION_MANAGER_EMBEDDED"] = "1"
            environment["SESSION_MANAGER_PARENT_PID"] = String(ProcessInfo.processInfo.processIdentifier)
            process.environment = environment

            let logURL = FileManager.default.homeDirectoryForCurrentUser
                .appendingPathComponent("Library/Logs", isDirectory: true)
                .appendingPathComponent("\(Bundle.main.bundleIdentifier ?? "ChatSessionManager").log")
            try? FileManager.default.createDirectory(at: logURL.deletingLastPathComponent(), withIntermediateDirectories: true)
            if !FileManager.default.fileExists(atPath: logURL.path) {
                FileManager.default.createFile(atPath: logURL.path, contents: nil)
            }
            let log = try? FileHandle(forWritingTo: logURL)
            _ = try? log?.seekToEnd()
            process.standardOutput = log
            process.standardError = log
            try process.run()
            server = process

            let url = URL(string: "http://127.0.0.1:\(port)/")!
            guard waitUntilReady(url: url, process: process) else {
                throw HostError.serverFailed("See \(logURL.path)")
            }
            DispatchQueue.main.async { [weak self] in
                self?.webView.load(URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData))
            }
        } catch {
            DispatchQueue.main.async { [weak self] in self?.showError(error.localizedDescription) }
        }
    }

    private func findPython() throws -> String {
        var candidates: [String] = []
        if let override = ProcessInfo.processInfo.environment["SESSION_MANAGER_PYTHON"], !override.isEmpty {
            candidates.append(override)
        }
        candidates += ["/opt/homebrew/bin/python3", "/usr/local/bin/python3", "/usr/bin/python3"]
        let paths = (ProcessInfo.processInfo.environment["PATH"] ?? "")
            .split(separator: ":").map { "\($0)/python3" }
        candidates += paths

        for candidate in candidates where FileManager.default.isExecutableFile(atPath: candidate) {
            let process = Process()
            process.executableURL = URL(fileURLWithPath: candidate)
            process.arguments = ["-c", "import sys; raise SystemExit(0 if sys.version_info >= (3,9) else 1)"]
            process.standardOutput = Pipe()
            process.standardError = Pipe()
            if (try? process.run()) != nil {
                process.waitUntilExit()
                if process.terminationStatus == 0 { return candidate }
            }
        }
        throw HostError.pythonMissing
    }

    private func freePort(using python: String) throws -> Int {
        let process = Process()
        let output = Pipe()
        process.executableURL = URL(fileURLWithPath: python)
        process.arguments = ["-c", "import socket; s=socket.socket(); s.bind(('127.0.0.1',0)); print(s.getsockname()[1]); s.close()"]
        process.standardOutput = output
        process.standardError = Pipe()
        try process.run()
        process.waitUntilExit()
        let data = output.fileHandleForReading.readDataToEndOfFile()
        guard process.terminationStatus == 0,
              let text = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines),
              let port = Int(text) else { throw HostError.serverFailed("Could not reserve a loopback port.") }
        return port
    }

    private func waitUntilReady(url: URL, process: Process) -> Bool {
        let deadline = Date().addingTimeInterval(8)
        while Date() < deadline, process.isRunning {
            if let data = try? Data(contentsOf: url), !data.isEmpty { return true }
            Thread.sleep(forTimeInterval: 0.08)
        }
        return false
    }

    private func showLoading() {
        webView.loadHTMLString("""
        <!doctype html><meta charset="utf-8"><style>
        body{margin:0;background:#0d0f13;color:#d9dde7;font:15px -apple-system;display:grid;place-items:center;height:100vh}
        div{text-align:center;line-height:1.8}.dot{color:#7c8cff}
        </style><div><span class="dot">●</span> Starting local session manager…<br><small>No conversation data is uploaded.</small></div>
        """, baseURL: nil)
    }

    private func showError(_ message: String) {
        let escaped = message
            .replacingOccurrences(of: "&", with: "&amp;")
            .replacingOccurrences(of: "<", with: "&lt;")
            .replacingOccurrences(of: ">", with: "&gt;")
        webView.loadHTMLString("""
        <!doctype html><meta charset="utf-8"><style>
        body{margin:0;background:#0d0f13;color:#e7e9ef;font:15px -apple-system;display:grid;place-items:center;height:100vh}
        div{max-width:620px;padding:32px;line-height:1.6}h2{color:#ff8b72}
        </style><div><h2>\(productName)</h2><p>\(escaped)</p></div>
        """, baseURL: nil)
    }

    private func installMenu() {
        let main = NSMenu()
        let appItem = NSMenuItem()
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "About \(productName)", action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Quit \(productName)", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = appMenu
        main.addItem(appItem)
        NSApp.mainMenu = main
    }
}

let application = NSApplication.shared
let delegate = AppDelegate()
application.delegate = delegate
application.setActivationPolicy(.regular)
application.run()
