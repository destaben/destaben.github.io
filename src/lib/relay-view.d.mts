// Type declarations for relay-view.mjs, so TypeScript (astro check) can type the page's imports.
import type { RelayComposerMode, RelayInboxPayload, RelayNodesPayload } from "./relay-live.mjs";

export type RelayRouteStepState = "waiting" | "active" | "complete" | "failed" | "unknown";

export interface RelayRouteStep {
  state: RelayRouteStepState;
  label: string;
}

// The page's label dataset (DOMStringMap) satisfies this shape.
export type RelayLabels = Record<string, string | undefined>;

export interface RelayAddressTargets {
  address: { textContent: string | null } | null | undefined;
  destination?: { textContent: string | null } | null;
  copyButton?: { disabled: boolean } | null;
}

export declare function renderInbox(
  doc: Pick<Document, "createElement">,
  list: Pick<HTMLElement, "replaceChildren"> | null | undefined,
  data: RelayInboxPayload | null | undefined,
): void;

export declare function renderNodes(
  doc: Pick<Document, "createElement">,
  list: Pick<HTMLElement, "replaceChildren"> | null | undefined,
  data: RelayNodesPayload | null | undefined,
  labels: RelayLabels,
): void;

export declare function routeSteps(state: string, errorCode: string, labels: RelayLabels): RelayRouteStep[];

export declare function sessionStatusText(state: string, labels: RelayLabels): string;

export declare function composerControls(mode: RelayComposerMode): { inputDisabled: boolean; submitDisabled: boolean };

export declare function renderAddress(targets: RelayAddressTargets, value: string): void;
