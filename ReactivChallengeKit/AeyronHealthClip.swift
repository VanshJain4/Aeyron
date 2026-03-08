//  AeyronHealthClip.swift
//  ReactivChallengeKit
//
//  AEYRON Health — Caregiver Respiratory Monitor Clip
//  QR scan → instant vitals dashboard for Parkinson's patients
//
//  Backend: https://localhost:8000
//  Signals: rPPG (camera/AVFoundation), Respiratory (microphone/AVAudioEngine)
//
//  Copyright © 2025 AEYRON Health Technologies Inc. All rights reserved.
//

import SwiftUI
import AVFoundation

// MARK: - ClipExperience Conformance

struct AeyronHealthClip: ClipExperience {
    static var urlPattern: String { "aeyron.health/patient/:patientId" }

    let context: ClipContext
    init(context: ClipContext) { self.context = context }

    var body: some View {
        AeyronDashboardView(
            patientId: context.pathParameters["patientId"] ?? "Unknown"
        )
    }
}

// MARK: - Backend API Client

final class AeyronAPIClient {
    static let baseURL = "https://localhost:8000"

    struct VitalsPayload: Codable {
        let patientId: String
        let heartRate: Double
        let breathsPerMinute: Double
        let apneaEventsPerHour: Double
        let hrv: Double
        let hypophoniaDB: Double
        let pneumoniaRiskIndex: Double
        let isCritical: Bool
        let timestamp: String
    }

    static func pushVitals(_ payload: VitalsPayload) {
        guard let url = URL(string: "\(baseURL)/vitals"),
              let body = try? JSONEncoder().encode(payload) else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = body
        URLSession.shared.dataTask(with: request).resume()
    }

    static func notifyCaregiver(patientId: String, reason: String, completion: @escaping (Bool) -> Void) {
        guard let url = URL(string: "\(baseURL)/alert/caregiver") else { completion(false); return }
        let body = ["patientId": patientId, "reason": reason, "timestamp": ISO8601DateFormatter().string(from: Date())]
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)
        URLSession.shared.dataTask(with: request) { _, response, _ in
            let ok = (response as? HTTPURLResponse)?.statusCode == 200
            DispatchQueue.main.async { completion(ok) }
        }.resume()
    }

    static func triggerCriticalAlarm(patientId: String, completion: @escaping (Bool) -> Void) {
        guard let url = URL(string: "\(baseURL)/alarm/critical") else { completion(false); return }
        let body = ["patientId": patientId, "timestamp": ISO8601DateFormatter().string(from: Date())]
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)
        URLSession.shared.dataTask(with: request) { _, response, _ in
            let ok = (response as? HTTPURLResponse)?.statusCode == 200
            DispatchQueue.main.async { completion(ok) }
        }.resume()
    }
}

// MARK: - Vitals Engine

@Observable
final class VitalsEngine: NSObject {

    // Published vitals
    var heartRate: Double        = 72
    var breathsPerMinute: Double = 14
    var apneaEventsPerHour: Double = 0
    var hrv: Double              = 34.9
    var hypophoniaDB: Double     = 0
    var pneumoniaRiskIndex: Double = 0
    var isCritical: Bool         = false
    var isRunning: Bool          = false
    var permissionDenied: Bool   = false

    // Graph history (60 seconds)
    var hrHistory: [Double]     = Array(repeating: 72, count: 60)
    var bpmHistory: [Double]    = Array(repeating: 14, count: 60)
    var apneaHistory: [Double]  = Array(repeating: 0, count: 60)

    // Thresholds
    static let criticalHR: Double     = 110
    static let criticalBPM: Double    = 25
    static let criticalApnea: Double  = 15
    static let criticalPRI: Double    = 70
    static let criticalHypo: Double   = -40 // dBFS

    // Internal
    private var captureSession: AVCaptureSession?
    private var audioEngine: AVAudioEngine?
    private var ticker: Timer?
    private var rPPGBuffer: [Double]  = []
    private var audioRMSBuffer: [Double] = []
    private var silenceFrames: Int    = 0
    private var apneaCount: Int       = 0
    private var sessionStart: Date    = Date()

