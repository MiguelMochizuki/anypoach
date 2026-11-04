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
        .background(Color(nsColor: .windowBackgroundColor))
        .preferredColorScheme(.light)
    }
}

struct MCPConnectorView: View {
    @AppStorage("setupAssistant") private var assistant = "Codex"
    @State private var copied = false

    private var serverPath: String? {
        guard let path = Bundle.main.object(forInfoDictionaryKey: "POACHMCPServerPath") as? String,
              FileManager.default.fileExists(atPath: path) else { return nil }
        return path
    }

    private var configuration: String? {
        guard let serverPath else { return nil }
        let node = Bundle.main.object(forInfoDictionaryKey: "POACHNodePath") as? String ?? "node"
        let runtimePath = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
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
                        Text(assistant == "Codex" ? "Terminal" : "claude_desktop_config.json").font(.caption)
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
                        Text(verbatim: configuration)
                            .font(.system(size: 12))
                            .lineSpacing(1)
                            .textSelection(.enabled)
                            .fixedSize(horizontal: false, vertical: true)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.horizontal, 12).padding(.bottom, 12)
                }
                .background(Color(nsColor: .textBackgroundColor), in: RoundedRectangle(cornerRadius: 9))

                Text(assistant == "Codex"
                     ? "Run in Terminal, then reopen Codex to load Poach."
                     : "In Claude Desktop settings, choose Developer → Edit Config. Merge the poach entry into mcpServers, then restart Claude.")
                    .font(.caption).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            } else {
                Text("Build the local MCP server with scripts/build-macos-app.sh, then reopen Poach.")
                    .foregroundStyle(.secondary)
            }
        }
        .padding(12)
        .background(Color(white: 0.97), in: RoundedRectangle(cornerRadius: 14))

    }

    private func quote(_ value: String) -> String {
        "'" + value.replacingOccurrences(of: "'", with: "'\"'\"'") + "'"
    }
}

struct PoachSettingsView: View {
    @AppStorage("setupAssistant") private var assistant = "Codex"
    @AppStorage("windowEdge") private var edge = "right"
    @AppStorage("defaultCaptureMode") private var defaultMode = PoachCaptureMode.selectedPortion.rawValue

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if assistant == "Codex" {
            HStack {
                Text("Window position")
                Spacer()
                PoachSegments(label: "Window position", selection: $edge, choices: [("left", "Left"), ("right", "Right")])
                    .frame(width: 140)
            }
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
        }
        .onChange(of: edge) {
            for window in NSApp.windows where window.title == "Poach" || window.title == "Poach — Implementation brief" {
                pinToEdge(window)
            }
        }
    }
}
