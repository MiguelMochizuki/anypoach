import SwiftUI
import AppKit
import UniformTypeIdentifiers
import OSLog

@main
struct PoachApp: App {
    private static let captureLog = Logger(subsystem: "dev.poach.app", category: "CaptureLifecycle")
    @State private var captureHotKey = PoachHotKey()
    @State private var hotKeyAvailable = true
    @State private var hudWindow = FloatingHUDWindowController()
    @State private var recordingWindow = RecordingStatusWindowController()
    @State private var captureServiceStorage: AnyObject?
    @State private var captureMode = PoachCaptureMode(rawValue: UserDefaults.standard.string(forKey: "defaultCaptureMode") ?? "") ?? .selectedPortion
    @AppStorage("defaultCaptureMode") private var defaultMode = PoachCaptureMode.selectedPortion.rawValue
    @State private var isWorking = false
    @State private var workingTitle = "Preparing your capture…"
    @State private var isRecording = false
    @State private var elapsedSeconds = 0

    var body: some Scene {
        Window("Poach", id: "main") {
            PoachHomeView(
                isWorking: isWorking,
                workingTitle: workingTitle,
                isRecording: isRecording,
                elapsedSeconds: elapsedSeconds,
                captureMode: $captureMode,
                onStartRecording: startRecording,
                onStopRecording: { Task { await stopRecording() } },
                onLoadMedia: loadMedia,
                onDropMedia: loadMedia(at:)
            )
            .background(HomeWindowAnchor())
            .onChange(of: defaultMode) { captureMode = PoachCaptureMode(rawValue: defaultMode) ?? .selectedPortion }
            .onAppear {
                hotKeyAvailable = captureHotKey.register {
                    if isRecording { Task { await stopRecording() } }
                    else if !isWorking {
                        captureMode = .selectedPortion
                        startRecording()
                    }
                }
            }
        }
        .defaultSize(width: 440, height: 278)
        .windowResizability(.contentSize)
        .windowStyle(.hiddenTitleBar)

        MenuBarExtra {
            VStack(alignment: .leading, spacing: 12) {
                Label("Poach", systemImage: "record.circle")
                    .font(.system(size: 13, weight: .semibold, design: .rounded))
                Button(isRecording ? "Stop and inspect" : "Start recording") {
                    if isRecording { Task { await stopRecording() } }
                    else { startRecording() }
                }
                .buttonStyle(.borderedProminent)
                .disabled(isWorking)

                Text(hotKeyAvailable ? "⌘⇧P — Select area or stop recording" : "⌘⇧P is unavailable. Use the recording button.")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                Button("Load video or image…", action: loadMedia)
                    .buttonStyle(.plain)
                    .disabled(isWorking || isRecording)
            }
            .padding(16)
            .frame(width: 240)
            .preferredColorScheme(.light)
        } label: {
            ZStack {
                PoachPouchShape()
                    .stroke(.primary, style: StrokeStyle(lineWidth: 1.4, lineCap: .round, lineJoin: .round))
                PoachBagDetails()
                    .stroke(.primary, style: StrokeStyle(lineWidth: 1.05, lineCap: .round, lineJoin: .round))
                PoachLootPixels().fill(.primary)
            }
            .frame(width: 18, height: 18)
        }
        .menuBarExtraStyle(.window)
    }

    private func loadMedia() {
        let picker = NSOpenPanel()
        picker.title = "Load a video or image"
        picker.prompt = "Load"
        picker.allowedContentTypes = [.mpeg4Movie, .quickTimeMovie, .png, .jpeg, .tiff, .webP, .bmp]
        picker.allowsOtherFileTypes = false
        picker.canChooseDirectories = false
        picker.canChooseFiles = true
        guard picker.runModal() == .OK, let mediaURL = picker.url else { return }

        loadMedia(at: mediaURL)
    }

    private func loadMedia(at mediaURL: URL) {
        guard !isWorking, !isRecording, mediaURL.isFileURL else { return }
        workingTitle = "Analyzing your media…"
        isWorking = true
        hudWindow.showPreparing()
        Task {
            do {
                let result = try await PoachInspectionRunner.inspect(videoURL: mediaURL)
                hudWindow.show(result)
            } catch {
                showError(title: "Poach couldn't load this media", error: error)
            }
            isWorking = false
        }
    }