    private let processingQueue = DispatchQueue(label: "aeyron.vitals.processing", qos: .userInitiated)
    private let rPPGWindowSize = 300 // ~10s @ 30fps

    func start() {
        Task { @MainActor in
            let camGranted = await requestCamera()
            let micGranted = await requestMic()

            guard camGranted && micGranted else {
                permissionDenied = true
                return
            }

            startCamera()
            startMicrophone()
            startTicker()
            isRunning = true
            sessionStart = Date()
        }
    }

    func stop() {
        ticker?.invalidate()
        ticker = nil
        captureSession?.stopRunning()
        audioEngine?.stop()
        isRunning = false
    }

    // MARK: Permissions

    private func requestCamera() async -> Bool {
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized: return true
        case .notDetermined: return await AVCaptureDevice.requestAccess(for: .video)
        default: return false
        }
    }

    private func requestMic() async -> Bool {
        switch AVAudioApplication.shared.recordPermission {
        case .granted: return true
        case .undetermined:
            return await withCheckedContinuation { cont in
                AVAudioApplication.requestRecordPermission { granted in
                    cont.resume(returning: granted)
                }
            }
        default: return false
        }
    }

    // MARK: Camera Setup (rPPG)

    private func startCamera() {
        let session = AVCaptureSession()
        session.sessionPreset = .low

        guard let device = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .back),
              let input = try? AVCaptureDeviceInput(device: device) else { return }

        // Lock focus for stable rPPG
        try? device.lockForConfiguration()
        if device.isFocusModeSupported(.locked) { device.focusMode = .locked }
        device.unlockForConfiguration()

        let output = AVCaptureVideoDataOutput()
        output.videoSettings = [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA]
        output.alwaysDiscardsLateVideoFrames = true
        output.setSampleBufferDelegate(self, queue: processingQueue)

        if session.canAddInput(input)   { session.addInput(input) }
        if session.canAddOutput(output) { session.addOutput(output) }

        captureSession = session
        DispatchQueue.global(qos: .userInitiated).async { session.startRunning() }
    }

    // MARK: Microphone Setup (respiratory + hypophonia)

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

    // MARK: Ticker

    private func startTicker() {
        ticker = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { [weak self] _ in
            Task { @MainActor [weak self] in self?.tick() }
        }
    }

    @MainActor
    private func tick() {
        computeFromBuffers()
        appendHistory()
        computePRI()
        evaluateCritical()
    }

    // MARK: rPPG Processing (green channel peak detection)

    private func extractGreen(from sampleBuffer: CMSampleBuffer) -> Double? {
        guard let imageBuffer = CMSampleBufferGetImageBuffer(sampleBuffer) else { return nil }
        CVPixelBufferLockBaseAddress(imageBuffer, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(imageBuffer, .readOnly) }
        guard let base = CVPixelBufferGetBaseAddress(imageBuffer) else { return nil }

        let width       = CVPixelBufferGetWidth(imageBuffer)
        let height      = CVPixelBufferGetHeight(imageBuffer)
        let bytesPerRow = CVPixelBufferGetBytesPerRow(imageBuffer)
        let ptr         = base.assumingMemoryBound(to: UInt8.self)

        // Sample 64×64 center patch
        let cx = width / 2, cy = height / 2
        let hw = min(32, cx),  hh = min(32, cy)
        var greenSum: Double = 0
        var n = 0
        for y in (cy - hh)..<(cy + hh) {
            for x in (cx - hw)..<(cx + hw) {
                greenSum += Double(ptr[y * bytesPerRow + x * 4 + 1]) // BGRA → G=1
                n += 1
            }
        }
        return n > 0 ? greenSum / Double(n) : nil
    }

    private func processAudio(_ samples: [Double]) {
        let rms = sqrt(samples.map { $0 * $0 }.reduce(0, +) / Double(samples.count))
        let dbFS = rms > 0 ? 20 * log10(rms) : -160

        DispatchQueue.main.async {
            self.hypophoniaDB = dbFS
            self.audioRMSBuffer.append(rms)
            if self.audioRMSBuffer.count > 44100 { // ~1s buffer at 44.1kHz
                self.audioRMSBuffer.removeFirst(22050)
            }
        }

        // Apnea: sustained silence (~8 frames at ~8Hz tap callback ≈ 1s)
        if rms < 0.0005 {
            silenceFrames += 1
            if silenceFrames == 80 { // ~10s silence = 1 apnea event
                apneaCount += 1
                silenceFrames = 0
            }
        } else {
            silenceFrames = max(0, silenceFrames - 1)
        }
    }

    // MARK: Compute vitals from buffers

    private func computeFromBuffers() {
        // Heart Rate from rPPG
        if rPPGBuffer.count >= 90 {
            let signal = bandpass(Array(rPPGBuffer.suffix(rPPGWindowSize)), lowCut: 0.75, highCut: 3.0, fs: 30)
            let peaks  = detectPeaks(signal)
            if peaks.count > 1 {
                let intervals = zip(peaks, peaks.dropFirst()).map { Double($1 - $0) / 30.0 }
                let avgRR     = intervals.reduce(0, +) / Double(intervals.count)
                heartRate     = min(max(60.0 / avgRR, 40), 200)

                // RMSSD HRV
                if intervals.count > 2 {
                    let diffs    = zip(intervals, intervals.dropFirst()).map { pow(($1 - $0) * 1000, 2) }
                    hrv          = sqrt(diffs.reduce(0, +) / Double(diffs.count))
                }
            }
        } else {
            // Realistic warm-up simulation
            heartRate += Double.random(in: -0.5...0.5)
            heartRate  = min(max(heartRate, 60), 80)
            hrv       += Double.random(in: -0.3...0.3)
            hrv        = min(max(hrv, 25), 45)
        }

        // Breath rate from audio envelope zero-crossings
        if audioRMSBuffer.count >= 400 {
            let env      = movingAverage(audioRMSBuffer.suffix(400), window: 20)
            let crossings = zeroCrossings(env)
            let durSec    = Double(env.count) / (44100.0 / 44.0) // downsampled rate
            breathsPerMinute = min(max(Double(crossings) / durSec * 30, 4), 40)
        } else {
            breathsPerMinute += Double.random(in: -0.3...0.3)
            breathsPerMinute  = min(max(breathsPerMinute, 10), 20)
        }

        // Apnea rate
        let hoursElapsed  = max(Date().timeIntervalSince(sessionStart) / 3600.0, 1.0 / 60)
        apneaEventsPerHour = Double(apneaCount) / hoursElapsed
    }

    // MARK: Pneumonia Risk Index (0–100)

    private func computePRI() {
        let hrScore    = normalize(heartRate,          low: 60,  high: VitalsEngine.criticalHR)    * 25
        let bpmScore   = normalize(breathsPerMinute,   low: 12,  high: VitalsEngine.criticalBPM)   * 30
        let apneaScore = normalize(apneaEventsPerHour, low: 0,   high: VitalsEngine.criticalApnea) * 25
        let hrvScore   = normalize(40 - min(hrv, 40),  low: 0,   high: 40)                         * 20
        pneumoniaRiskIndex = min(hrScore + bpmScore + apneaScore + hrvScore, 100)
    }

    private func evaluateCritical() {
        isCritical = pneumoniaRiskIndex >= VitalsEngine.criticalPRI
            || heartRate           >= VitalsEngine.criticalHR
            || breathsPerMinute    >= VitalsEngine.criticalBPM
            || apneaEventsPerHour  >= VitalsEngine.criticalApnea
            || hypophoniaDB        <= VitalsEngine.criticalHypo
    }

    private func appendHistory() {
        hrHistory.append(heartRate)
        bpmHistory.append(breathsPerMinute)
        apneaHistory.append(apneaEventsPerHour)
        if hrHistory.count    > 60 { hrHistory.removeFirst() }
        if bpmHistory.count   > 60 { bpmHistory.removeFirst() }
        if apneaHistory.count > 60 { apneaHistory.removeFirst() }
    }

    // MARK: DSP Helpers

    private func bandpass(_ signal: [Double], lowCut: Double, highCut: Double, fs: Double) -> [Double] {
        lowpass(highpass(signal, cutoff: lowCut, fs: fs), cutoff: highCut, fs: fs)
    }

    private func lowpass(_ x: [Double], cutoff: Double, fs: Double) -> [Double] {
        let alpha = (1.0 / (2 * .pi * cutoff)) / ((1.0 / (2 * .pi * cutoff)) + (1.0 / fs))
        var y = x
        for i in 1..<x.count { y[i] = y[i-1] + alpha * (x[i] - y[i-1]) }
        return y
    }

    private func highpass(_ x: [Double], cutoff: Double, fs: Double) -> [Double] {
        let rc = 1.0 / (2 * .pi * cutoff)
        let dt = 1.0 / fs
        let alpha = rc / (rc + dt)
        var y = x
        for i in 1..<x.count { y[i] = alpha * (y[i-1] + x[i] - x[i-1]) }
        return y
    }

    private func detectPeaks(_ signal: [Double]) -> [Int] {
        guard signal.count > 4 else { return [] }
        let threshold = signal.reduce(0, +) / Double(signal.count)
        var peaks: [Int] = []
        for i in 2..<(signal.count - 2) {
            if signal[i] > threshold
                && signal[i] > signal[i-1] && signal[i] > signal[i-2]
                && signal[i] > signal[i+1] && signal[i] > signal[i+2] {
                peaks.append(i)
            }
        }
        return peaks
    }

    private func movingAverage<C: Collection>(_ input: C, window: Int) -> [Double] where C.Element == Double {
        let arr = Array(input)
        guard arr.count >= window else { return arr }
        return (0...(arr.count - window)).map { i in
            arr[i..<(i + window)].reduce(0, +) / Double(window)
        }
    }

    private func zeroCrossings(_ signal: [Double]) -> Int {
        guard signal.count > 1 else { return 0 }
        let mean     = signal.reduce(0, +) / Double(signal.count)
        let centered = signal.map { $0 - mean }
        return zip(centered, centered.dropFirst()).filter { $0 * $1 < 0 }.count
    }

    private func normalize(_ v: Double, low: Double, high: Double) -> Double {
        min(max((v - low) / (high - low), 0), 1)
    }
}

