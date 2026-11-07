// CPU-only UI regression. Requires Playwright; never contacts a live backend.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const { chromium } = require("playwright");

const root = path.resolve(__dirname, "..");
const python = process.env.TEST_PYTHON || path.join(root, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
const fixture = spawnSync(python, ["-B", "-c", `
import json
from beginner_frontend import app, video_params
from beginner_frontend.model_catalog import MODEL_ASSETS
from beginner_frontend.social_presets import social_presets_payload
hardware = {"accelerator": "cuda", "max_vram_gb": 96, "platform_strategy": "cuda_multi_model"}
assets = [{"id": a["id"], "ok": a["id"] == "minimax_h3_lightx4_v11_768p"} for a in MODEL_ASSETS]
options = app.workflow_model_options(os_info={"name": "Windows"}, hardware=hardware, assets=assets,
    custom_nodes=[], tool_checks=[], node_checks=[], selected_model_id="minimax_h3_fl2va_int8")
print(json.dumps({"environment": {"ok": True, "os": {"name": "Windows"}, "hardware": hardware,
    "model_options": options, "comfy": {"connected": False}},
    "params": {"modes": {m: video_params.param_schema(m) for m in video_params.MODE_PARAMS},
    "capabilities": {m: video_params.mode_capabilities(m) for m in video_params.MODE_PARAMS}},
    "social": social_presets_payload()}))
`], { cwd: root, encoding: "utf8", env: { ...process.env, PYTHONIOENCODING: "utf-8",
  CUDA_VISIBLE_DEVICES: "-1", BEGINNER_FRONTEND_DISABLE_GPU_PROBES: "1", BEGINNER_FRONTEND_DISABLE_JOB_PERSISTENCE: "1" } });
assert.equal(fixture.status, 0, fixture.stderr);
const data = JSON.parse(fixture.stdout);
const output = process.env.WORKBENCH_QA_DIR || path.join(require("node:os").tmpdir(), "h3-profiles-ui-qa");
fs.mkdirSync(output, { recursive: true });

async function main() {
  const browser = await chromium.launch({ headless: true, args: ["--disable-gpu"] });
  try {
    for (const width of [1440, 390]) {
      const context = await browser.newContext({ viewport: { width, height: 1000 } });
      const page = await context.newPage();
      const errors = [];
      const requests = [];
      page.on("pageerror", (error) => errors.push(error.message));
      page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
      // Every URL is fulfilled locally or blocked, including all API requests.
      await context.route("**/*", async (route) => {
        const url = new URL(route.request().url());
        assert.equal(url.origin, "http://127.0.0.1:18760", `Unexpected network: ${url}`);
        if (url.pathname.startsWith("/api/")) {
          requests.push(url);
          const payload = {
            "/api/video-params": data.params,
            "/api/social-presets": data.social,
            "/api/environment": data.environment,
            "/api/workflow": { ok: false, message: "CPU fixture: no inference", errors: ["缺少 LoRA"] },
            "/api/status": { connected: false },
            "/api/jobs": { jobs: [] },
          }[url.pathname] || {};
          return route.fulfill({ contentType: "application/json", body: JSON.stringify(payload) });
        }
        const relative = url.pathname === "/" ? "index.html" : url.pathname.replace(/^\/static\//, "");
        const staticRoot = path.join(root, "beginner_frontend", "static");
        const file = path.resolve(staticRoot, relative);
        assert.ok(file.startsWith(staticRoot + path.sep));
        if (!fs.existsSync(file)) return route.fulfill({ status: 204 });
        return route.fulfill({ path: file, contentType: file.endsWith(".js") ? "text/javascript" : file.endsWith(".css") ? "text/css" : "text/html" });
      });
      await page.goto("http://127.0.0.1:18760/");
      await page.waitForFunction(() => appInitialized);
      await page.locator('button.view-tab[data-view="workflow"]').click();
      await page.locator('[data-level="full"]').click();
      const models = page.locator("#modelSelector");
      await models.selectOption("minimax_h3_fl2va_int8_t2v");
      await page.locator("#videoAdvancedDrawer > summary").click();
      const profile = page.locator('[data-param="h3_acceleration_profile"] select');
      const shift = page.locator('[data-param="h3_shift_video"] input[type="number"]');
      await shift.fill("8");
      await shift.dispatchEvent("change");
      await page.locator("#steps").fill("31");
      await profile.selectOption("lightx8_v10");
      assert.equal(await shift.inputValue(), "12");
      assert.equal(await shift.isDisabled(), true);
      assert.equal(await page.locator("#steps").inputValue(), "8");
      assert.match(await page.locator(".adv-profile-status").textContent(), /缺少 LoRA/);
      await profile.selectOption("lightx4_v11_768p");
      assert.match(await page.locator(".adv-profile-status").textContent(), /LoRA 已齐/);
      assert.equal(await page.locator("#steps").inputValue(), "4");
      await profile.selectOption("lightx4_v12_768p");
      assert.equal(await shift.inputValue(), "6");
      assert.match(await page.locator(".adv-profile-status").textContent(), /v1\.2_768p/);
      const request = page.waitForRequest((req) => req.url().includes("/api/workflow?") && new URL(req.url()).searchParams.get("advanced")?.includes("lightx8_v10_768p"));
      await profile.selectOption("lightx8_v10_768p");
      const query = new URL((await request).url()).searchParams;
      assert.equal(query.get("steps"), "8");
      assert.equal(JSON.parse(query.get("advanced")).h3_shift_video, 6);
      await profile.selectOption("native");
      assert.equal(await shift.inputValue(), "8");
      assert.equal(await shift.isDisabled(), false);
      assert.equal(await page.locator("#steps").inputValue(), "31");
      await profile.selectOption("lightx4_v12_768p");
      await models.selectOption("minimax_h3_ref2va_int8_r2v");
      assert.equal(await profile.inputValue(), "native");
      await profile.selectOption("lightx_ref4_v01");
      assert.equal(await shift.inputValue(), "12");
      await models.selectOption("minimax_h3_fl2va_int8_t2v");
      assert.equal(await profile.inputValue(), "native");
      await profile.selectOption("lightx8_v10_768p");
      await page.locator("#h3NativeBaseline").click();
      assert.equal(await profile.inputValue(), "native");
      assert.equal(await page.locator("#steps").inputValue(), "20");
      assert.equal(await page.locator('[data-param="h3_attention_backend"] select').inputValue(), "pytorch");
      await page.locator("#h3Task").selectOption("control");
      assert.equal(await page.locator("#h3ControlVideo").isDisabled(), false);
      assert.equal(await page.locator("#h3SourceVideo").isDisabled(), true);
      const controlQuery = page.waitForRequest((req) => req.url().includes("/api/workflow?") && new URL(req.url()).searchParams.get("has_h3_control_video") === "1");
      await page.locator("#h3ControlVideo").setInputFiles({ name: "motion.mp4", mimeType: "video/mp4", buffer: Buffer.from("CPU fixture") });
      assert.equal(JSON.parse(new URL((await controlQuery).url()).searchParams.get("advanced")).h3_task, "control");
      await page.locator("#h3Task").selectOption("inpaint");
      assert.equal(await page.locator("#h3ControlVideo").isDisabled(), true);
      await page.locator("#h3SourceVideo").setInputFiles({ name: "source.mp4", mimeType: "video/mp4", buffer: Buffer.from("CPU fixture") });
      const maskQuery = page.waitForRequest((req) => req.url().includes("/api/workflow?") && new URL(req.url()).searchParams.get("has_h3_mask") === "1");
      await page.locator("#h3Mask").setInputFiles({ name: "mask.png", mimeType: "image/png", buffer: Buffer.from("CPU fixture") });
      const maskParams = new URL((await maskQuery).url()).searchParams;
      assert.equal(maskParams.get("has_h3_source_video"), "1");
      assert.equal(maskParams.get("has_h3_control_video"), "0");
      assert.equal(maskParams.get("h3_mask_is_video"), "0");
      const files = await page.locator("#h3Mask").evaluate((input) => {
        const data = new FormData(input.form);
        return { source: data.get("h3_source_video")?.name, mask: data.get("h3_mask")?.name, control: data.has("h3_control_video") };
      });
      assert.deepEqual(files, { source: "source.mp4", mask: "mask.png", control: false });
      await page.locator("#h3Tools").scrollIntoViewIfNeeded();
      await page.screenshot({ path: path.join(output, `creative-inpaint-${width}.png`) });
      await page.locator("#h3Task").selectOption("generate");
      await page.locator("#h3LatentUpscale").check();
      await page.locator('#sizePreset button[data-width="1920"]').click();
      assert.match(await page.locator("#h3ResolutionSummary").textContent(), /1920 × 1080/);
      await page.locator("#height").fill("720");
      assert.match(await page.locator("#h3ResolutionSummary").textContent(), /精修 1920 × 704/);
      await page.locator("#width").fill("1920");
      await page.locator("#height").fill("1088");
      assert.match(await page.locator("#h3ResolutionSummary").textContent(), /1280 × 736.*1920 × 1088.*1920 × 1080/);
      await page.locator("#h3Tools").scrollIntoViewIfNeeded();
      await page.screenshot({ path: path.join(output, `creative-upscale-${width}.png`) });
      await models.selectOption("minimax_h3_ref2va_int8_r2v");
      assert.equal(await page.locator('#h3Task option[value="control"]').evaluate((option) => option.disabled), true,
        await page.locator('#h3Task').evaluate((select) => select.outerHTML));
      await page.locator("#h3NativeBaseline").click();
      await models.selectOption("minimax_h3_fl2va_int8_t2v");
      await profile.selectOption("lightx8_v10_768p");
      await page.locator('[data-param="h3_acceleration_profile"]').scrollIntoViewIfNeeded();
      await page.screenshot({ path: path.join(output, `${width}.png`) });
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
      assert.equal(overflow, false, `Horizontal overflow at ${width}px`);
      assert.deepEqual(errors, [], `Console errors at ${width}px`);
      assert.equal(requests.some((url) => /\/(generate|prompt|video-smoke-test)$/.test(url.pathname)), false);
      await context.close();
      console.log(`PASS H3 profile UI ${width}px: values, status, requests, model switching, no overflow`);
    }
  } finally { await browser.close(); }
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
