// Pure helpers for the 3D printer laboratory. Nothing here touches the DOM, so the Node test suite
// imports this file directly. Relay coordinates are integers in 0.1 mm units; decodeModel converts
// them to millimetres, and every later function works in millimetres.

export const PRINTER_STATES = Object.freeze(["idle", "printing", "paused", "complete", "cancelled", "error", "unavailable"]);

const drawableStates = new Set(["printing", "paused", "complete", "cancelled", "error"]);
const thumbnailStates = new Set(["printing", "paused", "complete"]);
const modelIdPattern = /^[0-9a-f]{32}$/;

// The relay caps: 5000 layers, 150000 drawn points, coordinates within 100 m (1000000 units).
const maxLayers = 5000;
const maxPoints = 150000;
const maxUnits = 1000000;
const maxLayerZmm = 100000;
const maxCount = 100000;
const unitsPerMm = 10;

export const pollBaseMs = 15000;
export const pollMaxMs = 120000;

// Fixed view tilt (about 34 degrees) and a slow turn of about 42 seconds per revolution.
const viewTilt = 0.6;
const baseAngle = 0.6;
const rotationRate = 0.15;

const dummyLayers = 12;
const dummyCycleMs = 12000;
const dummySquareMm = 40;
const dummyLayerHeightMm = 2;

const isRecord = (value) => typeof value === "object" && value !== null && !Array.isArray(value);
const isFiniteNumber = (value) => typeof value === "number" && Number.isFinite(value);
const isUnit = (value) => Number.isInteger(value) && Math.abs(value) <= maxUnits;

export const normalizeState = (value) => (PRINTER_STATES.includes(value) ? value : "unavailable");

export const isDrawableState = (state) => drawableStates.has(state);

// Returns null for a payload that is not an object. Every other field is checked on its own, so an
// out-of-range value becomes null (unknown) instead of being rendered. Only whitelisted keys are kept,
// which keeps any filename the relay might add out of the page.
export const parseStatus = (payload) => {
  if (!isRecord(payload)) return null;
  const { state, progress, layer, heightMm, objectHeightMm, modelId, thumbnail, updatedAt } = payload;
  const counts = isRecord(layer) ? layer : {};
  return {
    state: normalizeState(state),
    progress: isFiniteNumber(progress) && progress >= 0 && progress <= 1 ? progress : null,
    layer: {
      current: Number.isInteger(counts.current) && counts.current >= 0 && counts.current <= maxCount ? counts.current : null,
      total: Number.isInteger(counts.total) && counts.total >= 0 && counts.total <= maxCount ? counts.total : null,
    },
    heightMm: isFiniteNumber(heightMm) && heightMm >= 0 ? heightMm : null,
    objectHeightMm: isFiniteNumber(objectHeightMm) && objectHeightMm >= 0 ? objectHeightMm : null,
    modelId: typeof modelId === "string" && modelIdPattern.test(modelId) ? modelId : null,
    thumbnail: thumbnail === true,
    updatedAt: typeof updatedAt === "string" && !Number.isNaN(Date.parse(updatedAt)) ? updatedAt : null,
  };
};

// The relay reports the thumbnail from the file metadata, so it can exist before a model is built, or
// for a whole job whose model was rejected. It does not depend on a model id.
export const shouldShowThumbnail = (status) => Boolean(status && status.thumbnail && thumbnailStates.has(status.state));

// Identity of the thumbnail on screen: the model id when there is one, else the job epoch (bumped when a
// new job is detected), so a thumbnail from a previous job without a model is never kept.
export const thumbnailKey = (status, epoch) => (shouldShowThumbnail(status) ? status.modelId ?? `pending-${epoch}` : null);

const runningStates = new Set(["printing", "paused"]);

// Whether `next` starts a different job than `previous`, judged from the readings alone. It matters for
// jobs without a model id, which carry no identity of their own.
export const jobChanged = (previous, next) => {
  if (!previous || !next) return false;
  // A running job after anything that is not a running job (a finished print, a gap in the readings) is a
  // new job as far as a thumbnail without a model id is concerned.
  if (runningStates.has(next.state) && !runningStates.has(previous.state)) return true;
  if (isFiniteNumber(previous.progress) && isFiniteNumber(next.progress) && next.progress < previous.progress) return true;
  const before = previous.layer.current;
  const after = next.layer.current;
  return Number.isInteger(before) && Number.isInteger(after) && after < before;
};

const boundsOf = (layers) => {
  let bounds = null;
  for (const layer of layers) {
    for (const path of layer.paths) {
      for (let index = 0; index < path.length; index += 2) {
        const x = path[index];
        const y = path[index + 1];
        if (!bounds) bounds = { minX: x, minY: y, maxX: x, maxY: y, minZ: 0, maxZ: 0 };
        bounds.minX = Math.min(bounds.minX, x);
        bounds.maxX = Math.max(bounds.maxX, x);
        bounds.minY = Math.min(bounds.minY, y);
        bounds.maxY = Math.max(bounds.maxY, y);
      }
    }
  }
  if (!bounds) return null;
  const heights = layers.map((layer) => layer.z);
  bounds.minZ = Math.min(...heights);
  bounds.maxZ = Math.max(...heights);
  return bounds;
};

