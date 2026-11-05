import assert from "node:assert/strict";
import test from "node:test";
import {
  acceptsModel,
  animationMode,
  clipLayers,
  createDummyModel,
  decodeModel,
  dummyLayerCount,
  formatLayer,
  formatMillimetres,
  formatPercent,
  isDrawableState,
  makeProjector,
  normalizeState,
  parseStatus,
  pollDelayMs,
  resumeDelayMs,
  rotationAngle,
  shouldRequest,
  shouldShowThumbnail,
  strideFor,
  viewportFor,
} from "../src/lib/printer-lab.mjs";

const squarePath = [0, 0, 600, 0, 600, 400, 0, 400, 0, 0];
const modelId = "0123456789abcdef0123456789abcdef";

test("decodes Moonraker-style path units of 0.1 mm into millimetres", () => {
  const model = decodeModel({
    layerHeight: 0.2,
    layerCount: 2,
    bbox: { minX: 0, minY: 0, maxX: 60, maxY: 40 },
    layers: [
      { z: 0.2, paths: [squarePath] },
      { z: 0.4, paths: [[-12, 5, 12, 5]] },
    ],
  });

  assert.ok(model, "a valid model is accepted");
  assert.equal(model.layers.length, 2);
  assert.deepEqual(Array.from(model.layers[0].paths[0]), [0, 0, 60, 0, 60, 40, 0, 40, 0, 0]);
  assert.deepEqual(Array.from(model.layers[1].paths[0]), [-1.2, 0.5, 1.2, 0.5]);
  assert.equal(model.layers[1].z, 0.4);
  assert.deepEqual(model.bounds, { minX: -1.2, minY: 0, maxX: 60, maxY: 40, minZ: 0.2, maxZ: 0.4 });
});

test("keeps a model with no drawable paths but reports no bounds", () => {
  const model = decodeModel({ layerCount: 2, layers: [{ z: 0.2, paths: [] }, { z: 0.4, paths: [] }] });

  assert.ok(model);
  assert.equal(model.layers.length, 2);
  assert.equal(model.bounds, null);
});

test("drops single-point paths and refuses a model with malformed coordinates", () => {
  const withSinglePoint = decodeModel({ layers: [{ z: 0.2, paths: [[10, 10], squarePath] }] });
  assert.equal(withSinglePoint.layers[0].paths.length, 1, "a one-point path is dropped, not drawn");

  const malformed = [
    { layers: [{ z: 0.2, paths: [[0, 0, 1]] }] },
    { layers: [{ z: 0.2, paths: [[0, 0, 1.5, 2]] }] },
    { layers: [{ z: 0.2, paths: [[0, 0, 1000001, 0]] }] },
    { layers: [{ z: Number.NaN, paths: [squarePath] }] },
    { layers: [{ z: 0.2, paths: "not-an-array" }] },
    { layers: "not-an-array" },
    null,
  ];
  for (const payload of malformed) assert.equal(decodeModel(payload), null);
});

test("refuses a model above the relay's point and layer caps", () => {
  // One path of 150001 points: every coordinate is a valid integer, only the point cap is exceeded.
  const bigLayer = { z: 0.2, paths: [Array.from({ length: 300002 }, (_, index) => index % 2)] };
  assert.equal(decodeModel({ layers: [bigLayer] }), null, "more than 150000 points is refused whole");

  const tooManyLayers = { layers: Array.from({ length: 5001 }, (_, index) => ({ z: index * 0.2, paths: [] })) };
  assert.equal(decodeModel(tooManyLayers), null, "more than 5000 layers is refused whole");
});

