import AppKit
import Foundation
import ScreenCaptureKit
import SwiftUI

enum PoachCaptureMode: String, CaseIterable, Identifiable {
    case selectedPortion
    case fullScreen
    case window

    var id: String { rawValue }

    var title: String {
        switch self {
        case .selectedPortion: "Selected portion"
        case .fullScreen: "Full screen"
        case .window: "Window"
        }
    }

    var guidance: String {
        switch self {
        case .selectedPortion: "Select an area, then click the red record button. Recording starts after three seconds."
        case .fullScreen: "Choose the display you want to capture."
        case .window: "Choose the app window you want to capture."
        }
    }
}

enum ScreenCaptureError: LocalizedError {
    case requiresNewerMacOS
    case permissionDenied
    case selectionCancelled
    case selectionFailed(String)
    case noDisplay
    case recordingUnavailable
    case notRecording
    case emptyRecording

    var errorDescription: String? {
        switch self {
        case .requiresNewerMacOS:
            "Screen recording requires macOS 15 or later. You can still load an existing video or image."
        case .permissionDenied:
            "Poach needs Screen & System Audio Recording access. Enable Poach in System Settings > Privacy & Security, then quit and reopen the app."
        case .selectionCancelled:
            "Capture selection was cancelled."
        case .selectionFailed(let message): message
        case .noDisplay:
            "Poach couldn't find the selected display. Connect a display and try again."
        case .recordingUnavailable:
            "This Mac doesn't report a compatible screen recording format."
        case .notRecording:
            "There isn't an active recording to stop."
        case .emptyRecording:
            "No video frames were recorded. Check Screen Recording access in System Settings and try again."
        }
    }
}

@available(macOS 15.0, *)
@MainActor
final class ScreenCaptureService: NSObject, SCRecordingOutputDelegate, SCContentSharingPickerObserver {
    private var stream: SCStream?
    private var outputURL: URL?
    private var pickerContinuation: CheckedContinuation<ContentFilterBox, Error>?
    private var activePicker: SCContentSharingPicker?
    private var finishContinuation: CheckedContinuation<Void, Error>?
    private var didFinish = false
    private var recordingError: Error?

    func startRecording(mode: PoachCaptureMode) async throws {
        let selectedRegion: SelectedRegion?
        let filter: SCContentFilter
        if mode == .selectedPortion {
            let region = try await RegionSelectionWindowController.shared.selectRegion()
            let content: SCShareableContent
            do {
                content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
            } catch {
                if Self.isPermissionDenied(error) { throw ScreenCaptureError.permissionDenied }
                throw error
            }
            guard let display = content.displays.first(where: { $0.displayID == region.displayID }) else {
                throw ScreenCaptureError.noDisplay
            }
            let poachApplications = content.applications.filter {
                $0.processID == ProcessInfo.processInfo.processIdentifier
            }
            filter = SCContentFilter(display: display, excludingApplications: poachApplications, exceptingWindows: [])
            selectedRegion = region
        } else {
            filter = try await chooseContent(for: mode).filter
            selectedRegion = nil
        }
        let selectedRect: CGRect?
        selectedRect = selectedRegion?.rect

        let sourceSize = selectedRect?.size ?? filter.contentRect.size
        let scale = CGFloat(filter.pointPixelScale)
        let dimensionScale = min(1, 1920 / max(sourceSize.width * scale, sourceSize.height * scale))
        // H.264 encoders expect even dimensions, including arbitrary dragged regions.
        let width = max(2, Int(sourceSize.width * scale * dimensionScale) / 2 * 2)
        let height = max(2, Int(sourceSize.height * scale * dimensionScale) / 2 * 2)
        let configuration = SCStreamConfiguration()
        configuration.width = width
        configuration.height = height
        configuration.minimumFrameInterval = CMTime(value: 1, timescale: 30)
        configuration.queueDepth = 5
        // Keep both the pointer and Apple's click rings in the recorded pixels. The
        // cursor is part of the interaction being inspected, not just decoration.
        configuration.showsCursor = true
        configuration.showMouseClicks = true
        configuration.capturesAudio = false
        if let selectedRect { configuration.sourceRect = selectedRect }

        let directory = FileManager.default.temporaryDirectory.appending(path: "Poach", directoryHint: .isDirectory)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let url = directory.appending(path: "capture-\(UUID().uuidString).mov")
        let recordingConfiguration = SCRecordingOutputConfiguration()
        guard recordingConfiguration.availableOutputFileTypes.contains(.mov) else {
            throw ScreenCaptureError.recordingUnavailable
        }
        recordingConfiguration.outputURL = url
        recordingConfiguration.outputFileType = .mov
        recordingConfiguration.videoCodecType = recordingConfiguration.availableVideoCodecTypes.contains(.h264)
            ? .h264
            : recordingConfiguration.availableVideoCodecTypes.first ?? .h264

        let stream = SCStream(filter: filter, configuration: configuration, delegate: nil)
        let output = SCRecordingOutput(configuration: recordingConfiguration, delegate: self)
        try stream.addRecordingOutput(output)
        self.stream = stream
        self.outputURL = url
        self.didFinish = false
        self.recordingError = nil

        // Hide the setup UI before the first captured frame.
        NSApp.hide(nil)
        do {
            try await stream.startCapture()
        } catch {
            if Self.isPermissionDenied(error) { throw ScreenCaptureError.permissionDenied }
            throw error
        }
    }

