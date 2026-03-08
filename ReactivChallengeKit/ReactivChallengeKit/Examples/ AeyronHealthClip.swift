//  AeyronHealthClip.swift
//  ReactivChallengeKit
//
//  AEYRON Health — Caregiver Respiratory Monitor Clip
//  QR scan → instant vitals dashboard for Parkinson's patients
//
//  Copyright © 2025 AEYRON Health Technologies Inc. All rights reserved.
//


//vansh jain

import SwiftUI
import AVFoundation

// MARK: - ClipExperience Conformance

struct AeyronHealthClip: ClipExperience {
    static let urlPattern      = "aeyron.health/patient/:patientId"
    static let clipName        = "AEYRON Health Monitor"
    static let clipDescription = "Real-time respiratory vitals for Parkinson's patients."
    static let touchpoint: JourneyTouchpoint      = .onSite
    static let invocationSource: InvocationSource = .qrCode

    let context: ClipContext

    private var patientId: String {
        context.pathParameters["patientId"] ?? "PKS-0047"
    }

    var body: some View {
        AeyronDashboardView(patientId: patientId, bridgeHost: context.queryParameters["bridge"])
    }
}

// MARK: - Backend API Client

final class AeyronAPIClient {
    static let baseURL = "https://localhost:8000"

    static func notifyCaregiver(patientId: String, completion: @escaping (Bool) -> Void) {
        guard let url = URL(string: "\(baseURL)/alert/caregiver") else { completion(false); return }
        let body: [String: String] = [
            "patientId": patientId,
            "reason": "Manual caregiver notification",
            "timestamp": ISO8601DateFormatter().string(from: Date())
        ]
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try? JSONSerialization.data(withJSONObject: body)
        URLSession.shared.dataTask(with: req) { _, res, _ in
            DispatchQueue.main.async { completion((res as? HTTPURLResponse)?.statusCode == 200) }
        }.resume()
    }

    static func triggerCriticalAlarm(patientId: String, completion: @escaping (Bool) -> Void) {
        guard let url = URL(string: "\(baseURL)/alarm/critical") else { completion(false); return }
        let body: [String: String] = [
            "patientId": patientId,
            "timestamp": ISO8601DateFormatter().string(from: Date())
        ]
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try? JSONSerialization.data(withJSONObject: body)
        URLSession.shared.dataTask(with: req) { _, res, _ in
            DispatchQueue.main.async { completion((res as? HTTPURLResponse)?.statusCode == 200) }
        }.resume()
    }
}

// MARK: - Vitals Engine

@Observable
final class VitalsEngine: NSObject {

    var heartRate: Double          = 72
    var breathsPerMinute: Double   = 14
    var apneaEventsPerHour: Double = 0
    var hrv: Double                = 34.9
    var hypophoniaDB: Double       = -25
    var pneumoniaRiskIndex: Double = 0
    var isCritical: Bool           = false
    var isRunning: Bool            = false
    var permissionDenied: Bool     = false

    var hrHistory: [Double]    = Array(repeating: 72, count: 60)
    var bpmHistory: [Double]   = Array(repeating: 14, count: 60)
    var apneaHistory: [Double] = Array(repeating: 0,  count: 60)

    static let criticalHR: Double    = 110
    static let criticalBPM: Double   = 25
    static let criticalApnea: Double = 15
    static let criticalPRI: Double   = 70
    static let criticalHypo: Double  = -40

    private var audioEngine: AVAudioEngine?
    private var ticker: Timer?
    private var audioRMSBuffer: [Double] = []
    private var silenceFrames: Int       = 0
    private var apneaCount: Int          = 0
    private var sessionStart: Date       = Date()

    private let processingQueue = DispatchQueue(label: "aeyron.vitals", qos: .userInitiated)

    /// Set by SensorWebSocketClient when radar data is received (for optional UI hint).
    var lastSensorUpdate: Date?

    func start() {
        Task { @MainActor in
            let mic = await requestMic()
            guard mic else { permissionDenied = true; return }
            startMicrophone()
            startTicker()
            isRunning    = true
            sessionStart = Date()
        }
    }

    func stop() {
        ticker?.invalidate()
        ticker = nil
        isRunning = false
        audioEngine?.stop()
        audioEngine = nil
    }

    private func requestMic() async -> Bool {
        switch AVAudioApplication.shared.recordPermission {
        case .granted: return true
        case .undetermined:
            return await withCheckedContinuation { cont in
                AVAudioApplication.requestRecordPermission { cont.resume(returning: $0) }
            }
        default: return false
        }
    }