// Refuses the whole model on any malformed value, because the relay never publishes a partial model.
// A single-point path is dropped: it has nothing to draw.
export const decodeModel = (payload) => {
  if (!isRecord(payload) || !Array.isArray(payload.layers) || payload.layers.length > maxLayers) return null;
  let points = 0;
  const layers = [];
  for (const raw of payload.layers) {
    if (!isRecord(raw) || !isFiniteNumber(raw.z) || raw.z < 0 || raw.z > maxLayerZmm || !Array.isArray(raw.paths)) return null;
    const paths = [];
    for (const path of raw.paths) {
      if (!Array.isArray(path) || path.length % 2 !== 0 || !path.every(isUnit)) return null;
      points += path.length / 2;
      if (points > maxPoints) return null;
      if (path.length >= 4) paths.push(Float64Array.from(path, (unit) => unit / unitsPerMm));
    }
    layers.push({ z: raw.z, paths });
  }
  return { layers, bounds: boundsOf(layers) };
};

// The layers are 1-based in the relay's vocabulary: layer N is layers[N - 1]. The current layer is
// highlighted, the layers below it are solid, and the layers above it are ghosts.
export const clipLayers = (model, current) => {
  const built = Math.min(Math.max(0, Number.isFinite(current) ? Math.round(current) : 0), model.layers.length);
  return {
    solid: model.layers.slice(0, Math.max(0, built - 1)),
    highlight: built > 0 ? model.layers[built - 1] : null,
    ghost: model.layers.slice(built),
  };
};

// The fit depends only on the bounding sphere of the part, never on the angle, so the scale does not
// change while the part turns. The projection is orthonormal, so every point stays inside that sphere.
export const viewportFor = (bounds, { width, height, padding }) => {
  const radius = Math.hypot(bounds.maxX - bounds.minX, bounds.maxY - bounds.minY, bounds.maxZ - bounds.minZ) / 2;
  const available = Math.min(width, height) / 2 - padding;
  return {
    cx: (bounds.minX + bounds.maxX) / 2,
    cy: (bounds.minY + bounds.maxY) / 2,
    cz: (bounds.minZ + bounds.maxZ) / 2,
    scale: radius > 0 ? available / radius : 1,
    originX: width / 2,
    originY: height / 2,
  };
};

// Rotates about the vertical axis, then tilts the view about the horizontal axis and drops depth.
// The result is written into out[0] and out[1] in canvas pixels, with y growing downwards.
export const makeProjector = (viewport, angle) => {
  const cos = Math.cos(angle);
  const sin = Math.sin(angle);
  const cosTilt = Math.cos(viewTilt);
  const sinTilt = Math.sin(viewTilt);
  const { cx, cy, cz, scale, originX, originY } = viewport;
  return (x, y, z, out) => {
    const x0 = x - cx;
    const y0 = y - cy;
    const z0 = z - cz;
    const x1 = x0 * cos - y0 * sin;
    const y1 = x0 * sin + y0 * cos;
    const depthUp = y1 * sinTilt + z0 * cosTilt;
    out[0] = originX + scale * x1;
    out[1] = originY - scale * depthUp;
  };
};

export const rotationAngle = (elapsedMs, reducedMotion) =>
  reducedMotion ? baseAngle : baseAngle + (elapsedMs / 1000) * rotationRate;

// The decorative model: a square ring per layer, stacked upwards. It reuses the model shape, so the
// same renderer draws it.
export const createDummyModel = () => {
  const half = dummySquareMm / 2;
  const layers = Array.from({ length: dummyLayers }, (_, index) => ({
    z: (index + 1) * dummyLayerHeightMm,
    paths: [Float64Array.from([-half, -half, half, -half, half, half, -half, half, -half, -half])],
  }));
  return {
    layers,
    bounds: {
      minX: -half,
      minY: -half,
      maxX: half,
      maxY: half,
      minZ: dummyLayerHeightMm,
      maxZ: dummyLayers * dummyLayerHeightMm,
    },
  };
};

// Under reduced motion the stack is shown finished, as one static frame.
export const dummyLayerCount = (elapsedMs, reducedMotion) => {
  if (reducedMotion) return dummyLayers;
  const phase = (elapsedMs % dummyCycleMs) / dummyCycleMs;
  return Math.floor(phase * (dummyLayers + 1));
};

// Animation runs only while visible. Reduced motion draws one frame, and the lab is paused when hidden.
export const animationMode = ({ reducedMotion, visible }) => {
  if (!visible) return "paused";
  return reducedMotion ? "static" : "animate";
};

// The real part redraws at 30 frames per second. The decorative animation is slow and carries no reading,
// so it redraws at 12 and spares the battery of a visitor who left the panel on screen.
export const frameIntervalMs = (drawingPart) => (drawingPart ? 1000 / 30 : 1000 / 12);

