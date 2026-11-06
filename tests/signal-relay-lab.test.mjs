import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  createRelayLive,
  failedGiveUpMs,
  inboxIntervalMs,
  nodesIntervalMs,
  pollIntervalMs,
  readTimeoutMs,
  sendCooldownMs,
  sessionPollFailureLimit,
} from "../src/lib/relay-live.mjs";
import { renderInbox } from "../src/lib/relay-view.mjs";

const relayUrl = "http://127.0.0.1:8787";
const sessionPath = "/v1/lab/sessions/s1";
const messagesPath = "/v1/lab/sessions/s1/messages";

// Lets promise continuations (fetch answers, JSON bodies) run before the test reads the view.
const settle = () => new Promise((resolve) => setImmediate(resolve));

const deferred = () => {
  let resolve;
  const promise = new Promise((res) => {
    resolve = res;
  });
  return { promise, resolve };
};

const json = (body, status = 200) => Response.json(body, { status });

// Answers after `ms` of fake time, the way a slow relay does. The response is built when the timer fires.
const delayed = (ms, respond) => new Promise((resolve) => setTimeout(() => resolve(respond()), ms));

// Advances the fake clock in small steps and lets each step's promise work finish, as a responsive relay would.
// A single large tick would fire every overlapping poll before any answer arrived.
const advance = async (t, ms, step = 500) => {
  for (let elapsed = 0; elapsed < ms; elapsed += step) {
    t.mock.timers.tick(step);
    await settle();
  }
};

// Stands in for the network boundary. Every request is recorded, and the answer comes from `network.answer`.
// Like the platform fetch, a request rejects with AbortError when its signal aborts before the answer arrives.
const createNetwork = (answer) => {
  const network = {
    requests: [],
    answer,
    fetch: async (url, init = {}) => {
      const request = { url, method: init.method ?? "GET", signal: init.signal, body: init.body };
      network.requests.push(request);
      const aborted = new Promise((_, reject) => {
        init.signal?.addEventListener("abort", () => reject(new DOMException("The operation was aborted.", "AbortError")), { once: true });
      });
      return Promise.race([aborted, network.answer(request)]);
    },
  };
  return network;
};

// The relay as a healthy, configured node: a session is created, queued, and polled as queued.
const healthyAnswer = (request) => {
  const { method, url } = request;
  if (method === "POST" && url === `${relayUrl}/v1/lab/sessions`) return json({ sessionId: "s1", state: "identity_ready", nodeAlias: "node-a" }, 201);
  if (method === "POST" && url === `${relayUrl}${messagesPath}`) return json({ sessionId: "s1", state: "queued", nodeAlias: "node-a" });
  if (method === "GET" && url === `${relayUrl}${sessionPath}`) return json({ sessionId: "s1", state: "queued", nodeAlias: "node-a" });
  if (url === `${relayUrl}/healthz`) return json({ status: "ready" });
  if (url === `${relayUrl}/v1/contact`) return json({ address: "abc123" });
  if (url === `${relayUrl}/v1/inbox`) return json({ messages: [] });
  if (url === `${relayUrl}/v1/lab/capabilities`) return json({ telegramNotifications: false });
  if (url === `${relayUrl}/v1/lab/reticulum-nodes`) return json({ status: "unavailable", nodes: [] });
  throw new TypeError(`unexpected request ${method} ${url}`);
};

const requestCount = (network, path, method = "GET") =>
  network.requests.filter((request) => request.method === method && request.url === `${relayUrl}${path}`).length;

const isMessagePost = (request) => request.method === "POST" && request.url === `${relayUrl}${messagesPath}`;
const isSessionPost = (request) => request.method === "POST" && request.url === `${relayUrl}/v1/lab/sessions`;
const isSessionPoll = (request) => request.method === "GET" && request.url === `${relayUrl}${sessionPath}`;

// Records what the page would show. Each setter keeps the latest value, so tests assert on observable state.
// `overrides` replaces individual setters, for tests that make a render fail or run the page's real renderer.
const createView = (overrides = {}) => {
  const shown = {
    available: undefined,
    address: undefined,
    inbox: undefined,
    nodes: undefined,
    telegram: undefined,
    node: undefined,
    session: undefined,
    notice: undefined,
    composer: "open",
  };
  const view = {
    setAvailability: (isOnline) => {
      shown.available = isOnline;
    },
    setAddress: (address) => {
      shown.address = address;
    },
    setInbox: (data) => {
      shown.inbox = data;
    },
    setNodes: (data) => {
      shown.nodes = data;
    },
    setTelegram: (enabled) => {
      shown.telegram = enabled;
    },
    setSessionNode: (alias) => {
      shown.node = alias;
    },
    setSessionState: (state, errorCode) => {
      shown.session = { state, errorCode };
    },
    setSessionNotice: (kind) => {
      shown.notice = kind;
    },
    setComposer: (mode) => {
      shown.composer = mode;
    },
    ...overrides,
  };
  return { view, shown };
};