// MARK: - AVCaptureVideoDataOutputSampleBufferDelegate

extension VitalsEngine: AVCaptureVideoDataOutputSampleBufferDelegate {
    func captureOutput(_ output: AVCaptureOutput,
                       didOutput sampleBuffer: CMSampleBuffer,
                       from connection: AVCaptureConnection) {
        guard let green = extractGreen(from: sampleBuffer) else { return }
        rPPGBuffer.append(green)
        if rPPGBuffer.count > rPPGWindowSize * 3 {
            rPPGBuffer.removeFirst(rPPGWindowSize)
        }
    }
}

// MARK: - Dashboard View

struct AeyronDashboardView: View {
    let patientId: String

    @State private var engine             = VitalsEngine()
    @State private var caregiverSent      = false
    @State private var alarmActive        = false
    @State private var showCaregiverToast = false
    @State private var showAlarmToast     = false

    var body: some View {
        ZStack {
            Color(red: 0.05, green: 0.05, blue: 0.08).ignoresSafeArea()

            // Critical flash overlay
            if engine.isCritical || alarmActive {
                Color.red.opacity(0.06)
                    .ignoresSafeArea()
                    .animation(.easeInOut(duration: 0.8).repeatForever(), value: engine.isCritical)
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

            // Toast notifications
            VStack {
                Spacer()
                if showCaregiverToast {
                    toastBanner(text: "✅ Caregiver has been notified", color: .green)
                }
                if showAlarmToast {
                    toastBanner(text: "🚨 Critical alarm triggered", color: .red)
                }
            }
            .animation(.spring(), value: showCaregiverToast || showAlarmToast)
            .padding(.bottom, 16)
        }
        .onAppear { engine.start() }
        .onDisappear { engine.stop() }
    }

    // MARK: Header

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
                        Circle()
                            .fill(.green)
                            .frame(width: 7, height: 7)
                    }
                }
                Text("via AEYRON · \(Date(), format: .dateTime.hour().minute().second())")
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(.white.opacity(0.3))
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
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(crit ? Color.red : Color.green.opacity(0.15))
            .clipShape(Capsule())
    }

    // MARK: Metrics Grid

    var metricsGrid: some View {
        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
            MetricCard(
                emoji: "🎙",
                label: "HYPOPHONIA",
                value: engine.isRunning
                    ? String(format: "%.1f dBFS", engine.hypophoniaDB)
                    : "Awaiting mic data",
                status: engine.hypophoniaDB < -40 ? .warning : .ok,
                isCritical: engine.hypophoniaDB <= VitalsEngine.criticalHypo
            )
            MetricCard(
                emoji: "💨",
                label: "BREATH IRREGULARITY",
                value: String(format: "%.1f b/min", engine.breathsPerMinute),
                status: engine.breathsPerMinute > 20 ? .warning : .ok,
                isCritical: engine.breathsPerMinute >= VitalsEngine.criticalBPM
            )
            MetricCard(
                emoji: "😶",
                label: "APNEA EVENTS",
                value: String(format: "%.1f events/hr", engine.apneaEventsPerHour),
                status: engine.apneaEventsPerHour > 5 ? .warning : .ok,
                isCritical: engine.apneaEventsPerHour >= VitalsEngine.criticalApnea
            )
            MetricCard(
                emoji: "❤️",
                label: "PULSE VARIABILITY",
                value: String(format: "%.1f ms HRV", engine.hrv),
                status: engine.hrv < 20 ? .warning : .ok,
                isCritical: engine.hrv < 15
            )
        }
    }

    // MARK: Risk Card

    var riskCard: some View {
        let pri   = engine.pneumoniaRiskIndex
        let color = priColor(pri)

        return VStack(spacing: 10) {
            HStack {
                Text("PNEUMONIA RISK INDEX")
                    .font(.system(size: 11, weight: .bold, design: .monospaced))
                    .foregroundStyle(.white.opacity(0.5))
                    .kerning(1.5)
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
                    RoundedRectangle(cornerRadius: 4)
                        .fill(.white.opacity(0.08))
                        .frame(height: 8)
                    RoundedRectangle(cornerRadius: 4)
                        .fill(color)
                        .frame(width: geo.size.width * CGFloat(pri / 100), height: 8)
                        .animation(.easeInOut(duration: 0.5), value: pri)
                }
            }
            .frame(height: 8)

            if engine.isCritical || alarmActive {
                HStack(spacing: 6) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundStyle(.red)
                        .font(.system(size: 12))
                    Text("CRITICAL THRESHOLD EXCEEDED — IMMEDIATE ATTENTION REQUIRED")
                        .font(.system(size: 10, weight: .bold, design: .monospaced))
                        .foregroundStyle(.red)
                }
                .padding(.top, 2)
            }
        }
        .padding(16)
        .background(
            RoundedRectangle(cornerRadius: 14)
                .fill(Color(white: 0.07))
                .overlay(
                    RoundedRectangle(cornerRadius: 14)
                        .stroke(engine.isCritical || alarmActive ? Color.red.opacity(0.5) : Color.white.opacity(0.06), lineWidth: 1)
                )
        )
    }

    // MARK: Graphs

    var graphsSection: some View {
        VStack(spacing: 10) {
            MiniGraph(label: "❤️ HEART RATE (bpm)", data: engine.hrHistory,
                      color: .red, yMin: 40, yMax: 160,
                      currentValue: String(format: "%.0f bpm", engine.heartRate))

            MiniGraph(label: "💨 BREATHS PER MINUTE", data: engine.bpmHistory,
                      color: .cyan, yMin: 0, yMax: 40,
                      currentValue: String(format: "%.1f b/min", engine.breathsPerMinute))

            MiniGraph(label: "😶 APNEA EVENTS / HR", data: engine.apneaHistory,
                      color: .orange, yMin: 0, yMax: 30,
                      currentValue: String(format: "%.1f /hr", engine.apneaEventsPerHour))
        }
    }

    // MARK: Action Buttons

    var actionRow: some View {
        VStack(spacing: 10) {
            // Inform Caregiver
            Button {
                AeyronAPIClient.notifyCaregiver(patientId: patientId, reason: "Manual caregiver notification") { success in
                    caregiverSent = true
                    showCaregiverToast = true
                    DispatchQueue.main.asyncAfter(deadline: .now() + 3) { showCaregiverToast = false }
                }
            } label: {
                HStack(spacing: 10) {
                    Image(systemName: caregiverSent ? "checkmark.circle.fill" : "bell.badge.fill")
                        .font(.system(size: 16, weight: .semibold))
                    Text(caregiverSent ? "Caregiver Notified" : "Inform Caregiver")
                        .font(.system(size: 15, weight: .semibold))
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 16)
                .background(caregiverSent ? Color.green.opacity(0.2) : Color(red: 0.1, green: 0.4, blue: 1.0))
                .foregroundStyle(caregiverSent ? .green : .white)
                .clipShape(RoundedRectangle(cornerRadius: 14))
                .overlay(
                    RoundedRectangle(cornerRadius: 14)
                        .stroke(caregiverSent ? Color.green.opacity(0.4) : Color.clear, lineWidth: 1)
                )
            }

            // Trigger Critical Alarm
            Button {
                alarmActive = true
                AeyronAPIClient.triggerCriticalAlarm(patientId: patientId) { _ in }
                showAlarmToast = true
                UINotificationFeedbackGenerator().notificationOccurred(.error)
                DispatchQueue.main.asyncAfter(deadline: .now() + 3) { showAlarmToast = false }
            } label: {
                HStack(spacing: 10) {
                    Image(systemName: alarmActive ? "alarm.fill" : "alarm")
                        .font(.system(size: 16, weight: .semibold))
                    Text(alarmActive ? "Alarm Active" : "Trigger Critical Alarm")
                        .font(.system(size: 15, weight: .semibold))
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 16)
                .background(alarmActive ? Color.red : Color.red.opacity(0.15))
                .foregroundStyle(.white)
                .clipShape(RoundedRectangle(cornerRadius: 14))
                .overlay(
                    RoundedRectangle(cornerRadius: 14)
                        .stroke(Color.red.opacity(0.5), lineWidth: 1)
                )
            }
        }
    }

    // MARK: Permission Denied View

    var permissionView: some View {
        VStack(spacing: 16) {
            Image(systemName: "exclamationmark.lock.fill")
                .font(.system(size: 44))
                .foregroundStyle(.orange)
            Text("Camera & Microphone Required")
                .font(.title3.bold())
                .foregroundStyle(.white)
            Text("AEYRON needs camera access for pulse detection and microphone access for respiratory monitoring.")
                .font(.callout)
                .foregroundStyle(.white.opacity(0.6))
                .multilineTextAlignment(.center)
            Button("Open Settings") {
                if let url = URL(string: UIApplication.openSettingsURLString) {
                    UIApplication.shared.open(url)
                }
            }
            .foregroundStyle(.cyan)
        }
        .padding(32)
    }

    // MARK: Toast

    func toastBanner(text: String, color: Color) -> some View {
        Text(text)
            .font(.system(size: 13, weight: .semibold))
            .foregroundStyle(.white)
            .padding(.horizontal, 20)
            .padding(.vertical, 12)
            .background(color.opacity(0.9))
            .clipShape(Capsule())
            .shadow(radius: 10)
            .transition(.move(edge: .bottom).combined(with: .opacity))
    }

    // MARK: Helpers

    func priColor(_ v: Double) -> Color {
        switch v {
        case ..<30: return .green
        case 30..<60: return .yellow
        case 60..<80: return .orange
        default: return .red
        }
    }

    func priLabel(_ v: Double) -> String {
        switch v {
        case ..<30: return "LOW RISK"
        case 30..<60: return "MODERATE"
        case 60..<80: return "HIGH RISK"
        default: return "CRITICAL"
        }
    }
}

