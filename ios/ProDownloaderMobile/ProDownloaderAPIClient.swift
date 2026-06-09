import Foundation

enum ProDownloaderAPIError: LocalizedError {
    case invalidServerURL
    case badResponse(Int, String)
    case missingFileURL

    var errorDescription: String? {
        switch self {
        case .invalidServerURL:
            return "Server URL is invalid."
        case .badResponse(let status, let message):
            return "Server error \(status): \(message)"
        case .missingFileURL:
            return "The finished job does not have a file URL."
        }
    }
}

struct ProDownloaderAPIClient {
    var serverURL: URL
    var apiKey: String
    var session: URLSession = .shared

    func fetch(url: String, options: AdvancedOptionsPayload) async throws -> FetchResponse {
        try await send(path: "/api/fetch", method: "POST", body: FetchRequest(url: url, options: options))
    }

    func startDownload(_ request: DownloadRequest) async throws -> DownloadCreated {
        try await send(path: "/api/download", method: "POST", body: request)
    }

    func job(id: String) async throws -> JobResponse {
        try await send(path: "/api/jobs/\(id)", method: "GET", body: OptionalPayload.none)
    }

    func downloadFile(for job: JobResponse) async throws -> URL {
        guard let fileUrl = job.fileUrl else {
            throw ProDownloaderAPIError.missingFileURL
        }
        let remoteURL = absoluteURL(for: fileUrl)
        var request = URLRequest(url: remoteURL)
        if !apiKey.isEmpty {
            request.setValue(apiKey, forHTTPHeaderField: "X-API-Key")
        }
        let (tempURL, response) = try await session.download(for: request)
        try validate(response: response, data: Data())

        let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let fileName = job.fileName.isEmpty ? "download.mp4" : job.fileName
        let destination = documents.appending(path: fileName)
        if FileManager.default.fileExists(atPath: destination.path) {
            try FileManager.default.removeItem(at: destination)
        }
        try FileManager.default.moveItem(at: tempURL, to: destination)
        return destination
    }

    func absoluteURL(for path: String) -> URL {
        if let url = URL(string: path), url.scheme != nil {
            return url
        }
        return serverURL.appending(path: path.trimmingCharacters(in: CharacterSet(charactersIn: "/")))
    }

    private func send<Response: Decodable, Body: Encodable>(
        path: String,
        method: String,
        body: Body
    ) async throws -> Response {
        let url = serverURL.appending(path: path.trimmingCharacters(in: CharacterSet(charactersIn: "/")))
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if !apiKey.isEmpty {
            request.setValue(apiKey, forHTTPHeaderField: "X-API-Key")
        }
        if !(body is OptionalPayload) {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONEncoder.snakeCase.encode(body)
        }

        let (data, response) = try await session.data(for: request)
        try validate(response: response, data: data)
        return try JSONDecoder.snakeCase.decode(Response.self, from: data)
    }

    private func validate(response: URLResponse, data: Data) throws {
        guard let http = response as? HTTPURLResponse else {
            return
        }
        guard (200..<300).contains(http.statusCode) else {
            let message = String(data: data, encoding: .utf8) ?? ""
            throw ProDownloaderAPIError.badResponse(http.statusCode, message)
        }
    }
}

private enum OptionalPayload: Encodable {
    case none
}

private extension JSONEncoder {
    static var snakeCase: JSONEncoder {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        return encoder
    }
}

private extension JSONDecoder {
    static var snakeCase: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }
}