test("clips the drawing to the current layer and keeps the rest as ghost layers", () => {
  const model = decodeModel({
    layers: [0.2, 0.4, 0.6, 0.8, 1].map((z, index) => ({ z, paths: [[0, 0, (index + 1) * 10, 0]] })),
  });

  const midway = clipLayers(model, 3);
  assert.deepEqual(midway.solid.map((layer) => layer.z), [0.2, 0.4], "layers below the current one are solid");
  assert.equal(midway.highlight.z, 0.6, "the current layer is the highlighted one");
  assert.deepEqual(midway.ghost.map((layer) => layer.z), [0.8, 1], "layers above the current one are ghosts");

  const nothingBuilt = clipLayers(model, 0);
  assert.deepEqual(nothingBuilt.solid, []);
  assert.equal(nothingBuilt.highlight, null);
  assert.equal(nothingBuilt.ghost.length, 5);

  const finished = clipLayers(model, 5);
  assert.equal(finished.highlight.z, 1);
  assert.deepEqual(finished.ghost, []);

  const beyondTheEnd = clipLayers(model, 99);
  assert.equal(beyondTheEnd.highlight.z, 1, "a layer number past the model is clamped to its last layer");
  assert.deepEqual(beyondTheEnd.ghost, []);
});

const cornersOf = ({ minX, minY, maxX, maxY, minZ, maxZ }) => [
  [minX, minY, minZ], [maxX, minY, minZ], [minX, maxY, minZ], [maxX, maxY, minZ],
  [minX, minY, maxZ], [maxX, minY, maxZ], [minX, maxY, maxZ], [maxX, maxY, maxZ],
];

test("fits the part inside the canvas at every rotation without changing the scale", () => {
  const bounds = { minX: -20, minY: -10, maxX: 30, maxY: 25, minZ: 0, maxZ: 40 };
  const width = 480;
  const height = 360;
  const padding = 24;
  const viewport = viewportFor(bounds, { width, height, padding });

  for (const angle of [0, 0.6, 1.9, 3.1, 4.4, 6.2]) {
    const project = makeProjector(viewport, angle);
    for (const [x, y, z] of cornersOf(bounds)) {
      const out = [0, 0];
      project(x, y, z, out);
      assert.ok(out[0] >= 0 && out[0] <= width, `x ${out[0]} stays inside the canvas at angle ${angle}`);
      assert.ok(out[1] >= 0 && out[1] <= height, `y ${out[1]} stays inside the canvas at angle ${angle}`);
    }
  }
});

test("projects height upwards on screen and keeps the centre of the part at the canvas centre", () => {
  const bounds = { minX: 0, minY: 0, maxX: 40, maxY: 40, minZ: 0, maxZ: 20 };
  const viewport = viewportFor(bounds, { width: 400, height: 400, padding: 20 });
  const project = makeProjector(viewport, 0.8);

  const base = [0, 0];
  const top = [0, 0];
  project(20, 20, 0, base);
  project(20, 20, 20, top);
  assert.ok(top[1] < base[1], "a higher point is drawn higher on the canvas");
  assert.ok(Math.abs(top[0] - base[0]) < 1e-9, "a vertical offset does not move the point sideways");

  const centre = [0, 0];
  project(20, 20, 10, centre);
  assert.ok(Math.abs(centre[0] - 200) < 1e-9 && Math.abs(centre[1] - 200) < 1e-9, "the part centre maps to the canvas centre");
});

test("handles a flat model without dividing by zero", () => {
  const viewport = viewportFor({ minX: 0, minY: 0, maxX: 10, maxY: 10, minZ: 0.2, maxZ: 0.2 }, { width: 200, height: 200, padding: 10 });
  assert.ok(Number.isFinite(viewport.scale) && viewport.scale > 0);
});

test("maps every printer state to itself and anything unknown to unavailable", () => {
  for (const state of ["idle", "printing", "paused", "complete", "cancelled", "error", "unavailable"]) {
    assert.equal(normalizeState(state), state);
  }
  for (const value of ["PRINTING", "standby", "", undefined, null, 7, { state: "printing" }]) {
    assert.equal(normalizeState(value), "unavailable");
  }
  assert.equal(isDrawableState("printing"), true);
  assert.equal(isDrawableState("cancelled"), true);
  assert.equal(isDrawableState("idle"), false);
  assert.equal(isDrawableState("unavailable"), false);
});

