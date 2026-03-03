const ABS_MIN_SPEECH_START_DB = -85;
const ABS_MIN_SPEECH_CONTINUE_DB = -88;
const SPEECH_MARGIN_START_DB = 2.0;
const SPEECH_MARGIN_CONTINUE_DB = 1.0;
const SPEECH_OVERRIDE_DB = -65;
const SPEECH_RISE_DB = 1.5;
const SPEECH_ACCEPT_MS = 120;
const NOISE_FLOOR_ALPHA = 0.03;
const NOISE_FLOOR_WAITING_ALPHA = 0.08;
const NOISE_FLOOR_MAX_RISE_DB = 2.5;
const SILENCE_SOFT_MS = 1200;
const SILENCE_HARD_MS = 2600;
const SILENCE_CONFIRM_MS = 700;
const MIN_RECORDING_MS = 800;
const AUTO_SEND_MIN_RECORDING_MS = 2000;
const STARTUP_GRACE_MS = 500;
const MIN_SPEECH_SPAN_MS = 1200;
const MAX_WAIT_FOR_SPEECH_MS = 15000;
const FORCE_SEND_MS = 35000;
const MAX_RECORDING_MS = 60000;
const BARGE_IN_THRESHOLD_DB = -32;
const BARGE_IN_RISE_DB = 9;
const BARGE_IN_HOLD_MS = 280;
const BARGE_IN_IGNORE_MS = 900;
const BARGE_IN_NOISE_MAX_RISE_DB = 2.5;
const PREFERRED_VOICE_NAME = "Google US English";
const PREFERRED_VOICE_LANG = "en-us";
const RECORDER_MIME_CANDIDATES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/mp4",
  "audio/ogg;codecs=opus",
];

const STRIKE_PHRASES = [
  "i think we got a bit sidetracked",
  "i think i may have lost the thread",
  "i want to make sure we use the time",
  "let me bring us back",
  "i think we've covered what we needed",
  "i appreciate you coming in",
];

const CLOSING_PROMPT =
  "Thank you. That's all my questions for today. Do you have anything you'd like to ask me about the role or the company?";

const OPENING_TEMPLATE =
  "Good afternoon, {name}. Thank you for making time today. I'm Alex Chen — I manage HR here at NovaTech. We have about 12 minutes together, so let's get started.";

const state = {
  phase: "setup",
  studentName: "",
  roleName: "",
  questions: [],
  pinRequired: false,
  pinUnlocked: false,
  pinToken: "",
  serverTtsAvailable: false,
  speechSynthesisBlocked: false,
  questionIndex: 0,
  history: [],
  probeUsedCurrentQuestion: false,
  awaitingProbe: false,
  inClosing: false,
  strikeCount: 0,
  startedAt: 0,
  endedAt: 0,
  pendingStudentText: "",
  mediaSupported: false,
  recording: false,
  processing: false,
  reportPlainText: "",
};

const ui = {
  statusLine: document.getElementById("status-line"),
  setupScreen: document.getElementById("setup-screen"),
  interviewScreen: document.getElementById("interview-screen"),
  reportScreen: document.getElementById("report-screen"),
  setupForm: document.getElementById("setup-form"),
  beginBtn: document.getElementById("begin-btn"),
  studentName: document.getElementById("student-name"),
  roleName: document.getElementById("role-name"),
  pinBlock: document.getElementById("pin-block"),
  pinCode: document.getElementById("pin-code"),
  pinStatus: document.getElementById("pin-status"),
  micTest: document.getElementById("mic-test"),
  micTestUnavailable: document.getElementById("mic-test-unavailable"),
  micTestBtn: document.getElementById("mic-test-btn"),
  micStopBtn: document.getElementById("mic-stop-btn"),
  micRecordBtn: document.getElementById("mic-record-btn"),
  micMeterFill: document.getElementById("mic-meter-fill"),
  micTestStatus: document.getElementById("mic-test-status"),
  micPlayback: document.getElementById("mic-playback"),
  audioTestBtn: document.getElementById("audio-test-btn"),
  audioOpenBtn: document.getElementById("audio-open-btn"),
  audioTestStatus: document.getElementById("audio-test-status"),
  audioTestHint: document.getElementById("audio-test-hint"),
  turnIndicator: document.getElementById("turn-indicator"),
  statusLight: document.getElementById("status-light"),
  countdownChip: document.getElementById("countdown-chip"),
  timer: document.getElementById("timer"),
  qCounter: document.getElementById("q-counter"),
  progressFill: document.getElementById("progress-fill"),
  progressDots: document.getElementById("progress-dots"),
  lastAlexLine: document.getElementById("last-alex-line"),
  replayBtn: document.getElementById("replay-btn"),
  portraitGlow: document.getElementById("portrait-glow"),
  soundWave: document.getElementById("sound-wave"),
  pulseRing1: document.getElementById("pulse-ring-1"),
  pulseRing2: document.getElementById("pulse-ring-2"),
  recordingControls: document.getElementById("recording-controls"),
  recordingState: document.getElementById("recording-state"),
  debugPanel: document.getElementById("debug-panel"),
  endInterviewBtn: document.getElementById("end-interview-btn"),
  scoreGrid: document.getElementById("score-grid"),
  reportStudentName: document.getElementById("report-student-name"),
  reportMeta: document.getElementById("report-meta"),
  reportText: document.getElementById("report-text"),
  copyReportBtn: document.getElementById("copy-report-btn"),
  printReportBtn: document.getElementById("print-report-btn"),
  newInterviewBtn: document.getElementById("new-interview-btn"),
};

const debugEnabled = new URLSearchParams(window.location.search).has("debug");

let timerInterval = null;
let activeVoice = null;
let mediaStream = null;
let mediaRecorder = null;
let audioContext = null;
let analyser = null;
let silenceMonitorRaf = null;
let interactionGuardInterval = null;
let recordingStartedAt = 0;
let silenceStartedAt = null;
let hasVoiceActivity = false;
let firstVoiceAt = null;
let smoothedDb = -100;
let pauseHintShown = false;
let finalizeCandidateAt = null;
let vadPhase = "waiting_for_speech"; // waiting_for_speech | speaking | trailing_silence | finalize_pending
let preferredVoiceMissingWarned = false;
let voicePrimeTried = false;
let noiseFloorDb = -65;
let recorderSessionId = 0;
let autoListenRetryTimer = null;
let prevSpeechNow = false;
let resumeCooldownUntil = 0;
let lastFrameAt = 0;
let speechStreakMs = 0;
let lastAlexUtterance = "";
let audioUnlocked = false;
let micTestActive = false;
let micTestRaf = null;
let micTestRecorder = null;
let micTestChunks = [];
let micTestPlaybackUrl = "";
let micTestStartedAt = 0;
let micTestLastSpeechAt = 0;
let serverTtsAudio = null;
let serverTtsUrl = "";
let bargeInRaf = null;
let bargeStartAt = 0;
let bargeFrameAt = 0;
let bargeSpeechMs = 0;
let bargeNoiseFloorDb = -65;
let bargeSmoothedDb = -100;
let chunks = [];
let speaking = false;
let responsePending = false;
let speechToken = 0;
let pendingStopAction = "auto"; // auto | send | restart
let lastTranscribeMs = null;
let lastChatMs = null;
let lastTtsMs = null;
let autoListenStartedAt = 0;
let mediaInitPromise = null;

function setVisualState(mode) {
  const isSpeaking = mode === "speaking";
  [ui.portraitGlow, ui.soundWave, ui.pulseRing1, ui.pulseRing2].forEach((el) => {
    if (!el) {
      return;
    }
    el.classList.toggle("active", isSpeaking);
  });

  if (ui.turnIndicator) {
    ui.turnIndicator.className = `state-label ${mode}`;
  }
  if (ui.statusLight) {
    ui.statusLight.className = `status-light ${mode}`;
  }
}

function showCountdown(seconds, urgent = false) {
  if (!ui.countdownChip) {
    return;
  }
  const safeSeconds = Math.max(0, Math.ceil(seconds));
  ui.countdownChip.textContent = `${safeSeconds}s left`;
  ui.countdownChip.classList.toggle("warn", urgent);
  ui.countdownChip.classList.remove("hidden");
}

function clearCountdown() {
  if (!ui.countdownChip) {
    return;
  }
  ui.countdownChip.textContent = "";
  ui.countdownChip.classList.remove("warn");
  ui.countdownChip.classList.add("hidden");
}

function updateDebugPanel(data) {
  if (!debugEnabled || !ui.debugPanel) {
    return;
  }
  ui.debugPanel.classList.remove("hidden");
  ui.debugPanel.textContent = data;
}

