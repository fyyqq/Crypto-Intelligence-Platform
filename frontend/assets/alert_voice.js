// Plays Gemini price-alert speech (16-bit PCM) pushed from CoinState.speak_alert.
// One shared AudioContext, unlocked on the first click/key (browser autoplay rule);
// once running it keeps playing even when this tab is in the background.
(function () {
  if (window.repacePlayAlertVoice) return;
  let ctx = null;
  let nextStart = 0;
  const pending = [];

  function ensureCtx() {
    if (!ctx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return null;
      ctx = new AC();
    }
    if (ctx.state === "suspended") ctx.resume().catch(() => {});
    return ctx;
  }

  function play(b64, rate) {
    const c = ensureCtx();
    if (!c) return;
    if (c.state !== "running") {
      pending.push([b64, rate]);
      return;
    }
    const bin = atob(b64);
    const samples = Math.floor(bin.length / 2);
    const buf = c.createBuffer(1, samples, rate || 24000);
    const out = buf.getChannelData(0);
    for (let i = 0; i < samples; i++) {
      let v = bin.charCodeAt(2 * i) | (bin.charCodeAt(2 * i + 1) << 8);
      if (v >= 0x8000) v -= 0x10000;
      out[i] = v / 0x8000;
    }
    const src = c.createBufferSource();
    src.buffer = buf;
    src.connect(c.destination);
    // Queue back to back so two alerts in one tick don't talk over each other.
    nextStart = Math.max(nextStart, c.currentTime + 0.05);
    src.start(nextStart);
    nextStart += buf.duration + 0.3;
  }

  function unlock() {
    const c = ensureCtx();
    if (!c) return;
    const flush = () => {
      while (pending.length && c.state === "running") play(...pending.shift());
    };
    c.state === "running" ? flush() : c.resume().then(flush).catch(() => {});
  }

  ["pointerdown", "keydown", "touchstart"].forEach((ev) =>
    window.addEventListener(ev, unlock, { capture: true, passive: true })
  );

  window.repacePlayAlertVoice = play;
})();
