import SwiftUI
import AppKit

struct AssistantSetupView: View {
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .trailing, spacing: 16) {
            MCPConnectorView()
            Button("Done") { dismiss() }.keyboardShortcut(.cancelAction)
        }
        .padding(20)
        .frame(width: 560)
        .background(Color(nsColor: .windowBackgroundColor))
        .preferredColorScheme(.light)
    }
}

struct MCPConnectorView: View {
    @State private var assistant = "Codex"
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
                Image(systemName: "point.3.connected.trianglepath.dotted")
                    .foregroundStyle(.indigo)
                    .frame(width: 32, height: 32)
                    .background(Color.indigo.opacity(0.09), in: RoundedRectangle(cornerRadius: 8))
                    .accessibilityHidden(true)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Connect your assistant").font(.headline)
                    Text("Share capture briefs over MCP.").font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                Picker("Assistant", selection: $assistant) {
                    Text("Codex").tag("Codex")
                    Text("Claude Desktop").tag("Claude Desktop")
                }
                .labelsHidden()
                .pickerStyle(.segmented)
                .fixedSize()
                .onChange(of: assistant) { copied = false }
            }
            if let configuration {
                VStack(alignment: .leading, spacing: 0) {
                    HStack {
                        Label(assistant == "Codex" ? "Terminal" : "claude_desktop_config.json",
                              systemImage: assistant == "Codex" ? "terminal" : "curlybraces")
                            .font(.caption.monospaced()).foregroundStyle(.secondary)
                        Spacer()
                        Button {
                            NSPasteboard.general.clearContents()
                            copied = NSPasteboard.general.setString(configuration, forType: .string)
                        } label: {
                            Label(copied ? "Copied" : "Copy", systemImage: copied ? "checkmark" : "doc.on.doc")
                        }
                        .controlSize(.small)
                        .accessibilityLabel(copied ? "Copied" : assistant == "Codex" ? "Copy Codex command" : "Copy Claude configuration")
                    }
                    .padding(.horizontal, 12).padding(.vertical, 7)
                    Divider()
                    ScrollView {
                        Text(verbatim: configuration)
                            .font(.system(size: 12, design: .monospaced))
                            .lineSpacing(3)
                            .textSelection(.enabled)
                            .fixedSize(horizontal: false, vertical: true)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(12)
                    }
                    .frame(height: assistant == "Codex" ? 120 : 160)
                }
                .background(Color(nsColor: .textBackgroundColor), in: RoundedRectangle(cornerRadius: 9))
                .overlay { RoundedRectangle(cornerRadius: 9).strokeBorder(.quaternary) }
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
        .padding(16)
        .background(Color.indigo.opacity(0.035), in: RoundedRectangle(cornerRadius: 14))
        .overlay { RoundedRectangle(cornerRadius: 14).strokeBorder(.quaternary) }
    }

    private func quote(_ value: String) -> String {
        "'" + value.replacingOccurrences(of: "'", with: "'\"'\"'") + "'"
    }
}