function unlockAudioOutput(force = false) {
  if (!window.speechSynthesis) {
    return;
  }
  if (audioUnlocked && !force) {
    return;
  }
  try {
    const unlocker = new SpeechSynthesisUtterance(" ");
    unlocker.volume = 0.01;
    unlocker.rate = 1.0;
    window.speechSynthesis.speak(unlocker);
    if (force) {
      audioUnlocked = true;
    }
  } catch (_error) {
    // Best-effort only.
  }
}

function setAudioFallback(text, visible) {
  if (!ui.lastAlexLine) {
    return;
  }
  ui.lastAlexLine.textContent = visible ? text : "";
  ui.lastAlexLine.classList.toggle("audio-fallback", visible);
  if (ui.replayBtn) {
    ui.replayBtn.classList.toggle("hidden", !visible);
    ui.replayBtn.disabled = !visible;
  }
}

function stopBargeInMonitor() {
  if (bargeInRaf) {
    cancelAnimationFrame(bargeInRaf);
    bargeInRaf = null;
  }
}

function startBargeInMonitor() {
  stopBargeInMonitor();
  if (!analyser || !audioContext) {
    return;
  }
  bargeStartAt = performance.now();
  bargeFrameAt = 0;
  bargeSpeechMs = 0;
  bargeNoiseFloorDb = -65;
  bargeSmoothedDb = -100;

  const frame = new Float32Array(analyser.fftSize);
  const tick = () => {
    if (!speaking || !state.mediaSupported) {
      stopBargeInMonitor();
      return;
    }

    analyser.getFloatTimeDomainData(frame);
    let squareSum = 0;
    for (let index = 0; index < frame.length; index += 1) {
      squareSum += frame[index] * frame[index];
    }

    const rms = Math.sqrt(squareSum / frame.length);
    const dbRaw = rms > 0 ? 20 * Math.log10(rms) : -100;
    bargeSmoothedDb = bargeSmoothedDb <= -99 ? dbRaw : bargeSmoothedDb * 0.82 + dbRaw * 0.18;
    const db = bargeSmoothedDb;
    const now = performance.now();
    const frameDelta = bargeFrameAt ? Math.min(200, now - bargeFrameAt) : 0;
    bargeFrameAt = now;

    if (now - bargeStartAt < BARGE_IN_IGNORE_MS) {
      bargeInRaf = requestAnimationFrame(tick);
      return;
    }

    if (db <= bargeNoiseFloorDb + BARGE_IN_NOISE_MAX_RISE_DB) {
      bargeNoiseFloorDb = bargeNoiseFloorDb * 0.9 + db * 0.1;
    }
    const rise = db - bargeNoiseFloorDb;
    const speechNow =
      (db > BARGE_IN_THRESHOLD_DB && rise > 2) || rise >= BARGE_IN_RISE_DB;

    if (speechNow) {
      bargeSpeechMs = Math.min(2000, bargeSpeechMs + frameDelta);
    } else {
      bargeSpeechMs = 0;
    }

    if (bargeSpeechMs >= BARGE_IN_HOLD_MS) {
      if (window.speechSynthesis?.speaking) {
        window.speechSynthesis.cancel();
      }
      stopServerTtsPlayback();
      speaking = false;
      setVisualState("listening");
      stopBargeInMonitor();
      void scheduleAutoListen(0);
      return;
    }

    bargeInRaf = requestAnimationFrame(tick);
  };

  bargeInRaf = requestAnimationFrame(tick);
}

function pickRecorderMimeType() {
  if (!window.MediaRecorder || typeof MediaRecorder.isTypeSupported !== "function") {
    return null;
  }
  for (const candidate of RECORDER_MIME_CANDIDATES) {
    if (MediaRecorder.isTypeSupported(candidate)) {
      return candidate;
    }
  }
  return null;
}

function setStatus(text) {
  ui.statusLine.textContent = text;
}

function authHeaders(extra = {}) {
  const headers = { ...extra };
  if (state.pinRequired && state.pinToken) {
    headers["X-Access-Pin"] = state.pinToken;
  }
  return headers;
}

function stopServerTtsPlayback() {
  if (serverTtsAudio) {
    serverTtsAudio.pause();
    serverTtsAudio.currentTime = 0;
  }
  if (serverTtsUrl) {
    URL.revokeObjectURL(serverTtsUrl);
    serverTtsUrl = "";
  }
}

function showMicTest(available) {
  if (ui.micTest) {
    ui.micTest.classList.toggle("hidden", !available);
  }
  if (ui.micTestUnavailable) {
    ui.micTestUnavailable.classList.toggle("hidden", available);
  }
}

function setMicTestStatus(message, ok = false) {
  if (!ui.micTestStatus) {
    return;
  }
  ui.micTestStatus.textContent = message;
  ui.micTestStatus.style.color = ok ? "#2f7d32" : "#7a5520";
}

function setAudioTestStatus(message, ok = false) {
  if (!ui.audioTestStatus) {
    return;
  }
  ui.audioTestStatus.textContent = message;
  ui.audioTestStatus.style.color = ok ? "#2f7d32" : "#7a5520";
}

function isInIframe() {
  try {
    return window.self !== window.top;
  } catch (_error) {
    return true;
  }
}

async function playBeep() {
  if (!window.AudioContext && !window.webkitAudioContext) {
    return false;
  }
  const Ctor = window.AudioContext || window.webkitAudioContext;
  const ctx = new Ctor();
  try {
    if (ctx.state === "suspended") {
      await ctx.resume();
    }
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = 440;
    gain.gain.value = 0.12;
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    await new Promise((resolve) => window.setTimeout(resolve, 600));
    osc.stop();
    return true;
  } catch (_error) {
    return false;
  } finally {
    ctx.close().catch(() => {});
  }
}

function updateMicMeter(db) {
  if (!ui.micMeterFill) {
    return;
  }
  const level = Math.max(0, Math.min(1, (db + 90) / 70));
  ui.micMeterFill.style.width = `${Math.round(level * 100)}%`;
}

function stopMicTest() {
  micTestActive = false;
  if (micTestRaf) {
    cancelAnimationFrame(micTestRaf);
    micTestRaf = null;
  }
  if (ui.micTestBtn) {
    ui.micTestBtn.disabled = false;
  }
  if (ui.micStopBtn) {
    ui.micStopBtn.disabled = true;
  }
  if (ui.micRecordBtn) {
    ui.micRecordBtn.disabled = false;
  }
  setMicTestStatus("Microphone is idle.");
  updateMicMeter(-100);
}

async function startMicTest() {
  if (!state.mediaSupported) {
    setMicTestStatus("Voice mode is not available on this device.");
    return;
  }
  if (micTestActive) {
    return;
  }
  try {
    await setupMediaStream();
  } catch (_error) {
    setMicTestStatus("Microphone permission denied. Voice mode will be disabled.");
    state.mediaSupported = false;
    showMicTest(false);
    return;
  }
  if (!analyser) {
    setMicTestStatus("Microphone is not ready.");
    return;
  }
  micTestActive = true;
  micTestStartedAt = performance.now();
  micTestLastSpeechAt = 0;
  if (ui.micTestBtn) {
    ui.micTestBtn.disabled = true;
  }
  if (ui.micStopBtn) {
    ui.micStopBtn.disabled = false;
  }
  if (ui.micRecordBtn) {
    ui.micRecordBtn.disabled = false;
  }
  setMicTestStatus("Listening... speak now.");

  const frame = new Float32Array(analyser.fftSize);
  const tick = () => {
    if (!micTestActive || !analyser) {
      return;
    }
    analyser.getFloatTimeDomainData(frame);
    let squareSum = 0;
    for (let index = 0; index < frame.length; index += 1) {
      squareSum += frame[index] * frame[index];
    }
    const rms = Math.sqrt(squareSum / frame.length);
    const db = rms > 0 ? 20 * Math.log10(rms) : -100;
    updateMicMeter(db);

    const now = performance.now();
    const speaking = db > -55;
    if (speaking) {
      micTestLastSpeechAt = now;
      setMicTestStatus("Voice detected.", true);
    } else if (now - micTestStartedAt > 1200 && now - micTestLastSpeechAt > 1200) {
      setMicTestStatus("No speech detected. Speak closer or louder.");
    }

    micTestRaf = requestAnimationFrame(tick);
  };
  micTestRaf = requestAnimationFrame(tick);
}

function clearMicPlayback() {
  if (micTestPlaybackUrl) {
    URL.revokeObjectURL(micTestPlaybackUrl);
    micTestPlaybackUrl = "";
  }
  if (ui.micPlayback) {
    ui.micPlayback.classList.add("hidden");
    ui.micPlayback.src = "";
  }
}