const validStatus = {
  state: "printing",
  progress: 0.42,
  layer: { current: 12, total: 85 },
  heightMm: 2.4,
  objectHeightMm: 40,
  modelId,
  thumbnail: true,
  updatedAt: "2026-11-04T09:00:00Z",
};

test("parses the public status and drops every field it does not list", () => {
  const status = parseStatus({ ...validStatus, filename: "secret-part.gcode" });

  assert.deepEqual(status, validStatus);
  assert.equal("filename" in status, false, "the filename is never kept");
});

test("treats out-of-range values as unknown instead of rendering them", () => {
  const status = parseStatus({
    state: "printing",
    progress: 1.5,
    layer: { current: -1, total: 2.5 },
    heightMm: "2.4",
    objectHeightMm: -3,
    modelId: "not-a-model-id",
    thumbnail: "yes",
    updatedAt: "not a date",
  });

  assert.deepEqual(status, {
    state: "printing",
    progress: null,
    layer: { current: null, total: null },
    heightMm: null,
    objectHeightMm: null,
    modelId: null,
    thumbnail: false,
    updatedAt: null,
  });
});

test("returns null for a payload that is not an object", () => {
  for (const payload of [null, "printing", [validStatus], 42]) assert.equal(parseStatus(payload), null);
});

test("formats progress as a whole percentage and missing progress as null", () => {
  assert.equal(formatPercent(0.424), "42%");
  assert.equal(formatPercent(0), "0%");
  assert.equal(formatPercent(1), "100%");
  assert.equal(formatPercent(null), null);
});

test("formats millimetres with the locale's decimal separator", () => {
  assert.equal(formatMillimetres(2.4, "en"), "2.4 mm");
  assert.equal(formatMillimetres(2.4, "es"), "2,4 mm");
  assert.equal(formatMillimetres(null, "en"), null);
});

test("shows a thumbnail only for a job that is printing, paused, or complete and has one", () => {
  assert.equal(shouldShowThumbnail({ ...validStatus, state: "printing" }), true);
  assert.equal(shouldShowThumbnail({ ...validStatus, state: "paused" }), true);
  assert.equal(shouldShowThumbnail({ ...validStatus, state: "complete" }), true);
  assert.equal(shouldShowThumbnail({ ...validStatus, state: "idle" }), false);
  assert.equal(shouldShowThumbnail({ ...validStatus, state: "cancelled" }), false);
  assert.equal(shouldShowThumbnail({ ...validStatus, thumbnail: false }), false);
  assert.equal(shouldShowThumbnail({ ...validStatus, modelId: null }), false);
});

test("backs off from the 15 second poll to a 2 minute ceiling after failures", () => {
  assert.deepEqual([0, 1, 2, 3, 4, 50].map(pollDelayMs), [15000, 30000, 60000, 120000, 120000, 120000]);
});

test("resumes polling at once when the interval has passed, and never sooner than the interval", () => {
  assert.equal(resumeDelayMs({ now: 1000, lastStartedAt: null, delayMs: 15000 }), 0, "a lab that was never polled polls now");
  assert.equal(resumeDelayMs({ now: 60000, lastStartedAt: 1000, delayMs: 15000 }), 0);
  assert.equal(resumeDelayMs({ now: 5000, lastStartedAt: 1000, delayMs: 15000 }), 11000, "a quick return waits out the rest of the interval");
});

