import SwiftUI

@main
struct ProDownloaderMobileApp: App {
    @StateObject private var store = DownloadStore()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(store)
        }
    }
}