async function recordMicSample() {
  if (!state.mediaSupported) {
    setMicTestStatus("Voice mode is not available on this device.");
    return;
  }
  if (!mediaStream) {
    await setupMediaStream().catch(() => {});
  }
  if (!mediaStream) {
    setMicTestStatus("Microphone is not ready.");
    return;
  }
  if (micTestRecorder && micTestRecorder.state === "recording") {
    return;
  }
  clearMicPlayback();
  micTestChunks = [];
  const mimeType = pickRecorderMimeType();
  const recorderOptions = mimeType ? { mimeType } : undefined;
  try {
    micTestRecorder = recorderOptions
      ? new MediaRecorder(mediaStream, recorderOptions)
      : new MediaRecorder(mediaStream);
  } catch (_error) {
    setMicTestStatus("Sample recording is not supported in this browser.");
    return;
  }
  micTestRecorder.ondataavailable = (event) => {
    if (event.data.size > 0) {
      micTestChunks.push(event.data);
    }
  };
  micTestRecorder.onstop = () => {
    const blobType = micTestRecorder?.mimeType || "audio/webm";
    const blob = new Blob(micTestChunks, { type: blobType });
    micTestPlaybackUrl = URL.createObjectURL(blob);
    if (ui.micPlayback) {
      ui.micPlayback.src = micTestPlaybackUrl;
      ui.micPlayback.classList.remove("hidden");
    }
    setMicTestStatus("Sample ready. Press play to review.");
    if (ui.micRecordBtn) {
      ui.micRecordBtn.disabled = false;
    }
  };
  micTestRecorder.start();
  setMicTestStatus("Recording sample...");
  if (ui.micRecordBtn) {
    ui.micRecordBtn.disabled = true;
  }
  window.setTimeout(() => {
    if (micTestRecorder && micTestRecorder.state === "recording") {
      micTestRecorder.stop();
    }
  }, 3000);
}

async function playServerTts(text, onStart = null) {
  if (!state.serverTtsAvailable) {
    return false;
  }
  try {
    const startedAt = performance.now();
    const response = await fetch("/tts", {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ text }),
    });
    if (!response.ok) {
      if (response.status === 401) {
        handlePinRequired();
        return false;
      }
      return false;
    }
    const blob = await response.blob();
    lastTtsMs = Math.round(performance.now() - startedAt);
    stopServerTtsPlayback();
    serverTtsUrl = URL.createObjectURL(blob);
    if (!serverTtsAudio) {
      serverTtsAudio = new Audio();
    }
    serverTtsAudio.src = serverTtsUrl;
    serverTtsAudio.preload = "auto";
    return await new Promise((resolve) => {
      const cleanup = (ok) => {
        stopServerTtsPlayback();
        resolve(ok);
      };
      let started = false;
      serverTtsAudio.onplay = () => {
        if (!started) {
          started = true;
          if (onStart) {
            onStart();
          }
        }
      };
      serverTtsAudio.onended = () => cleanup(true);
      serverTtsAudio.onerror = () => cleanup(false);
      const playPromise = serverTtsAudio.play();
      if (playPromise && typeof playPromise.catch === "function") {
        playPromise.catch(() => cleanup(false));
      }
    });
  } catch (_error) {
    return false;
  }
}

async function runAudioTest() {
  if (!window.speechSynthesis) {
    setAudioTestStatus("Audio output is not supported in this browser.");
    return;
  }
  if (ui.audioTestBtn) {
    ui.audioTestBtn.disabled = true;
  }
  unlockAudioOutput(true);
  if (window.speechSynthesis.paused) {
    window.speechSynthesis.resume();
  }
  const sample = "Audio check. If you hear this, Alex will be audible.";

  // Prefer server voice first when available to avoid slow browser-voice fallbacks.
  if (state.serverTtsAvailable) {
    setAudioTestStatus("Playing server voice test...");
    const serverOk = await playServerTts(sample);
    if (serverOk) {
      setAudioTestStatus("Server voice check passed.", true);
      state.speechSynthesisBlocked = true;
      if (ui.audioTestBtn) {
        ui.audioTestBtn.disabled = false;
      }
      return;
    }
  }

  await ensurePreferredVoice(1200);
  setAudioTestStatus("Playing browser voice test...");
  const voices = window.speechSynthesis.getVoices?.() || [];
  if (!voices.length) {
    const beepOk = await playBeep();
    if (beepOk) {
      setAudioTestStatus("Beep played. Speech voice is blocked or unavailable.");
      state.speechSynthesisBlocked = true;
    } else {
      setAudioTestStatus("No voices available. Try Chrome or open in a new tab.");
    }
    if (ui.audioTestBtn) {
      ui.audioTestBtn.disabled = false;
    }
    return;
  }

  const result = await runSynthesisUtterance(sample, activeVoice, null, 1600);
  if (result.ok) {
    setAudioTestStatus("Audio check passed.", true);
    state.speechSynthesisBlocked = false;
  } else {
    const beepOk = await playBeep();
    if (beepOk) {
      setAudioTestStatus("Beep played. Speech voice is blocked or unavailable.");
      state.speechSynthesisBlocked = true;
    } else {
      setAudioTestStatus("No audio heard. Check system volume or browser permissions.");
    }
  }
  if (ui.audioTestBtn) {
    ui.audioTestBtn.disabled = false;
  }
}

function showPinBlock(show) {
  if (!ui.pinBlock) {
    return;
  }
  ui.pinBlock.classList.toggle("hidden", !show);
}

function setPinStatus(message, ok = false) {
  if (!ui.pinStatus) {
    return;
  }
  ui.pinStatus.textContent = message;
  ui.pinStatus.style.color = ok ? "#2f7d32" : "#7a5520";
}

function handlePinRequired(message = "Enter the class PIN to continue.") {
  state.pinRequired = true;
  state.pinUnlocked = false;
  showPinBlock(true);
  setPinStatus(message);
  updateBeginEnabled();
}

async function tryUnlockPin(pin) {
  if (!state.pinRequired) {
    return true;
  }
  if (!pin) {
    setPinStatus("Enter the PIN.");
    return false;
  }
  try {
    const response = await fetch("/auth", {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ pin }),
    });
    if (!response.ok) {
      throw new Error("Incorrect PIN.");
    }
    state.pinUnlocked = true;
    state.pinToken = pin;
    await fetchTtsStatus();
    setPinStatus("Unlocked.", true);
    showPinBlock(false);
    return true;
  } catch (error) {
    setPinStatus(error.message || "Incorrect PIN.");
    return false;
  }
}

function nowTimestamp() {
  return new Date().toLocaleTimeString("en-GB", { hour12: false });
}

function pushTurn(role, content) {
  state.history.push({ role, content, timestamp: nowTimestamp() });
}

function looksLikeSpeech(text) {
  const trimmed = String(text || "").trim();
  if (!trimmed) {
    return false;
  }
  const letters = (trimmed.match(/[A-Za-z]/g) || []).length;
  const digits = (trimmed.match(/[0-9]/g) || []).length;
  const words = trimmed.split(/\s+/).length;
  if (letters < 3) {
    return false;
  }
  if (digits > letters * 2) {
    return false;
  }
  return words >= 2 || letters >= 6;
}

function showScreen(target) {
  const screens = [ui.setupScreen, ui.interviewScreen, ui.reportScreen];
  screens.forEach((screen) => screen.classList.add("hidden"));
  target.classList.remove("hidden");
}

function updateTimer() {
  if (!state.startedAt) {
    ui.timer.textContent = "00:00";
    return;
  }
  const elapsedMs = (state.endedAt || Date.now()) - state.startedAt;
  const totalSec = Math.max(Math.floor(elapsedMs / 1000), 0);
  const minutes = String(Math.floor(totalSec / 60)).padStart(2, "0");
  const seconds = String(totalSec % 60).padStart(2, "0");
  ui.timer.textContent = `${minutes}:${seconds}`;
}

if (debugEnabled && ui.debugPanel) {
  ui.debugPanel.classList.remove("hidden");
}

function startTimer() {
  stopTimer();
  timerInterval = setInterval(updateTimer, 1000);
  updateTimer();
}

function stopTimer() {
  if (timerInterval) {
    clearInterval(timerInterval);
    timerInterval = null;
  }
}

function renderDots() {
  ui.progressDots.innerHTML = "";
  const total = state.questions.length || 7;
  for (let index = 0; index < state.questions.length; index += 1) {
    const dot = document.createElement("span");
    dot.className = "dot";
    if (index < state.questionIndex) {
      dot.classList.add("done");
    } else if (index === state.questionIndex && !state.inClosing) {
      dot.classList.add("active");
    }
    dot.setAttribute("aria-label", `Question ${index + 1}`);
    ui.progressDots.appendChild(dot);
  }

  if (ui.qCounter) {
    const displayIndex = state.inClosing ? total : Math.min(state.questionIndex + 1, total);
    ui.qCounter.textContent = `Q ${displayIndex} / ${total}`;
  }
  if (ui.progressFill) {
    const ratio = Math.min(state.questionIndex / total, 1);
    ui.progressFill.style.width = `${Math.round(ratio * 100)}%`;
  }
}

