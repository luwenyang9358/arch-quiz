import Foundation

func xmlEsc(_ s: String) -> String {
    s.replacingOccurrences(of: "&", with: "&amp;")
     .replacingOccurrences(of: "<", with: "&lt;")
     .replacingOccurrences(of: ">", with: "&gt;")
}

func docxParagraph(_ text: String, style: Int) -> String {
    let sz = style == 1 ? 30 : style == 2 ? 24 : 21
    let bold = style > 0 ? "<w:b/>" : ""
    let spacing = style == 1
        ? "<w:spacing w:before=\"200\" w:after=\"120\"/>"
        : "<w:spacing w:before=\"60\" w:after=\"60\"/>"
    return "<w:p><w:pPr>\(spacing)</w:pPr><w:r><w:rPr>\(bold)<w:rFonts w:ascii=\"Helvetica\" w:hAnsi=\"Helvetica\" w:eastAsia=\"PingFang SC\"/><w:sz w:val=\"\(sz)\"/><w:szCs w:val=\"\(sz)\"/></w:rPr><w:t xml:space=\"preserve\">\(xmlEsc(text))</w:t></w:r></w:p>"
}

func writeDocx(_ text: String, to url: URL) throws {
    let fm = FileManager.default
    let tmp = fm.temporaryDirectory.appendingPathComponent("docx-" + UUID().uuidString)
    let wordDir = tmp.appendingPathComponent("word")
    let relsDir = tmp.appendingPathComponent("_rels")
    try fm.createDirectory(at: wordDir, withIntermediateDirectories: true)
    try fm.createDirectory(at: relsDir, withIntermediateDirectories: true)

    var body = ""
    for raw in text.components(separatedBy: "\n") {
        let line = raw.trimmingCharacters(in: .whitespaces)
        if line.isEmpty { body += "<w:p/>"; continue }
        if line.hasPrefix("## ") { body += docxParagraph(String(line.dropFirst(3)), style: 2) }
        else if line.hasPrefix("# ") { body += docxParagraph(String(line.dropFirst(2)), style: 1) }
        else if line.hasPrefix("- ") { body += docxParagraph("• " + String(line.dropFirst(2)), style: 0) }
        else { body += docxParagraph(line, style: 0) }
    }

    let doc = "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n"
        + "<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\"><w:body>"
        + body
        + "<w:sectPr><w:pgSz w:w=\"11906\" w:h=\"16838\"/><w:pgMar w:top=\"1134\" w:right=\"1134\" w:bottom=\"1134\" w:left=\"1134\" w:header=\"720\" w:footer=\"720\" w:gutter=\"0\"/></w:sectPr></w:body></w:document>"

    let types = "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n"
        + "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">"
        + "<Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/>"
        + "<Default Extension=\"xml\" ContentType=\"application/xml\"/>"
        + "<Override PartName=\"/word/document.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml\"/></Types>"

    let rels = "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n"
        + "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
        + "<Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"word/document.xml\"/></Relationships>"

    try types.write(to: tmp.appendingPathComponent("[Content_Types].xml"), atomically: true, encoding: .utf8)
    try rels.write(to: relsDir.appendingPathComponent(".rels"), atomically: true, encoding: .utf8)
    try doc.write(to: wordDir.appendingPathComponent("document.xml"), atomically: true, encoding: .utf8)

    if fm.fileExists(atPath: url.path) { try fm.removeItem(at: url) }
    let p = Process()
    p.executableURL = URL(fileURLWithPath: "/usr/bin/zip")
    p.arguments = ["-X", "-D", "-r", "-q", url.path, "[Content_Types].xml", "_rels", "word"]
    p.currentDirectoryURL = tmp
    try p.run()
    p.waitUntilExit()
    try? fm.removeItem(at: tmp)
    if p.terminationStatus != 0 {
        throw NSError(domain: "zip", code: Int(p.terminationStatus),
                      userInfo: [NSLocalizedDescriptionKey: "zip 打包失败"])
    }
}