    private func startMicrophone() {
        let engine = AVAudioEngine()
        let input  = engine.inputNode
        let format = input.inputFormat(forBus: 0)
        input.installTap(onBus: 0, bufferSize: 4096, format: format) { [weak self] buffer, _ in
            guard let self, let data = buffer.floatChannelData?[0] else { return }
            let count   = Int(buffer.frameLength)
            let samples = (0..<count).map { Double(data[$0]) }
            self.processingQueue.async { self.processAudio(samples) }
        }
        try? engine.start()
        audioEngine = engine
    }

    private func startTicker() {
        ticker = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { [weak self] _ in
            Task { @MainActor [weak self] in self?.tick() }
        }
    }

    @MainActor
    private func tick() {
        computeVitals()
        appendHistory()
        computePRI()
        evaluateCritical()
    }

    private func processAudio(_ samples: [Double]) {
        let rms  = sqrt(samples.map { $0 * $0 }.reduce(0, +) / Double(samples.count))
        let dbFS = rms > 0 ? 20 * log10(rms) : -160.0
        DispatchQueue.main.async {
            self.hypophoniaDB = dbFS
            self.audioRMSBuffer.append(rms)
            if self.audioRMSBuffer.count > 44100 { self.audioRMSBuffer.removeFirst(22050) }
        }
        if rms < 0.0005 {
            silenceFrames += 1
            if silenceFrames == 80 { apneaCount += 1; silenceFrames = 0 }
        } else {
            silenceFrames = max(0, silenceFrames - 1)
        }
    }

    /// Heart rate and breath rate come from radar (WebSocket) only. This only updates apnea from mic.
    private func computeVitals() {
        let hours          = max(Date().timeIntervalSince(sessionStart) / 3600.0, 1.0 / 60)
        apneaEventsPerHour = Double(apneaCount) / hours
    }

    func computePRI() {
        let hrScore    = normalize(heartRate,          low: 60, high: VitalsEngine.criticalHR)    * 25
        let bpmScore   = normalize(breathsPerMinute,   low: 12, high: VitalsEngine.criticalBPM)   * 30
        let apneaScore = normalize(apneaEventsPerHour, low: 0,  high: VitalsEngine.criticalApnea) * 25
        let hrvScore   = normalize(40 - min(hrv, 40),  low: 0,  high: 40)                         * 20
        pneumoniaRiskIndex = min(hrScore + bpmScore + apneaScore + hrvScore, 100)
    }

    func evaluateCritical() {
        isCritical = pneumoniaRiskIndex   >= VitalsEngine.criticalPRI
            || heartRate          >= VitalsEngine.criticalHR
            || breathsPerMinute   >= VitalsEngine.criticalBPM
            || apneaEventsPerHour >= VitalsEngine.criticalApnea
            || hypophoniaDB       <= VitalsEngine.criticalHypo
    }

    func appendHistory() {
        hrHistory.append(heartRate)
        bpmHistory.append(breathsPerMinute)
        apneaHistory.append(apneaEventsPerHour)
        if hrHistory.count    > 60 { hrHistory.removeFirst() }
        if bpmHistory.count   > 60 { bpmHistory.removeFirst() }
        if apneaHistory.count > 60 { apneaHistory.removeFirst() }
    }

    private func normalize(_ v: Double, low: Double, high: Double) -> Double {
        min(max((v - low) / (high - low), 0), 1)
    }
}

// MARK: - Dashboard View

struct AeyronDashboardView: View {
    let patientId: String
    /// Optional bridge host from clip URL ?bridge=192.168.1.100 (Mac IP from ipconfig getifaddr en0).
    let bridgeHost: String?

    @State private var engine             = VitalsEngine()
    @State private var wsClient           = SensorWebSocketClient()
    @State private var caregiverSent      = false
    @State private var alarmActive        = false
    @State private var showCaregiverToast = false
    @State private var showAlarmToast     = false