async function fetchQuestions() {
  const response =
    state.pinRequired && state.pinToken
      ? await fetch("/questions", { headers: authHeaders() })
      : await fetch("/questions");
  if (!response.ok) {
    if (response.status === 401) {
      handlePinRequired();
      throw new Error("PIN required");
    }
    throw new Error("Failed to load questions");
  }
  const payload = await response.json();
  if (!Array.isArray(payload.questions) || payload.questions.length !== 7) {
    throw new Error("Question payload must contain exactly 7 questions");
  }
  state.questions = payload.questions;
  renderDots();
}

async function fetchTtsStatus() {
  try {
    const response = await fetch("/tts/status", { headers: authHeaders() });
    if (!response.ok) {
      return;
    }
    const payload = await response.json();
    state.serverTtsAvailable = Boolean(payload?.enabled);
  } catch (_error) {
    // Non-fatal.
  }
}

async function fetchPinStatus() {
  try {
    const response = await fetch("/auth/status");
    if (!response.ok) {
      return;
    }
    const payload = await response.json();
    state.pinRequired = Boolean(payload?.required);
    if (state.pinRequired && !state.pinUnlocked) {
      showPinBlock(true);
      setPinStatus("Enter the class PIN to unlock this interview.");
    } else {
      showPinBlock(false);
    }
  } catch (_error) {
    // Non-fatal: allow access if status check fails.
  }
}

function detectInputMode() {
  const hasMediaApis = Boolean(window.MediaRecorder && navigator.mediaDevices?.getUserMedia);
  state.mediaSupported = hasMediaApis;

  if (state.mediaSupported) {
    ui.recordingControls.classList.remove("hidden");
    ui.recordingState.textContent = "Listening will start automatically when it's your turn.";
  } else {
    ui.recordingControls.classList.add("hidden");
  }
  showMicTest(state.mediaSupported);
}

function updateBeginEnabled() {
  const ready =
    ui.studentName.value.trim().length > 0 &&
    ui.roleName.value.trim().length > 0 &&
    (!state.pinRequired || state.pinUnlocked || (ui.pinCode && ui.pinCode.value.trim().length > 0));
  ui.beginBtn.disabled = !ready;
}

function loadVoices() {
  const voices = window.speechSynthesis?.getVoices?.() || [];
  if (!voices.length) {
    activeVoice = null;
    return;
  }

  const normLang = (value) => (value || "").toLowerCase().replaceAll("_", "-");

  const exactGoogleUs = voices.find(
    (voice) =>
      voice.name.trim() === PREFERRED_VOICE_NAME &&
      normLang(voice.lang) === PREFERRED_VOICE_LANG,
  );
  const googleUsByName = voices.find(
    (voice) => voice.name.toLowerCase().includes(PREFERRED_VOICE_NAME.toLowerCase()),
  );
  const googleByUsLang = voices.find(
    (voice) =>
      voice.name.toLowerCase().includes("google") && normLang(voice.lang).startsWith("en-us"),
  );
  const anyUs = voices.find((voice) => normLang(voice.lang).startsWith("en-us"));
  const anyEn = voices.find((voice) => normLang(voice.lang).startsWith("en"));
  activeVoice = exactGoogleUs || googleUsByName || googleByUsLang || anyUs || anyEn || null;
}

function primeVoiceEngine() {
  if (voicePrimeTried || !window.speechSynthesis) {
    return;
  }
  voicePrimeTried = true;
  try {
    const probe = new SpeechSynthesisUtterance(" ");
    probe.volume = 0;
    probe.rate = 1.0;
    window.speechSynthesis.speak(probe);
    window.speechSynthesis.cancel();
  } catch (_error) {
    // Best-effort only.
  }
}

async function ensurePreferredVoice(maxWaitMs = 4200) {
  if (!window.speechSynthesis) {
    return null;
  }
  primeVoiceEngine();
  const startedAt = performance.now();
  while (performance.now() - startedAt < maxWaitMs) {
    loadVoices();
    if (activeVoice) {
      return activeVoice;
    }
    await new Promise((resolve) => window.setTimeout(resolve, 120));
  }
  loadVoices();
  if (!activeVoice && state.phase === "setup" && !preferredVoiceMissingWarned) {
    preferredVoiceMissingWarned = true;
    setStatus(
      "Google US English voice is not available in this browser session. Chrome usually provides it.",
    );
  }
  return activeVoice;
}

function runSynthesisUtterance(clean, voiceToUse = null, onStart = null, startGuardMs = 3000) {
  return new Promise((resolve) => {
    const synth = window.speechSynthesis;
    const utterance = new SpeechSynthesisUtterance(clean);
    utterance.rate = 0.98;
    utterance.pitch = 1.0;
    utterance.volume = 1.0;
    utterance.lang = "en-US";
    if (voiceToUse) {
      utterance.voice = voiceToUse;
      utterance.lang = voiceToUse.lang || "en-US";
    }

    let finished = false;
    let playbackObserved = false;
    let started = false;
    const resolveOnce = (ok) => {
      if (finished) {
        return;
      }
      finished = true;
      window.clearInterval(observeId);
      window.clearTimeout(startGuardId);
      window.clearTimeout(timeoutId);
      resolve({ ok, started });
    };

    const observeId = window.setInterval(() => {
      if (synth.speaking || synth.pending) {
        playbackObserved = true;
      }
    }, 80);

    const startGuardId = window.setTimeout(() => {
      if (!playbackObserved) {
        synth.cancel();
        resolveOnce(false);
      }
    }, startGuardMs);

    const words = clean.split(/\s+/).filter(Boolean).length;
    const estimatedMs = words * 430 + 3000;
    const timeoutMs = Math.max(12000, Math.min(90000, estimatedMs));
    const timeoutId = window.setTimeout(() => {
      if (synth?.speaking || synth?.pending) {
        synth.cancel();
        resolveOnce(false);
        return;
      }
      resolveOnce(playbackObserved);
    }, timeoutMs);

    utterance.onstart = () => {
      started = true;
      playbackObserved = true;
      window.clearTimeout(startGuardId);
      if (onStart) {
        onStart();
      }
    };

    utterance.onend = () => {
      resolveOnce(true);
    };

    utterance.onerror = () => {
      resolveOnce(false);
    };

    synth.cancel();
    window.setTimeout(() => {
      synth.speak(utterance);
    }, 50);
  });
}

async function speak(text) {
  const clean = text.trim();
  // Keep interview stage audio-first: do not render full assistant utterances on screen.
  setAudioFallback("", false);

  if (!clean) {
    return;
  }

  const localToken = ++speechToken;
  const allowSpeech = () => localToken === speechToken && state.phase === "interview";

  haltRecordingForSpeech();
  stopServerTtsPlayback();
  if (window.speechSynthesis) {
    window.speechSynthesis.cancel();
    if (window.speechSynthesis.paused) {
      window.speechSynthesis.resume();
    }
  }

  speaking = false;
  responsePending = true;
  ui.turnIndicator.textContent = "Turn: Alex responding";
  setVisualState("thinking");
  lastAlexUtterance = clean;
  if (!allowSpeech()) {
    responsePending = false;
    return;
  }

  const allowBargeIn = state.phase === "interview" && state.mediaSupported && !state.processing;
  let bargeStarted = false;
  const onSpeechStart = () => {
    if (!allowSpeech()) {
      return;
    }
    responsePending = false;
    speaking = true;
    ui.turnIndicator.textContent = "Turn: Alex speaking";
    setVisualState("speaking");
    if (ui.recordingState) {
      ui.recordingState.textContent = "Listening will start automatically when it's your turn.";
    }
    if (allowBargeIn && !bargeStarted) {
      startBargeInMonitor();
      bargeStarted = true;
    }
  };

  let spokenOk = false;
  try {
    if (state.serverTtsAvailable) {
      spokenOk = await playServerTts(clean, onSpeechStart);
      if (spokenOk) {
        state.speechSynthesisBlocked = true;
      }
    }

    const useSpeechSynthesis = window.speechSynthesis && !state.speechSynthesisBlocked;
    if (!spokenOk && useSpeechSynthesis) {
      await ensurePreferredVoice(1200);
      const startGuardMs = 1600;
      const firstTry = await runSynthesisUtterance(clean, activeVoice, onSpeechStart, startGuardMs);
      spokenOk = firstTry.ok;
      if (!firstTry.ok) {
        const fallbackTry = await runSynthesisUtterance(clean, null, onSpeechStart, startGuardMs);
        spokenOk = fallbackTry.ok;
      }
    }

    if (!spokenOk && state.serverTtsAvailable) {
      spokenOk = await playServerTts(clean, onSpeechStart);
      if (spokenOk) {
        state.speechSynthesisBlocked = true;
      }
    }
  } finally {
    if (bargeStarted) {
      stopBargeInMonitor();
    }
  }

  if (!spokenOk) {
    if (localToken === speechToken) {
      responsePending = false;
    }
    setStatus("Audio output failed. Click Replay to hear Alex.");
    setAudioFallback(clean, true);
  }

  speaking = false;
  if (localToken === speechToken) {
    responsePending = false;
  }
  if (!allowSpeech()) {
    return;
  }
  if (state.phase === "interview" && !state.processing) {
    setVisualState("listening");
  } else {
    setVisualState("thinking");
  }
}

