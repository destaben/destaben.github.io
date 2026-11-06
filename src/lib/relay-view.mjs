// Rendering rules for the Signal Relay laboratory. The page supplies its elements, a document for creating
// nodes, and its label dataset; the Node test suite drives these with a minimal document stand-in.
// Relay content only ever reaches the page as text (textContent), never as markup.

const maxInboxMessages = 5;
const sessionLabelKeys = { queued: "queuedLabel", delivered: "deliveredLabel", failed: "failedLabel", unconfirmed: "unconfirmedLabel" };

// A relay answer with an empty message list clears earlier messages; a payload without a message list leaves the list as it was.
// Entries that are not objects (such as null) cannot be shown, so they are skipped rather than failing the whole list.
export function renderInbox(doc, list, data, labels = {}) {
  if (!list || !Array.isArray(data?.messages)) return;
  const messages = data.messages.filter((message) => message !== null && typeof message === "object");
  if (!messages.length) {
    const empty = doc.createElement("li");
    empty.textContent = labels.inboxEmptyLabel || "No messages have been recorded yet.";
    list.replaceChildren(empty);
    return;
  }
  list.replaceChildren(...messages.slice(0, maxInboxMessages).map((message) => {
    const item = doc.createElement("li");
    const body = doc.createElement("span");
    body.textContent = message.content || "(empty message)";
    const timestamp = doc.createElement("time");
    timestamp.dateTime = message.receivedAt;
    timestamp.textContent = new Date(message.receivedAt).toLocaleString();
    item.replaceChildren(body, timestamp);
    return item;
  }));
}

export function renderNodes(doc, list, data, labels) {
  if (!list) return;
  const publicNodes = data?.status === "available" && Array.isArray(data.nodes)
    ? data.nodes.filter((node) => node?.alias && node.url)
    : [];
  if (!publicNodes.length) {
    const unavailable = doc.createElement("li");
    unavailable.className = "relay-nodes-unavailable";
    unavailable.textContent = labels.nodeUnavailableLabel || "Node status is unavailable.";
    list.replaceChildren(unavailable);
    return;
  }
  list.replaceChildren(...publicNodes.map((node) => {
    const item = doc.createElement("li");
    item.className = "relay-node-card";
    const heading = doc.createElement("div");
    const alias = doc.createElement("strong");
    alias.textContent = node.alias || "";
    const status = doc.createElement("span");
    const isUp = node.status === "up";
    status.dataset.state = isUp ? "up" : "down";
    status.textContent = isUp ? labels.nodeUpLabel || "Online" : labels.nodeDownLabel || "Offline";
    const url = doc.createElement("code");
    url.textContent = node.url || "";
    heading.replaceChildren(alias, status);
    item.replaceChildren(heading, url);
    return item;
  }));
}

// Maps a relay session state to the four route steps. `unconfirmed` is a browser-only state: the delivery steps show
// "unknown" rather than "failed", because the relay may already have accepted the message.
export function routeSteps(state, errorCode, labels) {
  const waiting = { state: "waiting", label: labels.routeWaitingLabel || "Waiting" };
  const failedLabel = (errorCode === "outbound_error"
    ? labels.routeOutboundFailedLabel
    : errorCode === "delivery_failed"
      ? labels.routeDeliveryFailedLabel
      : labels.routeUnknownFailedLabel) || "Delivery failed";
  const deliveryStep = (completeLabel) => {
    if (state === "delivered") return { state: "complete", label: completeLabel };
    if (state === "failed") return { state: "failed", label: failedLabel };
    if (state === "unconfirmed") return { state: "unknown", label: labels.routeUnconfirmedLabel || "Confirmation unknown" };
    if (state === "queued") return { state: "active", label: labels.routeRoutingLabel || "Routing" };
    return waiting;
  };
  const sourceReady = ["identity_ready", "queued", "delivered", "failed"].includes(state);
  const encrypted = state === "queued" || state === "delivered";
  return [
    { state: sourceReady ? "complete" : "waiting", label: labels.routeSourceReadyLabel || "Ready" },
    deliveryStep(labels.routeReceivedLabel || "Received"),
    encrypted ? { state: "complete", label: labels.routeEncryptedLabel || "Encrypted" } : waiting,
    deliveryStep(labels.routeConfirmedLabel || "Confirmed"),
  ];
}

export function sessionStatusText(state, labels) {
  return (Object.hasOwn(sessionLabelKeys, state) && labels[sessionLabelKeys[state]]) || state;
}

export function composerControls(mode) {
  return { inputDisabled: mode === "sent", submitDisabled: mode !== "open" };
}

export function renderAddress({ address, destination, copyButton }, value) {
  if (!address) return;
  address.textContent = value;
  if (destination) destination.textContent = value;
  if (copyButton) copyButton.disabled = false;
}