// Builds a relay lab on a stubbed page, with fake timers. A page starts visible unless the test says otherwise.
const setup = (t, { visibilityState = "visible", answer = healthyAnswer, view: viewOverrides } = {}) => {
  t.mock.timers.enable({ apis: ["setInterval", "setTimeout", "Date"] });
  const documentTarget = Object.assign(new EventTarget(), { visibilityState });
  const windowTarget = new EventTarget();
  const network = createNetwork(answer);
  const { view, shown } = createView(viewOverrides);
  const relay = createRelayLive({ relayUrl, fetch: network.fetch, view, documentTarget, windowTarget });
  const page = {
    hide() {
      documentTarget.visibilityState = "hidden";
      documentTarget.dispatchEvent(new Event("visibilitychange"));
    },
    show() {
      documentTarget.visibilityState = "visible";
      documentTarget.dispatchEvent(new Event("visibilitychange"));
    },
    leave() {
      windowTarget.dispatchEvent(new Event("pagehide"));
    },
    restore(persisted) {
      windowTarget.dispatchEvent(Object.assign(new Event("pageshow"), { persisted }));
    },
  };
  return { relay, network, page, shown };
};

test("starts each refresh timer once, however often the page is shown or restored", async (t) => {
  const { network, page } = setup(t);
  await settle();
  assert.equal(requestCount(network, "/v1/inbox"), 1, "the initial status check reads the inbox once");

  page.show();
  page.restore(true);
  await settle();
  assert.equal(requestCount(network, "/v1/inbox"), 1, "a page that is already live starts no second set of reads");

  t.mock.timers.tick(inboxIntervalMs);
  await settle();
  assert.equal(requestCount(network, "/v1/inbox"), 2, "one interval adds exactly one inbox read");
});

test("hiding the page aborts the in-flight reads and stops every read timer", async (t) => {
  const { network, page } = setup(t);
  await settle();
  const held = deferred();
  network.answer = (request) => (request.url === `${relayUrl}/v1/inbox` ? held.promise : healthyAnswer(request));

  t.mock.timers.tick(inboxIntervalMs);
  const inboxRead = network.requests.at(-1);
  assert.equal(inboxRead.url, `${relayUrl}/v1/inbox`);
  assert.equal(inboxRead.signal.aborted, false);

  page.hide();
  assert.equal(inboxRead.signal.aborted, true, "the in-flight read is aborted");

  const requestsWhileHidden = network.requests.length;
  t.mock.timers.tick(nodesIntervalMs * 3);
  await settle();
  assert.equal(network.requests.length, requestsWhileHidden, "no read is issued while the page is hidden");
});

test("leaving the page with pagehide aborts the reads and stops the timers", async (t) => {
  const { network, page } = setup(t);
  await settle();
  const held = deferred();
  network.answer = (request) => (request.url === `${relayUrl}/v1/inbox` ? held.promise : healthyAnswer(request));
  t.mock.timers.tick(inboxIntervalMs);
  const inboxRead = network.requests.at(-1);

  page.leave();
  assert.equal(inboxRead.signal.aborted, true);

  const requestsWhileLeft = network.requests.length;
  t.mock.timers.tick(nodesIntervalMs * 3);
  await settle();
  assert.equal(network.requests.length, requestsWhileLeft);
});

test("resumes the reads when the page becomes visible or is restored from the back/forward cache", async (t) => {
  const { network, page } = setup(t);
  await settle();

  page.hide();
  page.show();
  await settle();
  assert.equal(requestCount(network, "/healthz"), 2, "becoming visible refreshes the status once more");

  page.leave();
  page.restore(false);
  const requestsWhileStopped = network.requests.length;
  t.mock.timers.tick(nodesIntervalMs);
  await settle();
  assert.equal(network.requests.length, requestsWhileStopped, "a normal pageshow does not restart the reads");

  page.restore(true);
  await settle();
  assert.ok(network.requests.length > requestsWhileStopped, "a persisted pageshow restarts the reads");
  assert.equal(requestCount(network, "/healthz"), 3);
});

test("a read aborted by hiding does not mark the relay offline", async (t) => {
  const { page, shown } = setup(t, {
    answer: (request) => (request.url === `${relayUrl}/healthz` ? new Promise(() => {}) : healthyAnswer(request)),
  });
  await settle();
  page.hide();
  await settle();
  assert.equal(shown.available, undefined, "the aborted status check writes nothing");
});

test("an inbox body that arrives after hiding is not rendered", async (t) => {
  const { network, page, shown } = setup(t);
  await settle();
  const lateBody = deferred();
  network.answer = (request) => (request.url === `${relayUrl}/v1/inbox` ? { ok: true, json: () => lateBody.promise } : healthyAnswer(request));

  t.mock.timers.tick(inboxIntervalMs);
  page.hide();
  lateBody.resolve({ messages: [{ content: "late", receivedAt: "2026-11-06T00:00:00.000Z" }] });
  await settle();
  assert.deepEqual(shown.inbox, { messages: [] }, "the aborted read writes nothing");
});

test("reads the relay status, address, and inbox into the view", async (t) => {
  const { shown } = setup(t);
  await settle();
  assert.equal(shown.available, true);
  assert.equal(shown.address, "abc123");
  assert.deepEqual(shown.inbox, { messages: [] });
  assert.equal(shown.telegram, false);
});