function stripCompleteTag(reply) {
  return reply.replace("[INTERVIEW_COMPLETE]", "").trim();
}

function normalizeForQuestionMatch(text) {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function replyContainsCanonicalQuestion(reply, question) {
  const normalizedReply = normalizeForQuestionMatch(reply);
  const normalizedQuestion = normalizeForQuestionMatch(question);
  if (!normalizedReply || !normalizedQuestion) {
    return false;
  }
  if (normalizedReply.includes(normalizedQuestion)) {
    return true;
  }

  const key = normalizedQuestion.split(" ").slice(0, 8).join(" ");
  return key.length > 0 && normalizedReply.includes(key);
}

async function apiPost(path, payload, timeoutMs = 60000) {
  const controller = new AbortController();
  const startedAt = performance.now();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  let response;
  try {
    response = await fetch(path, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
  } catch (error) {
    window.clearTimeout(timeoutId);
    if (error.name === "AbortError") {
      throw new Error(`Request timeout after ${Math.round(timeoutMs / 1000)} seconds`);
    }
    throw error;
  }
  window.clearTimeout(timeoutId);

  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const err = await response.json();
      if (response.status === 401 && err?.detail?.code === "PIN_REQUIRED") {
        handlePinRequired();
        throw new Error("PIN required");
      }
      if (err?.detail?.message) {
        message = err.detail.message;
      }
    } catch (_error) {
      // Ignore JSON parsing errors here.
    }
    throw new Error(message);
  }

  const data = await response.json();
  lastChatMs = Math.round(performance.now() - startedAt);
  return data;
}

async function setupMediaStream() {
  if (!state.mediaSupported) {
    return;
  }
  if (mediaStream) {
    return;
  }
  if (mediaInitPromise) {
    await mediaInitPromise;
    return;
  }

  mediaInitPromise = (async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaStream = stream;
    audioContext = new AudioContext();
    analyser = audioContext.createAnalyser();
    analyser.fftSize = 2048;
    const source = audioContext.createMediaStreamSource(stream);
    source.connect(analyser);
  })();

  try {
    await mediaInitPromise;
  } finally {
    mediaInitPromise = null;
  }
}

function stopSilenceMonitor() {
  if (silenceMonitorRaf) {
    cancelAnimationFrame(silenceMonitorRaf);
    silenceMonitorRaf = null;
  }
}

function clearAutoListenRetry() {
  if (autoListenRetryTimer) {
    window.clearTimeout(autoListenRetryTimer);
    autoListenRetryTimer = null;
  }
}

function haltRecordingForSpeech() {
  clearAutoListenRetry();
  stopSilenceMonitor();
  clearCountdown();
  if (state.recording || (mediaRecorder && mediaRecorder.state === "recording")) {
    stopRecording("cancel");
    state.recording = false;
  }
}

async function ensureMediaReady() {
  if (!state.mediaSupported) {
    return false;
  }
  if (mediaStream) {
    return true;
  }
  try {
    await setupMediaStream();
    return Boolean(mediaStream);
  } catch (_error) {
    state.mediaSupported = false;
    ui.recordingState.textContent =
      "Microphone permission or support is unavailable. Voice mode is required.";
    return false;
  }
}

function recorderIsRunning() {
  return Boolean((mediaRecorder && mediaRecorder.state === "recording") || state.recording);
}

function canAutoListen() {
  return (
    state.phase === "interview" &&
    state.mediaSupported &&
    !state.processing &&
    !speaking &&
    !responsePending
  );
}

async function scheduleAutoListen(attempt = 0) {
  clearAutoListenRetry();
  if (!canAutoListen()) {
    autoListenStartedAt = 0;
    return;
  }

  if (state.recording && (!mediaRecorder || mediaRecorder.state !== "recording")) {
    state.recording = false;
  }
  if (recorderIsRunning()) {
    return;
  }

  if (attempt === 0) {
    autoListenStartedAt = performance.now();
    ui.recordingState.textContent = "Preparing microphone...";
  }

  const mediaReady = await ensureMediaReady();
  if (!mediaReady || !canAutoListen()) {
    autoListenStartedAt = 0;
    return;
  }

  startRecording();

  if (recorderIsRunning()) {
    autoListenStartedAt = 0;
    return;
  }

  const waitMs = autoListenStartedAt ? performance.now() - autoListenStartedAt : 0;
  if (waitMs >= 6000) {
    autoListenStartedAt = 0;
    ui.recordingState.textContent =
      "Microphone is taking too long to start. Click Start Mic Test or allow mic access.";
    return;
  }

  if (attempt < 12) {
    autoListenRetryTimer = window.setTimeout(() => {
      void scheduleAutoListen(attempt + 1);
    }, 220);
    return;
  }

  ui.recordingState.textContent = "Microphone did not start. Retrying...";
  autoListenRetryTimer = window.setTimeout(() => {
    void scheduleAutoListen(0);
  }, 700);
}

