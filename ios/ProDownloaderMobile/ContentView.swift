import AVKit
import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var store: DownloadStore

    var body: some View {
        NavigationStack {
            Form {
                serverSection
                inputSection
                if let result = store.fetchResult {
                    resultSection(result)
                    optionSection
                    downloadSection
                }
                if let localFileURL = store.localFileURL {
                    playbackSection(localFileURL)
                }
                if !store.errorMessage.isEmpty {
                    errorSection
                }
            }
            .navigationTitle("Pro Downloader")
        }
    }

    private var serverSection: some View {
        Section("Server") {
            TextField("Server URL", text: $store.serverURLText)
                .textInputAutocapitalization(.never)
                .keyboardType(.URL)
            SecureField("API Key", text: $store.apiKey)
                .textInputAutocapitalization(.never)
        }
    }

    private var inputSection: some View {
        Section("URL") {
            TextField("TikTok, Douyin, YouTube...", text: $store.urlText, axis: .vertical)
                .lineLimit(2...4)
                .textInputAutocapitalization(.never)
                .keyboardType(.URL)

            HStack {
                Button("Paste") {
                    store.pasteAndFetch()
                }
                .buttonStyle(.bordered)

                Button {
                    Task { await store.fetch() }
                } label: {
                    if store.isFetching {
                        ProgressView()
                    } else {
                        Text("Fetch")
                    }
                }
                .buttonStyle(.borderedProminent)
                .disabled(store.isFetching || store.urlText.isEmpty)
            }
        }
    }

    private func resultSection(_ result: FetchResponse) -> some View {
        Section("Info") {
            VStack(alignment: .leading, spacing: 8) {
                Text(result.title.isEmpty ? result.url : result.title)
                    .font(.headline)
                if !result.uploader.isEmpty {
                    Text(result.uploader)
                        .foregroundStyle(.secondary)
                }
                if let duration = result.duration {
                    Text(formatDuration(duration))
                        .foregroundStyle(.secondary)
                }
            }
        }
    }

    private var optionSection: some View {
        Section("Options") {
            Picker("Format", selection: $store.mediaFormat) {
                Text("MP4").tag("video")
                Text("MP3").tag("audio")
            }
            .pickerStyle(.segmented)

            Picker("Quality", selection: Binding(
                get: { store.selectedFormatID ?? store.compatibleFormats.first?.id ?? "" },
                set: { store.selectedFormatID = $0 }
            )) {
                ForEach(store.compatibleFormats) { format in
                    Text(format.displayName).tag(format.id)
                }
            }
            .disabled(store.compatibleFormats.isEmpty)

            Toggle("Metadata", isOn: $store.options.metadata)
                .disabled(!(store.fetchResult?.supportsMetadata ?? false))
            Toggle("Thumbnail", isOn: $store.options.thumbnail)
                .disabled(!(store.fetchResult?.supportsThumbnail ?? false))
        }
    }

    private var downloadSection: some View {
        Section("Download") {
            if let job = store.currentJob {
                VStack(alignment: .leading, spacing: 8) {
                    Text(job.status.capitalized)
                    ProgressView(value: Double(job.progress), total: 100)
                    if !job.fileName.isEmpty {
                        Text(job.fileName)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }

            Button {
                Task { await store.startDownload() }
            } label: {
                if store.isDownloading {
                    ProgressView()
                } else {
                    Text("Download")
                }
            }
            .buttonStyle(.borderedProminent)
            .disabled(store.isDownloading || store.compatibleFormats.isEmpty)
        }
    }

    private func playbackSection(_ url: URL) -> some View {
        Section("File") {
            VideoPlayer(player: AVPlayer(url: url))
                .frame(height: 220)
            ShareLink(item: url)
        }
    }

    private var errorSection: some View {
        Section("Status") {
            Text(store.errorMessage)
                .foregroundStyle(.red)
        }
    }

    private func formatDuration(_ seconds: Int) -> String {
        let minutes = seconds / 60
        let remaining = seconds % 60
        return "\(minutes):" + String(format: "%02d", remaining)
    }
}

#Preview {
    ContentView()
        .environmentObject(DownloadStore())
}
