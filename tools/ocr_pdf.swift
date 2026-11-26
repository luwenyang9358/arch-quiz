// 把图片型 PDF 逐页 OCR 成 JSON（macOS 12+，用系统 Vision 框架，离线可用）
//
//   swiftc -O tools/ocr_pdf.swift -o /tmp/ocr_pdf
//   /tmp/ocr_pdf 讲义.pdf /tmp/ocr.json [缩放倍率，默认 2.2]
//
// 输出结构：[ [ {"t": 文本, "x","y","w","h": 归一化坐标, "c": 置信度}, ... ], ... ]
// 交给 tools/import_material.py 解析成题库 / 背诵卡。

import Foundation
import PDFKit
import Vision
import AppKit

let args = CommandLine.arguments
guard args.count > 2, let doc = PDFDocument(url: URL(fileURLWithPath: args[1])) else { print("open fail"); exit(1) }
let outPath = args[2]
let scale: CGFloat = args.count > 3 ? CGFloat(Double(args[3])!) : 2.2

var pages: [[[String: Any]]] = []
for i in 0..<doc.pageCount {
    guard let page = doc.page(at: i) else { pages.append([]); continue }
    let r = page.bounds(for: .mediaBox)
    let w = Int(r.width * scale), h = Int(r.height * scale)
    guard let ctx = CGContext(data: nil, width: w, height: h, bitsPerComponent: 8, bytesPerRow: 0,
                              space: CGColorSpaceCreateDeviceRGB(),
                              bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue) else { pages.append([]); continue }
    ctx.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 1))
    ctx.fill(CGRect(x: 0, y: 0, width: w, height: h))
    ctx.scaleBy(x: scale, y: scale)
    page.draw(with: .mediaBox, to: ctx)
    guard let cg = ctx.makeImage() else { pages.append([]); continue }

    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.recognitionLanguages = ["zh-Hans", "en-US"]
    req.usesLanguageCorrection = true
    let handler = VNImageRequestHandler(cgImage: cg, options: [:])
    try? handler.perform([req])
    var lines: [[String: Any]] = []
    for o in req.results ?? [] {
        guard let c = o.topCandidates(1).first else { continue }
        let b = o.boundingBox
        lines.append(["t": c.string, "x": Double(b.minX), "y": Double(b.minY),
                      "w": Double(b.width), "h": Double(b.height), "c": Double(c.confidence)])
    }
    lines.sort { ($0["y"] as! Double) > ($1["y"] as! Double) }
    pages.append(lines)
    FileHandle.standardError.write("page \(i+1)/\(doc.pageCount) lines=\(lines.count)\n".data(using: .utf8)!)
}
let data = try! JSONSerialization.data(withJSONObject: pages, options: [])
try! data.write(to: URL(fileURLWithPath: outPath))
print("WROTE \(outPath) pages=\(pages.count)")