function monitorSilence() {
  if (!state.recording || !analyser) {
    return;
  }

  const frame = new Float32Array(analyser.fftSize);
  analyser.getFloatTimeDomainData(frame);
  let squareSum = 0;
  for (let index = 0; index < frame.length; index += 1) {
    squareSum += frame[index] * frame[index];
  }

  const rms = Math.sqrt(squareSum / frame.length);
  const dbRaw = rms > 0 ? 20 * Math.log10(rms) : -100;
  smoothedDb = smoothedDb <= -99 ? dbRaw : smoothedDb * 0.82 + dbRaw * 0.18;
  const db = smoothedDb;
  const now = performance.now();
  const elapsed = now - recordingStartedAt;
  const frameDelta = lastFrameAt ? Math.min(200, now - lastFrameAt) : 0;
  lastFrameAt = now;

  if (elapsed >= FORCE_SEND_MS) {
    ui.recordingState.textContent = "Sending answer...";
    stopRecording("auto");
    return;
  }

  if (!hasVoiceActivity) {
    if (db <= noiseFloorDb + NOISE_FLOOR_MAX_RISE_DB) {
      noiseFloorDb = noiseFloorDb * (1 - NOISE_FLOOR_WAITING_ALPHA) + db * NOISE_FLOOR_WAITING_ALPHA;
      noiseFloorDb = Math.max(-90, Math.min(-35, noiseFloorDb));
    }
  }

  const startThreshold = Math.max(ABS_MIN_SPEECH_START_DB, noiseFloorDb + SPEECH_MARGIN_START_DB);
  const continueThreshold = Math.max(
    ABS_MIN_SPEECH_CONTINUE_DB,
    noiseFloorDb + SPEECH_MARGIN_CONTINUE_DB,
  );
  const thresholdSpeech =
    vadPhase === "speaking" || vadPhase === "trailing_silence" || vadPhase === "finalize_pending"
      ? db > continueThreshold
      : db > startThreshold;
  const speechNow = thresholdSpeech || db > SPEECH_OVERRIDE_DB || db - noiseFloorDb >= SPEECH_RISE_DB;
  if (speechNow) {
    speechStreakMs = Math.min(2000, speechStreakMs + frameDelta);
  } else {
    speechStreakMs = 0;
  }
  const speechAccepted = speechNow && speechStreakMs >= SPEECH_ACCEPT_MS;

  if (speechNow && !prevSpeechNow) {
    resumeCooldownUntil = now + 1600;
  }
  prevSpeechNow = speechNow;

  if (!speechNow) {
    if (db <= noiseFloorDb + NOISE_FLOOR_MAX_RISE_DB) {
      noiseFloorDb = noiseFloorDb * (1 - NOISE_FLOOR_ALPHA) + db * NOISE_FLOOR_ALPHA;
      noiseFloorDb = Math.max(-90, Math.min(-35, noiseFloorDb));
    }
  }

  if (speechAccepted) {
    if (!hasVoiceActivity) {
      firstVoiceAt = now;
    }
    hasVoiceActivity = true;
  }

  if (elapsed >= MAX_RECORDING_MS) {
    ui.recordingState.textContent = "Sending answer...";
    stopRecording("auto");
    return;
  }

  if (!hasVoiceActivity) {
    if (elapsed >= MAX_WAIT_FOR_SPEECH_MS) {
      ui.recordingState.textContent =
        "Still listening... speak a bit louder or check microphone access.";
    }
    if (speechAccepted) {
      vadPhase = "speaking";
      ui.recordingState.textContent = "Listening... I will send automatically when you finish.";
    } else {
      vadPhase = "waiting_for_speech";
      ui.recordingState.textContent = "Listening... start speaking when ready.";
    }
    silenceMonitorRaf = requestAnimationFrame(monitorSilence);
    return;
  }

  const spokenFor = firstVoiceAt ? now - firstVoiceAt : 0;
  const canFinalize =
    elapsed >= MIN_RECORDING_MS &&
    elapsed >= STARTUP_GRACE_MS &&
    spokenFor >= MIN_SPEECH_SPAN_MS &&
    elapsed >= AUTO_SEND_MIN_RECORDING_MS &&
    now >= resumeCooldownUntil;

  if (!canFinalize) {
    silenceStartedAt = null;
    pauseHintShown = false;
    finalizeCandidateAt = null;
    clearCountdown();
    ui.recordingState.textContent = "Listening... I will send automatically when you finish.";
    vadPhase = speechAccepted ? "speaking" : "trailing_silence";
    silenceMonitorRaf = requestAnimationFrame(monitorSilence);
    return;
  }

  if (speechAccepted) {
    vadPhase = "speaking";
    silenceStartedAt = null;
    finalizeCandidateAt = null;
    resumeCooldownUntil = now + 1600;
    if (pauseHintShown) {
      pauseHintShown = false;
    }
    clearCountdown();
    ui.recordingState.textContent = "Listening... I will send automatically when you finish.";
    silenceMonitorRaf = requestAnimationFrame(monitorSilence);
    return;
  }

  if (silenceStartedAt === null) {
    silenceStartedAt = now;
    vadPhase = "trailing_silence";
  }

  const silentFor = now - silenceStartedAt;
  if (silentFor >= SILENCE_SOFT_MS && !pauseHintShown) {
    pauseHintShown = true;
    ui.recordingState.textContent = "Pause detected. Continue speaking if you are not finished.";
  }

  if (silentFor >= SILENCE_HARD_MS) {
    vadPhase = "finalize_pending";
    if (finalizeCandidateAt === null) {
      finalizeCandidateAt = now;
      ui.recordingState.textContent = "If you are finished, stay silent. Sending shortly...";
    } else {
      const confirmFor = now - finalizeCandidateAt;
      if (confirmFor >= SILENCE_CONFIRM_MS) {
        stopRecording("auto");
        return;
      }
    }
  }

  if (silentFor >= 0) {
    let remainingMs = 0;
    if (silentFor < SILENCE_HARD_MS) {
      remainingMs = SILENCE_HARD_MS + SILENCE_CONFIRM_MS - silentFor;
    } else if (finalizeCandidateAt !== null) {
      remainingMs = Math.max(0, SILENCE_CONFIRM_MS - (now - finalizeCandidateAt));
    } else {
      remainingMs = SILENCE_CONFIRM_MS;
    }
    const remainingSec = Math.max(0, Math.ceil(remainingMs / 1000));
    if (remainingSec > 0) {
      ui.recordingState.textContent = `Pause detected. Continue speaking (${remainingSec}s).`;
      showCountdown(remainingSec, remainingSec <= 2);
    }
  }

  if (debugEnabled) {
    const recorderState = mediaRecorder ? mediaRecorder.state : "none";
    const audioState = audioContext ? audioContext.state : "none";
    updateDebugPanel(
      [
        `vad: ${vadPhase}`,
        `speechNow: ${speechNow}`,
        `db: ${db.toFixed(1)}`,
        `noise: ${noiseFloorDb.toFixed(1)}`,
        `startThr: ${startThreshold.toFixed(1)}`,
        `contThr: ${continueThreshold.toFixed(1)}`,
        `recording: ${state.recording}`,
        `recorder: ${recorderState}`,
        `audioCtx: ${audioState}`,
        `accepted: ${speechAccepted}`,
        `streak: ${Math.round(speechStreakMs)}ms`,
        `transcribe: ${lastTranscribeMs !== null ? `${lastTranscribeMs}ms` : "--"}`,
        `chat: ${lastChatMs !== null ? `${lastChatMs}ms` : "--"}`,
        `tts: ${lastTtsMs !== null ? `${lastTtsMs}ms` : "--"}`,
      ].join(" | "),
    );
  }

  silenceMonitorRaf = requestAnimationFrame(monitorSilence);
}

function startRecording() {
  clearAutoListenRetry();
  if (!state.mediaSupported || state.recording) {
    return;
  }
  if (speaking) {
    return;
  }
  if (!mediaStream) {
    ui.recordingState.textContent =
      "Microphone is not ready yet. Please allow microphone access and retry.";
    state.mediaSupported = false;
    return;
  }
  if (audioContext && audioContext.state === "suspended") {
    audioContext.resume().catch(() => {});
  }

  chunks = [];
  recorderSessionId += 1;
  const currentSession = recorderSessionId;
  state.pendingStudentText = "";
  silenceStartedAt = null;
  recordingStartedAt = performance.now();
  hasVoiceActivity = false;
  firstVoiceAt = null;
  smoothedDb = -100;
  noiseFloorDb = -65;
  pauseHintShown = false;
  finalizeCandidateAt = null;
  vadPhase = "waiting_for_speech";
  prevSpeechNow = false;
  resumeCooldownUntil = 0;
  lastFrameAt = 0;
  speechStreakMs = 0;
  clearCountdown();
  pendingStopAction = "auto";
  const mimeType = pickRecorderMimeType();
  const recorderOptions = mimeType ? { mimeType } : undefined;
  try {
    mediaRecorder = recorderOptions
      ? new MediaRecorder(mediaStream, recorderOptions)
      : new MediaRecorder(mediaStream);
  } catch (_error) {
    ui.recordingState.textContent =
      "This browser cannot start microphone recording. Voice mode is required.";
    state.mediaSupported = false;
    return;
  }
  mediaRecorder.onstart = () => {
    ui.recordingState.textContent = "Listening... start speaking when ready.";
  };
  mediaRecorder.ondataavailable = (event) => {
    if (currentSession !== recorderSessionId) {
      return;
    }
    if (event.data.size > 0) {
      chunks.push(event.data);
    }
  };

  mediaRecorder.onstop = async () => {
    if (currentSession !== recorderSessionId) {
      return;
    }
    const stopAction = pendingStopAction;
    pendingStopAction = "auto";
    stopSilenceMonitor();
    state.recording = false;

    if (stopAction === "cancel") {
      ui.recordingState.textContent = "Listening stopped.";
      return;
    }

    if (stopAction === "restart") {
      ui.recordingState.textContent = "Restarting answer...";
      if (state.phase === "interview" && !state.processing && state.mediaSupported) {
        startRecording();
      }
      return;
    }

    if (!chunks.length) {
      ui.recordingState.textContent = "No speech detected. Listening again...";
      if (state.phase === "interview" && !state.processing && state.mediaSupported) {
        startRecording();
      }
      return;
    }

    ui.recordingState.textContent = "Transcribing...";
    const blobType = mediaRecorder.mimeType || "audio/webm";
    const blob = new Blob(chunks, { type: blobType });
    const durationMs = Math.max(Math.round(performance.now() - recordingStartedAt), 0);

    const form = new FormData();
    const ext = blobType.includes("mp4") ? "m4a" : blobType.includes("ogg") ? "ogg" : "webm";
    form.append("audio", blob, `answer.${ext}`);
    form.append("duration_ms", String(durationMs));

    try {
      const transcribeStarted = performance.now();
      const response = await fetch("/transcribe", {
        method: "POST",
        headers: authHeaders(),
        body: form,
      });
      if (!response.ok) {
        let message = `Transcription failed (${response.status})`;
        try {
          const err = await response.json();
          message = err?.detail?.message || err?.message || message;
        } catch (_error) {
          // Ignore JSON parsing errors.
        }
        throw new Error(message);
      }
      const payload = await response.json();
      lastTranscribeMs = Math.round(performance.now() - transcribeStarted);
      state.pendingStudentText = (payload.text || "").trim();
      if (state.pendingStudentText.length > 0 && looksLikeSpeech(state.pendingStudentText)) {
        ui.recordingState.textContent = "Response captured. Sending...";
        await handleStudentSubmit(state.pendingStudentText);
      } else {
        ui.recordingState.textContent =
          "Could not detect a clear response. Please answer again.";
        if (state.phase === "interview" && !state.processing && state.mediaSupported) {
          startRecording();
        }
      }
    } catch (error) {
      ui.recordingState.textContent = error.message;
      if (state.phase === "interview" && !state.processing && state.mediaSupported) {
        window.setTimeout(() => {
          if (state.phase === "interview" && !state.processing && !state.recording && state.mediaSupported) {
            startRecording();
          }
        }, 500);
      }
    }
  };

  mediaRecorder.start();
  state.recording = true;
  ui.recordingState.textContent = "Listening... start speaking when ready.";
  monitorSilence();
}