    private func startRecording() {
        guard !isWorking, !isRecording else { return }
        Self.captureLog.notice("Capture selection requested")
        workingTitle = "Preparing your capture…"
        isWorking = true
        Task {
            do {
                guard #available(macOS 15.0, *) else { throw ScreenCaptureError.requiresNewerMacOS }
                let service = ScreenCaptureService()
                captureServiceStorage = service
                try await service.startRecording(mode: captureMode) {
                    try await recordingWindow.countDown()
                }

                NSApp.unhide(nil)
                NSApp.windows.filter { $0.title == "Poach" }.forEach { $0.orderOut(nil) }
                isWorking = false
                isRecording = true
                Self.captureLog.notice("Recording started")
                elapsedSeconds = 0
                recordingWindow.show(elapsedSeconds: 0) { Task { await stopRecording() } }

                while isRecording && elapsedSeconds < 30 {
                    try? await Task.sleep(for: .seconds(1))
                    guard isRecording else { break }
                    elapsedSeconds += 1
                    recordingWindow.update(elapsedSeconds: elapsedSeconds)
                }
                if isRecording { await stopRecording() }
            } catch {
                if let captureError = error as? ScreenCaptureError, captureError.isUserCancelled {
                    Self.captureLog.notice("Capture selection cancelled")
                    isWorking = false
                    captureServiceStorage = nil
                    NSApp.unhide(nil)
                    NSApp.windows.first { $0.title == "Poach" }?.makeKeyAndOrderFront(nil)
                    return
                }
                NSApp.unhide(nil)
                NSApp.activate(ignoringOtherApps: true)
                Self.captureLog.error("Capture start failed: code \((error as NSError).code)")
                showCaptureStartError(error)
                isWorking = false
                captureServiceStorage = nil
            }
        }
    }

    private func stopRecording() async {
        guard #available(macOS 15.0, *) else { return }
        guard isRecording, let service = captureServiceStorage as? ScreenCaptureService else { return }
        Self.captureLog.notice("Recording stop requested")
        isRecording = false
        workingTitle = "Analyzing your recording…"
        isWorking = true
        recordingWindow.showFinishing()
        do {
            let videoURL = try await service.stopRecording()
            Self.captureLog.notice("Recording file finalized")
            captureServiceStorage = nil
            NSApp.unhide(nil)
            NSApp.activate(ignoringOtherApps: true)
            hudWindow.showPreparing()
            recordingWindow.close()
            let result = try await PoachInspectionRunner.inspect(videoURL: videoURL, isRecording: true)
            Self.captureLog.notice("Recording analysis completed")
            hudWindow.show(result)
            Self.captureLog.notice("Review editor presented")
        } catch {
            NSApp.unhide(nil)
            NSApp.activate(ignoringOtherApps: true)
            recordingWindow.close()
            Self.captureLog.error("Capture processing failed: code \((error as NSError).code)")
            showError(title: "Poach couldn't finish this capture", error: error)
            captureServiceStorage = nil
        }
        isWorking = false
    }

    private func showError(title: String, error: Error) {
        hudWindow.dismissPreparing()
        let alert = NSAlert()
        alert.messageText = title
        alert.informativeText = error.localizedDescription
        alert.alertStyle = .warning
        alert.runModal()
    }

    private func showCaptureStartError(_ error: Error) {
        let nsError = error as NSError
        let isPermissionDenied: Bool
        if let captureError = error as? ScreenCaptureError, case .permissionDenied = captureError {
            isPermissionDenied = true
        } else {
            isPermissionDenied = nsError.domain == "SCStreamErrorDomain" && nsError.code == -3801
        }
        guard isPermissionDenied else {
            showError(title: "Poach couldn't start recording", error: error)
            return
        }

        let alert = NSAlert()
        alert.messageText = "Allow screen recording for Poach"
        alert.informativeText = "macOS denied screen capture. Open Privacy & Security → Screen & System Audio Recording and enable Poach, then quit and reopen it. If Poach is already enabled, remove its entry and add this copy of Poach again. A rebuilt development app may need a fresh approval."
        alert.alertStyle = .informational
        alert.addButton(withTitle: "Open Settings")
        alert.addButton(withTitle: "Not now")
        if alert.runModal() == .alertFirstButtonReturn,
           let settingsURL = URL(string: "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_ScreenCapture") {
            NSWorkspace.shared.open(settingsURL)
        }
    }
}

private extension ScreenCaptureError {
    var isUserCancelled: Bool {
        if case .selectionCancelled = self { return true }
        return false
    }
}

@MainActor
private final class RecordingStatusWindowController {
    private var panel: NSPanel?
    private var stopAction: (() -> Void)?

