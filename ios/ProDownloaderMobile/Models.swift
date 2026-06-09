import Foundation

struct AdvancedOptionsPayload: Codable, Equatable {
    var cookieBrowser = "Auto"
    var proxy = ""
    var maxQuality = "Best"
    var subtitles = false
    var subtitleLanguages = "all"
    var metadata = false
    var thumbnail = false
    var douyinEngine = "Auto"
    var impersonate = "Off"

    enum CodingKeys: String, CodingKey {
        case cookieBrowser = "cookie_browser"
        case proxy
        case maxQuality = "max_quality"
        case subtitles
        case subtitleLanguages = "subtitle_languages"
        case metadata
        case thumbnail
        case douyinEngine = "douyin_engine"
        case impersonate
    }
}

struct FetchRequest: Codable {
    var url: String
    var options = AdvancedOptionsPayload()
}

struct FormatOption: Codable, Identifiable, Hashable {
    var id: String
    var label: String?
    var height: Int?
    var provider: String?
    var extensionValue: String?
    var mediaFormat: String?

    enum CodingKeys: String, CodingKey {
        case id
        case label
        case height
        case provider
        case extensionValue = "extension"
        case mediaFormat = "media_format"
    }

    var displayName: String {
        let providerText = provider?.isEmpty == false ? "\(provider!) - " : ""
        return providerText + (label ?? id)
    }
}

struct FetchResponse: Codable {
    var url: String
    var title: String
    var thumbnail: String
    var uploader: String
    var duration: Int?
    var formats: [FormatOption]
    var subtitleLanguages: [String]
    var supportsMetadata: Bool
    var supportsThumbnail: Bool

    enum CodingKeys: String, CodingKey {
        case url
        case title
        case thumbnail
        case uploader
        case duration
        case formats
        case subtitleLanguages = "subtitle_languages"
        case supportsMetadata = "supports_metadata"
        case supportsThumbnail = "supports_thumbnail"
    }
}

struct DownloadRequest: Codable {
    var url: String
    var mediaFormat: String = "video"
    var formatId: String?
    var title: String = ""
    var provider: String = ""
    var option: String = ""
    var reuseHistory = true
    var options = AdvancedOptionsPayload()

    enum CodingKeys: String, CodingKey {
        case url
        case mediaFormat = "media_format"
        case formatId = "format_id"
        case title
        case provider
        case option
        case reuseHistory = "reuse_history"
        case options
    }
}

struct DownloadCreated: Codable {
    var jobId: String
    var status: String

    enum CodingKeys: String, CodingKey {
        case jobId = "job_id"
        case status
    }
}

struct JobResponse: Codable, Identifiable {
    var jobId: String
    var status: String
    var progress: Int
    var url: String
    var mediaFormat: String
    var title: String
    var provider: String
    var option: String
    var error: String
    var fileUrl: String?
    var fileName: String
    var createdAt: String
    var updatedAt: String

    var id: String { jobId }

    enum CodingKeys: String, CodingKey {
        case jobId = "job_id"
        case status
        case progress
        case url
        case mediaFormat = "media_format"
        case title
        case provider
        case option
        case error
        case fileUrl = "file_url"
        case fileName = "file_name"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}