    var body: some View {
        ZStack {
            Color(red: 0.05, green: 0.05, blue: 0.08).ignoresSafeArea()

            if engine.isCritical || alarmActive {
                Color.red.opacity(0.07).ignoresSafeArea()
            }

            ScrollView(showsIndicators: false) {
                VStack(spacing: 14) {
                    headerBar
                    if engine.permissionDenied {
                        permissionView
                    } else {
                        metricsGrid
                        riskCard
                        graphsSection
                        actionRow
                    }
                }
                .padding(.horizontal, 16)
                .padding(.bottom, 40)
            }

            VStack {
                Spacer()
                if showCaregiverToast {
                    toastBanner(text: "✅ Caregiver has been notified", color: .green)
                }
                if showAlarmToast {
                    toastBanner(text: "🚨 Critical alarm triggered", color: .red)
                }
            }
            .animation(.spring(), value: showCaregiverToast)
            .animation(.spring(), value: showAlarmToast)
            .padding(.bottom, 16)
        }
        .onAppear {
            engine.start()
            wsClient.engine = engine
            if let host = bridgeHost, !host.isEmpty { wsClient.bridgeHost = host }
            wsClient.connect()
        }
        .onDisappear {
            engine.stop()
            wsClient.disconnect()
        }
    }

    var headerBar: some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 3) {
                Text("AEYRON HEALTH")
                    .font(.system(size: 10, weight: .bold, design: .monospaced))
                    .foregroundStyle(.cyan.opacity(0.6))
                    .kerning(2)
                HStack(spacing: 6) {
                    Text("Patient \(patientId)")
                        .font(.system(size: 20, weight: .bold))
                        .foregroundStyle(.white)
                    if engine.isRunning {
                        Circle().fill(.green).frame(width: 7, height: 7)
                    }
                }
                Text("via AEYRON · \(Date(), format: .dateTime.hour().minute().second())")
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(.white.opacity(0.3))
                if let err = wsClient.connectionError {
                    Text(err)
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(.orange)
                }
            }
            Spacer()
            statusPill
        }
        .padding(.top, 12)
    }

    var statusPill: some View {
        let crit = engine.isCritical || alarmActive
        return Text(crit ? "⚠ CRITICAL" : "● STABLE")
            .font(.system(size: 11, weight: .heavy, design: .monospaced))
            .foregroundStyle(crit ? .black : .green)
            .padding(.horizontal, 12).padding(.vertical, 6)
            .background(crit ? Color.red : Color.green.opacity(0.15))
            .clipShape(Capsule())
    }

    var metricsGrid: some View {
        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
            AeyronMetricCard(
                emoji: "🎙", label: "HYPOPHONIA",
                value: engine.isRunning ? String(format: "%.1f dBFS", engine.hypophoniaDB) : "Awaiting mic data",
                status: engine.hypophoniaDB < -40 ? .warn : .ok,
                isCritical: engine.hypophoniaDB <= VitalsEngine.criticalHypo
            )
            AeyronMetricCard(
                emoji: "💨", label: "BREATH IRREGULARITY",
                value: String(format: "%.1f b/min", engine.breathsPerMinute),
                status: engine.breathsPerMinute > 20 ? .warn : .ok,
                isCritical: engine.breathsPerMinute >= VitalsEngine.criticalBPM
            )
            AeyronMetricCard(
                emoji: "😶", label: "APNEA EVENTS",
                value: String(format: "%.1f events/hr", engine.apneaEventsPerHour),
                status: engine.apneaEventsPerHour > 5 ? .warn : .ok,
                isCritical: engine.apneaEventsPerHour >= VitalsEngine.criticalApnea
            )
            AeyronMetricCard(
                emoji: "❤️", label: "PULSE VARIABILITY",
                value: String(format: "%.1f ms HRV", engine.hrv),
                status: engine.hrv < 20 ? .warn : .ok,
                isCritical: engine.hrv < 15
            )
        }
    }

    var riskCard: some View {
        let pri   = engine.pneumoniaRiskIndex
        let color = priColor(pri)
        return VStack(spacing: 10) {
            HStack {
                Text("PNEUMONIA RISK INDEX")
                    .font(.system(size: 11, weight: .bold, design: .monospaced))
                    .foregroundStyle(.white.opacity(0.5)).kerning(1.5)
                Spacer()
                Text(priLabel(pri))
                    .font(.system(size: 11, weight: .bold, design: .monospaced))
                    .foregroundStyle(color)
            }
            HStack(alignment: .lastTextBaseline, spacing: 4) {
                Text(String(format: "%.0f", pri))
                    .font(.system(size: 52, weight: .black, design: .rounded))
                    .foregroundStyle(color)
                Text("/ 100")
                    .font(.system(size: 16, weight: .medium))
                    .foregroundStyle(.white.opacity(0.3))
                Spacer()
            }
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 4).fill(.white.opacity(0.08)).frame(height: 8)
                    RoundedRectangle(cornerRadius: 4).fill(color)
                        .frame(width: geo.size.width * CGFloat(pri / 100), height: 8)
                        .animation(.easeInOut(duration: 0.5), value: pri)
                }
            }
            .frame(height: 8)
            if engine.isCritical || alarmActive {
                HStack(spacing: 6) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundStyle(.red).font(.system(size: 12))
                    Text("CRITICAL THRESHOLD EXCEEDED — IMMEDIATE ATTENTION REQUIRED")
                        .font(.system(size: 10, weight: .bold, design: .monospaced))
                        .foregroundStyle(.red)
                }
                .padding(.top, 2)
            }
        }
        .padding(16)
        .background(
            RoundedRectangle(cornerRadius: 14).fill(Color(white: 0.07))
                .overlay(RoundedRectangle(cornerRadius: 14)
                    .stroke(engine.isCritical || alarmActive ? Color.red.opacity(0.5) : Color.white.opacity(0.06), lineWidth: 1))
        )
    }

    var graphsSection: some View {
        VStack(spacing: 10) {
            AeyronMiniGraph(label: "❤️ HEART RATE", data: engine.hrHistory,
                            color: .red, yMin: 40, yMax: 160,
                            current: String(format: "%.0f bpm", engine.heartRate))
            AeyronMiniGraph(label: "💨 BREATHS / MIN", data: engine.bpmHistory,
                            color: .cyan, yMin: 0, yMax: 40,
                            current: String(format: "%.1f b/min", engine.breathsPerMinute))
            AeyronMiniGraph(label: "😶 APNEA EVENTS / HR", data: engine.apneaHistory,
                            color: .orange, yMin: 0, yMax: 30,
                            current: String(format: "%.1f /hr", engine.apneaEventsPerHour))
        }
    }

    var actionRow: some View {
        VStack(spacing: 10) {
            Button {
                AeyronAPIClient.notifyCaregiver(patientId: patientId) { _ in
                    caregiverSent      = true
                    showCaregiverToast = true
                    DispatchQueue.main.asyncAfter(deadline: .now() + 3) { showCaregiverToast = false }
                }
            } label: {
                HStack(spacing: 10) {
                    Image(systemName: caregiverSent ? "checkmark.circle.fill" : "bell.badge.fill")
                    Text(caregiverSent ? "Caregiver Notified" : "Inform Caregiver")
                }
                .font(.system(size: 15, weight: .semibold))
                .frame(maxWidth: .infinity)
                .padding(.vertical, 16)
                .background(caregiverSent ? Color.green.opacity(0.2) : Color(red: 0.1, green: 0.4, blue: 1.0))
                .foregroundStyle(caregiverSent ? .green : .white)
                .clipShape(RoundedRectangle(cornerRadius: 14))
            }

            Button {
                alarmActive    = true
                showAlarmToast = true
                UINotificationFeedbackGenerator().notificationOccurred(.error)
                AeyronAPIClient.triggerCriticalAlarm(patientId: patientId) { _ in }
                DispatchQueue.main.asyncAfter(deadline: .now() + 3) { showAlarmToast = false }
            } label: {
                HStack(spacing: 10) {
                    Image(systemName: alarmActive ? "alarm.fill" : "alarm")
                    Text(alarmActive ? "Alarm Active" : "Trigger Critical Alarm")
                }
                .font(.system(size: 15, weight: .semibold))
                .frame(maxWidth: .infinity)
                .padding(.vertical, 16)
                .background(alarmActive ? Color.red : Color.red.opacity(0.15))
                .foregroundStyle(.white)
                .clipShape(RoundedRectangle(cornerRadius: 14))
                .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color.red.opacity(0.5), lineWidth: 1))
            }
        }
    }

    var permissionView: some View {
        VStack(spacing: 16) {
            Image(systemName: "exclamationmark.lock.fill").font(.system(size: 44)).foregroundStyle(.orange)
            Text("Microphone Required").font(.title3.bold()).foregroundStyle(.white)
            Text("AEYRON uses the microphone for voice and respiratory analysis (hypophonia). Heart and breath rate come from the radar sensor.")
                .font(.callout).foregroundStyle(.white.opacity(0.6)).multilineTextAlignment(.center)
            Button("Open Settings") {
                if let url = URL(string: UIApplication.openSettingsURLString) { UIApplication.shared.open(url) }
            }
            .foregroundStyle(.cyan)
        }
        .padding(32)
    }

    func toastBanner(text: String, color: Color) -> some View {
        Text(text)
            .font(.system(size: 13, weight: .semibold)).foregroundStyle(.white)
            .padding(.horizontal, 20).padding(.vertical, 12)
            .background(color.opacity(0.9)).clipShape(Capsule()).shadow(radius: 10)
            .transition(.move(edge: .bottom).combined(with: .opacity))
    }

    func priColor(_ v: Double) -> Color {
        switch v {
        case ..<30:   return .green
        case 30..<60: return .yellow
        case 60..<80: return .orange
        default:      return .red
        }
    }

    func priLabel(_ v: Double) -> String {
        switch v {
        case ..<30:   return "LOW RISK"
        case 30..<60: return "MODERATE"
        case 60..<80: return "HIGH RISK"
        default:      return "CRITICAL"
        }
    }
}

