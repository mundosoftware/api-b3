//
//  NotificationService.swift
//  OneSignalNotificationServiceExtension
//
//  Created by Codex on 02/08/26.
//

import OneSignalExtension
import UserNotifications

final class NotificationService: UNNotificationServiceExtension {
    private var contentHandler: ((UNNotificationContent) -> Void)?
    private var receivedRequest: UNNotificationRequest!
    private var bestAttemptContent: UNMutableNotificationContent?

    override func didReceive(
        _ request: UNNotificationRequest,
        withContentHandler contentHandler: @escaping (UNNotificationContent) -> Void
    ) {
        self.receivedRequest = request
        self.contentHandler = contentHandler
        bestAttemptContent = (request.content.mutableCopy() as? UNMutableNotificationContent)

        guard let bestAttemptContent else {
            contentHandler(request.content)
            return
        }

        OneSignalExtension.didReceiveNotificationExtensionRequest(
            receivedRequest,
            with: bestAttemptContent,
            withContentHandler: contentHandler
        )
    }

    override func serviceExtensionTimeWillExpire() {
        guard let contentHandler, let bestAttemptContent else { return }

        OneSignalExtension.serviceExtensionTimeWillExpireRequest(
            receivedRequest,
            with: bestAttemptContent
        )
        contentHandler(bestAttemptContent)
    }
}
