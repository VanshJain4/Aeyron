//  AeyronHealthClip.swift
//  ReactivChallengeKit
//
//  AEYRON Health Caregiver Respiratory Monitor Clip
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
    /// Distance (m) from radar; set by SensorWebSocketClient.
    var distance: Double           = 0
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
    @State private var showCaregiverToast  = false
    @State private var showAlarmToast      = false
    @State private var isPulsing          = false
    @Environment(\.colorScheme) private var colorScheme

    private var isAlert: Bool {
        engine.distance > 1.5 || engine.isCritical || alarmActive
    }
    private var accentColor: Color { isAlert ? .red : .teal }
    /// Central breath wave circle: green initially, red when critical alarm is triggered.
    private var breathWaveCircleColor: Color { alarmActive ? .red : .green }

    var body: some View {
        ZStack {
            (colorScheme == .dark ? Color.black : Color(white: 0.98)).ignoresSafeArea()
            ScrollView(showsIndicators: false) {
                VStack(spacing: 32) {
                    if engine.permissionDenied {
                        permissionView
                    } else {
                        medicalGreeting
                        breathWaveSection
                        symptomCardsSection
                        telemetryHeartRateSection
                        telemetryBreathRateSection
                        actionRow
                        surveillanceSection
                        oneMillionSection
                        founderStorySection
                        respiratoryFidelitySection
                        criticalWindowSection
                        footerButton
                    }
                }
                .padding(.bottom, 40)
            }
            VStack {
                Spacer()
                if showCaregiverToast { toastBanner(text: "✅ Caregiver has been notified", color: .green) }
                if showAlarmToast { toastBanner(text: "🚨 Critical alarm triggered", color: .red) }
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
            withAnimation(.easeInOut(duration: 60.0 / max(engine.breathsPerMinute, 1)).repeatForever(autoreverses: true)) { isPulsing = true }
        }
        .onDisappear {
            engine.stop()
            wsClient.disconnect()
        }
    }

    private var medicalGreeting: some View {
        HStack(spacing: 12) {
            Circle()
                .fill(Color.red)
                .frame(width: 10, height: 10)
                .opacity(isPulsing ? 1 : 0.3)
                .animation(.easeInOut(duration: 1).repeatForever(), value: isPulsing)
            VStack(alignment: .leading, spacing: 4) {
                Text("CLINICAL ASSESSMENT ACTIVE")
                    .font(.system(size: 16, weight: .bold, design: .monospaced))
                    .foregroundColor(colorScheme == .dark ? .white : .primary)
                Text("Patient \(patientId) · \(engine.isRunning ? "Live" : "Connecting…")")
                    .font(.system(size: 14))
                    .foregroundColor(.secondary)
                if let err = wsClient.connectionError {
                    Text(err).font(.system(size: 9, design: .monospaced)).foregroundColor(.orange)
                }
            }
            Spacer()
        }
        .padding(.horizontal, 24)
        .padding(.top, 40)
    }

    private var breathWaveSection: some View {
        let circleColor = breathWaveCircleColor
        return ZStack {
            Circle()
                .stroke(circleColor.opacity(colorScheme == .dark ? 0.2 : 0.3), lineWidth: 2)
                .frame(width: 260, height: 260)
            Circle()
                .fill(circleColor.opacity(0.15))
                .frame(width: 200, height: 200)
                .scaleEffect(isPulsing ? 1.2 : 0.9)
                .blur(radius: isPulsing ? 30 : 15)
            Circle()
                .fill(circleColor)
                .frame(width: 100, height: 100)
                .shadow(color: circleColor.opacity(0.6), radius: 30)
                .scaleEffect(isPulsing ? 1.1 : 0.95)
                .overlay(Image(systemName: "wind").font(.system(size: 32, weight: .bold)).foregroundColor(.black))
        }
        .frame(height: 320)
    }

    private var symptomCardsSection: some View {
        VStack(spacing: 16) {
            AeyronSymptomCard(number: 1, title: "Hypophonia", value: engine.isRunning ? String(format: "%.0f dB", engine.hypophoniaDB) : "...", isAlert: false)
            AeyronSymptomCard(number: 2, title: "Heart Rate", value: "\(Int(engine.heartRate)) BPM", isAlert: false)
            AeyronSymptomCard(number: 3, title: "Breath Rate", value: "\(Int(engine.breathsPerMinute)) RPM", isAlert: false)
            AeyronSymptomCard(number: 4, title: "Motion distance", value: String(format: "%.1f CM", engine.distance), isAlert: engine.distance > 1.5)
        }
        .padding(.horizontal, 24)
    }

    private var telemetryHeartRateSection: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("TELEMETRY: HEART RATE")
                .font(.system(size: 14, weight: .bold, design: .monospaced))
                .foregroundColor(.secondary)
                .padding(.horizontal, 24)
            AeyronMiniGraph(label: "HEART RATE", data: engine.hrHistory, color: accentColor, yMin: 40, yMax: 160, current: String(format: "%.0f bpm", engine.heartRate))
                .padding(.horizontal, 24)
        }
    }

    private var telemetryBreathRateSection: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("TELEMETRY: BREATH RATE")
                .font(.system(size: 14, weight: .bold, design: .monospaced))
                .foregroundColor(.secondary)
                .padding(.horizontal, 24)
            AeyronMiniGraph(label: "BREATH RATE", data: engine.bpmHistory, color: accentColor, yMin: 0, yMax: 40, current: String(format: "%.1f b/min", engine.breathsPerMinute))
                .padding(.horizontal, 24)
        }
    }

    private var surveillanceSection: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 48)
                .fill(colorScheme == .dark ? Color(white: 0.05) : Color.white)
                .frame(height: 360)
                .overlay(RoundedRectangle(cornerRadius: 48).stroke(colorScheme == .dark ? Color.white.opacity(0.05) : Color.black.opacity(0.05), lineWidth: 1))
                .shadow(color: colorScheme == .dark ? .clear : .black.opacity(0.1), radius: 20, x: 0, y: 10)
            Circle()
                .trim(from: 0, to: 0.2)
                .stroke(AngularGradient(gradient: Gradient(colors: [accentColor, .clear]), center: .center), style: StrokeStyle(lineWidth: 120, lineCap: .round))
                .frame(width: 240, height: 240)
                .rotationEffect(.degrees(isPulsing ? 360 : 0))
                .animation(.linear(duration: 4).repeatForever(autoreverses: false), value: isPulsing)
                .opacity(0.2)
            VStack(spacing: 20) {
                Image(systemName: "antenna.radiowaves.left.and.right").font(.system(size: 50)).foregroundColor(accentColor)
                Text("Ambient Surveillance").font(.system(size: 24, weight: .bold)).foregroundColor(colorScheme == .dark ? .white : .primary)
                Text("Our radar technology maps micro-movements in the room, detecting tremors and respiratory patterns through walls and furniture.")
                    .font(.system(size: 16)).foregroundColor(.secondary).multilineTextAlignment(.center).padding(.horizontal, 48)
            }
        }
        .padding(.horizontal, 24)
    }

    private var oneMillionSection: some View {
        VStack(spacing: 12) {
            Text("1,000,000+").font(.system(size: 44, weight: .black, design: .rounded)).foregroundColor(.red).tracking(-2)
            Text("LIVES IMPACTED BY PARKINSON'S").font(.system(size: 12, weight: .bold, design: .monospaced)).foregroundColor(.secondary).tracking(3)
            Text("Parkinson's is the fastest growing neurological condition in the world. Early detection isn't just a goal, it's a necessity.")
                .font(.system(size: 18)).foregroundColor(.secondary).multilineTextAlignment(.center).padding(.horizontal, 40).padding(.top, 16)
        }
        .padding(.vertical, 60)
    }

    private var founderStorySection: some View {
        VStack(alignment: .leading, spacing: 20) {
            HStack(spacing: 12) {
                Image(systemName: "heart.fill").font(.title2).foregroundColor(.teal)
                Text("The Founder's Journey").font(.title3).fontWeight(.bold)
            }
            Text("Aeyron Health was born from a personal mission. Our founder watched a loved one struggle with Parkinson's, realizing that the most critical data was being lost in the gaps between doctor visits.")
                .font(.system(size: 17)).foregroundColor(.secondary).lineSpacing(4)
            Text("\"No one was watching when it mattered most. We built Aeyron to be that silent guardian, turning every room into a clinical-grade monitoring suite.\"")
                .font(.system(size: 17)).italic().foregroundColor(.secondary).lineSpacing(4)
        }
        .padding(40)
        .background(colorScheme == .dark ? Color(white: 0.05) : Color.white)
        .cornerRadius(40)
        .shadow(color: colorScheme == .dark ? .clear : .black.opacity(0.05), radius: 15, x: 0, y: 8)
        .padding(.horizontal, 24)
    }

    private var respiratoryFidelitySection: some View {
        VStack(alignment: .leading, spacing: 24) {
            HStack {
                Text("Respiratory Fidelity").font(.system(size: 18, weight: .bold))
                Spacer()
                Text("LIVE STREAM").font(.system(size: 12, weight: .bold)).foregroundColor(accentColor)
                    .padding(.horizontal, 12).padding(.vertical, 6).background(accentColor.opacity(0.1)).cornerRadius(10)
            }
            HStack(spacing: 16) {
                VStack(spacing: 12) {
                    Image(systemName: "lungs.fill").font(.system(size: 36)).foregroundColor(accentColor)
                    Text("LUNG CAPACITY").font(.system(size: 10, weight: .bold)).foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity).frame(height: 140)
                .background(colorScheme == .dark ? Color(white: 0.05) : Color.white).cornerRadius(28)
                VStack(spacing: 12) {
                    Image(systemName: "waveform.path").font(.system(size: 36)).foregroundColor(colorScheme == .dark ? .white : .primary)
                    Text("TREMOR INDEX").font(.system(size: 10, weight: .bold)).foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity).frame(height: 140)
                .background(colorScheme == .dark ? Color(white: 0.05) : Color.white).cornerRadius(28)
            }
        }
        .padding(.horizontal, 24)
    }

    private var criticalWindowSection: some View {
        VStack(spacing: 32) {
            VStack(spacing: 12) {
                Text("10-14 WEEKS").font(.system(size: 44, weight: .black))
                Text("THE CRITICAL WINDOW")
                .font(.system(size: 14, weight: .bold))
                .tracking(4)
                .opacity(0.7)
                .lineLimit(1)
                .minimumScaleFactor(0.6)
            }
            Text("Clinical studies show that the first 10-14 weeks of monitoring provide the highest predictive value for treatment adjustment.")
                .font(.system(size: 18, weight: .medium)).multilineTextAlignment(.center).padding(.horizontal, 24)
            Link(destination: URL(string: "https://www.aeyronhealth.co/#s6")!) {
                Text("Request Clinical Access").font(.system(size: 20, weight: .bold))
                    .foregroundColor(colorScheme == .dark ? .black : .white).frame(maxWidth: .infinity).padding(.vertical, 20)
                    .background(colorScheme == .dark ? Color.white : Color.black).cornerRadius(24).shadow(color: .black.opacity(0.2), radius: 15, x: 0, y: 10)
            }
        }
        .padding(40)
        .background(accentColor)
        .foregroundColor(isAlert ? .white : .black)
        .cornerRadius(56)
        .padding(.horizontal, 24)
        .padding(.top, 60)
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
        .padding(.horizontal, 24)
    }

    private var footerButton: some View {
        Button(action: {}) {
            HStack {
                Text("View full patient history in Aeyron Hub")
                Image(systemName: "arrow.up.right")
            }
            .font(.system(size: 16, weight: .medium))
            .foregroundColor(.secondary)
            .padding(.vertical, 60)
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

// MARK: - Symptom Card (new UI)

struct AeyronSymptomCard: View {
    let number: Int
    let title: String
    let value: String
    var isAlert: Bool = false
    @Environment(\.colorScheme) private var colorScheme

    private var circleFill: Color {
        if isAlert { return Color.red.opacity(0.2) }
        return colorScheme == .dark ? Color.white.opacity(0.1) : Color.black.opacity(0.05)
    }
    private var textColor: Color {
        if isAlert { return .red }
        return colorScheme == .dark ? .white : .primary
    }
    private var cardBackground: Color {
        if isAlert { return Color.red.opacity(0.1) }
        return colorScheme == .dark ? Color.white.opacity(0.05) : Color.white
    }
    private var strokeColor: Color {
        if isAlert { return Color.red.opacity(0.5) }
        return colorScheme == .dark ? Color.white.opacity(0.1) : Color.black.opacity(0.05)
    }

    var body: some View {
        HStack(spacing: 20) {
            ZStack {
                Circle().fill(circleFill).frame(width: 50, height: 50)
                Text("\(number)").font(.system(size: 22, weight: .bold)).foregroundColor(textColor)
            }
            VStack(alignment: .leading, spacing: 4) {
                Text(title.uppercased())
                    .font(.system(size: 12, weight: .bold))
                    .foregroundColor(.secondary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.6)
                Text(value)
                    .font(.system(size: 26, weight: .bold))
                    .foregroundColor(textColor)
                    .lineLimit(1)
                    .minimumScaleFactor(0.5)
            }
            .frame(minWidth: 0, maxWidth: .infinity, alignment: .leading)
            Spacer()
            if isAlert {
                Image(systemName: "exclamationmark.triangle.fill").foregroundColor(.red).font(.system(size: 28))
            }
        }
        .padding(20)
        .background(cardBackground)
        .cornerRadius(24)
        .overlay(RoundedRectangle(cornerRadius: 24).stroke(strokeColor, lineWidth: 1))
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