    func stopRecording() async throws -> URL {
        guard let stream, let outputURL else { throw ScreenCaptureError.notRecording }
        try await stream.stopCapture()
        try await waitForRecordingFinish()
        guard FileManager.default.fileExists(atPath: outputURL.path),
              let attributes = try? FileManager.default.attributesOfItem(atPath: outputURL.path),
              ((attributes[.size] as? NSNumber)?.intValue ?? 0) > 0 else {
            throw ScreenCaptureError.emptyRecording
        }
        self.stream = nil
        self.outputURL = nil
        return outputURL
    }

    private func chooseContent(for mode: PoachCaptureMode) async throws -> ContentFilterBox {
        try await withCheckedThrowingContinuation { continuation in
            pickerContinuation = continuation
            var configuration = SCContentSharingPickerConfiguration()
            configuration.allowedPickerModes = mode == .window ? .singleWindow : .singleDisplay
            configuration.excludedBundleIDs = [Bundle.main.bundleIdentifier ?? "dev.poach.app"]
            let picker = SCContentSharingPicker.shared
            activePicker = picker
            picker.defaultConfiguration = configuration
            picker.add(self)
            picker.isActive = true
            picker.present()
        }
    }

    nonisolated func contentSharingPicker(
        _ picker: SCContentSharingPicker,
        didUpdateWith filter: SCContentFilter,
        for stream: SCStream?
    ) {
        let box = ContentFilterBox(filter)
        Task { @MainActor [weak self] in self?.resolvePicker(.success(box)) }
    }

    nonisolated func contentSharingPicker(_ picker: SCContentSharingPicker, didCancelFor stream: SCStream?) {
        Task { @MainActor [weak self] in self?.resolvePicker(.failure(ScreenCaptureError.selectionCancelled)) }
    }

    nonisolated func contentSharingPickerStartDidFailWithError(_ error: Error) {
        let selectionError: ScreenCaptureError = Self.isPermissionDenied(error)
            ? .permissionDenied
            : .selectionFailed(error.localizedDescription)
        Task { @MainActor [weak self] in
            self?.resolvePicker(.failure(selectionError))
        }
    }

    nonisolated private static func isPermissionDenied(_ error: Error) -> Bool {
        let nsError = error as NSError
        if nsError.domain == SCStreamErrorDomain && nsError.code == -3801 { return true }
        if let underlyingError = nsError.userInfo[NSUnderlyingErrorKey] as? Error {
            return isPermissionDenied(underlyingError)
        }
        return false
    }

    nonisolated func recordingOutputDidStartRecording(_ recordingOutput: SCRecordingOutput) {}

    nonisolated func recordingOutputDidFinishRecording(_ recordingOutput: SCRecordingOutput) {
        Task { @MainActor [weak self] in self?.finishRecording(.success(())) }
    }