test("reports the relay offline when its health check fails", async (t) => {
  const { shown } = setup(t, {
    answer: (request) => (request.url === `${relayUrl}/healthz` ? json({}, 503) : healthyAnswer(request)),
  });
  await settle();
  assert.equal(shown.available, false);
});

test("a relay whose optional capabilities read fails stays online, and telegram stays off", async (t) => {
  const { shown } = setup(t, {
    answer: (request) => {
      if (request.url === `${relayUrl}/v1/lab/capabilities`) throw new TypeError("fetch failed");
      return healthyAnswer(request);
    },
  });
  await settle();
  assert.equal(shown.available, true, "an optional read that fails does not mark the relay offline");
  assert.equal(shown.telegram, false);
  assert.deepEqual(shown.inbox, { messages: [] }, "the required reads still render");
});

test("a relay whose optional node read returns an unreadable body stays online with no nodes", async (t) => {
  const { shown } = setup(t, {
    answer: (request) => (request.url === `${relayUrl}/v1/lab/reticulum-nodes` ? new Response("<html>gateway</html>", { status: 200 }) : healthyAnswer(request)),
  });
  await settle();
  assert.equal(shown.available, true, "an unreadable optional body does not mark the relay offline");
  assert.deepEqual(shown.nodes, {}, "the node line falls back to unavailable");
});

test("a failed required inbox read marks the relay offline", async (t) => {
  const { shown } = setup(t, {
    answer: (request) => (request.url === `${relayUrl}/v1/inbox` ? json({}, 502) : healthyAnswer(request)),
  });
  await settle();
  assert.equal(shown.available, false);
});

test("an aborted session poll does not mark the session failed", async (t) => {
  const { network, page, shown, relay } = setup(t);
  await settle();
  await relay.send(() => "hello");
  network.answer = (request) => (isSessionPoll(request) ? new Promise(() => {}) : healthyAnswer(request));

  t.mock.timers.tick(pollIntervalMs);
  page.hide();
  await settle();
  assert.equal(shown.session.state, "queued", "hiding the page is not a relay failure");
});

test("a late session answer after hiding writes nothing and leaves the next run's poll timer armed", async (t) => {
  const { network, page, shown, relay } = setup(t);
  await settle();
  await relay.send(() => "hello");
  assert.equal(shown.session.state, "queued");

  const lateBody = deferred();
  network.answer = (request) => (isSessionPoll(request) ? { ok: true, json: () => lateBody.promise } : healthyAnswer(request));
  t.mock.timers.tick(pollIntervalMs);
  page.hide();
  page.show();
  await settle();

  lateBody.resolve({ sessionId: "s1", state: "delivered", nodeAlias: "late-node" });
  await settle();
  assert.deepEqual(shown.session, { state: "queued", errorCode: "" }, "the aborted answer does not write its delivered state");
  assert.equal(shown.node, "node-a", "the aborted answer does not write its node");

  network.answer = healthyAnswer;
  const pollsBefore = requestCount(network, sessionPath);
  t.mock.timers.tick(pollIntervalMs);
  await settle();
  assert.equal(requestCount(network, sessionPath), pollsBefore + 1, "the next run's poll timer is still armed");
});

test("a queued session is polled only while the page is live, and resumes when it becomes visible", async (t) => {
  const { network, page, shown, relay } = setup(t, { visibilityState: "hidden" });
  await settle();
  assert.equal(requestCount(network, "/healthz"), 0, "a hidden page does not start the relay reads");

  await relay.send(() => "hello");
  assert.equal(shown.session.state, "queued", "the send completes while the page is hidden");
  assert.equal(shown.composer, "sent");

  t.mock.timers.tick(pollIntervalMs * 3);
  await settle();
  assert.equal(requestCount(network, sessionPath), 0, "no session poll runs while the page is hidden");

  page.show();
  await settle();
  t.mock.timers.tick(pollIntervalMs);
  await settle();
  assert.equal(requestCount(network, sessionPath), 1, "becoming visible resumes the poll for the queued session");
});

test("a session poll that fails while visible marks the session failed and stops polling", async (t) => {
  const { network, shown, relay } = setup(t);
  await settle();
  await relay.send(() => "hello");
  network.answer = (request) => (isSessionPoll(request) ? json({}, 503) : healthyAnswer(request));

  t.mock.timers.tick(pollIntervalMs);
  await settle();
  assert.deepEqual(shown.session, { state: "failed", errorCode: "outbound_error" });

  const polls = requestCount(network, sessionPath);
  t.mock.timers.tick(pollIntervalMs * 5);
  await settle();
  assert.equal(requestCount(network, sessionPath), polls, "polling stops after the failure");
});

