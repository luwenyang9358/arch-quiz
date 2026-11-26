import Cocoa
import WebKit

let supportDir = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
    .appendingPathComponent("JiaGouShuaTi", isDirectory: true)
let stateFile = supportDir.appendingPathComponent("progress.json")

func saveExport(name: String, content: String, fmt: String) {
    let panel = NSSavePanel()
    panel.nameFieldStringValue = name
    panel.canCreateDirectories = true
    panel.title = "导出"
    panel.begin { resp in
        guard resp == .OK, let url = panel.url else { return }
        do {
            if fmt == "docx" {
                try writeDocx(content, to: url)
            } else {
                try content.write(to: url, atomically: true, encoding: .utf8)
            }
        } catch {
            let a = NSAlert()
            a.messageText = "导出失败"
            a.informativeText = error.localizedDescription
            a.runModal()
        }
    }
}

func readState() -> String {
    try? FileManager.default.createDirectory(at: supportDir, withIntermediateDirectories: true)
    if let d = try? Data(contentsOf: stateFile), let s = String(data: d, encoding: .utf8), !s.isEmpty {
        return s
    }
    return "{}"
}

final class Bridge: NSObject, WKScriptMessageHandler {
    func userContentController(_ ucc: WKUserContentController, didReceive message: WKScriptMessage) {
        if message.name == "open" {
            if let u = message.body as? String { NSWorkspace.shared.open(URL(string: u)!) }
            return
        }
        if message.name == "exportFile" {
            guard let d = message.body as? [String: Any],
                  let name = d["filename"] as? String,
                  let content = d["content"] as? String,
                  let fmt = d["fmt"] as? String else { return }
            DispatchQueue.main.async { saveExport(name: name, content: content, fmt: fmt) }
            return
        }
        guard let s = message.body as? String else { return }
        try? s.write(to: stateFile, atomically: true, encoding: .utf8)
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate {
    var window: NSWindow!
    var web: WKWebView!

    func applicationDidFinishLaunching(_ note: Notification) {
        buildMenu()

        let cfg = WKWebViewConfiguration()
        let ucc = WKUserContentController()
        let bridge = Bridge()
        ucc.add(bridge, name: "store")
        ucc.add(bridge, name: "open")
        ucc.add(bridge, name: "exportFile")

        let state = readState()
        if let d = try? JSONSerialization.data(withJSONObject: state, options: .fragmentsAllowed),
           let js = String(data: d, encoding: .utf8) {
            ucc.addUserScript(WKUserScript(source: "window.__INIT__ = \(js);",
                                           injectionTime: .atDocumentStart,
                                           forMainFrameOnly: true))
        }
        cfg.userContentController = ucc

        let rect = NSRect(x: 0, y: 0, width: 1180, height: 840)
        window = NSWindow(contentRect: rect,
                          styleMask: [.titled, .closable, .miniaturizable, .resizable],
                          backing: .buffered, defer: false)
        window.title = "架构刷题"
        window.minSize = NSSize(width: 880, height: 620)
        window.titlebarAppearsTransparent = false
        window.setFrameAutosaveName("MainWindow")
        window.center()

        web = WKWebView(frame: rect, configuration: cfg)
        web.autoresizingMask = [.width, .height]
        web.navigationDelegate = self
        window.contentView = web

        if let url = Bundle.main.url(forResource: "app", withExtension: "html") {
            web.loadFileURL(url, allowingReadAccessTo: url.deletingLastPathComponent())
        }
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func webView(_ webView: WKWebView, decidePolicyFor navAction: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if let url = navAction.request.url,
           navAction.navigationType == .linkActivated,
           url.scheme == "http" || url.scheme == "https" {
            NSWorkspace.shared.open(url)
            decisionHandler(.cancel)
            return
        }
        decisionHandler(.allow)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    private func buildMenu() {
        let bar = NSMenu()

        let appItem = NSMenuItem()
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "关于架构刷题", action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "隐藏架构刷题", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "退出架构刷题", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = appMenu
        bar.addItem(appItem)

        let editItem = NSMenuItem()
        let edit = NSMenu(title: "编辑")
        edit.addItem(withTitle: "复制", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        edit.addItem(withTitle: "全选", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        editItem.submenu = edit
        bar.addItem(editItem)

        let winItem = NSMenuItem()
        let winMenu = NSMenu(title: "窗口")
        winMenu.addItem(withTitle: "最小化", action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m")
        winMenu.addItem(withTitle: "缩放", action: #selector(NSWindow.performZoom(_:)), keyEquivalent: "")
        winItem.submenu = winMenu
        bar.addItem(winItem)

        NSApp.mainMenu = bar
    }
}

if CommandLine.arguments.contains("--test-docx") {
    let sample = """
    # 系统架构设计师 · 错题本
    # 导出时间 2026-11-26 ｜ 共 2 题

    ## 1. 2024下半 第26题　【软件架构】
    在软件架构风格中，（ ）由一组构件和一组连接件组成。
    - A．管道-过滤器风格
    - B．事件驱动风格
    正确答案：A
    解析：过滤器处理数据，数据以流的形式传输。
    """
    do {
        try writeDocx(sample, to: URL(fileURLWithPath: "/tmp/test.docx"))
        print("DOCX OK")
    } catch { print("DOCX FAIL", error) }
    exit(0)
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