// MARK: - Metric Card

enum AeyronMetricStatus { case ok, warn }

struct AeyronMetricCard: View {
    let emoji: String
    let label: String
    let value: String
    let status: AeyronMetricStatus
    let isCritical: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(emoji).font(.system(size: 20))
                Spacer()
                Text(isCritical ? "CRITICAL" : status == .warn ? "WARN" : "OK")
                    .font(.system(size: 9, weight: .bold, design: .monospaced))
                    .foregroundStyle(isCritical ? .black : status == .warn ? .orange : .green)
                    .padding(.horizontal, 6).padding(.vertical, 3)
                    .background(isCritical ? Color.red : status == .warn ? Color.orange.opacity(0.2) : Color.green.opacity(0.15))
                    .clipShape(Capsule())
            }
            Text(label)
                .font(.system(size: 9, weight: .bold, design: .monospaced))
                .foregroundStyle(.white.opacity(0.4))
                .kerning(0.5).lineLimit(1).minimumScaleFactor(0.7)
            Text(value)
                .font(.system(size: 15, weight: .bold, design: .rounded))
                .foregroundStyle(isCritical ? .red : .white)
                .lineLimit(1).minimumScaleFactor(0.7)
        }
        .padding(14)
        .background(
            RoundedRectangle(cornerRadius: 14).fill(Color(white: 0.07))
                .overlay(RoundedRectangle(cornerRadius: 14)
                    .stroke(isCritical ? Color.red.opacity(0.5) : Color.white.opacity(0.06), lineWidth: 1))
        )
    }
}