test("a failed session is polled for 15 seconds and then left alone", async (t) => {
  const { network, shown, relay } = setup(t);
  await settle();
  await relay.send(() => "hello");
  network.answer = (request) => (isSessionPoll(request) ? json({ sessionId: "s1", state: "failed", errorCode: "delivery_failed" }) : healthyAnswer(request));

  await advance(t, failedGiveUpMs + pollIntervalMs * 2);
  assert.deepEqual(shown.session, { state: "failed", errorCode: "delivery_failed" });

  const polls = requestCount(network, sessionPath);
  await advance(t, 60_000);
  assert.equal(requestCount(network, sessionPath), polls, "polling stops once the failure has lasted 15 seconds");
});

test("a delivered session stops polling and refreshes the inbox", async (t) => {
  const { network, shown, relay } = setup(t);
  await settle();
  await relay.send(() => "hello");
  network.answer = (request) => (isSessionPoll(request) ? json({ sessionId: "s1", state: "delivered", nodeAlias: "node-a" }) : healthyAnswer(request));
  const inboxBefore = requestCount(network, "/v1/inbox");

  t.mock.timers.tick(pollIntervalMs);
  await settle();
  assert.deepEqual(shown.session, { state: "delivered", errorCode: "" });
  assert.equal(requestCount(network, "/v1/inbox"), inboxBefore + 1, "delivery refreshes the inbox once");

  const polls = requestCount(network, sessionPath);
  t.mock.timers.tick(pollIntervalMs * 5);
  await settle();
  assert.equal(requestCount(network, sessionPath), polls, "polling stops after delivery");
});

test("hiding the page does not abort a send, and its answer is applied", async (t) => {
  const { network, page, shown, relay } = setup(t);
  await settle();
  const answer = deferred();
  network.answer = (request) => (isMessagePost(request) ? answer.promise : healthyAnswer(request));

  const sending = relay.send(() => "hello");
  await settle();
  page.hide();
  const post = network.requests.find(isMessagePost);
  assert.notEqual(post.signal?.aborted, true, "the send is not aborted");

  answer.resolve(json({ sessionId: "s1", state: "delivered", nodeAlias: "node-a" }));
  await sending;
  assert.deepEqual(shown.session, { state: "delivered", errorCode: "" });
  assert.equal(shown.composer, "sent", "the composer locks after the relay accepts the message");
});

test("a network error on send shows the unconfirmed state, and sending stays locked until the cooldown ends", async (t) => {
  const { network, shown, relay } = setup(t);
  await settle();
  network.answer = (request) => {
    if (isMessagePost(request)) throw new TypeError("fetch failed");
    return healthyAnswer(request);
  };

  await relay.send(() => "hello");
  assert.deepEqual(shown.session, { state: "unconfirmed", errorCode: "" });
  assert.equal(shown.composer, "cooldown", "the submit button stays disabled after the failure");

  const postsBefore = requestCount(network, messagesPath, "POST");
  await relay.send(() => "again");
  assert.equal(requestCount(network, messagesPath, "POST"), postsBefore, "a send during the cooldown makes no request");

  t.mock.timers.tick(sendCooldownMs - 1);
  assert.equal(shown.composer, "cooldown", "sending stays locked until the cooldown has fully elapsed");

  t.mock.timers.tick(1);
  assert.equal(shown.composer, "open", "sending is available again once the cooldown ends");
  assert.deepEqual(shown.session, { state: "unconfirmed", errorCode: "" }, "the unconfirmed state stays until the relay answers again");

  network.answer = healthyAnswer;
  await relay.send(() => "again");
  assert.deepEqual(shown.session, { state: "queued", errorCode: "" });
});

test("a network error creating the session shows a failed state, never an unconfirmed one, and sends no message", async (t) => {
  const { network, shown, relay } = setup(t);
  await settle();
  network.answer = (request) => {
    if (isSessionPost(request)) throw new TypeError("fetch failed");
    return healthyAnswer(request);
  };

  await relay.send(() => "hello");
  assert.deepEqual(shown.session, { state: "failed", errorCode: "" }, "no message was sent, so the delivery failed rather than being unconfirmed");
  assert.equal(shown.composer, "cooldown");
  assert.equal(requestCount(network, messagesPath, "POST"), 0, "no message is sent without a session");

  t.mock.timers.tick(sendCooldownMs);
  network.answer = healthyAnswer;
  await relay.send(() => "again");
  assert.deepEqual(shown.session, { state: "queued", errorCode: "" }, "the next send asks the relay for a session again");
});

test("an HTTP error on send keeps the failed state and starts the cooldown before a retry", async (t) => {
  const { network, shown, relay } = setup(t);
  await settle();
  network.answer = (request) => (isMessagePost(request) ? json({ detail: "delivery_failed" }, 502) : healthyAnswer(request));

  await relay.send(() => "hello");
  assert.deepEqual(shown.session, { state: "failed", errorCode: "delivery_failed" });
  assert.equal(shown.composer, "cooldown", "an edge error starts the cooldown, so a retry cannot hammer the edge");

  const postsBefore = requestCount(network, messagesPath, "POST");
  await relay.send(() => "again");
  assert.equal(requestCount(network, messagesPath, "POST"), postsBefore, "a submit during the cooldown makes no request");

  t.mock.timers.tick(sendCooldownMs);
  assert.equal(shown.composer, "open", "sending reopens once the cooldown ends");

  network.answer = (request) => (isMessagePost(request) ? new Response("upstream down", { status: 500 }) : healthyAnswer(request));
  await relay.send(() => "again");
  assert.deepEqual(shown.session, { state: "failed", errorCode: "outbound_error" }, "an error body without a detail falls back to outbound_error");
});

