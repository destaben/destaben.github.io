// Type declarations for relay-live.mjs, so TypeScript (astro check) can type its imports.

export interface RelayInboxPayload {
  messages?: { content?: string; receivedAt: string }[];
}

export interface RelayNodesPayload {
  status?: string;
  nodes?: { alias?: string; url?: string; status?: string }[];
}

export type RelayComposerMode = "open" | "cooldown" | "sent";
export type RelayNoticeKind = "preparing" | "unavailable";

// Render callbacks supplied by the page. The helper decides what to show; the page decides how.
export interface RelayLiveView {
  setAvailability(isOnline: boolean): void;
  setAddress(address: string): void;
  setInbox(data: RelayInboxPayload): void;
  setNodes(data: RelayNodesPayload): void;
  setTelegram(enabled: boolean): void;
  setSessionNode(alias: string | undefined): void;
  setSessionState(state: string, errorCode: string): void;
  setSessionNotice(kind: RelayNoticeKind): void;
  setComposer(mode: RelayComposerMode): void;
}

export interface RelayLiveOptions {
  relayUrl: string | undefined;
  fetch: (input: string, init?: RequestInit) => Promise<Response>;
  view: RelayLiveView;
  documentTarget: Pick<Document, "visibilityState" | "addEventListener">;
  windowTarget: Pick<Window, "addEventListener">;
}

export declare const pollIntervalMs: number;
export declare const inboxIntervalMs: number;
export declare const nodesIntervalMs: number;
export declare const failedGiveUpMs: number;
export declare const sendCooldownMs: number;
export declare const readTimeoutMs: number;
export declare const sessionPollFailureLimit: number;

export declare function createRelayLive(options: RelayLiveOptions): {
  send(readContent: () => string): Promise<void>;
};
