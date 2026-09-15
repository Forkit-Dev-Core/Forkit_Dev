// Fixed local file operation for the guarded Python installer. No shell or UI.
import Foundation

do {
    let bytes = FileHandle.standardInput.readData(ofLength: 8_193)
    guard bytes.count <= 8_192,
        let request = try JSONSerialization.jsonObject(with: bytes) as? [String: String],
        Set(request.keys) == ["source"], let path = request["source"], path.hasPrefix("/")
    else { throw CocoaError(.fileReadCorruptFile) }
    let source = URL(fileURLWithPath: path).standardizedFileURL
    let name = source.lastPathComponent
    guard source.deletingLastPathComponent().lastPathComponent == "Applications",
        name == "Forkit Session Receipt.app"
        || name.range(of: "^\\.Forkit Previous [0-9a-f-]{36}\\.app$", options: .regularExpression) != nil
    else { throw CocoaError(.fileWriteNoPermission) }
    var info = stat()
    guard lstat(source.path, &info) == 0, info.st_mode & S_IFMT == S_IFDIR,
        info.st_uid == geteuid(), info.st_mode & 0o022 == 0,
        source.resolvingSymlinksInPath().path == source.path
    else { throw CocoaError(.fileWriteNoPermission) }
    var destination: NSURL?
    try FileManager.default.trashItem(at: source, resultingItemURL: &destination)
    let result: [String: Any] = ["ok": true, "destination": destination?.path ?? NSNull()]
    FileHandle.standardOutput.write(try JSONSerialization.data(withJSONObject: result))
} catch {
    // No project data, arbitrary errors or permission requests leave the helper.
    FileHandle.standardOutput.write(Data("{\"ok\":false}".utf8))
    exit(1)
}