// A relay that refuses session creation with `status` shows the unavailable notice and starts the same cooldown as a refused message.
const refusesSession = async (t, status) => {
  const { network, shown, relay } = setup(t);
  await settle();
  network.answer = (request) => (isSessionPost(request) ? json({ detail: "refused" }, status) : healthyAnswer(request));

  await relay.send(() => "hello");
  assert.equal(shown.notice, "unavailable");
  assert.equal(shown.session, undefined, "the route state is not touched");
  assert.equal(shown.composer, "cooldown", "the refusal locks sending for the cooldown");
  assert.equal(requestCount(network, messagesPath, "POST"), 0);

  await relay.send(() => "again");
  assert.equal(requestCount(network, "/v1/lab/sessions", "POST"), 1, "a submit during the cooldown does not ask the relay for a session again");

  t.mock.timers.tick(sendCooldownMs);
  assert.equal(shown.composer, "open", "sending reopens after the cooldown");
};

test("a session the relay refuses with 503 shows the unavailable notice and starts the cooldown", (t) => refusesSession(t, 503));

test("a session the relay rate-limits with 429 starts the cooldown instead of being requested again at once", (t) => refusesSession(t, 429));

test("a poll answer that arrives after a newer poll cannot move the session back to queued", async (t) => {
  const { network, shown, relay } = setup(t);
  await settle();
  await relay.send(() => "hello");
  const slowPoll = deferred();
  let polls = 0;
  network.answer = (request) => {
    if (!isSessionPoll(request)) return healthyAnswer(request);
    polls += 1;
    return polls === 1 ? slowPoll.promise : json({ sessionId: "s1", state: "delivered", nodeAlias: "node-a" });
  };

  t.mock.timers.tick(pollIntervalMs);
  t.mock.timers.tick(pollIntervalMs);
  await settle();
  assert.deepEqual(shown.session, { state: "delivered", errorCode: "" });

  slowPoll.resolve(json({ sessionId: "s1", state: "queued", nodeAlias: "node-a" }));
  await settle();
  assert.deepEqual(shown.session, { state: "delivered", errorCode: "" }, "the older answer does not overwrite the newer delivered state");
});

test("a poll answer slower than the poll interval still lands when no newer answer has landed", async (t) => {
  const { network, shown, relay } = setup(t);
  await settle();
  await relay.send(() => "hello");
  network.answer = (request) =>
    isSessionPoll(request)
      ? delayed(pollIntervalMs * 2 + 500, () => json({ sessionId: "s1", state: "delivered", nodeAlias: "node-a" }))
      : healthyAnswer(request);

  await advance(t, pollIntervalMs * 4);
  assert.deepEqual(shown.session, { state: "delivered", errorCode: "" }, "each poll answers after the next tick has started, and the delivery is still shown");
});

test("a slow session poll failure that is newer than every applied answer still marks the session failed", async (t) => {
  const { network, shown, relay } = setup(t);
  await settle();
  await relay.send(() => "hello");
  network.answer = (request) =>
    isSessionPoll(request) ? delayed(pollIntervalMs * 2 + 500, () => json({}, 503)) : healthyAnswer(request);

  await advance(t, pollIntervalMs * 4);
  assert.deepEqual(shown.session, { state: "failed", errorCode: "outbound_error" });
});

test("a poll that fails after a newer answer does not mark the session failed", async (t) => {
  const { network, shown, relay } = setup(t);
  await settle();
  await relay.send(() => "hello");
  const slowPoll = deferred();
  let polls = 0;
  network.answer = (request) => {
    if (!isSessionPoll(request)) return healthyAnswer(request);
    polls += 1;
    return polls === 1 ? slowPoll.promise : json({}, 503);
  };

  t.mock.timers.tick(pollIntervalMs);
  t.mock.timers.tick(pollIntervalMs);
  await settle();
  assert.deepEqual(shown.session, { state: "failed", errorCode: "outbound_error" });

  slowPoll.resolve(json({ sessionId: "s1", state: "queued", nodeAlias: "node-a" }));
  await settle();
  assert.deepEqual(shown.session, { state: "failed", errorCode: "outbound_error" }, "the older answer does not undo the newer failure");
});

test("a second submit while a message is in flight sends no second message", async (t) => {
  const { network, shown, relay } = setup(t);
  await settle();
  const answer = deferred();
  network.answer = (request) => (isMessagePost(request) ? answer.promise : healthyAnswer(request));

  const first = relay.send(() => "hello");
  await settle();
  const second = relay.send(() => "hello again");
  await settle();
  assert.equal(requestCount(network, messagesPath, "POST"), 1, "the second submit makes no request while the first is in flight");

  answer.resolve(json({ sessionId: "s1", state: "queued", nodeAlias: "node-a" }));
  await Promise.all([first, second]);
  assert.deepEqual(shown.session, { state: "queued", errorCode: "" });
  assert.equal(requestCount(network, messagesPath, "POST"), 1);
});