    nonisolated func recordingOutput(_ recordingOutput: SCRecordingOutput, didFailWithError error: Error) {
        let message = error.localizedDescription
        Task { @MainActor [weak self] in
            self?.finishRecording(.failure(ScreenCaptureServiceError(message: message)))
        }
    }

    private func resolvePicker(_ result: Result<ContentFilterBox, Error>) {
        activePicker?.remove(self)
        activePicker?.isActive = false
        activePicker = nil
        switch result {
        case .success(let filter): pickerContinuation?.resume(returning: filter)
        case .failure(let error): pickerContinuation?.resume(throwing: error)
        }
        pickerContinuation = nil
    }

    private func waitForRecordingFinish() async throws {
        if let recordingError { throw recordingError }
        if didFinish { return }
        try await withCheckedThrowingContinuation { continuation in
            finishContinuation = continuation
        }
    }

    private func finishRecording(_ result: Result<Void, Error>) {
        didFinish = true
        if case .failure(let error) = result { recordingError = error }
        finishContinuation?.resume(with: result)
        finishContinuation = nil
    }
}

private struct ContentFilterBox: @unchecked Sendable {
    let filter: SCContentFilter
    init(_ filter: SCContentFilter) { self.filter = filter }
}

private struct SelectedRegion {
    let displayID: CGDirectDisplayID
    let rect: CGRect
}

private struct ScreenCaptureServiceError: LocalizedError {
    let message: String
    var errorDescription: String? { message }
}

@MainActor
private final class RegionSelectionWindowController {
    static let shared = RegionSelectionWindowController()
    private var panels: [NSPanel] = []
    private var continuation: CheckedContinuation<SelectedRegion, Error>?

    func selectRegion() async throws -> SelectedRegion {
        try await withCheckedThrowingContinuation { continuation in
            self.continuation = continuation
            NSApp.hide(nil)
            for screen in NSScreen.screens {
                guard let displayID = (screen.deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? NSNumber)?.uint32Value else { continue }
                let panel = NSPanel(
                    contentRect: NSRect(origin: .zero, size: screen.frame.size),
                    styleMask: [.borderless, .nonactivatingPanel],
                    backing: .buffered,
                    defer: false
                )
                panel.level = .screenSaver
                panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
                panel.isOpaque = false
                panel.backgroundColor = .clear
                panel.hasShadow = false
                panel.becomesKeyOnlyIfNeeded = true
                panel.contentView = NSHostingView(rootView: RegionSelectionView(
                    onSelect: { [weak self] rect in self?.finish(.success(SelectedRegion(displayID: displayID, rect: rect))) },
                    onCancel: { [weak self] in self?.finish(.failure(ScreenCaptureError.selectionCancelled)) }
                ))
                panel.setFrame(screen.frame, display: true)
                self.panels.append(panel)
                panel.orderFrontRegardless()
            }
            guard !panels.isEmpty else {
                self.continuation = nil
                continuation.resume(throwing: ScreenCaptureError.noDisplay)
                return
            }
            NSApp.activate(ignoringOtherApps: true)
            NSApp.windows
                .filter { $0.title == "Poach" }
                .forEach { $0.orderOut(nil) }
        }
    }

    private func finish(_ result: Result<SelectedRegion, Error>) {
        panels.forEach { $0.orderOut(nil) }
        panels.removeAll()
        if case .failure = result {
            NSApp.unhide(nil)
            NSApp.activate(ignoringOtherApps: true)
            NSApp.windows
                .first(where: { $0.title == "Poach" })?
                .makeKeyAndOrderFront(nil)
        }
        continuation?.resume(with: result)
        continuation = nil
    }
}

private struct RegionSelectionView: View {
    let onSelect: (CGRect) -> Void
    let onCancel: () -> Void
    @State private var origin: CGPoint?
    @State private var current: CGPoint?
    @State private var countdownValue: Int?
    @State private var countdownTask: Task<Void, Never>?

    private var selection: CGRect? {
        guard let origin, let current else { return nil }
        return CGRect(x: min(origin.x, current.x), y: min(origin.y, current.y),
                      width: abs(current.x - origin.x), height: abs(current.y - origin.y))
    }

