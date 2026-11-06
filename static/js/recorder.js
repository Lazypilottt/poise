(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const questions = JSON.parse($("questions-data").textContent);

  const preview = $("preview");
  const playback = $("playback");
  const camMessage = $("cam-message");
  const statusEl = $("status");
  const badge = $("rec-badge");
  const timerEl = $("timer");
  const overlay = $("overlay");
  const btn = {
    start: $("btn-start"),
    stop: $("btn-stop"),
    retake: $("btn-retake"),
    submit: $("btn-submit"),
    prev: $("q-prev"),
    next: $("q-next"),
  };

  let stream = null;
  let recorder = null;
  let chunks = [];
  let recording = null;
  let timerId = null;
  let startedAt = 0;
  let current = 0;

  // ---------- questions ----------
  function showQuestion(index) {
    current = Math.max(0, Math.min(index, questions.length - 1));
    $("q-text").textContent = questions[current];
    $("q-counter").textContent = `Question ${current + 1} of ${questions.length}`;
    document.querySelectorAll("#q-dots .dot").forEach((dot, i) => {
      dot.classList.toggle("dot--active", i === current);
      dot.classList.toggle("dot--done", i < current);
    });
    btn.prev.disabled = current === 0;
    btn.next.disabled = current === questions.length - 1;
  }
  btn.prev.addEventListener("click", () => showQuestion(current - 1));
  btn.next.addEventListener("click", () => showQuestion(current + 1));

  // ---------- camera ----------
  function pickMimeType() {
    const candidates = ["video/webm;codecs=vp9,opus", "video/webm;codecs=vp8,opus", "video/webm", "video/mp4"];
    return candidates.find((t) => window.MediaRecorder && MediaRecorder.isTypeSupported(t)) || "";
  }

  async function initCamera() {
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      camMessage.textContent = "Your browser doesn't support in-browser recording. Try the latest Chrome, Edge or Firefox.";
      return;
    }
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: "user" },
        audio: { echoCancellation: true, noiseSuppression: true },
      });
      preview.srcObject = stream;
      camMessage.hidden = true;
      btn.start.disabled = false;
    } catch (err) {
      camMessage.textContent =
        err.name === "NotAllowedError"
          ? "Camera/microphone access was blocked. Allow access in your browser's address bar and reload."
          : `Couldn't start the camera: ${err.message}`;
    }
  }

  // ---------- recording ----------
  function formatTime(ms) {
    const s = Math.floor(ms / 1000);
    return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
  }

  function startRecording() {
    chunks = [];
    const mimeType = pickMimeType();
    recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    recorder.onstop = () => {
      recording = new Blob(chunks, { type: recorder.mimeType || "video/webm" });
      playback.src = URL.createObjectURL(recording);
      playback.hidden = false;
      preview.hidden = true;
    };
    recorder.start(1000);

    startedAt = Date.now();
    timerEl.textContent = "00:00";
    timerId = setInterval(() => (timerEl.textContent = formatTime(Date.now() - startedAt)), 500);

    showQuestion(0);
    badge.hidden = false;
    btn.start.hidden = true;
    btn.stop.hidden = false;
    statusEl.textContent = "Recording - use “Next question” as you go.";
  }

  function stopRecording() {
    if (Date.now() - startedAt < 5000) {
      statusEl.textContent = "Keep going - record at least a few seconds of speech.";
      return;
    }
    recorder.stop();
    clearInterval(timerId);
    badge.hidden = true;
    btn.stop.hidden = true;
    btn.retake.hidden = false;
    btn.submit.hidden = false;
    statusEl.textContent = `Recorded ${timerEl.textContent}. Review it, then submit for analysis.`;
  }

  function retake() {
    if (playback.src) URL.revokeObjectURL(playback.src);
    playback.removeAttribute("src");
    playback.hidden = true;
    preview.hidden = false;
    recording = null;
    btn.retake.hidden = true;
    btn.submit.hidden = true;
    btn.start.hidden = false;
    statusEl.textContent = "Ready when you are.";
  }

  async function submit() {
    if (!recording) return;
    const ext = recording.type.includes("mp4") ? "mp4" : "webm";
    const body = new FormData();
    body.append("recording", recording, `interview.${ext}`);

    overlay.hidden = false;
    btn.submit.disabled = true;
    try {
      const res = await fetch(window.POISE.submitUrl, {
        method: "POST",
        body,
        headers: { "X-CSRFToken": window.POISE.csrfToken },
        credentials: "same-origin",
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok && data.redirect) {
        stream?.getTracks().forEach((t) => t.stop());
        window.location.href = data.redirect;
        return;
      }
      throw new Error(data.error || `Server returned ${res.status}`);
    } catch (err) {
      overlay.hidden = true;
      btn.submit.disabled = false;
      statusEl.textContent = err.message;
      statusEl.classList.add("error");
    }
  }

  btn.start.addEventListener("click", startRecording);
  btn.stop.addEventListener("click", stopRecording);
  btn.retake.addEventListener("click", retake);
  btn.submit.addEventListener("click", submit);

  showQuestion(0);
  initCamera();
})();