test("a second submit while the session is being created does not start another session", async (t) => {
  const { network, shown, relay } = setup(t);
  await settle();
  const session = deferred();
  network.answer = (request) => (isSessionPost(request) ? session.promise : healthyAnswer(request));

  const first = relay.send(() => "hello");
  await settle();
  const second = relay.send(() => "hello again");
  await settle();
  assert.equal(requestCount(network, "/v1/lab/sessions", "POST"), 1, "only one session is created while the first is pending");

  session.resolve(json({ sessionId: "s1", state: "identity_ready", nodeAlias: "node-a" }, 201));
  await Promise.all([first, second]);
  assert.equal(requestCount(network, messagesPath, "POST"), 1, "the first submit sends its one message");
  assert.deepEqual(shown.session, { state: "queued", errorCode: "" });
});

test("a message answered with an unreadable 200 body is unconfirmed, starts the cooldown, and does not reject", async (t) => {
  const { network, shown, relay } = setup(t);
  await settle();
  network.answer = (request) => (isMessagePost(request) ? new Response("<html>gateway</html>", { status: 200 }) : healthyAnswer(request));

  await relay.send(() => "hello");
  assert.deepEqual(shown.session, { state: "unconfirmed", errorCode: "" }, "the relay may have accepted the message");
  assert.equal(shown.composer, "cooldown");

  t.mock.timers.tick(sendCooldownMs);
  assert.equal(shown.composer, "open", "sending is available again once the cooldown ends");
});

test("a 429 on a session poll is transient: the session is not failed and polling continues", async (t) => {
  const { network, shown, relay } = setup(t);
  await settle();
  await relay.send(() => "hello");
  let polls = 0;
  network.answer = (request) => {
    if (!isSessionPoll(request)) return healthyAnswer(request);
    polls += 1;
    return polls === 1 ? json({ detail: "rate limited" }, 429) : json({ sessionId: "s1", state: "delivered", nodeAlias: "node-a" });
  };

  t.mock.timers.tick(pollIntervalMs);
  await settle();
  assert.deepEqual(shown.session, { state: "queued", errorCode: "" }, "a rate-limited poll keeps the last shown state");

  t.mock.timers.tick(pollIntervalMs);
  await settle();
  assert.deepEqual(shown.session, { state: "delivered", errorCode: "" }, "polling continues after the 429");
});

test("a 429 on a message shows the unavailable notice with the cooldown, not a failure", async (t) => {
  const { network, shown, relay } = setup(t);
  await settle();
  network.answer = (request) => (isMessagePost(request) ? json({ detail: "rate limited" }, 429) : healthyAnswer(request));

  await relay.send(() => "hello");
  assert.equal(shown.notice, "unavailable");
  assert.deepEqual(shown.session, { state: "identity_ready", errorCode: "" }, "the session keeps its last state instead of failing");
  assert.equal(shown.composer, "cooldown");

  t.mock.timers.tick(sendCooldownMs);
  assert.equal(shown.composer, "open", "sending reopens after the cooldown");

  network.answer = healthyAnswer;
  await relay.send(() => "again");
  assert.deepEqual(shown.session, { state: "queued", errorCode: "" });
});

test("the lab page delegates its relay and rendering rules to the tested helpers", async () => {
  // Behavior is covered through the helpers themselves; this single check confirms the page wires them in.
  const source = await readFile(new URL("../src/components/SignalRelayLab.astro", import.meta.url), "utf8");
  assert.match(source, /import \{ createRelayLive \} from "\.\.\/lib\/relay-live\.mjs";/);
  assert.match(source, /from "\.\.\/lib\/relay-view\.mjs";/);
});

test("a session poll with no answer within the read timeout is abandoned as transient, and polling continues", async (t) => {
  const { network, shown, relay } = setup(t);
  await settle();
  await relay.send(() => "hello");
  let stall = true;
  network.answer = (request) => {
    if (!isSessionPoll(request)) return healthyAnswer(request);
    return stall ? new Promise(() => {}) : json({ sessionId: "s1", state: "delivered", nodeAlias: "node-a" });
  };

  await advance(t, pollIntervalMs);
  const stalled = network.requests.find(isSessionPoll);
  await advance(t, readTimeoutMs);
  assert.equal(stalled.signal.aborted, true, "the stalled poll is abandoned at the read timeout");
  assert.deepEqual(shown.session, { state: "queued", errorCode: "" }, "a timed-out poll is transient: it keeps the last shown state and is not a failure");

  stall = false;
  await advance(t, pollIntervalMs * 3);
  assert.deepEqual(shown.session, { state: "delivered", errorCode: "" }, "polling continues after the timeout");
});

