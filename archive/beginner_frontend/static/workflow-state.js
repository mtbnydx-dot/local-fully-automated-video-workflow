/* Pure workflow state: no DOM, network, or inference side effects. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.WorkbenchState = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";
  const order = ["draft", "deflicker", "rife", "upscale", "edit"];
  const mediaKey = (media) => media?.filename
    ? [media.type || "output", media.subfolder || "", media.filename].join("/") : "";

  function create() {
    return { revision: 0, outputs: {}, latest: {}, processed: [] };
  }

  function invalidateAfter(state, step) {
    for (const next of order.slice(order.indexOf(step) + 1)) {
      delete state.outputs[next];
      delete state.latest[next];
    }
  }

  function sourceFor(state, step) {
    const index = order.indexOf(step);
    return order.slice(0, index < 0 ? order.length : index).reverse()
      .map((key) => state.outputs[key]).find(Boolean) || null;
  }

  function begin(state, id, context) {
    if (!order.includes(context.stepId)) return context;
    if (context.expectedRevision !== undefined && context.expectedRevision !== state.revision) {
      return { ...context, revision: context.expectedRevision, detached: true };
    }
    if (context.stepId === "draft" || context.newSource) {
      state.revision += 1;
      state.outputs = {};
      state.latest = {};
    }
    invalidateAfter(state, context.stepId);
    state.latest[context.stepId] = id;
    return { ...context, revision: state.revision };
  }

  function complete(state, job, context) {
    if (!context || !order.includes(context.stepId) || state.processed.includes(job.id)) return false;
    state.processed.push(job.id);
    state.processed = state.processed.slice(-500);
    const media = (job.media || []).find((item) => item.kind === "video");
    if (job.status !== "success" || !media || context.detached || context.revision !== state.revision ||
        state.latest[context.stepId] !== job.id) return false;
    const source = context.source || {};
    const meta = media.metadata || job.output_metadata || {};
    const scale = Number(job.upscale_scale || context.scale || 2);
    const multiplier = Number(job.rife_multiplier || context.multiplier || 2);
    const isUpscale = context.stepId === "upscale";
    const sourceWidth = Number(source.width || context.width || job.width || 0);
    const sourceHeight = Number(source.height || context.height || job.height || 0);
    const inputFps = Number(job.fps || context.fps || source.fps || 24);
    const record = {
      ...media, jobId: job.id,
      width: Number(meta.width || (isUpscale ? sourceWidth * scale : job.width || sourceWidth)),
      height: Number(meta.height || (isUpscale ? sourceHeight * scale : job.height || sourceHeight)),
      fps: Number(meta.fps || (context.stepId === "rife" ? inputFps * multiplier : inputFps)),
      estimated: !meta.width,
    };
    if (["deflicker", "rife"].includes(context.stepId) && !meta.width) {
      record.width = sourceWidth;
      record.height = sourceHeight;
    }
    invalidateAfter(state, context.stepId);
    state.outputs[context.stepId] = record;
    return true;
  }

  function adopt(state, media) {
    state.revision += 1;
    state.outputs = { draft: { ...media } };
    state.latest = {};
  }

  function trustedApiUrl(value, origin, serverUrl = "") {
    try {
      const url = new URL(String(value), origin);
      const trusted = [new URL(origin).origin];
      if (serverUrl) trusted.push(new URL(serverUrl).origin);
      return trusted.includes(url.origin) && (url.pathname === "/api" || url.pathname.startsWith("/api/"));
    } catch (_) { return false; }
  }

  return { order, mediaKey, create, sourceFor, begin, complete, adopt, trustedApiUrl };
});
