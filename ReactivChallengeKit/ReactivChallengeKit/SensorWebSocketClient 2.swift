//  SensorWebSocketClient.swift
//  ReactivChallengeKit
//
//  Connects to aeyron_bridge.py WebSocket and feeds heart_rate / breath_rate
//  into VitalsEngine for real MR60BHA2 sensor data.
//

import Foundation

/// Payload from aeyron_bridge.py (ESP32 → WebSocket JSON).
struct SensorPayload: Decodable {
    let heart_rate: Double?
    let breath_rate: Double?
    let distance: Double?
    let total_phase: Double?
    let breath_phase: Double?
    let heart_phase: Double?
    let timestamp: String?
}

/// Callback when new sensor data is received from the bridge.
typealias SensorUpdateHandler = (SensorPayload) -> Void

@Observable
final class SensorWebSocketClient {
    /// Default host. Simulator: localhost. Device: Mac IP (e.g. ipconfig getifaddr en0). Override via clip URL ?bridge=IP.
    private static let kDefaultHost: String = {
        #if targetEnvironment(simulator)
        return "127.0.0.1"
        #else
        return "172.20.10.14"  // Mac on iPhone hotspot; use ?bridge=YOUR_IP for other networks
        #endif
    }()
    private static let kPort = 8765

    /// Override bridge host (e.g. from clip URL ?bridge=192.168.1.100). Set before connect().
    var bridgeHost: String?

    private var task: URLSessionWebSocketTask?
    private var isReceiving = false
    private let session: URLSession = {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 30
        config.timeoutIntervalForResource = 60
        return URLSession(configuration: config)
    }()

    var isConnected: Bool { task != nil }
    /// Shown in UI when connection fails (e.g. timeout). Clear when receiving data.
    var connectionError: String?

    var onUpdate: SensorUpdateHandler?
    weak var engine: VitalsEngine?
    private var hasLoggedConnected = false
    private var hasLoggedFirstReceive = false

    private var effectiveBridgeURL: String {
        let host = bridgeHost ?? Self.kDefaultHost
        return "ws://\(host):\(Self.kPort)"
    }

    func connect() {
        connectionError = nil
        hasLoggedConnected = false
        hasLoggedFirstReceive = false
        let urlString = effectiveBridgeURL
        guard let url = URL(string: urlString) else {
            print("[sensor] ERROR: invalid bridge URL: \(urlString)")
            return
        }
        print("[sensor] connecting to \(urlString)")
        #if !targetEnvironment(simulator)
        if bridgeHost == nil {
            print("[sensor] Device: add ?bridge=YOUR_MAC_IP to clip URL, or set bridgeHost. Mac IP: ipconfig getifaddr en0")
        }
        #endif
        var request = URLRequest(url: url)
        request.timeoutInterval = 30
        task = session.webSocketTask(with: request)
        print("[sensor] WebSocket task started (resume). Waiting for connection…")
        task?.resume()
        isReceiving = true
        receiveLoop()
    }

    func disconnect() {
        isReceiving = false
        hasLoggedConnected = false
        hasLoggedFirstReceive = false
        task?.cancel(with: .goingAway, reason: nil)
        task = nil
    }

    private func receiveLoop() {
        task?.receive { [weak self] result in
            guard let self else { return }
            switch result {
            case .success(let message):
                if self.hasLoggedFirstReceive == false {
                    self.hasLoggedFirstReceive = true
                    print("[sensor] receiveLoop: got first message (connection is up)")
                }
                if case .string(let text) = message {
                    self.handleMessage(text)
                } else {
                    print("[sensor] received non-string message (ignored)")
                }
                if self.isReceiving { self.receiveLoop() }
            case .failure(let err):
                self.task = nil
                let code = (err as NSError).code
                print("[sensor] WebSocket failed: \(err.localizedDescription) (code: \(code))")
                DispatchQueue.main.async { self.connectionError = "Connect iPhone & laptop to same WiFi (or check Mac IP / firewall)" }
                if self.isReceiving {
                    DispatchQueue.main.asyncAfter(deadline: .now() + 3) { [weak self] in
                        guard let self, self.isReceiving else { return }
                        self.connect()
                    }
                }
            }
        }
    }

    private func handleMessage(_ text: String) {
        guard let data = text.data(using: .utf8),
              let payload = try? JSONDecoder().decode(SensorPayload.self, from: data) else {
            print("[sensor] failed to decode JSON: \(text.prefix(200))")
            return
        }
        DispatchQueue.main.async { [weak self] in
            self?.connectionError = nil
            if self?.hasLoggedConnected == false {
                self?.hasLoggedConnected = true
                print("[sensor] connected and receiving data from bridge")
            }
            print("[sensor] heart_rate: \(payload.heart_rate ?? 0), breath_rate: \(payload.breath_rate ?? 0), distance: \(payload.distance ?? 0) — from bridge")
            self?.onUpdate?(payload)
            guard let eng = self?.engine else {
                print("[sensor] WARNING: engine is nil, vitals not updated")
                return
            }
            let hr = payload.heart_rate ?? eng.heartRate
            let br = payload.breath_rate ?? eng.breathsPerMinute
            eng.heartRate = hr
            eng.breathsPerMinute = br
            eng.lastSensorUpdate = Date()
            eng.appendHistory()
            eng.computePRI()
            eng.evaluateCritical()
            print("[sensor] SET vitals: heartRate=\(eng.heartRate) breathsPerMinute=\(eng.breathsPerMinute)")
        }
    }
}