// MARK: - Mini Graph

struct AeyronMiniGraph: View {
    let label:   String
    let data:    [Double]
    let color:   Color
    let yMin:    Double
    let yMax:    Double
    let current: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(label)
                    .font(.system(size: 10, weight: .bold, design: .monospaced))
                    .foregroundStyle(.white.opacity(0.5)).kerning(1)
                Spacer()
                Text(current)
                    .font(.system(size: 12, weight: .bold, design: .rounded))
                    .foregroundStyle(color)
            }
            GeometryReader { geo in
                let w = geo.size.width
                let h = geo.size.height
                let pts = data.enumerated().map { i, v -> CGPoint in
                    let x = w * CGFloat(i) / CGFloat(max(data.count - 1, 1))
                    let y = h - h * CGFloat((v - yMin) / (yMax - yMin))
                    return CGPoint(x: x, y: min(max(y, 0), h))
                }
                ZStack {
                    if pts.count > 1 {
                        Path { p in
                            p.move(to: CGPoint(x: pts[0].x, y: h))
                            pts.forEach { p.addLine(to: $0) }
                            p.addLine(to: CGPoint(x: pts.last!.x, y: h))
                            p.closeSubpath()
                        }
                        .fill(LinearGradient(colors: [color.opacity(0.3), .clear], startPoint: .top, endPoint: .bottom))

                        Path { p in
                            p.move(to: pts[0])
                            pts.dropFirst().forEach { p.addLine(to: $0) }
                        }
                        .stroke(color, style: StrokeStyle(lineWidth: 1.5, lineCap: .round, lineJoin: .round))
                    }
                    if let last = pts.last {
                        Circle().fill(color).frame(width: 5, height: 5).position(last)
                    }
                }
            }
            .frame(height: 56)
            .background(Color.white.opacity(0.03))
            .clipShape(RoundedRectangle(cornerRadius: 8))
        }
        .padding(14)
        .background(
            RoundedRectangle(cornerRadius: 14).fill(Color(white: 0.07))
                .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color.white.opacity(0.06), lineWidth: 1))
        )
    }
}
