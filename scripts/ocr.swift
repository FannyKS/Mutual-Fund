// OCR helper: extract text from images using the macOS Vision framework.
// Usage: swift ocr.swift <image> [more images...]
import Foundation
import Vision
import AppKit

let args = Array(CommandLine.arguments.dropFirst())
if args.isEmpty {
    FileHandle.standardError.write("usage: ocr.swift <image>...\n".data(using: .utf8)!)
    exit(2)
}

for path in args {
    guard let image = NSImage(contentsOfFile: path),
          let tiff = image.tiffRepresentation,
          let bitmap = NSBitmapImageRep(data: tiff),
          let cg = bitmap.cgImage else {
        FileHandle.standardError.write("cannot load: \(path)\n".data(using: .utf8)!)
        continue
    }

    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = true

    let handler = VNImageRequestHandler(cgImage: cg, options: [:])
    do {
        try handler.perform([request])
    } catch {
        FileHandle.standardError.write("OCR failed for \(path): \(error)\n".data(using: .utf8)!)
        continue
    }

    print("===== \(path) =====")
    let observations = request.results ?? []
    // Sort roughly top-to-bottom, left-to-right for a readable layout.
    let sorted = observations.sorted { a, b in
        let ay = a.boundingBox.midY, by = b.boundingBox.midY
        if abs(ay - by) > 0.01 { return ay > by }
        return a.boundingBox.minX < b.boundingBox.minX
    }
    for obs in sorted {
        if let text = obs.topCandidates(1).first?.string {
            print(text)
        }
    }
    print("")
}