    func countDown() async throws {
        var cancelled = false
        let countdownPanel = makePanel()
        countdownPanel.setContentSize(NSSize(width: 260, height: 150))
        pinToEdge(countdownPanel)
        NSApp.unhide(nil)
        NSApp.windows.filter { $0.title == "Poach" }.forEach { $0.orderOut(nil) }
        defer { countdownPanel.orderOut(nil) }
        for count in stride(from: 3, through: 1, by: -1) {
            countdownPanel.contentView = NSHostingView(rootView:
                VStack(spacing: 10) {
                    Text("Recording starts in")
                    Text("\(count)").font(.system(size: 48, weight: .bold, design: .rounded))
                        .foregroundStyle(.red)
                    Button { cancelled = true } label: {
                        Image(systemName: "xmark").padding(6)
                    }
                    .accessibilityLabel("Cancel recording")
                    .keyboardShortcut(.cancelAction)
                }
                .frame(width: 260, height: 150)
                .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 18))
                .preferredColorScheme(.light)
            )
            countdownPanel.makeKeyAndOrderFront(nil)
            try await Task.sleep(for: .seconds(1))
            if cancelled { throw ScreenCaptureError.selectionCancelled }
        }
    }

    func show(elapsedSeconds: Int, onStop: @escaping () -> Void) {
        stopAction = onStop
        let panel = self.panel ?? makePanel()
        panel.contentView = NSHostingView(rootView: PoachRecordingStatusView(elapsedSeconds: elapsedSeconds) { [weak self] in
            self?.stopAction?()
        })
        pinToEdge(panel)
        panel.orderFrontRegardless()
        self.panel = panel
    }

    func update(elapsedSeconds: Int) {
        guard let panel else { return }
        panel.contentView = NSHostingView(rootView: PoachRecordingStatusView(elapsedSeconds: elapsedSeconds) { [weak self] in
            self?.stopAction?()
        })
    }

    func showFinishing() {
        stopAction = nil
        panel?.contentView = NSHostingView(rootView:
            HStack {
                ProgressView().controlSize(.small)
                Text("Finishing recording…")
            }
            .frame(width: 260, height: 58)
            .background(Color(nsColor: .windowBackgroundColor), in: RoundedRectangle(cornerRadius: 12))
            .preferredColorScheme(.light)
        )
    }

    func close() {
        panel?.orderOut(nil)
        panel = nil
        stopAction = nil
    }

    private func makePanel() -> NSPanel {
        let panel = EditableBriefPanel(
            contentRect: NSRect(x: 0, y: 0, width: 260, height: 58),
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )
        panel.isMovable = false
        panel.level = .floating
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .ignoresCycle]
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = false
        panel.becomesKeyOnlyIfNeeded = true
        panel.isReleasedWhenClosed = false
        return panel
    }
}

@MainActor
private final class FloatingHUDWindowController {
    private var panel: NSPanel?

    func showPreparing() {
        let panel = self.panel ?? makePanel()
        panel.title = "Poach — Preparing your brief"
        panel.contentView = NSHostingView(rootView:
            VStack(spacing: 16) {
                ProgressView()
                Text("Preparing your capture for review").font(.headline)
                Text("Preparing the editor…").foregroundStyle(.secondary)
            }
            .frame(width: 660, height: 500)
            .background(Color(nsColor: .windowBackgroundColor))
            .preferredColorScheme(.light)
        )
        panel.setContentSize(NSSize(width: 660, height: 500))
        pinToEdge(panel)
        NSApp.windows.filter { $0.title == "Poach" }.forEach { $0.orderOut(nil) }
        panel.makeKeyAndOrderFront(nil)
        self.panel = panel
    }

    func dismissPreparing() {
        guard panel?.title == "Poach — Preparing your brief" else { return }
        panel?.orderOut(nil)
        NSApp.windows.first { $0.title == "Poach" }?.makeKeyAndOrderFront(nil)
    }

