// Type declarations for printer-lab.mjs, so TypeScript (astro check) can type its imports.

export type PrinterState = "idle" | "printing" | "paused" | "complete" | "cancelled" | "error" | "unavailable";

export interface PrinterStatus {
  state: PrinterState;
  progress: number | null;
  layer: { current: number | null; total: number | null };
  heightMm: number | null;
  objectHeightMm: number | null;
  modelId: string | null;
  thumbnail: boolean;
  updatedAt: string | null;
}

export interface PrinterBounds {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
  minZ: number;
  maxZ: number;
}

export interface PrinterLayer {
  z: number;
  paths: Float64Array[];
}

export interface PrinterModel {
  layers: PrinterLayer[];
  bounds: PrinterBounds | null;
}

export interface PrinterViewport {
  cx: number;
  cy: number;
  cz: number;
  scale: number;
  originX: number;
  originY: number;
}

export type PrinterProjector = (x: number, y: number, z: number, out: number[] | Float64Array) => void;

export declare const PRINTER_STATES: readonly PrinterState[];
export declare const pollBaseMs: number;
export declare const pollMaxMs: number;

export declare function normalizeState(value: unknown): PrinterState;
export declare function isDrawableState(state: PrinterState): boolean;
export declare function parseStatus(payload: unknown): PrinterStatus | null;
export declare function shouldShowThumbnail(status: PrinterStatus | null): boolean;
export declare function decodeModel(payload: unknown): PrinterModel | null;
export declare function clipLayers(
  model: PrinterModel,
  current: number | null,
): { solid: PrinterLayer[]; highlight: PrinterLayer | null; ghost: PrinterLayer[] };
export declare function viewportFor(
  bounds: PrinterBounds,
  size: { width: number; height: number; padding: number },
): PrinterViewport;
export declare function makeProjector(viewport: PrinterViewport, angle: number): PrinterProjector;
export declare function rotationAngle(elapsedMs: number, reducedMotion: boolean): number;
export declare function createDummyModel(): PrinterModel;
export declare function dummyLayerCount(elapsedMs: number, reducedMotion: boolean): number;
export declare function animationMode(options: { reducedMotion: boolean; visible: boolean }): "animate" | "static" | "paused";
export declare function pollDelayMs(failures: number): number;
export declare function resumeDelayMs(options: { now: number; lastStartedAt: number | null; delayMs: number }): number;
export declare function shouldRequest(options: {
  wanted: string | null;
  loaded: string | null;
  inFlight: boolean;
  failure: { key: string; at: number } | null;
  now: number;
  retryMs: number;
}): boolean;
export interface SamplingPlan { stride: number; pathStride: number; none?: boolean }
export declare function sampleLayers(
  layers: PrinterLayer[],
  plan: SamplingPlan,
  onMove: (x: number, y: number, z: number) => void,
  onLine: (x: number, y: number, z: number) => void,
): void;
export declare function countSampled(layers: PrinterLayer[], plan: SamplingPlan): number;
export declare function planSampling(layers: PrinterLayer[], budget: number): SamplingPlan;
export declare function planFrame(
  clip: { solid: PrinterLayer[]; highlight: PrinterLayer | null; ghost: PrinterLayer[] },
  budget: number,
): { ghost: SamplingPlan; solid: SamplingPlan; highlight: SamplingPlan };
export declare const fullSampling: SamplingPlan;
export declare function thumbnailKey(status: PrinterStatus | null, epoch: number): string | null;
export declare function jobChanged(previous: PrinterStatus | null, next: PrinterStatus | null): boolean;
export declare function frameIntervalMs(drawingPart: boolean): number;
export declare function strideFor(totalPoints: number, budget: number): number;
export declare function formatLayer(layer: { current: number | null; total: number | null }): string | null;
export declare function acceptsModel(status: { modelId: string | null } | null, id: string): boolean;
export declare function formatPercent(progress: number | null): string | null;
export declare function formatMillimetres(value: number | null, locale: string): string | null;
