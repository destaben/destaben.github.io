import assert from "node:assert/strict";
import test from "node:test";
import { composerControls, renderAddress, renderInbox, renderNodes, routeSteps, sessionStatusText } from "../src/lib/relay-view.mjs";

// A minimal document stand-in. Elements keep their children and text as plain values, and innerHTML throws,
// so any markup from the relay can only reach the page as text.
const createDocument = () => ({
  createElement(tagName) {
    const element = {
      tagName: tagName.toUpperCase(),
      children: [],
      className: "",
      dataset: {},
      textContent: "",
      dateTime: "",
      replaceChildren(...nodes) {
        this.children = nodes;
      },
    };
    Object.defineProperty(element, "innerHTML", {
      set() {
        throw new Error("relay content must be written as text, never as innerHTML");
      },
    });
    return element;
  },
});

const messageAt = (content, receivedAt = "2026-11-06T10:00:00.000Z") => ({ content, receivedAt });

test("writes each inbox message as plain text and never builds elements from it", () => {
  const doc = createDocument();
  const list = doc.createElement("ul");
  const hostile = '<img src="x" onerror="alert(1)"><b>bold</b>';

  renderInbox(doc, list, { messages: [messageAt(hostile)] });

  assert.equal(list.children.length, 1);
  const [body, timestamp] = list.children[0].children;
  assert.equal(body.textContent, hostile, "the message text is kept exactly as received");
  assert.deepEqual(body.children, [], "no element is created from the message");
  assert.equal(timestamp.dateTime, "2026-11-06T10:00:00.000Z");
  assert.notEqual(timestamp.textContent, "", "the timestamp has visible text");
});

test("shows a placeholder for an inbox message without content", () => {
  const doc = createDocument();
  const list = doc.createElement("ul");

  renderInbox(doc, list, { messages: [messageAt(""), { receivedAt: "2026-11-06T10:00:00.000Z" }] });

  assert.deepEqual(list.children.map((item) => item.children[0].textContent), ["(empty message)", "(empty message)"]);
});

test("shows at most the five most recent inbox messages, in the order the relay sent them", () => {
  const doc = createDocument();
  const list = doc.createElement("ul");
  const messages = Array.from({ length: 7 }, (_, index) => messageAt(`message ${index + 1}`));

  renderInbox(doc, list, { messages });

  assert.deepEqual(list.children.map((item) => item.children[0].textContent), ["message 1", "message 2", "message 3", "message 4", "message 5"]);
});

const inboxLabels = { inboxEmptyLabel: "No messages have been recorded yet." };

test("an empty inbox clears earlier messages and shows the empty line", () => {
  const doc = createDocument();
  const list = doc.createElement("ul");
  renderInbox(doc, list, { messages: [messageAt("stale")] });

  renderInbox(doc, list, { messages: [] }, inboxLabels);

  assert.equal(list.children.length, 1, "only the empty line remains");
  assert.equal(list.children[0].textContent, "No messages have been recorded yet.");
  assert.deepEqual(list.children[0].children, [], "the stale message is gone");
});

test("a payload without a usable message list leaves the list as it was", () => {
  const doc = createDocument();
  const placeholder = doc.createElement("li");
  const list = doc.createElement("ul");
  list.replaceChildren(placeholder);

  for (const data of [{}, { messages: "not a list" }, undefined]) {
    renderInbox(doc, list, data, inboxLabels);
    assert.deepEqual(list.children, [placeholder], `${JSON.stringify(data)} does not replace the list`);
  }
  assert.doesNotThrow(() => renderInbox(doc, null, { messages: [messageAt("x")] }), "a page without an inbox list is a no-op");
});

const nodeLabels = {
  nodeUpLabel: "Online",
  nodeDownLabel: "Offline",
  nodeUnavailableLabel: "Node status is unavailable.",
};

test("shows the node unavailable line when the relay reports no public nodes", () => {
  const doc = createDocument();
  const list = doc.createElement("ul");

  renderNodes(doc, list, { status: "unavailable", nodes: [] }, nodeLabels);
  assert.equal(list.children.length, 1);
  assert.equal(list.children[0].className, "relay-nodes-unavailable");
  assert.equal(list.children[0].textContent, "Node status is unavailable.");

  renderNodes(doc, list, { status: "available", nodes: [{ alias: "only-alias" }] }, nodeLabels);
  assert.equal(list.children[0].className, "relay-nodes-unavailable", "a node without a public URL is not shown");
});

test("uses a fallback node line when the label is not configured", () => {
  const doc = createDocument();
  const list = doc.createElement("ul");

  renderNodes(doc, list, {}, {});

  assert.equal(list.children[0].textContent, "Node status is unavailable.");
});

test("shows each public node with its status label and its alias and URL as plain text", () => {
  const doc = createDocument();
  const list = doc.createElement("ul");

  renderNodes(
    doc,
    list,
    {
      status: "available",
      nodes: [
        { alias: "<em>edge</em>", url: "tcp://edge.example:4242", status: "up" },
        { alias: "backup", url: "tcp://backup.example:4242", status: "down" },
        { alias: "", url: "tcp://hidden.example:4242", status: "up" },
      ],
    },
    nodeLabels,
  );

  assert.equal(list.children.length, 2, "the node without an alias is filtered out");
  const [up, down] = list.children;
  assert.equal(up.className, "relay-node-card");
  const [heading, url] = up.children;
  const [alias, status] = heading.children;
  assert.equal(alias.textContent, "<em>edge</em>");
  assert.deepEqual(alias.children, []);
  assert.equal(status.dataset.state, "up");
  assert.equal(status.textContent, "Online");
  assert.equal(url.textContent, "tcp://edge.example:4242");

  const [, downStatus] = down.children[0].children;
  assert.equal(downStatus.dataset.state, "down");
  assert.equal(downStatus.textContent, "Offline");
});