function stopRecording(action = "auto") {
  if (action !== "restart") {
    clearAutoListenRetry();
  }
  if (!mediaRecorder || mediaRecorder.state !== "recording") {
    if (
      action === "restart" &&
      state.phase === "interview" &&
      state.mediaSupported &&
      !state.processing &&
      !state.recording
    ) {
      startRecording();
      return;
    }
    if (action === "send" && state.pendingStudentText && !state.processing) {
      void handleStudentSubmit(state.pendingStudentText);
      return;
    }
    return;
  }
  pendingStopAction = action;
  mediaRecorder.stop();
}

function unlockStudentTurn(statusText = "", autoListen = true) {
  state.processing = false;
  if (!state.recording) {
    setStudentTurnEnabled(true);
  }
  if (statusText) {
    setStatus(statusText);
  }
  setVisualState("listening");
  if (
    autoListen &&
    state.phase === "interview" &&
    state.mediaSupported &&
    !state.processing &&
    !state.recording
  ) {
    window.setTimeout(() => {
      void scheduleAutoListen(0);
    }, 120);
  }
}

function startInteractionGuard() {
  stopInteractionGuard();
  interactionGuardInterval = window.setInterval(() => {
    if (state.phase !== "interview") {
      return;
    }
    if (state.processing || state.recording) {
      return;
    }
    if (speaking || responsePending) {
      return;
    }
    setStudentTurnEnabled(true);
    if (state.mediaSupported && !state.recording) {
      void scheduleAutoListen(0);
    }
  }, 1500);
}

function stopInteractionGuard() {
  clearAutoListenRetry();
  if (interactionGuardInterval) {
    window.clearInterval(interactionGuardInterval);
    interactionGuardInterval = null;
  }
}

function setStudentTurnEnabled(enabled) {
  ui.turnIndicator.textContent = enabled ? "Turn: Your response" : "Turn: Alex speaking";
  setVisualState(enabled ? "listening" : "thinking");
}

function registerStrike(replyText) {
  const normalized = replyText.toLowerCase();
  if (STRIKE_PHRASES.some((phrase) => normalized.includes(phrase))) {
    state.strikeCount = Math.min(state.strikeCount + 1, 3);
  }
}

async function askQuestion() {
  const question = state.questions[state.questionIndex];
  setStatus(`Question ${state.questionIndex + 1} of 7`);
  renderDots();
  pushTurn("assistant", question);
  state.awaitingProbe = false;
  state.probeUsedCurrentQuestion = false;
  setStudentTurnEnabled(false);
  try {
    await speak(question);
  } finally {
    unlockStudentTurn();
  }
}

async function startClosing() {
  state.inClosing = true;
  setStatus("Closing question");
  pushTurn("assistant", CLOSING_PROMPT);
  setStudentTurnEnabled(false);
  try {
    await speak(CLOSING_PROMPT);
  } finally {
    unlockStudentTurn();
  }
}

async function runChat(studentText) {
  const historyBeforeAnswer = [...state.history];
  pushTurn("user", studentText);

  const phase = state.inClosing
    ? "closing_question"
    : state.awaitingProbe
      ? "probe_answer"
      : "main_answer";

  return apiPost(
    "/chat",
    {
      student_name: state.studentName,
      role_name: state.roleName,
      question_index: Math.min(state.questionIndex + 1, 7),
      phase,
      probe_used_current_question: state.probeUsedCurrentQuestion,
      strike_count: state.strikeCount,
      history: historyBeforeAnswer,
      student_text: studentText,
    },
    65000,
  );
}

async function finishInterview(reason = "completed") {
  if (state.phase === "report") {
    return;
  }

  state.phase = "report";
  speechToken += 1;
  responsePending = false;
  state.endedAt = Date.now();
  stopTimer();
  stopRecording("cancel");
  stopInteractionGuard();
  setStudentTurnEnabled(false);
  if (window.speechSynthesis) {
    window.speechSynthesis.cancel();
  }
  stopServerTtsPlayback();
  stopBargeInMonitor();
  speaking = false;

  setStatus(reason === "manual" ? "Interview ended manually. Generating report..." : "Interview complete. Generating report...");
  showScreen(ui.reportScreen);

  const askedQuestionIndexes = new Set();
  state.history.forEach((turn) => {
    if (turn.role !== "assistant") {
      return;
    }
    const idx = state.questions.indexOf(turn.content);
    if (idx >= 0) {
      askedQuestionIndexes.add(idx);
    }
  });
  const askedMainQuestions = askedQuestionIndexes.size;
  const userTurnCount = state.history.filter((turn) => turn.role === "user").length;
  const answeredQuestions = Math.min(state.questions.length, askedMainQuestions, userTurnCount);
  const interviewCompleted =
    reason === "completed" && state.inClosing && state.questionIndex >= state.questions.length;
  const durationSeconds = Math.max(Math.floor((state.endedAt - state.startedAt) / 1000), 0);
  const today = new Date();
  const dateStr = `${String(today.getDate()).padStart(2, "0")}/${String(today.getMonth() + 1).padStart(2, "0")}/${today.getFullYear()}`;

  if (ui.reportStudentName) {
    ui.reportStudentName.textContent = state.studentName || "Candidate";
  }
  if (ui.reportMeta) {
    ui.reportMeta.textContent = `${state.roleName || "Role"} · NovaTech Solutions · ${dateStr} · ${formatReportDuration(durationSeconds)}`;
  }

  try {
    const payload = await apiPost(
      "/evaluate",
      {
        student_name: state.studentName,
        role_name: state.roleName,
        transcript: state.history,
        duration_seconds: durationSeconds,
        off_topic_strikes: state.strikeCount,
        answered_questions: answeredQuestions,
        total_questions: state.questions.length || 7,
        interview_completed: interviewCompleted,
      },
      120000,
    );

    renderScores(payload.scores);
    renderReportText(payload.report_text || "No report returned.");
    setStatus("Report ready.");
  } catch (error) {
    ui.scoreGrid.classList.add("hidden");
    renderReportText(`Failed to generate report: ${error.message}`);
    setStatus("Report generation failed.");
  }
}

function renderScores(scores) {
  const values = [scores?.c1, scores?.c2, scores?.c3, scores?.c4, scores?.c5, scores?.total, scores?.cefr];
  const hasValues = values.some((value) => value !== null && value !== undefined && value !== "");

  if (!hasValues) {
    ui.scoreGrid.classList.add("hidden");
    return;
  }

  ui.scoreGrid.classList.remove("hidden");
  ui.scoreGrid.innerHTML = "";

  const cells = [
    ["C1", scores.c1],
    ["C2", scores.c2],
    ["C3", scores.c3],
    ["C4", scores.c4],
    ["C5", scores.c5],
    ["Total", scores.total],
    ["Grade", scores.grade],
    ["CEFR", scores.cefr],
  ];

  cells.forEach(([label, value]) => {
    const cell = document.createElement("div");
    cell.className = "score-cell";
    cell.innerHTML = `<strong>${label}</strong><br>${value ?? "-"}`;
    ui.scoreGrid.appendChild(cell);
  });
}

function formatReportDuration(seconds) {
  const minutes = Math.max(1, Math.round(seconds / 60));
  return `~${minutes} min`;
}