    var body: some View {
        GeometryReader { geometry in
            ZStack(alignment: .bottom) {
                Canvas { context, size in
                    var mask = Path(CGRect(origin: .zero, size: size))
                    if let selection, selection.width > 3, selection.height > 3 {
                        mask.addRect(selection)
                    }
                    context.fill(mask, with: .color(.black.opacity(0.48)), style: FillStyle(eoFill: true))
                    if let selection {
                        context.stroke(Path(selection), with: .color(.white), lineWidth: 2)
                        context.stroke(Path(selection.insetBy(dx: 3, dy: 3)), with: .color(.white.opacity(0.5)), lineWidth: 1)
                    }
                }
                .contentShape(Rectangle())
                .gesture(DragGesture(minimumDistance: 0, coordinateSpace: .local)
                    .onChanged { value in
                        guard countdownValue == nil else { return }
                        origin = value.startLocation
                        current = value.location
                    })
                    .allowsHitTesting(countdownValue == nil)

                if let countdownValue {
                    Text("\(countdownValue)")
                        .font(.system(size: 96, weight: .bold, design: .rounded).monospacedDigit())
                        .foregroundStyle(.white)
                        .contentTransition(.numericText())
                        .padding(42)
                        .background(.regularMaterial, in: Circle())
                        .overlay {
                            Circle().strokeBorder(.red.opacity(0.9), lineWidth: 5)
                        }
                        .shadow(color: .black.opacity(0.28), radius: 26, y: 10)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        .accessibilityLabel("Recording starts in \(countdownValue) seconds")
                        .allowsHitTesting(false)
                }

                VStack(spacing: 10) {
                    Label(countdownValue != nil ? "Get ready — recording starts shortly" : selection == nil ? "Drag to select an area" : "Adjust the area, then start recording", systemImage: "viewfinder")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(.secondary)

                    HStack(spacing: 10) {
                        Button {
                            countdownTask?.cancel()
                            onCancel()
                        } label: {
                            Image(systemName: "xmark")
                                .font(.system(size: 14, weight: .semibold))
                                .frame(width: 44, height: 44)
                        }
                        .buttonStyle(.plain)
                        .background(.quaternary, in: Circle())
                        .accessibilityLabel("Cancel area selection")
                        .help("Cancel")

                        Button {
                            beginCountdown()
                        } label: {
                            Image(systemName: "record.circle.fill")
                                .font(.system(size: 40, weight: .regular))
                                .foregroundStyle(.red)
                                .frame(width: 52, height: 52)
                                .contentTransition(.symbolEffect(.replace))
                        }
                        .buttonStyle(.plain)
                        .disabled((selection?.width ?? 0) < 32 || (selection?.height ?? 0) < 32 || countdownValue != nil)
                        .accessibilityLabel("Start recording")
                        .help("Start the three-second countdown (Return)")
                        .keyboardShortcut(.defaultAction)
                    }
                }
                .padding(12)
                .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                .overlay {
                    RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .strokeBorder(.white.opacity(0.6), lineWidth: 0.5)
                }
                .shadow(color: .black.opacity(0.18), radius: 18, x: 0, y: 8)
                .padding(.bottom, 26)
                .allowsHitTesting(true)
            }
            .frame(width: geometry.size.width, height: geometry.size.height)
        }
        .background(.clear)
        .preferredColorScheme(.light)
        .onExitCommand {
            countdownTask?.cancel()
            onCancel()
        }
        .onDisappear { countdownTask?.cancel() }
    }

    private func beginCountdown() {
        guard countdownValue == nil, let selectedArea = selection?.integral else { return }
        countdownTask = Task { @MainActor in
            for count in stride(from: 3, through: 1, by: -1) {
                guard !Task.isCancelled else { return }
                withAnimation(.easeInOut(duration: 0.18)) { countdownValue = count }
                do {
                    try await Task.sleep(for: .seconds(1))
                } catch {
                    return
                }
            }
            guard !Task.isCancelled else { return }
            countdownValue = nil
            countdownTask = nil
            onSelect(selectedArea)
        }
    }
}