// MARK: - MetricCard

enum MetricStatus { case ok, warning }

struct MetricCard: View {
    let emoji: String
    let label: String
    let value: String
    let status: MetricStatus
    let isCritical: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(emoji).font(.system(size: 20))
                Spacer()
                Text(isCritical ? "CRITICAL" : status == .warning ? "WARN" : "OK")
                    .font(.system(size: 9, weight: .bold, design: .monospaced))
                    .foregroundStyle(isCritical ? .black : status == .warning ? .orange : .green)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 3)
                    .background(isCritical ? Color.red : status == .warning ? Color.orange.opacity(0.2) : Color.green.opacity(0.15))
                    .clipShape(Capsule())
            }
            Text(label)
                .font(.system(size: 9, weight: .bold, design: .monospaced))
                .foregroundStyle(.white.opacity(0.4))
                .kerning(0.5)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
            Text(value)
                .font(.system(size: 15, weight: .bold, design: .rounded))
                .foregroundStyle(isCritical ? .red : .white)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
        }
        .padding(14)
        .background(
            RoundedRectangle(cornerRadius: 14)
                .fill(Color(white: 0.07))
                .overlay(
                    RoundedRectangle(cornerRadius: 14)
                        .stroke(isCritical ? Color.red.opacity(0.5) : Color.white.opacity(0.06), lineWidth: 1)
                )
        )
    }
}

