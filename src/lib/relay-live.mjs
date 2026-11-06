// Network and state rules for the Signal Relay laboratory. Nothing here touches the DOM: the page passes
// a `view` of render callbacks, and the Node test suite drives this module with a stubbed fetch, event
// targets, and fake timers.

export const pollIntervalMs = 2000;
export const inboxIntervalMs = 10_000;
export const nodesIntervalMs = 20_000;
export const failedGiveUpMs = 15_000;
export const sendCooldownMs = 10_000;
export const readTimeoutMs = 10_000;
// Session polls are ticked every pollIntervalMs. Two may be pending at once, so one honest slow answer does not block the next poll,
// while a relay that never answers cannot stack more than two requests.
const maxPendingSessionPolls = 2;

export function createRelayLive({ relayUrl, fetch, view, documentTarget, windowTarget }) {
  let controller = new AbortController();
  let live = false;
  let sessionId;
  let sessionState;
  let sent = false;
  let sending = false;
  let cooling = false;
  let pollSequence = 0;
  let appliedPollSequence = 0;
  let pendingSessionPolls = 0;
  let inboxTimer;
  let nodesTimer;
  let sessionTimer;

  const applySessionState = (state, errorCode = "") => {
    sessionState = state;
    view.setSessionState(state, errorCode);
  };

  // Every relay GET runs under its own read timeout, and the run's signal still aborts it. A read that times out rejects
  // with a TimeoutError. Sends are POSTs and never go through here, so the timeout cannot abort a message.
  const withReadTimeout = async (runSignal, read) => {
    const readController = new AbortController();
    let timedOut = false;
    const abortRead = () => readController.abort();
    const timer = setTimeout(() => {
      timedOut = true;
      readController.abort();
    }, readTimeoutMs);
    runSignal.addEventListener("abort", abortRead, { once: true });
    if (runSignal.aborted) readController.abort();
    try {
      return await read(readController.signal);
    } catch (error) {
      if (timedOut) throw new DOMException("The relay read timed out.", "TimeoutError");
      throw error;
    } finally {
      clearTimeout(timer);
      runSignal.removeEventListener("abort", abortRead);
    }
  };

  // Reads one JSON document. A non-2xx answer or an unreadable body rejects, and the caller decides how much that matters.
  const readJson = (path, signal) =>
    withReadTimeout(signal, async (readSignal) => {
      const response = await fetch(`${relayUrl}${path}`, { signal: readSignal });
      if (!response.ok) throw new Error(`${path} answered ${response.status}`);
      return response.json();
    });

  const refreshInbox = async () => {
    if (!relayUrl) return;
    const { signal } = controller;
    try {
      const data = await readJson("/v1/inbox", signal);
      if (!signal.aborted) view.setInbox(data);
    } catch {
      // The availability request remains the source of the relay health state.
    }
  };

  const refreshNodes = async () => {
    if (!relayUrl) return;
    const { signal } = controller;
    try {
      const data = await readJson("/v1/lab/reticulum-nodes", signal);
      if (!signal.aborted) view.setNodes(data);
    } catch {
      if (!signal.aborted) view.setNodes({});
    }
  };

  // Health, contact, and inbox decide availability. Capabilities and nodes are optional: when they fail, only their own panel falls back.
  const refreshStatus = async () => {
    if (!relayUrl) return;
    const { signal } = controller;
    try {
      const [health, contact, inbox, capabilities, nodes] = await Promise.allSettled([
        readJson("/healthz", signal),
        readJson("/v1/contact", signal),
        readJson("/v1/inbox", signal),
        readJson("/v1/lab/capabilities", signal),
        readJson("/v1/lab/reticulum-nodes", signal),
      ]);
      if (signal.aborted) return;
      if (![health, contact, inbox].every((result) => result.status === "fulfilled")) throw new Error("relay unavailable");
      view.setAvailability(health.value.status === "ready");
      if (contact.value.address) view.setAddress(contact.value.address);
      view.setInbox(inbox.value);
      view.setNodes(nodes.status === "fulfilled" ? nodes.value : {});
      view.setTelegram(capabilities.status === "fulfilled" && Boolean(capabilities.value?.telegramNotifications));
    } catch {
      if (!signal.aborted) view.setAvailability(false);
    }
  };

  // Polling runs only while the page is live, so a send that resolves while hidden waits for the next start.
  const pollSession = () => {
    if (!relayUrl || !sessionId || !live) return;
    let failedAt;
    clearInterval(sessionTimer);
    sessionTimer = setInterval(async () => {
      // A tick that finds the pending cap reached skips its poll, so a relay that never answers cannot stack requests.
      if (pendingSessionPolls >= maxPendingSessionPolls) return;
      const { signal } = controller;
      // Each tick numbers its request. An answer may write state only if no answer from a later tick has written state yet,
      // so a slow answer still lands while an out-of-order answer that arrives after a newer one cannot undo it.
      const sequence = ++pollSequence;
      const mayApply = () => !signal.aborted && sequence > appliedPollSequence;
      pendingSessionPolls += 1;
      try {
        const session = await withReadTimeout(signal, async (readSignal) => {
          const response = await fetch(`${relayUrl}/v1/lab/sessions/${sessionId}`, { signal: readSignal });
          if (!response.ok) throw Object.assign(new Error("session unavailable"), { status: response.status });
          return response.json();
        });
        // A poll that resolves after hiding or leaving the page must not write state or touch the timer of the next run.
        if (!mayApply()) return;
        appliedPollSequence = sequence;
        view.setSessionNode(session.nodeAlias);
        applySessionState(session.state, session.errorCode);
        if (session.state === "delivered") {
          clearInterval(sessionTimer);
          refreshInbox();
        }
        if (session.state === "failed") {
          failedAt ??= Date.now();
          if (Date.now() - failedAt >= failedGiveUpMs) clearInterval(sessionTimer);
        } else {
          failedAt = undefined;
        }
      } catch (error) {
        // A poll aborted by hiding or leaving the page is not a relay failure; start() resumes polling with the page.
        // A superseded poll's error is ignored too, because an answer from a later tick already decided the state.
        if (!mayApply()) return;
        // A rate-limited or timed-out poll is transient: it keeps the last shown state and the next tick polls again.
        if (error.status === 429 || error.name === "TimeoutError") return;
        appliedPollSequence = sequence;
        clearInterval(sessionTimer);
        // A 404 means the relay no longer knows the session: it expired, or the relay restarted.
        applySessionState("failed", error.status === 404 ? "session_not_found" : "outbound_error");
      } finally {
        pendingSessionPolls -= 1;
      }
    }, pollIntervalMs);
  };

  // Resolves to "ready", "unavailable" (the relay refused or sent an unreadable answer), or "unreachable" (the request failed at the
  // network layer). Creating a session sends no message, so "unreachable" is a plain failure, never an unconfirmed delivery.
  const createSession = async () => {
    view.setSessionNotice("preparing");
    let response;
    try {
      response = await fetch(`${relayUrl}/v1/lab/sessions`, { method: "POST" });
    } catch {
      return "unreachable";
    }
    let session;
    try {
      if (!response.ok) throw new Error("session refused");
      session = await response.json();
    } catch {
      view.setSessionNotice("unavailable");
      return "unavailable";
    }
    sessionId = session.sessionId;
    view.setSessionNode(session.nodeAlias);
    applySessionState(session.state, session.errorCode);
    return "ready";
  };

  // Sending is locked for the cooldown, after which the composer reopens unless the message was accepted.
  const startCooldown = () => {
    cooling = true;
    view.setComposer("cooldown");
    setTimeout(() => {
      cooling = false;
      view.setComposer(sent ? "sent" : "open");
    }, sendCooldownMs);
  };

  // The relay may already have accepted the request, so the page must not report a plain failure or re-enable sending at once.
  const markUnconfirmed = () => {
    applySessionState("unconfirmed");
    startCooldown();
  };

  // `readContent` runs when the message POST starts, so text typed while the session is being created is sent.
  // Sends are single-flight: a submit while a session is being created or a message is in flight is ignored, so no second session or message starts.
  const send = async (readContent) => {
    if (!relayUrl || sent || cooling || sending) return;
    sending = true;
    try {
      if (!sessionId) {
        const outcome = await createSession();
        // No session was created and no message was sent, so the delivery failed. The cooldown keeps retries off the edge rate limiter.
        if (outcome === "unreachable") {
          applySessionState("failed");
          return startCooldown();
        }
        // A refused session gets the same cooldown as a refused message, so repeated submits do not hit the edge rate limiter.
        if (outcome === "unavailable") return startCooldown();
      }
      let response;
      try {
        // A send is not tied to the polling controller: hiding or leaving the page does not abort it, and it resolves to its delivered, queued, or failed state.
        response = await fetch(`${relayUrl}/v1/lab/sessions/${sessionId}/messages`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content: readContent() }),
        });
      } catch {
        return markUnconfirmed();
      }
      if (response.status === 429) {
        // Rate-limited means the relay refused the message: the session is not failed, and the cooldown keeps retries from hammering the edge.
        view.setSessionNotice("unavailable");
        return startCooldown();
      }
      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        // session_not_found means the relay forgot the session (it expired after 15 minutes, or the relay restarted) before it accepted
        // anything. The session is dropped, so the next send creates a fresh one instead of retrying the dead session.
        if (error.detail === "session_not_found") sessionId = undefined;
        applySessionState("failed", error.detail || "outbound_error");
        return;
      }
      let session;
      try {
        session = await response.json();
      } catch {
        // A 200 with an unreadable body may still have accepted the message, so it is treated like a network failure.
        return markUnconfirmed();
      }
      applySessionState(session.state, session.errorCode);
      if (session.state === "queued") pollSession();
      sent = true;
      view.setComposer("sent");
    } finally {
      sending = false;
    }
  };

  // Hidden or leaving stops the polling timers and aborts the polling GETs; visible or a restore from the back/forward cache starts them again.
  const start = () => {
    if (!relayUrl || live) return;
    live = true;
    controller = new AbortController();
    void refreshStatus();
    inboxTimer = setInterval(refreshInbox, inboxIntervalMs);
    nodesTimer = setInterval(refreshNodes, nodesIntervalMs);
    if (sessionState === "queued") pollSession();
  };

  const stop = () => {
    if (!live) return;
    live = false;
    controller.abort();
    clearInterval(inboxTimer);
    clearInterval(nodesTimer);
    clearInterval(sessionTimer);
  };

  documentTarget.addEventListener("visibilitychange", () => (documentTarget.visibilityState === "hidden" ? stop() : start()));
  windowTarget.addEventListener("pagehide", stop);
  windowTarget.addEventListener("pageshow", (event) => {
    if (event.persisted) start();
  });
  if (documentTarget.visibilityState !== "hidden") start();

  return { send };
}
