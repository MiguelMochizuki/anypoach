import Foundation

struct PoachInspection: Codable {
    let mediaType: String
    let sourcePath: String
    let durationMs: Int
    let keyframes: [PoachKeyframe]
    let palette: [String]
    let timing: PoachTiming
}

struct PoachKeyframe: Codable {
    let kind: String
    let timeMs: Int
    let imagePath: String
}

struct PoachTiming: Codable {
    let durationMs: Int
    let bezier: [Double]
    let token: String
}

enum PoachInspectionError: LocalizedError {
    case projectNotBuilt
    case nodeNotFound
    case processFailed(String)

    var errorDescription: String? {
        switch self {
        case .projectNotBuilt:
            "Poach's analysis engine isn't built yet. From the project folder, run `pnpm install` and `pnpm build`, then reopen Poach."
        case .nodeNotFound:
            "Node.js wasn't found on PATH. Install Node.js 20 or newer, then launch Poach again."
        case .processFailed(let message):
            message
        }
    }
}

enum PoachInspectionRunner {
    static func inspect(videoURL: URL) async throws -> PoachInspection {
        guard let projectRoot = findProjectRoot() else { throw PoachInspectionError.projectNotBuilt }
        guard let node = findNode() else { throw PoachInspectionError.nodeNotFound }
        let entry = projectRoot.appending(path: "packages/core/dist/index.js").path
        let videoPath = videoURL.path
        let rootPath = projectRoot.path

        return try await Task.detached(priority: .userInitiated) {
            let process = Process()
            process.executableURL = node
            process.arguments = [
                "--input-type=module", "-e",
                "import { inspectImage, inspectVideo } from \(Self.jsString(entry)); const inspect = /\\.(png|jpe?g|webp|tiff?|bmp)$/i.test(process.argv[1]) ? inspectImage : inspectVideo; try { const result = await inspect(process.argv[1]); process.stdout.write(JSON.stringify(result)); } catch (error) { console.error(error instanceof Error ? error.message : String(error)); process.exitCode = 1; }",
                videoPath,
            ]
            process.currentDirectoryURL = URL(fileURLWithPath: rootPath)
            var environment = ProcessInfo.processInfo.environment
            let bundledPath = environment["PATH", default: ""]
            environment["PATH"] = [bundledPath, "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"].joined(separator: ":")
            process.environment = environment
            let output = Pipe()
            let errors = Pipe()
            process.standardOutput = output
            process.standardError = errors
            do {
                try process.run()
                let data = output.fileHandleForReading.readDataToEndOfFile()
                process.waitUntilExit()
                guard process.terminationStatus == 0 else {
                    let details = String(data: errors.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8)?
                        .trimmingCharacters(in: .whitespacesAndNewlines)
                    throw PoachInspectionError.processFailed(details?.isEmpty == false ? details! : "The analysis process exited with status \(process.terminationStatus). Check that ffmpeg and ffprobe are available.")
                }
                do {
                    return try JSONDecoder().decode(PoachInspection.self, from: data)
                } catch {
                    throw PoachInspectionError.processFailed("Poach returned an unreadable analysis result: \(error.localizedDescription)")
                }
            } catch let error as PoachInspectionError {
                throw error
            } catch {
                throw PoachInspectionError.processFailed("Poach couldn't start its analysis engine: \(error.localizedDescription)")
            }
        }.value
    }

    private static func findProjectRoot() -> URL? {
        if let configuredRoot = Bundle.main.object(forInfoDictionaryKey: "POACHProjectRoot") as? String {
            let root = URL(fileURLWithPath: configuredRoot, isDirectory: true)
            if FileManager.default.fileExists(atPath: root.appending(path: "packages/core/dist/index.js").path) {
                return root
            }
        }
        var candidate = URL(fileURLWithPath: FileManager.default.currentDirectoryPath, isDirectory: true)
        for _ in 0..<10 {
            let entry = candidate.appending(path: "packages/core/dist/index.js")
            if FileManager.default.fileExists(atPath: entry.path) { return candidate }
            let parent = candidate.deletingLastPathComponent()
            if parent.path == candidate.path { break }
            candidate = parent
        }
        return nil
    }

    private static func findNode() -> URL? {
        let configuredNode = Bundle.main.object(forInfoDictionaryKey: "POACHNodePath") as? String
        let environmentPaths = ProcessInfo.processInfo.environment["PATH", default: ""].split(separator: ":")
        let paths = (configuredNode.map { [Substring(URL(fileURLWithPath: $0).deletingLastPathComponent().path)] } ?? [])
            + environmentPaths + ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"]
        return paths.lazy.map { URL(fileURLWithPath: String($0)).appending(path: "node") }
            .first { FileManager.default.isExecutableFile(atPath: $0.path) }
    }

    private static func jsString(_ value: String) -> String {
        let data = try! JSONEncoder().encode(value)
        return String(decoding: data, as: UTF8.self)
    }
}