function escapeHtml(text) {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function normalizeReportText(text) {
  return String(text || "")
    .replaceAll("\r\n", "\n")
    .replaceAll(/\*\*/g, "")
    .trim();
}

function classifyReportLine(line) {
  const trimmed = line.trim();
  if (!trimmed) {
    return "m-line-empty";
  }
  if (/^[═─-]{8,}$/.test(trimmed)) {
    return "m-line-rule";
  }
  if (
    /^INTERVIEW EVALUATION REPORT$/.test(trimmed) ||
    /^CRITERION SCORES$/.test(trimmed) ||
    /^LANGUAGE SAMPLES FROM THIS INTERVIEW$/.test(trimmed) ||
    /^CEFR MAPPING:$/.test(trimmed)
  ) {
    return "m-line-section";
  }
  if (/^TOTAL:\s*/.test(trimmed)) {
    return "m-line-total";
  }
  if (/^C1\s*[—-]/.test(trimmed)) {
    return "m-line-criterion c1";
  }
  if (/^C2\s*[—-]/.test(trimmed)) {
    return "m-line-criterion c2";
  }
  if (/^C3\s*[—-]/.test(trimmed)) {
    return "m-line-criterion c3";
  }
  if (/^C4\s*[—-]/.test(trimmed)) {
    return "m-line-criterion c4";
  }
  if (/^C5\s*[—-]/.test(trimmed)) {
    return "m-line-criterion c5";
  }
  if (/^[✓△⚠]/.test(trimmed)) {
    return "m-line-sample";
  }
  return "m-line-body";
}

function renderReportText(text) {
  const normalized = normalizeReportText(text);
  state.reportPlainText = normalized;
  if (!normalized) {
    ui.reportText.innerHTML = "";
    return;
  }
  const html = normalized
    .split("\n")
    .map((line) => `<span class="${classifyReportLine(line)}">${escapeHtml(line)}</span>`)
    .join("\n");
  ui.reportText.innerHTML = html;
}

async function handleStudentSubmit(textOverride = null) {
  if (state.processing || state.phase !== "interview") {
    return;
  }

  const text = (
    textOverride !== null
      ? String(textOverride)
      : state.mediaSupported
        ? state.pendingStudentText.trim()
        : ""
  ).trim();
  if (!text) {
    setStatus("Please provide an answer before submitting.");
    return;
  }
  if (!looksLikeSpeech(text)) {
    setStatus("Please provide a clear spoken answer.");
    if (state.phase === "interview" && state.mediaSupported && !state.processing) {
      startRecording();
    }
    return;
  }

  state.processing = true;
  setStudentTurnEnabled(false);
  setStatus("Alex is reviewing your answer...");
  setVisualState("thinking");
  const lockWatchdog = window.setTimeout(() => {
    if (state.phase === "interview" && state.processing) {
      unlockStudentTurn("Response took too long. Please try again.");
    }
  }, 75000);

  try {
    const chat = await runChat(text);
    const cleanReply = stripCompleteTag(chat.reply || "");

    if (cleanReply) {
      pushTurn("assistant", cleanReply);
      registerStrike(cleanReply);
      await speak(cleanReply);
    }

    state.pendingStudentText = "";

    if (chat.contains_complete_tag) {
      window.clearTimeout(lockWatchdog);
      await finishInterview("completed");
      return;
    }

    if (state.inClosing) {
      window.clearTimeout(lockWatchdog);
      await finishInterview("completed");
      return;
    }

    if (chat.is_probe && !state.probeUsedCurrentQuestion) {
      state.probeUsedCurrentQuestion = true;
      state.awaitingProbe = true;
      window.clearTimeout(lockWatchdog);
      unlockStudentTurn(`Question ${state.questionIndex + 1} follow-up`);
      return;
    }

    state.questionIndex += 1;
    if (state.questionIndex < state.questions.length) {
      const upcomingQuestion = state.questions[state.questionIndex];
      const replyAlreadyAskedNextQuestion = Boolean(
        cleanReply && replyContainsCanonicalQuestion(cleanReply, upcomingQuestion),
      );

      if (replyAlreadyAskedNextQuestion) {
        state.awaitingProbe = false;
        state.probeUsedCurrentQuestion = false;
        setStatus(`Question ${state.questionIndex + 1} of 7`);
        renderDots();
        window.clearTimeout(lockWatchdog);
        unlockStudentTurn();
        return;
      }

      window.clearTimeout(lockWatchdog);
      await askQuestion();
      return;
    }

    window.clearTimeout(lockWatchdog);
    await startClosing();
  } catch (error) {
    window.clearTimeout(lockWatchdog);
    unlockStudentTurn(`Error: ${error.message}`);
  }
}

async function beginInterview() {
  if (state.pinRequired && !state.pinUnlocked) {
    const pin = ui.pinCode ? ui.pinCode.value.trim() : "";
    const unlocked = await tryUnlockPin(pin);
    if (!unlocked) {
      handlePinRequired("Enter the class PIN to begin.");
      return;
    }
  }
  if (state.questions.length !== 7) {
    try {
      await fetchQuestions();
      await fetchTtsStatus();
    } catch (error) {
      if (error.message !== "PIN required") {
        setStatus(`Unable to load questions: ${error.message}`);
      }
      return;
    }
  }
  stopMicTest();
  clearMicPlayback();
  state.studentName = ui.studentName.value.trim();
  state.roleName = ui.roleName.value.trim();
  state.phase = "interview";
  state.questionIndex = 0;
  state.history = [];
  state.strikeCount = 0;
  state.awaitingProbe = false;
  state.probeUsedCurrentQuestion = false;
  state.inClosing = false;
  state.pendingStudentText = "";
  state.reportPlainText = "";
  state.startedAt = Date.now();
  state.endedAt = 0;

  detectInputMode();
  if (!state.mediaSupported) {
    setStatus("Voice mode requires microphone recording support. Please use a current Chrome/Safari browser.");
    return;
  }
  const mediaReady = await ensureMediaReady();
  if (!mediaReady) {
    setStatus("Microphone access is required for speaking mode. Please allow access and try again.");
    return;
  }

  showScreen(ui.interviewScreen);
  startTimer();
  startInteractionGuard();
  renderDots();
  setVisualState("speaking");

  const opening = OPENING_TEMPLATE.replace("{name}", state.studentName);
  pushTurn("assistant", opening);
  await speak(opening);
  await askQuestion();
}

function attachEvents() {
  ui.studentName.addEventListener("input", updateBeginEnabled);
  ui.roleName.addEventListener("input", updateBeginEnabled);
  if (ui.pinCode) {
    ui.pinCode.addEventListener("input", () => {
      if (state.pinRequired && !state.pinUnlocked) {
        setPinStatus("");
      }
      updateBeginEnabled();
    });
  }

  ui.setupForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    unlockAudioOutput(true);
    try {
      window.speechSynthesis?.getVoices?.();
    } catch (_error) {
      // Ignore.
    }
    ui.beginBtn.disabled = true;
    try {
      await beginInterview();
    } catch (error) {
      setStatus(`Could not start interview: ${error.message}`);
    } finally {
      if (state.phase === "setup") {
        ui.beginBtn.disabled = false;
      }
    }
  });

  if (ui.replayBtn) {
    ui.replayBtn.addEventListener("click", async () => {
      if (!lastAlexUtterance) {
        return;
      }
      await speak(lastAlexUtterance);
    });
  }

  if (ui.micTestBtn) {
    ui.micTestBtn.addEventListener("click", () => {
      void startMicTest();
    });
  }
  if (ui.micStopBtn) {
    ui.micStopBtn.addEventListener("click", () => {
      stopMicTest();
    });
  }
  if (ui.micRecordBtn) {
    ui.micRecordBtn.addEventListener("click", () => {
      void recordMicSample();
    });
  }
  if (ui.audioTestBtn) {
    ui.audioTestBtn.addEventListener("click", () => {
      void runAudioTest();
    });
  }
  if (ui.audioOpenBtn) {
    ui.audioOpenBtn.addEventListener("click", () => {
      window.open(window.location.href, "_blank", "noopener");
    });
  }

  ui.endInterviewBtn.addEventListener("click", async () => {
    await finishInterview("manual");
  });

  if (ui.copyReportBtn) {
    ui.copyReportBtn.addEventListener("click", async () => {
      const report = state.reportPlainText || ui.reportText.textContent || "";
      if (!report) {
        return;
      }
      await navigator.clipboard.writeText(report);
      setStatus("Report copied to clipboard.");
    });
  }

  if (ui.printReportBtn) {
    ui.printReportBtn.addEventListener("click", () => {
      window.print();
    });
  }

  if (ui.newInterviewBtn) {
    ui.newInterviewBtn.addEventListener("click", () => {
      window.location.reload();
    });
  }
}

async function initialize() {
  showScreen(ui.setupScreen);
  detectInputMode();
  attachEvents();

  if (window.speechSynthesis) {
    unlockAudioOutput();
    loadVoices();
    window.speechSynthesis.onvoiceschanged = loadVoices;
    setAudioTestStatus("Audio is idle.");
  } else {
    setAudioTestStatus("Audio output is not supported in this browser.");
  }

  if (ui.audioTestHint) {
    ui.audioTestHint.classList.toggle("hidden", !isInIframe());
  }
  if (ui.audioOpenBtn) {
    ui.audioOpenBtn.classList.toggle("hidden", !isInIframe());
  }

  try {
    await fetchPinStatus();
    await fetchTtsStatus();
    if (!state.pinRequired || state.pinUnlocked) {
      await fetchQuestions();
      setStatus("Questions loaded. Enter your details to begin.");
    } else {
      setStatus("Enter the class PIN to load questions.");
    }
  } catch (error) {
    if (error.message === "PIN required") {
      setStatus("Enter the class PIN to load questions.");
    } else {
      setStatus(`Unable to load questions: ${error.message}`);
    }
  }

  updateBeginEnabled();
}

initialize();