test("never starts a duplicate request and waits out a failed model fetch before retrying it", () => {
  const base = { retryMs: 60000 };
  assert.equal(shouldRequest({ ...base, wanted: modelId, loaded: null, inFlight: false, failure: null, now: 0 }), true);
  assert.equal(shouldRequest({ ...base, wanted: modelId, loaded: null, inFlight: true, failure: null, now: 0 }), false, "one request at a time");
  assert.equal(shouldRequest({ ...base, wanted: modelId, loaded: modelId, inFlight: false, failure: null, now: 0 }), false, "a cached model is not fetched again");
  assert.equal(shouldRequest({ ...base, wanted: null, loaded: null, inFlight: false, failure: null, now: 0 }), false, "nothing wanted, nothing fetched");
  assert.equal(
    shouldRequest({ ...base, wanted: modelId, loaded: null, inFlight: false, failure: { key: modelId, at: 0 }, now: 30000 }),
    false,
    "a 404 while the model is still building is not repeated every poll",
  );
  assert.equal(
    shouldRequest({ ...base, wanted: modelId, loaded: null, inFlight: false, failure: { key: modelId, at: 0 }, now: 60000 }),
    true,
    "the model is tried again after the retry window",
  );
  assert.equal(
    shouldRequest({ ...base, wanted: "f".repeat(32), loaded: null, inFlight: false, failure: { key: modelId, at: 0 }, now: 1 }),
    true,
    "a new job is requested at once",
  );
});

test("animates only when visible and not under reduced motion", () => {
  assert.equal(animationMode({ reducedMotion: false, visible: true }), "animate");
  assert.equal(animationMode({ reducedMotion: false, visible: false }), "paused");
  assert.equal(animationMode({ reducedMotion: true, visible: true }), "static", "reduced motion draws a single frame");
  assert.equal(animationMode({ reducedMotion: true, visible: false }), "paused");
});

test("rotates slowly about the vertical axis and holds still under reduced motion", () => {
  const start = rotationAngle(0, false);
  const later = rotationAngle(10000, false);
  assert.ok(later > start, "the part turns over time");
  assert.ok((later - start) / 10 < 0.25, "the turn is slower than a quarter radian per second");
  assert.equal(rotationAngle(0, true), rotationAngle(90000, true), "reduced motion never rotates");
});

test("grows the dummy printing bed stack over a cycle, and shows the full stack statically under reduced motion", () => {
  const dummy = createDummyModel();
  const total = dummy.layers.length;
  assert.ok(total >= 8, "the decorative stack has enough layers to read as building");
  assert.equal(dummy.bounds.minX, -20);
  assert.equal(dummy.bounds.maxX, 20);

  assert.equal(dummyLayerCount(0, false), 0);
  const middle = dummyLayerCount(6000, false);
  assert.ok(middle > 0 && middle < total, "a cycle passes through partial stacks");
  assert.equal(dummyLayerCount(12000, false), dummyLayerCount(0, false), "the animation loops");
  assert.ok(dummyLayerCount(11999, false) <= total);

  assert.equal(dummyLayerCount(0, true), total, "reduced motion shows the finished stack");
  assert.equal(dummyLayerCount(5000, true), total);
});

test("limits the number of drawn points per frame with a stride", () => {
  assert.equal(strideFor(10000, 60000), 1);
  assert.equal(strideFor(150000, 60000), 3);
  assert.equal(strideFor(0, 60000), 1);
});

test("shows the layer readout only when the total is a positive number", () => {
  assert.equal(formatLayer({ current: 12, total: 85 }), "12 / 85");
  assert.equal(formatLayer({ current: 12, total: 0 }), null, "a zero total would read as 12 / 0");
  assert.equal(formatLayer({ current: null, total: 85 }), null);
  assert.equal(formatLayer({ current: 12, total: null }), null);
});

test("accepts a downloaded model only while it still belongs to the job on screen", () => {
  const other = "fedcba9876543210fedcba9876543210";
  assert.equal(acceptsModel({ modelId }, modelId), true);
  assert.equal(acceptsModel({ modelId: other }, modelId), false, "a newer job replaced this one while it downloaded");
  assert.equal(acceptsModel({ modelId: null }, modelId), false);
  assert.equal(acceptsModel(null, modelId), false);
});
