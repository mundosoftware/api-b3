import Foundation
import WatchConnectivity

final class CompanionWatchSyncService: NSObject, WCSessionDelegate {
    static let shared = CompanionWatchSyncService()

    private weak var model: CompanionAppModel?
    private var session: WCSession?
    private let dateFormatter = ISO8601DateFormatter()

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
        sendAccessState(
            userId: userId,
            hasAccess: nil,
            paidAccess: nil,
            paidAccessExpiresAt: nil,
            trialDaysLeft: nil
        )
    }

    func sendAccessState(
        userId: String,
        hasAccess: Bool?,
        paidAccess: Bool?,
        paidAccessExpiresAt: Date?,
        trialDaysLeft: Int?
    ) {
        guard let session else { return }
        var context: [String: Any] = ["user_id": userId]
        if let hasAccess {
            context["has_access"] = hasAccess
        }
        if let paidAccess {
            context["paid_access"] = paidAccess
        }
        if let paidAccessExpiresAt {
            context["paid_access_expires_at"] = dateFormatter.string(from: paidAccessExpiresAt)
        }
        if let trialDaysLeft {
            context["trial_days_left"] = trialDaysLeft
        }
        do {
            try session.updateApplicationContext(context)
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

    func session(_ session: WCSession, didReceiveMessage message: [String: Any]) {
        handleWatchMessage(message)
    }

    func session(_ session: WCSession, didReceiveUserInfo userInfo: [String: Any]) {
        handleWatchMessage(userInfo)
    }

    private func handleWatchMessage(_ message: [String: Any]) {
        guard message["action"] as? String == "show_paywall" else { return }
        Task { @MainActor in
            self.model?.requestPurchasePlansFromWatch()
        }
    }

    func sessionDidBecomeInactive(_ session: WCSession) {}

    func sessionDidDeactivate(_ session: WCSession) {
        session.activate()
    }
}
