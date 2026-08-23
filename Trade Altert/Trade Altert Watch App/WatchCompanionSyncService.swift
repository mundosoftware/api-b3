import Foundation
import WatchConnectivity

final class WatchCompanionSyncService: NSObject, WCSessionDelegate {
    static let shared = WatchCompanionSyncService()

    private weak var model: AppModel?
    private var session: WCSession?

    private override init() {}

    func start(model: AppModel) {
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

    func requestPurchaseOnPhone() {
        guard let session else { return }
        let payload = ["action": "show_paywall"]
        if session.isReachable {
            session.sendMessage(payload, replyHandler: nil) { error in
                print("WatchConnectivity paywall request failed: \(error.localizedDescription)")
            }
        } else {
            session.transferUserInfo(payload)
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
        if activationState == .activated {
            Task { @MainActor in
                self.model?.resendUserIdToCompanion()
            }
        }
    }

    func session(_ session: WCSession, didReceiveApplicationContext applicationContext: [String: Any]) {
        Task { @MainActor in
            if let userId = applicationContext["user_id"] as? String {
                self.model?.adoptUserIdFromCompanion(userId)
            }
            self.model?.applyCompanionAccessContext(applicationContext)
        }
    }
}
