import SwiftUI
import AppKit

struct AssistantSetupView: View {
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .trailing, spacing: 16) {
            PoachSettingsView()
            Button("Done") { dismiss() }.keyboardShortcut(.cancelAction)
        }
        .padding(20)
        .frame(width: 560)
        .background(PoachPalette.canvas)
        .preferredColorScheme(.light)
    }
}

struct MCPConnectorView: View {
    @AppStorage("setupAssistant") private var assistant = "Codex"
    @State private var copied = false
    @State private var showingConfiguration = false

    private var serverPath: String? {
        Bundle.main.url(forResource: "server", withExtension: "mjs")?.path
    }

    private var configuration: String? {
        guard let serverPath, let executable = PoachInspectionRunner.findNode() else { return nil }
        let node = executable.path
        let runtimePath = executable.deletingLastPathComponent().path + ":/usr/bin:/bin"
        if assistant == "Codex" {
            return [
                "codex mcp add poach",
                "  --env PATH=\(quote(runtimePath))",
                "  -- \(quote(node))",
                "  \(quote(serverPath))"
            ].joined(separator: " \\\n")
        }
        let config: [String: Any] = ["mcpServers": ["poach": ["command": node, "args": [serverPath], "env": ["PATH": runtimePath]]]]
        guard let data = try? JSONSerialization.data(withJSONObject: config, options: [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]) else { return nil }
        return String(decoding: data, as: UTF8.self)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 10) {
                Text("MCP")
                    .font(.headline)
                    .accessibilityLabel("MCP connection")
                Spacer()
                PoachSegments(label: "Assistant", selection: $assistant,
                              choices: [("Codex", "Codex"), ("Claude Desktop", "Claude")])
                    .frame(width: 180)
                .onChange(of: assistant) { copied = false }
            }
            if let configuration {
                VStack(alignment: .leading, spacing: 0) {
                    HStack {
                        Button("View setup…") { showingConfiguration = true }
                            .popover(isPresented: $showingConfiguration) {
                                VStack(alignment: .leading, spacing: 10) {
                                    Text(assistant == "Codex" ? "Run in Terminal, then reopen Codex." : "Merge this entry into your Claude Desktop configuration, then restart Claude.")
                                    Text(verbatim: configuration)
                                        .font(.system(.caption, design: .monospaced))
                                        .textSelection(.enabled)
                                }
                                .padding(16)
                                .frame(width: 380, alignment: .leading)
                                .fixedSize(horizontal: false, vertical: true)
                            }
                        Spacer()
                        Button {
                            NSPasteboard.general.clearContents()
                            copied = NSPasteboard.general.setString(configuration, forType: .string)
                        } label: {
                            Text(copied ? "Copied" : "Copy")
                        }
                        .buttonStyle(PoachActionStyle())
                        .accessibilityLabel(copied ? "Copied" : assistant == "Codex" ? "Copy Codex command" : "Copy Claude configuration")
                    }
                    .padding(.horizontal, 12).padding(.vertical, 7)
                }
                .background(PoachPalette.canvas, in: RoundedRectangle(cornerRadius: 9))

            } else {
                Text("Reinstall Poach to restore the bundled connector.")
                    .foregroundStyle(.secondary)
            }
        }
        .padding(12)
        .background(PoachPalette.panel, in: RoundedRectangle(cornerRadius: 14))

    }

    private func quote(_ value: String) -> String {
        "'" + value.replacingOccurrences(of: "'", with: "'\"'\"'") + "'"
    }
}

struct PoachSettingsView: View {
    var storageVisible = true
    var captureBusy = false
    @State private var usage: CaptureStorage.Usage?
    @State private var storageError: String?

    private func refreshStorage() {
        do { usage = try CaptureStorage.scan(); storageError = nil }
        catch { usage = nil; storageError = error.localizedDescription }
    }

    @AppStorage("windowEdge") private var edge = "right"
    @AppStorage("defaultCaptureMode") private var defaultMode = PoachCaptureMode.selectedPortion.rawValue

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Window position")
                Spacer()
                PoachSegments(label: "Window position", selection: $edge, choices: [("left", "Left"), ("right", "Right")])
                    .frame(width: 140)
            }
            HStack {
                Text("Default recording mode")
                Spacer()
                Picker("Default recording mode", selection: $defaultMode) {
                    ForEach(PoachCaptureMode.allCases) { mode in Text(mode.title).tag(mode.rawValue) }
                }
                .labelsHidden().pickerStyle(.menu).buttonStyle(.plain).fixedSize()
            }
            .frame(height: 24)
            MCPConnectorView()
            Divider()
            HStack {
                VStack(alignment: .leading) {
                    Text("Storage").font(.headline)
                    if let usage {
                        Text("\(usage.total.formatted(.byteCount(style: .file))) used · \(usage.unused.formatted(.byteCount(style: .file))) unused")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }
                Spacer()
                Button("Clear unused captures") {
                    do { try CaptureStorage.clear(); refreshStorage() }
                    catch { refreshStorage(); storageError = error.localizedDescription }
                }
                .disabled(captureBusy || usage?.removable.isEmpty != false)
            }
            if let storageError { Text(storageError).font(.caption).foregroundStyle(.secondary) }
        }
        .task(id: storageVisible && !captureBusy) { if storageVisible && !captureBusy { refreshStorage() } }
        .onChange(of: edge) {
            for window in NSApp.windows where window.title == "Poach" || window.title == "Poach — Implementation brief" {
                pinToEdge(window)
            }
        }
    }
}
