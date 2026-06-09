import Foundation
import UIKit

@MainActor
final class DownloadStore: ObservableObject {
    @Published var serverURLText = "http://192.168.1.10:8000"
    @Published var apiKey = "change-me"
    @Published var urlText = ""
    @Published var mediaFormat = "video"
    @Published var options = AdvancedOptionsPayload()
    @Published var fetchResult: FetchResponse?
    @Published var selectedFormatID: String?
    @Published var currentJob: JobResponse?
    @Published var localFileURL: URL?
    @Published var isFetching = false
    @Published var isDownloading = false
    @Published var errorMessage = ""

    var compatibleFormats: [FormatOption] {
        let expected = mediaFormat == "audio" ? "audio" : "video"
        let formats = fetchResult?.formats.filter { format in
            guard let media = format.mediaFormat else {
                return expected == "video"
            }
            return media == expected
        } ?? []
        return formats
    }

    var selectedFormat: FormatOption? {
        compatibleFormats.first { $0.id == selectedFormatID } ?? compatibleFormats.first
    }

    func pasteAndFetch() {
        if let pasted = UIPasteboard.general.string {
            urlText = pasted.trimmingCharacters(in: .whitespacesAndNewlines)
        }
        Task {
            await fetch()
        }
    }

    func fetch() async {
        guard let client = makeClient() else {
            return
        }
        isFetching = true
        errorMessage = ""
        currentJob = nil
        localFileURL = nil
        defer { isFetching = false }

        do {
            let result = try await client.fetch(url: urlText, options: options)
            fetchResult = result
            selectedFormatID = compatibleFormats.first?.id
        } catch {
            fetchResult = nil
            selectedFormatID = nil
            errorMessage = error.localizedDescription
        }
    }

    func startDownload() async {
        guard let client = makeClient(), let result = fetchResult else {
            return
        }
        isDownloading = true
        errorMessage = ""
        localFileURL = nil
        defer { isDownloading = false }

        let format = selectedFormat
        let request = DownloadRequest(
            url: result.url,
            mediaFormat: mediaFormat,
            formatId: format?.id,
            title: result.title,
            provider: format?.provider ?? "",
            option: format?.label ?? format?.id ?? "",
            reuseHistory: true,
            options: options
        )

        do {
            let created = try await client.startDownload(request)
            try await pollJob(client: client, jobID: created.jobId)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func pollJob(client: ProDownloaderAPIClient, jobID: String) async throws {
        while true {
            let job = try await client.job(id: jobID)
            currentJob = job
            if job.status == "done" {
                localFileURL = try await client.downloadFile(for: job)
                return
            }
            if job.status == "error" {
                throw ProDownloaderAPIError.badResponse(500, job.error)
            }
            try await Task.sleep(nanoseconds: 1_000_000_000)
        }
    }

    private func makeClient() -> ProDownloaderAPIClient? {
        guard let baseURL = URL(string: serverURLText.trimmingCharacters(in: .whitespacesAndNewlines)) else {
            errorMessage = "Server URL is invalid."
            return nil
        }
        return ProDownloaderAPIClient(serverURL: baseURL, apiKey: apiKey)
    }
}