// Doubles the poll interval after each failure, from 15 seconds up to 2 minutes.
export const pollDelayMs = (failures) => Math.min(pollBaseMs * 2 ** Math.max(0, failures), pollMaxMs);

// Resuming after a hide polls at once only when the interval has passed since the last poll began.
export const resumeDelayMs = ({ now, lastStartedAt, delayMs }) =>
  lastStartedAt === null ? 0 : Math.max(0, lastStartedAt + delayMs - now);

// A wanted key is fetched once. A failed key waits out the retry window, so a model that is still
// being built is not requested on every poll.
export const shouldRequest = ({ wanted, loaded, inFlight, failure, now, retryMs }) => {
  if (!wanted || inFlight || wanted === loaded) return false;
  if (failure && failure.key === wanted && now - failure.at < retryMs) return false;
  return true;
};

// Caps the points drawn per frame by skipping vertices with a stride.
export const strideFor = (totalPoints, budget) => Math.max(1, Math.ceil(totalPoints / budget));

// Draw sampling. A plan keeps every `stride`-th vertex of an outline (always its first and last, so it
// still closes) and every `pathStride`-th outline. The same walk draws and counts, so what the renderer
// emits is exactly what the budget was checked against.
export const sampleLayers = (layers, plan, onMove, onLine) => {
  if (plan.none) return;
  let pathIndex = 0;
  for (const layer of layers) {
    for (const path of layer.paths) {
      const keep = pathIndex % plan.pathStride === 0;
      pathIndex += 1;
      const vertices = path.length / 2;
      if (!keep || vertices < 1) continue;
      onMove(path[0], path[1], layer.z);
      for (let vertex = 1; vertex < vertices; vertex += 1) {
        if (vertex % plan.stride !== 0 && vertex !== vertices - 1) continue;
        onLine(path[vertex * 2], path[vertex * 2 + 1], layer.z);
      }
    }
  }
};

export const countSampled = (layers, plan) => {
  let count = 0;
  const add = () => {
    count += 1;
  };
  sampleLayers(layers, plan, add, add);
  return count;
};

const fullPlan = Object.freeze({ stride: 1, pathStride: 1 });
const noSampling = Object.freeze({ stride: 1, pathStride: 1, none: true });

// A plan that keeps the emitted vertices within the budget. It thins vertices first and, when
// the outlines are so short that their endpoints alone exceed the budget, skips whole outlines.
export const planSampling = (layers, budget) => {
  const limit = Math.floor(budget);
  let total = 0;
  let longest = 1;
  for (const layer of layers) {
    for (const path of layer.paths) {
      total += path.length / 2;
      longest = Math.max(longest, path.length / 2);
    }
  }
  if (total === 0) return { stride: 1, pathStride: 1 };
  // An outline needs two vertices, so a budget below that draws nothing at all.
  if (limit < 2) return noSampling;
  let plan = { stride: strideFor(total, limit), pathStride: 1 };
  while (countSampled(layers, plan) > limit) {
    plan = plan.stride < longest ? { ...plan, stride: plan.stride * 2 } : { ...plan, pathStride: plan.pathStride * 2 };
  }
  return plan;
};

const pointCount = (layers) => layers.reduce((sum, layer) => sum + layer.paths.reduce((inner, path) => inner + path.length / 2, 0), 0);

// One frame draws the ghost layers, the solid layers and the highlighted layer, each with its own plan.
// The highlight gets a quarter of the budget and the rest is shared by the other two in proportion to
// their size, so the three together never add up to more than the whole (a share too small to draw an
// outline draws nothing).
export const planFrame = (clip, budget) => {
  const highlightBudget = Math.floor(budget / 4);
  const bodyBudget = budget - highlightBudget;
  const ghostPoints = pointCount(clip.ghost);
  const solidPoints = pointCount(clip.solid);
  const ghostBudget = ghostPoints + solidPoints === 0 ? 0 : Math.floor((bodyBudget * ghostPoints) / (ghostPoints + solidPoints));
  return {
    ghost: planSampling(clip.ghost, ghostBudget),
    solid: planSampling(clip.solid, bodyBudget - ghostBudget),
    highlight: clip.highlight ? planSampling([clip.highlight], highlightBudget) : fullPlan,
  };
};

export const fullSampling = fullPlan;

// "12 / 85", or null when either number is missing or the total is not positive (a "12 / 0" would mislead).
export const formatLayer = (layer) =>
  isFiniteNumber(layer.current) && isFiniteNumber(layer.total) && layer.total > 0 ? `${layer.current} / ${layer.total}` : null;

// A downloaded model is kept only while the latest status still names it; a newer job may have replaced it.
export const acceptsModel = (status, id) => Boolean(status && status.modelId === id);

export const formatPercent = (progress) => (isFiniteNumber(progress) ? `${Math.round(progress * 100)}%` : null);

export const formatMillimetres = (value, locale) =>
  isFiniteNumber(value) ? `${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(value)} mm` : null;
