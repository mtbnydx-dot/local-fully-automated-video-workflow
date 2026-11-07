/* Navigation decisions only. Model selection and submission stay in their owners. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.WorkbenchJourney = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";
  const tools = ["deflicker", "rife", "upscale", "edit"];
  const views = ["image-studio", "workflow", "process", "library", "tasks", "environment", "download-center", "video-face-swap"];
  function operation(value) { return tools.includes(value) ? value : "deflicker"; }
  function route(view, step = "draft") {
    if (view === "process") return { view: "workflow", step: operation(step), task: "process" };
    if (view === "workflow") return { view, step: "draft", task: "video" };
    return { view: views.includes(view) ? view : "workflow", step: "draft", task: view === "image-studio" ? "image" : "video" };
  }
  function restore(saved) {
    if (!saved || !views.includes(saved.view)) return route("workflow");
    return route(saved.view, saved.operation);
  }
  return { tools, views, operation, route, restore };
});