test("maps each relay state to the four route steps", () => {
  const labels = {
    routeSourceReadyLabel: "Ready",
    routeWaitingLabel: "Waiting",
    routeEncryptedLabel: "Encrypted",
    routeRoutingLabel: "Routing",
    routeReceivedLabel: "Received",
    routeConfirmedLabel: "Confirmed",
  };
  const shape = (state, errorCode = "") => routeSteps(state, errorCode, labels).map((step) => [step.state, step.label]);

  assert.deepEqual(shape("identity_ready"), [["complete", "Ready"], ["waiting", "Waiting"], ["waiting", "Waiting"], ["waiting", "Waiting"]]);
  assert.deepEqual(shape("queued"), [["complete", "Ready"], ["active", "Routing"], ["complete", "Encrypted"], ["active", "Routing"]]);
  assert.deepEqual(shape("delivered"), [["complete", "Ready"], ["complete", "Received"], ["complete", "Encrypted"], ["complete", "Confirmed"]]);
});

test("maps a failed send to failed steps labelled by the error code", () => {
  const labels = {
    routeWaitingLabel: "Waiting",
    routeOutboundFailedLabel: "Outbound failed",
    routeDeliveryFailedLabel: "Relay delivery failed",
    routeUnknownFailedLabel: "Failed",
  };
  const failedLabels = (errorCode) => routeSteps("failed", errorCode, labels).map((step) => [step.state, step.label]);

  assert.deepEqual(failedLabels("outbound_error"), [["complete", "Ready"], ["failed", "Outbound failed"], ["waiting", "Waiting"], ["failed", "Outbound failed"]]);
  assert.deepEqual(failedLabels("delivery_failed")[1], ["failed", "Relay delivery failed"]);
  assert.deepEqual(failedLabels("")[3], ["failed", "Failed"], "an unrecognised error falls back to the generic failure label");
});

test("maps an unconfirmed send to unknown on the delivery steps, not to failed", () => {
  const labels = {
    routeWaitingLabel: "Waiting",
    routeUnconfirmedLabel: "Confirmation unknown",
    routeOutboundFailedLabel: "Outbound failed",
  };
  const steps = routeSteps("unconfirmed", "", labels);

  assert.deepEqual(steps.map((step) => step.state), ["waiting", "unknown", "waiting", "unknown"]);
  assert.equal(steps[1].label, "Confirmation unknown");
  assert.equal(steps[3].label, "Confirmation unknown", "the confirmation step carries the same unknown label");
  assert.ok(steps.every((step) => step.state !== "failed"), "an unconfirmed send is never shown as failed");
});

test("falls back to built-in route labels when the page has no label for a step", () => {
  const labels = {};

  assert.deepEqual(routeSteps("queued", "", labels).map((step) => step.label), ["Ready", "Routing", "Encrypted", "Routing"]);
  assert.equal(routeSteps("unconfirmed", "", labels)[1].label, "Confirmation unknown");
  assert.equal(routeSteps("failed", "delivery_failed", labels)[1].label, "Delivery failed");
  assert.equal(routeSteps("delivered", "", labels)[3].label, "Confirmed");
});

test("shows the configured session label for a known state and the raw state otherwise", () => {
  const labels = { queuedLabel: "Queued for delivery", deliveredLabel: "Delivered", failedLabel: "Failed", unconfirmedLabel: "Unconfirmed" };

  assert.equal(sessionStatusText("queued", labels), "Queued for delivery");
  assert.equal(sessionStatusText("unconfirmed", labels), "Unconfirmed");
  assert.equal(sessionStatusText("queued", {}), "queued", "a missing label falls back to the state");
  assert.equal(sessionStatusText("constructor", labels), "constructor", "an unknown name never resolves to an object property");
});

test("locks the input after the relay accepts a message and locks submit outside the open state", () => {
  assert.deepEqual(composerControls("open"), { inputDisabled: false, submitDisabled: false });
  assert.deepEqual(composerControls("cooldown"), { inputDisabled: false, submitDisabled: true });
  assert.deepEqual(composerControls("sent"), { inputDisabled: true, submitDisabled: true });
});

test("shows the relay address in the copy target and enables copying it", () => {
  const address = { textContent: "pending" };
  const destination = { textContent: "pending" };
  const copyButton = { disabled: true };

  renderAddress({ address, destination, copyButton }, "abc123");

  assert.equal(address.textContent, "abc123");
  assert.equal(destination.textContent, "abc123");
  assert.equal(copyButton.disabled, false, "copying is enabled once an address is shown");
});

test("keeps the copy button disabled when there is no address element, and tolerates a missing destination", () => {
  const copyButton = { disabled: true };

  renderAddress({ address: null, destination: null, copyButton }, "abc123");
  assert.equal(copyButton.disabled, true, "without an address element there is nothing to copy");

  const address = { textContent: "pending" };
  renderAddress({ address, destination: null, copyButton }, "abc123");
  assert.equal(address.textContent, "abc123");
  assert.equal(copyButton.disabled, false);
});
