# How SmartSpectra Works — Very Simple Explanation

This explains the SmartSpectra system **one step at a time**, in plain words.
You can read it word by word.

---

## Part 1: What This System Does

- The system **measures your heart** (pulse) and **breathing** using a **camera**.
- It does **not** touch your body. It only **looks** at your face (or body) with the camera.
- At the end, you get **numbers** (like "heart rate: 72") and **wavy lines** (the pulse and breathing signals).

---

## Part 2: The Big Picture (5 Steps)

1. **Camera takes pictures.**  
   One picture is called one **frame**.  
   Frames are taken over and over, like a video.

2. **Each frame is prepared on your device.**  
   The app finds the **face** (or body) in the picture and gets a **small summary** of the image.  
   That summary is called **preprocessed data**.  
   It is **not** the full video. It is a compact version so it can be sent quickly.

3. **That preprocessed data is sent to Presage’s computers on the internet.**  
   Your app uses the **internet** and an **API key** (like a password) to send this data.  
   This is called the **REST API**.

4. **Presage’s computers work out your pulse and breathing.**  
   They use the preprocessed data to compute:
   - **Pulse rate** (heart beats per minute),
   - **Pulse trace** (the wavy heartbeat line),
   - **Breathing rate** and **breathing trace**.

5. **Those results are sent back to your app.**  
   The results are packed in something called **MetricsBuffer**.  
   Inside it you have **pulse** (with rate and trace) and **breathing** (with rate and trace).  
   Your app can **show** them on the screen or **use** them in code.

So in one sentence:  
**Camera → frames → preprocessing on device → send summary to internet → Presage’s servers compute pulse and breathing → send results back → your app gets numbers and waves.**

---

## Part 3: Word-by-Word Flow

- **Camera**  
  The thing that takes pictures. It can be the camera on your phone, or on your computer.

- **Frame**  
  One single picture. Like one photo from a video.  
  The app handles many frames, one after another.

- **Video source**  
  The place the frames come from.  
  Either the **camera** (live) or a **video file** (from disk).

- **Graph**  
  A pipeline inside the app.  
  Frames go **in** at one end.  
  At the other end come:  
  - a **processed video frame** (to show on screen), and  
  - **preprocessed data** (to send to the internet).

- **Preprocessed data**  
  A **short summary** of the video, made on your device.  
  It is small so it can be sent over the internet without sending the full video.

- **Buffer**  
  A place where data is **collected for a short time**.  
  For example, the app might collect 0.5 seconds of preprocessed data, then send that chunk.

- **REST API**  
  A way for your app to **talk to Presage’s servers** over the internet.  
  Your app **sends** preprocessed data.  
  The server **sends back** pulse and breathing results.

- **API key**  
  A **secret string** (like a password) that you get from Presage.  
  You put it in the app.  
  The app uses it so the server knows it is allowed to use the service.

- **Physiology (Core) server**  
  Presage’s computers that **compute** pulse and breathing from the preprocessed data.  
  They send back **Core metrics**.

- **Core metrics / MetricsBuffer**  
  The **answer** from the server.  
  It is one big bundle that contains:
  - **Pulse**: rate (heart beats per minute), trace (wavy line), sometimes “strict” value.
  - **Breathing**: rate, traces, and other breathing numbers.
  - **Face**: e.g. blinking, talking, if needed.
  - **Metadata**: when the measurement was made, etc.

- **Pulse rate**  
  How many heart beats per minute.  
  Example: 72 means 72 beats in one minute.

- **Pulse trace**  
  A **list of points** (time, value) that draw the heartbeat wave (pleth).  
  The app can draw this as a wavy line on the screen.

- **Edge metrics**  
  Some numbers are computed **on your device** (on the “edge”), not on the server.  
  For example, a **breathing trace** can be computed frame-by-frame on the device.  
  Edge metrics come **more often** (every frame); Core metrics come **when the server answers** (a bit later).

- **Callback**  
  A **function** your code gives to the SDK.  
  When new data is ready (e.g. new pulse and breathing), the SDK **calls** your function and passes the data.  
  So: “When you have new pulse, **call this function** and give it the pulse.”

- **OnCoreMetricsOutput**  
  The **name** of the callback that receives **Core metrics** (pulse, breathing, etc.) from the server.  
  You register it once. Then every time the server sends new metrics, your function runs and you can read **metrics.pulse** and **metrics.breathing**.

---

## Part 4: What Happens in Code (Simple Order)

1. You **create settings**.  
   You say: use camera 0, use REST, use continuous mode, here is my API key.

2. You **build a container**.  
   The container is the thing that runs the **graph**, talks to the **video source**, and talks to the **server**.

3. You **give the container a callback** (OnCoreMetricsOutput).  
   You say: “When you get new pulse and breathing from the server, call this function with the MetricsBuffer.”

4. You **start** the container (Initialize, then Run).

5. **Loop:**  
   - The container gets a **frame** from the camera (or file).  
   - It puts the frame **into the graph**.  
   - The graph **preprocesses** it and may send a **buffer** to the server.  
   - When the server **replies**, the container gets a **MetricsBuffer**.  
   - The container **calls your callback** with that MetricsBuffer.  
   - Inside the callback you read **metrics.pulse.rate** and **metrics.pulse.trace** (and breathing if you want).  
   - The container also **shows the video** (if you set that up) so you see yourself on screen.

6. This **repeats** for every frame until you stop (e.g. press Quit).

So: **Start → get frame → put in graph → preprocess → send to server → get back MetricsBuffer → your callback runs with pulse and breathing → repeat.**

---

## Part 5: Where “Heart” Fits

- **Heart** in this system = **pulse**.
- **Pulse** lives inside **MetricsBuffer.pulse**.
- **MetricsBuffer** is what your **OnCoreMetricsOutput** callback receives.
- So: when your callback runs, you look at **metrics.pulse**:
  - **metrics.pulse.rate** → list of heart rate values (with time and confidence).
  - **metrics.pulse.trace** → list of points for the heartbeat wave.
- The **camera** and **face** are only used to **get** that pulse; the actual heart number and wave are **computed** by Presage’s server from the preprocessed video summary.

---

## Summary in One Paragraph

The **camera** takes **pictures** (frames). The app **preprocesses** them on your device into a **small summary** and sends that to **Presage’s servers** over the **internet** (using an **API key**). The servers **compute** your **pulse** (heart rate and wave) and **breathing**, then send the result back in a **MetricsBuffer**. Your app receives it in a **callback** (OnCoreMetricsOutput) and can then read **pulse.rate** and **pulse.trace** and show or use them. So: **camera → preprocessing → internet → server computes heart and breathing → result back → your code gets pulse and breathing.**