test("stalled session polls never stack: at most two are pending at once", async (t) => {
  const { network, relay } = setup(t);
  await settle();
  await relay.send(() => "hello");
  network.answer = (request) => (isSessionPoll(request) ? new Promise(() => {}) : healthyAnswer(request));

  for (let elapsed = 0; elapsed < readTimeoutMs * 3; elapsed += 500) {
    t.mock.timers.tick(500);
    await settle();
    const pending = network.requests.filter((request) => isSessionPoll(request) && !request.signal.aborted).length;
    assert.ok(pending <= 2, `at most two session polls are pending, got ${pending} after ${elapsed + 500} ms`);
  }
  assert.ok(network.requests.filter(isSessionPoll).length > 2, "polling still runs while the relay stalls");
});

test("a status read with no answer within the read timeout marks the relay offline", async (t) => {
  const { shown } = setup(t, {
    answer: (request) => (request.url === `${relayUrl}/healthz` ? new Promise(() => {}) : healthyAnswer(request)),
  });
  await settle();
  await advance(t, readTimeoutMs - 500);
  assert.equal(shown.available, undefined, "the status check is still waiting before the timeout");

  await advance(t, 1000);
  assert.equal(shown.available, false, "a status check that never answers counts as offline once the timeout passes");
});

test("a message POST is never aborted by the read timeout", async (t) => {
  const { network, shown, relay } = setup(t);
  await settle();
  const answer = deferred();
  network.answer = (request) => (isMessagePost(request) ? answer.promise : healthyAnswer(request));

  const sending = relay.send(() => "hello");
  await settle();
  await advance(t, readTimeoutMs * 2);
  const post = network.requests.find(isMessagePost);
  assert.notEqual(post.signal?.aborted, true, "the message is not aborted, however long the relay takes to answer");
  assert.deepEqual(shown.session, { state: "identity_ready", errorCode: "" }, "the read timeout writes no state for a message");

  answer.resolve(json({ sessionId: "s1", state: "queued", nodeAlias: "node-a" }));
  await sending;
  assert.deepEqual(shown.session, { state: "queued", errorCode: "" });
});

test("a message to a session the relay no longer knows fails, and the next send creates a fresh session", async (t) => {
  const { network, shown, relay } = setup(t);
  await settle();
  let created = 0;
  network.answer = (request) => {
    if (isSessionPost(request)) {
      created += 1;
      return json({ sessionId: `s${created}`, state: "identity_ready", nodeAlias: "node-a" }, 201);
    }
    if (isMessagePost(request)) return json({ detail: "session_not_found" }, 404);
    if (request.method === "POST" && request.url === `${relayUrl}/v1/lab/sessions/s2/messages`) {
      return json({ sessionId: "s2", state: "queued", nodeAlias: "node-a" });
    }
    return healthyAnswer(request);
  };

  await relay.send(() => "hello");
  assert.deepEqual(shown.session, { state: "failed", errorCode: "session_not_found" }, "the expired session is reported as a failure");
  assert.equal(shown.composer, "cooldown", "an expired session starts the cooldown like any refused message");

  t.mock.timers.tick(sendCooldownMs);
  assert.equal(shown.composer, "open", "an expired session reopens sending once the cooldown ends");

  await relay.send(() => "again");
  assert.equal(created, 2, "the next send creates a fresh session instead of reusing the expired one");
  assert.equal(requestCount(network, "/v1/lab/sessions/s2/messages", "POST"), 1, "the message goes to the fresh session");
  assert.deepEqual(shown.session, { state: "queued", errorCode: "" });
});

test("a session poll answered 404 is a failure that says the session is gone, and polling stops", async (t) => {
  const { network, shown, relay } = setup(t);
  await settle();
  await relay.send(() => "hello");
  network.answer = (request) => (isSessionPoll(request) ? json({ detail: "session_not_found" }, 404) : healthyAnswer(request));

  t.mock.timers.tick(pollIntervalMs);
  await settle();
  assert.deepEqual(shown.session, { state: "failed", errorCode: "session_not_found" });

  const polls = requestCount(network, sessionPath);
  t.mock.timers.tick(pollIntervalMs * 5);
  await settle();
  assert.equal(requestCount(network, sessionPath), polls, "polling stops once the relay has forgotten the session");
});

// Each session poll takes the next outcome from `outcomes`: "network" rejects like a dropped connection, "timeout" never answers,
// "429" is a rate limit, and any other word is the session state the relay reports. Polls past the script report "queued".
const scriptedPolls = (network, outcomes) => {
  network.answer = (request) => {
    if (!isSessionPoll(request)) return healthyAnswer(request);
    const outcome = outcomes.shift() ?? "queued";
    if (outcome === "network") throw new TypeError("fetch failed");
    if (outcome === "timeout") return new Promise(() => {});
    if (outcome === "429") return json({ detail: "rate limited" }, 429);
    return json({ sessionId: "s1", state: outcome, nodeAlias: "node-a" });
  };
};

const networkErrors = (count) => Array.from({ length: count }, () => "network");

test("a single network error on a session poll keeps the last shown state, and the next poll applies its answer", async (t) => {
  const { network, shown, relay } = setup(t);
  await settle();
  await relay.send(() => "hello");
  scriptedPolls(network, ["network", "delivered"]);

  t.mock.timers.tick(pollIntervalMs);
  await settle();
  assert.deepEqual(shown.session, { state: "queued", errorCode: "" }, "one dropped poll does not fail the session");

  t.mock.timers.tick(pollIntervalMs);
  await settle();
  assert.deepEqual(shown.session, { state: "delivered", errorCode: "" }, "polling continues after the dropped poll");
});