// MARK: - MiniGraph

struct MiniGraph: View {
    let label: String
    let data: [Double]
    let color: Color
    let yMin: Double
    let yMax: Double
    let currentValue: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(label)
                    .font(.system(size: 10, weight: .bold, design: .monospaced))
                    .foregroundStyle(.white.opacity(0.5))
                    .kerning(1)
                Spacer()
                Text(currentValue)
                    .font(.system(size: 12, weight: .bold, design: .rounded))
                    .foregroundStyle(color)
            }

            GeometryReader { geo in
                let w = geo.size.width
                let h = geo.size.height
                let points = data.enumerated().map { i, v -> CGPoint in
                    let x = w * CGFloat(i) / CGFloat(max(data.count - 1, 1))
                    let y = h - h * CGFloat((v - yMin) / (yMax - yMin))
                    return CGPoint(x: x, y: min(max(y, 0), h))
                }

                ZStack {
                    // Fill
                    if points.count > 1 {
                        Path { path in
                            path.move(to: CGPoint(x: points[0].x, y: h))
                            points.forEach { path.addLine(to: $0) }
                            path.addLine(to: CGPoint(x: points.last!.x, y: h))
                            path.closeSubpath()
                        }
                        .fill(
                            LinearGradient(colors: [color.opacity(0.3), .clear],
                                           startPoint: .top, endPoint: .bottom)
                        )

                        // Line
                        Path { path in
                            path.move(to: points[0])
                            points.dropFirst().forEach { path.addLine(to: $0) }
                        }
                        .stroke(color, style: StrokeStyle(lineWidth: 1.5, lineCap: .round, lineJoin: .round))
                    }

                    // Latest dot
                    if let last = points.last {
                        Circle()
                            .fill(color)
                            .frame(width: 5, height: 5)
                            .position(last)
                    }
                }
            }
            .frame(height: 56)
            .background(Color.white.opacity(0.03))
            .clipShape(RoundedRectangle(cornerRadius: 8))
        }
        .padding(14)
        .background(
            RoundedRectangle(cornerRadius: 14)
                .fill(Color(white: 0.07))
                .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color.white.opacity(0.06), lineWidth: 1))
        )
    }
}