    func show(_ result: PoachInspection) {
        let palette = result.palette.map { HUDPaletteToken(hex: $0, color: Color(hex: $0)) }
        let view = FloatingHUDView(
            sourceURL: URL(fileURLWithPath: result.sourcePath),
            isVideo: result.mediaType != "image",
            palette: palette,
            onCopyContext: { Self.copyContext(result, context: $0) },
            onShareContext: { try Self.shareContext(result, context: $0) },
            onClose: { [weak self] in
                self?.panel?.orderOut(nil)
                NSApp.windows.first { $0.title == "Poach" }?.makeKeyAndOrderFront(nil)
            }
        )

        let panel = self.panel ?? makePanel()
        panel.title = "Poach — Implementation brief"
        panel.contentView = NSHostingView(rootView: view.id(UUID()))
        panel.setContentSize(panel.contentView?.fittingSize ?? NSSize(width: 340, height: 370))
        pinToEdge(panel)
        panel.alphaValue = 0
        NSApp.windows.filter { $0.title == "Poach" }.forEach { $0.orderOut(nil) }
        NSApp.activate(ignoringOtherApps: true)
        panel.makeKeyAndOrderFront(nil)
        NSAnimationContext.runAnimationGroup { context in
            context.duration = 0.22
            panel.animator().alphaValue = 1
        }
        self.panel = panel
    }

    private func makePanel() -> NSPanel {
        let panel = EditableBriefPanel(
            contentRect: NSRect(x: 0, y: 0, width: 660, height: 720),
            styleMask: [.titled, .closable, .miniaturizable],
            backing: .buffered,
            defer: false
        )
        panel.isFloatingPanel = false
        panel.level = .normal
        panel.collectionBehavior = [.moveToActiveSpace]
        panel.isOpaque = true
        panel.appearance = NSAppearance(named: .aqua)
        panel.backgroundColor = .windowBackgroundColor
        panel.hasShadow = true
        panel.isMovable = false
        panel.becomesKeyOnlyIfNeeded = true
        panel.isReleasedWhenClosed = false
        return panel
    }

    private static func copyContext(_ result: PoachInspection, context: String) {
        guard let data = try? JSONEncoder().encode(result), let text = String(data: data, encoding: .utf8) else { return }
        let pasteboard = NSPasteboard.general
        pasteboard.clearContents()
        let prompt = """
        Recreate the UI component described by this Poach capture in the current project.
        Inspect the referenced keyframes before implementing. Preserve the observed layout,
        colors, pointer-triggered behavior, and motion. Timing and easing are estimates;
        distinguish visible evidence from assumptions and ask about ambiguous behavior.

        Additional context from the user:
        \(context.isEmpty ? "No additional context." : context)

        Capture evidence (local file paths require access to this Mac):
        \(text)
        """
        pasteboard.setString(prompt, forType: .string)
    }

    private static func shareContext(_ result: PoachInspection, context: String) throws {
        let directory = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Caches/Poach", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true,
            attributes: [.posixPermissions: 0o700])
        let evidence = try JSONSerialization.jsonObject(with: JSONEncoder().encode(result))
        let brief: [String: Any] = [
            "version": 1,
            "sharedAt": Date().timeIntervalSince1970,
            "context": context,
            "instruction": "Recreate this UI in the current project. Inspect the keyframes, preserve observed behavior and colors, and treat timing estimates as approximate. Ask about ambiguous behavior.",
            "evidence": evidence
        ]
        let destination = directory.appendingPathComponent("active-brief.json")
        try JSONSerialization.data(withJSONObject: brief, options: [.sortedKeys]).write(to: destination, options: .atomic)
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: destination.path)
    }
}

private final class EditableBriefPanel: NSPanel {
    override var canBecomeKey: Bool { true }
}

private extension Color {
    init(hex: String) {
        let cleaned = hex.trimmingCharacters(in: CharacterSet(charactersIn: "#"))
        let value = UInt64(cleaned, radix: 16) ?? 0
        self.init(
            .sRGB,
            red: Double((value >> 16) & 0xFF) / 255,
            green: Double((value >> 8) & 0xFF) / 255,
            blue: Double(value & 0xFF) / 255,
            opacity: 1
        )
    }
}

@MainActor
func pinToEdge(_ window: NSWindow) {
    guard let visible = (window.screen ?? NSScreen.main)?.visibleFrame else { return }
    window.isMovable = false
    let left = UserDefaults.standard.string(forKey: "windowEdge") == "left"
    window.setFrameOrigin(NSPoint(x: left ? visible.minX + 16 : max(visible.minX, visible.maxX - window.frame.width - 16),
                                  y: max(visible.minY, visible.midY - window.frame.height / 2)))
}

private struct HomeWindowAnchor: NSViewRepresentable {
    final class Anchor: NSView {
        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            if let window { DispatchQueue.main.async { pinToEdge(window) } }
        }
    }
    func makeNSView(context: Context) -> Anchor { Anchor() }
    func updateNSView(_ view: Anchor, context: Context) {}
}