test("a run of failed session polls gives up at the limit: the session is failed, polling stops, and the composer stays as the relay left it", async (t) => {
  const { network, shown, relay } = setup(t);
  await settle();
  await relay.send(() => "hello");
  scriptedPolls(network, networkErrors(sessionPollFailureLimit));

  for (let tick = 1; tick < sessionPollFailureLimit; tick += 1) {
    t.mock.timers.tick(pollIntervalMs);
    await settle();
  }
  assert.deepEqual(shown.session, { state: "queued", errorCode: "" }, "one tick short of the limit the session is still shown as queued");

  t.mock.timers.tick(pollIntervalMs);
  await settle();
  assert.deepEqual(shown.session, { state: "failed", errorCode: "outbound_error" }, "the limit of consecutive failed polls marks the session failed");
  assert.equal(shown.composer, "sent", "the relay accepted the message, so the composer stays locked and a retry cannot duplicate it");

  const polls = requestCount(network, sessionPath);
  t.mock.timers.tick(pollIntervalMs * 5);
  await settle();
  assert.equal(requestCount(network, sessionPath), polls, "polling stops after the give-up");
});

// Runs `ticks` poll ticks, letting each tick's promise work finish before the next.
const tickPolls = async (t, ticks) => {
  for (let tick = 0; tick < ticks; tick += 1) {
    t.mock.timers.tick(pollIntervalMs);
    await settle();
  }
};

test("an answer from the relay resets the run of failed session polls", async (t) => {
  const { network, shown, relay } = setup(t);
  await settle();
  await relay.send(() => "hello");
  scriptedPolls(network, [...networkErrors(sessionPollFailureLimit - 1), "queued", ...networkErrors(sessionPollFailureLimit)]);

  await tickPolls(t, 2 * sessionPollFailureLimit - 1);
  assert.deepEqual(shown.session, { state: "queued", errorCode: "" }, "a run of fewer than the limit before and after an answer does not fail the session");

  await tickPolls(t, 1);
  assert.deepEqual(shown.session, { state: "failed", errorCode: "outbound_error" }, "a full run of the limit after the answer does fail the session");
});

test("a rate-limited session poll is an answer, so it resets the run of failed polls", async (t) => {
  const { network, shown, relay } = setup(t);
  await settle();
  await relay.send(() => "hello");
  scriptedPolls(network, [...networkErrors(sessionPollFailureLimit - 1), "429", ...networkErrors(sessionPollFailureLimit)]);

  await tickPolls(t, 2 * sessionPollFailureLimit - 1);
  assert.deepEqual(shown.session, { state: "queued", errorCode: "" }, "the rate limit proves the relay is reachable, so the run starts again");

  await tickPolls(t, 1);
  assert.deepEqual(shown.session, { state: "failed", errorCode: "outbound_error" }, "a full run after the rate limit does fail the session");
});

test("a session poll that never answers is transient once, then gives up after a run of timeouts", async (t) => {
  const { network, shown, relay } = setup(t);
  await settle();
  await relay.send(() => "hello");
  network.answer = (request) => (isSessionPoll(request) ? new Promise(() => {}) : healthyAnswer(request));

  await advance(t, pollIntervalMs + readTimeoutMs);
  assert.deepEqual(shown.session, { state: "queued", errorCode: "" }, "a single timed-out poll keeps the last shown state");

  await advance(t, readTimeoutMs * sessionPollFailureLimit);
  assert.deepEqual(shown.session, { state: "failed", errorCode: "outbound_error" }, "a relay that stays silent for a run of polls is given up on");
});

test("a malformed inbox entry in a ready relay's answer renders without marking the relay offline", async (t) => {
  const doc = { createElement: (tagName) => ({ tagName, children: [], textContent: "", dataset: {}, replaceChildren(...nodes) { this.children = nodes; } }) };
  const list = doc.createElement("ul");
  const { shown } = setup(t, {
    answer: (request) => (request.url === `${relayUrl}/v1/inbox` ? json({ messages: [null] }) : healthyAnswer(request)),
    view: { setInbox: (data) => renderInbox(doc, list, data, { inboxEmptyLabel: "No messages." }) },
  });
  await settle();
  assert.equal(shown.available, true, "health is ready, so a payload the page cannot draw must not mark the relay offline");
  assert.equal(list.children[0].textContent, "No messages.", "the inbox shows its empty line");
});

test("a render failure does not mark a ready relay offline, and the other panels still render", async (t) => {
  const { shown } = setup(t, {
    view: {
      setInbox: () => {
        throw new TypeError("render failed");
      },
    },
  });
  await settle();
  assert.equal(shown.available, true, "a render failure is not a failed read, so the relay stays online");
  assert.equal(shown.address, "abc123", "the address still renders after the inbox render failed");
  assert.deepEqual(shown.nodes, { status: "unavailable", nodes: [] }, "the node list still renders after the inbox render failed");
});
