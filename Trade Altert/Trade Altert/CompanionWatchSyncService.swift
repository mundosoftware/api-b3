import Foundation
import WatchConnectivity

final class CompanionWatchSyncService: NSObject, WCSessionDelegate {
    static let shared = CompanionWatchSyncService()

    private weak var model: CompanionAppModel?
    private var session: WCSession?

    private override init() {}

    func start(model: CompanionAppModel) {
        guard WCSession.isSupported() else { return }
        self.model = model

        let session = WCSession.default
        self.session = session
        if session.delegate == nil {
            session.delegate = self
            session.activate()
        }
    }

    func sendUserId(_ userId: String) {
        guard let session else { return }
        do {
            try session.updateApplicationContext(["user_id": userId])
        } catch {
            print("WatchConnectivity user sync failed: \(error.localizedDescription)")
        }
    }

    func session(
        _ session: WCSession,
        activationDidCompleteWith activationState: WCSessionActivationState,
        error: Error?
    ) {
        if let error {
            print("WatchConnectivity activation failed: \(error.localizedDescription)")
        }
        if activationState == .activated, let userId = model?.userId {
            sendUserId(userId)
        }
    }

    func session(_ session: WCSession, didReceiveApplicationContext applicationContext: [String: Any]) {
        guard let userId = applicationContext["user_id"] as? String else { return }
        Task { @MainActor in
            self.model?.adoptUserIdFromWatch(userId)
        }
    }

    func sessionDidBecomeInactive(_ session: WCSession) {}

    func sessionDidDeactivate(_ session: WCSession) {
        session.activate()
    }
}
