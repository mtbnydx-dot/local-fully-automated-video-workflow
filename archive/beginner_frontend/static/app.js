const defaultPrompt = "";

const defaultNegative =
  "overexposed, low quality, blurry, jpeg artifacts, distorted hands, deformed face, extra fingers, warped screens, unreadable text, watermark, subtitles, flicker, jitter, chaotic background";

const nativeFetch = window.fetch.bind(window);
const serviceModeLabels = {
  both: "本机一体",
  server: "服务端",
  client: "客户端",
};

let serviceConfig = {
  mode: "both",
  mode_configured: false,
  first_run_required: true,
  server_url: "",
  api_base_url: "",
  access_token: "",
};

function cleanBaseUrl(value) {
  return String(value || "").trim().replace(/\/+$/, "");
}

function localApiPath(value) {
  const text = String(value || "");
  if (text.startsWith("/api/") || text === "/api") return true;
  try {
    const parsed = new URL(text, window.location.href);
    return parsed.origin === window.location.origin && (parsed.pathname.startsWith("/api/") || parsed.pathname === "/api");
  } catch (_) {
    return false;
  }
}

function rewriteApiUrl(value) {
  const base = cleanBaseUrl(serviceConfig?.api_base_url || serviceConfig?.server_url || "");
  if (!base || serviceConfig?.mode !== "client" || !localApiPath(value)) return value;
  const parsed = new URL(String(value), window.location.href);
  return `${base}${parsed.pathname}${parsed.search}${parsed.hash}`;
}

function isApiUrl(value) {
  return WorkbenchState.trustedApiUrl(value, window.location.origin,
    serviceConfig?.mode === "client" ? serviceConfig.api_base_url || serviceConfig.server_url : "");
}

function buildServiceFetchInput(input) {
  const sourceUrl =
    typeof input === "string"
      ? input
      : input instanceof URL
        ? input.href
        : input instanceof Request
          ? input.url
          : "";
  const rewritten = rewriteApiUrl(sourceUrl);
  if (!sourceUrl || rewritten === sourceUrl) return input;
  if (input instanceof Request) return new Request(rewritten, input);
  if (input instanceof URL) return new URL(rewritten);
  return rewritten;
}

window.fetch = (input, init = {}) => {
  const sourceUrl =
    typeof input === "string"
      ? input
      : input instanceof URL
        ? input.href
        : input instanceof Request
          ? input.url
          : "";
  const rewritten = rewriteApiUrl(sourceUrl);
  const nextInput = buildServiceFetchInput(input);
  const shouldAttachToken = isApiUrl(sourceUrl) || isApiUrl(rewritten);
  if (!shouldAttachToken || !serviceConfig?.access_token) {
    return nativeFetch(nextInput, init);
  }
  const headers = new Headers(init.headers || (input instanceof Request ? input.headers : undefined));
  if (!headers.has("X-Local-AI-Token") && !headers.has("X-WAN22-Token") && !headers.has("Authorization")) {
    headers.set("X-Local-AI-Token", serviceConfig.access_token);
  }
  return nativeFetch(nextInput, { ...init, headers });
};

function apiUrl(path) {
  return rewriteApiUrl(path);
}

function mediaUrl(path) {
  if (!path) return "";
  const text = String(path);
  if (/^https?:\/\//i.test(text) || text.startsWith("blob:") || text.startsWith("data:")) return text;
  const rewritten = apiUrl(text);
  // 客户端模式下 <img>/<video> 标签无法带请求头，媒体 GET 接口在服务端
  // 需要令牌，因此把令牌附在 query 上（与 EventSource 的做法一致）。
  if (serviceConfig?.mode === "client" && serviceConfig?.access_token && isApiUrl(text)) {
    try {
      const parsed = new URL(rewritten, window.location.href);
      if (!parsed.searchParams.has("token")) parsed.searchParams.set("token", serviceConfig.access_token);
      return parsed.toString();
    } catch (_) {
      return rewritten;
    }
  }
  return rewritten;
}

// Operation definitions; legacy keyframe links are normalized by setStep.
const steps = [
  {
    id: "keyframe",
    mode: "",
    title: "1. 关键帧（可选）",
    subtitle: "需要锁定首帧时再上传；不上传可直接使用文字生视频。",
    badge: "可选",
    goal:
      "上传图片可以稳定人物、空间、品牌风格和构图；没有参考图时可跳过，平台会优先切换到匹配的 T2V 模型。",
    sections: ["summary", "modelChoice", "prompt", "negative", "unrestricted", "image", "keyframePreview"],
    primary: "进入视频生成",
  },
  {
    id: "draft",
    mode: "",
    title: "视频生成",
    subtitle: "模型、画幅、时长和质量集中在同一步自由选择。",
    badge: "生成",
    goal:
      "选择与硬件和目标匹配的模型直接生成可用片段；建议先用短镜头确认运动，需要时再提高分辨率、时长或采样步数。",
    sections: [
      "summary",
      "modelChoice",
      "socialTarget",
      "project",
      "prompt",
      "negative",
      "unrestricted",
      "image",
      "referenceMedia",
      "endImage",
      "keyframePreview",
      "size",
      "duration",
      "fps",
      "steps",
      "cfg",
      "seed",
      "advanced",
      "pipeline",
      "videoTools",
    ],
    primary: "加入视频生成队列",
    defaults: { mode: "", steps: 12, cfg: 1.0 },
  },
  {
    id: "deflicker",
    mode: "deflicker",
    title: "修复与调色",
    subtitle: "稳定曝光与轻微纹理跳动，也可调整亮度、对比度、饱和度和锐度。",
    badge: "微调",
    goal:
      "这一关优先使用最近完成的视频。它会降低亮度闪烁、曝光跳动和轻微细节噪声，但不能修掉人物变形或物体乱变。",
    sections: ["summary", "modelChoice", "project", "videoTools"],
    primary: "开始均衡闪烁修复",
    defaults: { mode: "deflicker" },
  },
  {
    id: "rife",
    mode: "rife_2x",
    title: "流畅度增强",
    subtitle: "把最终片段插到更高帧率，运动更顺。",
    badge: "后期",
    goal:
      "这一关优先使用微调后的视频；如果没做微调，会使用最近完成的生成视频。RIFE 主要改善运动顺滑度。",
    sections: ["summary", "modelChoice", "project", "videoTools", "fps", "advanced"],
    primary: "开始插帧",
    defaults: { mode: "rife_2x", fps: 24 },
  },
  {
    id: "upscale",
    mode: "upscale_2x",
    title: "清晰度增强",
    subtitle: "优先用时序视频修复做 2x 超分，同时改善清晰度和连续帧稳定性。",
    badge: "超分",
    goal:
      "这一关优先使用插帧后的视频；如果没做插帧，会使用最近完成的视频。SeedVR2 画质更好但更慢，RealESRGAN 是更省显存的快速兼容档。",
    sections: ["summary", "modelChoice", "project", "videoTools", "targetResolution", "fps", "advanced"],
    primary: "开始清晰度增强",
    defaults: { mode: "upscale_2x", fps: 48 },
  },
  {
    id: "edit",
    mode: "stitch",
    title: "成片拼接",
    subtitle: "按顺序合并多个片段，直接输出完整 MP4。",
    badge: "合成",
    goal:
      "这一关使用本机 ffmpeg 统一画幅和帧率，再按列表顺序拼接。声音、转场、字幕和调色仍交给剪映、达芬奇或 PR。",
    sections: ["summary", "project", "clips", "size", "fps"],
    primary: "开始拼接",
    defaults: { mode: "stitch", fps: 24 },
  },
];

const pendingGenerationOption = {
  id: "pending_environment_video",
  label: "正在根据本机环境匹配视频模型",
  mode: "unsupported",
  status: "blocked",
  reason: "环境侦测完成后会显示所有兼容模型、输入能力和安装状态。",
  defaults: {},
  uses_image: false,
  image_optional: false,
  image_required: false,
  supported: false,
  group: "环境状态",
  model_label: "等待环境侦测",
  capabilities: {
    kind: "other",
    text_to_video: false,
    image_to_video: false,
    image_input: "none",
    native_audio: false,
    last_frame: false,
  },
  capability_labels: ["自动匹配中"],
  counterparts: {},
};

const fallbackModelOptions = {
  keyframe: [
    {
      id: "upload_keyframe",
      label: "上传关键帧（可选）",
      mode: "",
      status: "ok",
      reason: "有参考图就上传，没有也可直接进入文字生视频。",
      defaults: {},
      uses_image: true,
      supported: true,
      model_label: "上传关键帧（可选）",
    },
  ],
  draft: [
    pendingGenerationOption,
  ],
  final: [pendingGenerationOption],
  deflicker: [
    {
      id: "ffmpeg_deflicker_balanced",
      label: "ffmpeg deflicker + hqdn3d",
      mode: "deflicker",
      status: "ok",
      reason: "修曝光闪烁和轻微纹理跳动。",
      defaults: {},
      uses_image: false,
      supported: true,
      model_label: "ffmpeg deflicker + hqdn3d",
    },
  ],
  rife: [
    {
      id: "rife49_2x",
      label: "RIFE 4.9 2x",
      mode: "rife_2x",
      status: "ok",
      reason: "24fps 到 48fps。",
      defaults: { fps: 24 },
      uses_image: false,
      supported: true,
      rife_multiplier: 2,
      model_label: "RIFE 4.9 2x",
    },
  ],
  upscale: [
    {
      id: "realesrgan_x2plus",
      label: "RealESRGAN x2plus 快速兼容 2x",
      mode: "upscale_2x",
      status: "ok",
      reason: "成熟的逐帧快速 2x 超分。",
      defaults: { fps: 48 },
      uses_image: false,
      supported: true,
      scale: 2,
      upscale_model: "RealESRGAN_x2plus.pth",
      model_label: "RealESRGAN x2plus 2x",
    },
  ],
};

const fallbackRecommendedModels = {
  keyframe: "upload_keyframe",
  draft: "pending_environment_video",
  final: "pending_environment_video",
  deflicker: "ffmpeg_deflicker_balanced",
  rife: "rife49_2x",
  upscale: "realesrgan_x2plus",
};

const macFallbackModelOptions = fallbackModelOptions;
const macFallbackRecommendedModels = fallbackRecommendedModels;

const form = document.querySelector("#generateForm");
const statusStrip = document.querySelector("#statusStrip");
const statusText = document.querySelector("#statusText");
const modeInput = document.querySelector("#mode");
const stepTitle = document.querySelector("#stepTitle");
const stepSubtitle = document.querySelector("#stepSubtitle");
const stepBadge = document.querySelector("#stepBadge");
const stepGoal = document.querySelector("#stepGoal");
const topModelLabel = document.querySelector("#topModelLabel");
const topModelContext = document.querySelector("#topModelContext");
const promptInput = document.querySelector("#prompt");
const negativeInput = document.querySelector("#negative");
const imageInput = document.querySelector("#imageInput");
const referenceMediaInput = document.querySelector("#referenceMediaInput");
const referenceMediaList = document.querySelector("#referenceMediaList");
const referenceMediaCount = document.querySelector("#referenceMediaCount");
const socialPlatformSelect = document.querySelector("#socialPlatformSelect");
const socialQualitySwitch = document.querySelector("#socialQualitySwitch");
const socialQualityInput = document.querySelector("#socialQuality");
const socialAutoTune = document.querySelector("#socialAutoTune");
const socialSafeZoneToggle = document.querySelector("#socialSafeZoneToggle");
const socialGenerationSize = document.querySelector("#socialGenerationSize");
const socialDeliverySize = document.querySelector("#socialDeliverySize");
const socialDurationText = document.querySelector("#socialDurationText");
const socialTargetNote = document.querySelector("#socialTargetNote");
const socialSpecLink = document.querySelector("#socialSpecLink");
const videoUnrestrictedToggle = document.querySelector("#videoUnrestrictedToggle");
const adultContentAttestation = document.querySelector("#adultContentAttestation");
const adultContentAck = document.querySelector("#adultContentAck");
const videoUnrestrictedStatus = document.querySelector("#videoUnrestrictedStatus");
const videoUnrestrictedStrengthField = document.querySelector("#videoUnrestrictedStrengthField");
const videoUnrestrictedStrengthRange = document.querySelector("#videoUnrestrictedStrengthRange");
const videoUnrestrictedStrength = document.querySelector("#videoUnrestrictedStrength");
const videoUnrestrictedStrengthHelp = document.querySelector("#videoUnrestrictedStrengthHelp");
const videoInstallUnrestrictedButton = document.querySelector("#videoInstallUnrestrictedButton");
const videoUnrestrictedSource = document.querySelector("#videoUnrestrictedSource");
const videoNsfwExtras = document.querySelector("#videoNsfwExtras");
const videoMotionSwitch = document.querySelector("#videoMotionSwitch");
const videoMotionPreset = document.querySelector("#videoMotionPreset");
const videoSceneChips = document.querySelector("#videoSceneChips");
const videoAdultRecipeChips = document.querySelector("#videoAdultRecipeChips");
const videoAdultRecipeHint = document.querySelector("#videoAdultRecipeHint");
const videoMotionLoraChips = document.querySelector("#videoMotionLoraChips");
const videoAutoInjectTrigger = document.querySelector("#videoAutoInjectTrigger");
const videoAutoStripNegative = document.querySelector("#videoAutoStripNegative");
const videoTriggerPreview = document.querySelector("#videoTriggerPreview");
const videoCustomTrigger = document.querySelector("#videoCustomTrigger");
const videoCharacterSelect = document.querySelector("#videoCharacterSelect");
const videoCharacterSelectHelp = document.querySelector("#videoCharacterSelectHelp");
const videoMotionLoraPack = document.querySelector("#videoMotionLoraPack");
const videoToolsBlock = document.querySelector("#videoToolsBlock");
const videoExtractFrameButton = document.querySelector("#videoExtractFrameButton");
const videoExtractFrameToImageButton = document.querySelector("#videoExtractFrameToImageButton");
const videoExtractPreview = document.querySelector("#videoExtractPreview");
const videoFaceSwapIdentityFile = document.querySelector("#videoFaceSwapIdentityFile");
const videoFaceSwapBatchInput = document.querySelector("#videoFaceSwapBatchInput");
const videoFaceSwapBatchSummary = document.querySelector("#videoFaceSwapBatchSummary");
const videoFaceSwapFallbackSource = document.querySelector("#videoFaceSwapFallbackSource");
const videoFaceSwapWeightRange = document.querySelector("#videoFaceSwapWeightRange");
const videoFaceSwapWeight = document.querySelector("#videoFaceSwapWeight");
const videoFaceSwapFps = document.querySelector("#videoFaceSwapFps");
const videoFaceSwapSubmitButton = document.querySelector("#videoFaceSwapSubmitButton");
const videoFaceSwapInstallButton = document.querySelector("#videoFaceSwapInstallButton");
const videoFaceSwapModuleBadge = document.querySelector("#videoFaceSwapModuleBadge");
const videoFaceSwapStandaloneStatus = document.querySelector("#videoFaceSwapStandaloneStatus");
const videoFaceSwapJobBadge = document.querySelector("#videoFaceSwapJobBadge");
const videoFaceSwapProgressLabel = document.querySelector("#videoFaceSwapProgressLabel");
const videoFaceSwapProgressPercent = document.querySelector("#videoFaceSwapProgressPercent");
const videoFaceSwapProgressShell = document.querySelector("#videoFaceSwapProgressShell");
const videoFaceSwapProgressBar = document.querySelector("#videoFaceSwapProgressBar");
const videoFaceSwapQueueCount = document.querySelector("#videoFaceSwapQueueCount");
const videoFaceSwapQueueList = document.querySelector("#videoFaceSwapQueueList");
const videoFaceSwapResultView = document.querySelector("#videoFaceSwapResultView");
const videoFaceSwapCancelButton = document.querySelector("#videoFaceSwapCancelButton");
const videoFaceSwapLog = document.querySelector("#videoFaceSwapLog");
const videoTuneFlickerPreset = document.querySelector("#videoTuneFlickerPreset");
const videoTuneBrightness = document.querySelector("#videoTuneBrightness");
const videoTuneContrast = document.querySelector("#videoTuneContrast");
const videoTuneSaturation = document.querySelector("#videoTuneSaturation");
const videoTuneSharpness = document.querySelector("#videoTuneSharpness");
const videoTuneSubmitButton = document.querySelector("#videoTuneSubmitButton");
const pipelineTuneToggle = document.querySelector("#pipelineTune");
const pipelineRifeToggle = document.querySelector("#pipelineRife");
const pipelineUpscaleToggle = document.querySelector("#pipelineUpscale");
const videoTemporalStability = document.querySelector("#videoTemporalStability");
const batchKeyframeInput = document.querySelector("#batchKeyframeInput");
const videoInput = document.querySelector("#videoInput");
const clipsInput = document.querySelector("#clipsInput");
const stitchClipList = document.querySelector("#stitchClipList");
const stepsInput = document.querySelector("#steps");
const cfgInput = document.querySelector("#cfg");
const widthInput = document.querySelector("#width");
const heightInput = document.querySelector("#height");
const sizeHelp = document.querySelector("#sizeHelp");
const lengthInput = document.querySelector("#length");
const fpsInput = document.querySelector("#fps");
const durationHelp = document.querySelector("#durationHelp");
const fpsHelp = document.querySelector("#fpsHelp");
const cfgHelp = document.querySelector("#cfgHelp");
const seedInput = document.querySelector("#seed");
const sourceVideoFilename = document.querySelector("#sourceVideoFilename");
const sourceVideoSubfolder = document.querySelector("#sourceVideoSubfolder");
const sourceVideoType = document.querySelector("#sourceVideoType");
const sourceImageFilename = document.querySelector("#sourceImageFilename");
const sourceImagePreviewUrl = document.querySelector("#sourceImagePreviewUrl");
const sourceImageLabel = document.querySelector("#sourceImageLabel");
const sourceResolutionText = document.querySelector("#sourceResolutionText");
const targetResolutionLabel = document.querySelector("#targetResolutionLabel");
const targetResolutionText = document.querySelector("#targetResolutionText");
const targetResolutionNote = document.querySelector("#targetResolutionNote");
const environmentSummary = document.querySelector("#environmentSummary");
const environmentCards = document.querySelector("#environmentCards");
const modelRecommendations = document.querySelector("#modelRecommendations");
const loadDiagnostics = document.querySelector("#loadDiagnostics");
const missingItems = document.querySelector("#missingItems");
const smallModelRoutes = document.querySelector("#smallModelRoutes");
const prerequisiteChecks = document.querySelector("#prerequisiteChecks");
const bootstrapCards = document.querySelector("#bootstrapCards");
const hfEndpointInput = document.querySelector("#hfEndpointInput");
const pipIndexInput = document.querySelector("#pipIndexInput");
const proxyUrlInput = document.querySelector("#proxyUrlInput");
const downloadRegionOptions = document.querySelector("#downloadRegionOptions");
const openSourceConfigButton = document.querySelector("#openSourceConfigButton");
const openSourceConfigInlineButton = document.querySelector("#openSourceConfigInlineButton");
const closeSourceConfigButton = document.querySelector("#closeSourceConfigButton");
const sourceConfigModal = document.querySelector("#sourceConfigModal");
const sourceConfigBackdrop = document.querySelector("#sourceConfigBackdrop");
const downloadSourceBrief = document.querySelector("#downloadSourceBrief");
const downloadSourceDetail = document.querySelector("#downloadSourceDetail");
const installProfileHint = document.querySelector("#installProfileHint");
const fullSetupScope = document.querySelector("#fullSetupScope");
const workflowInstallScope = document.querySelector("#workflowInstallScope");
const modelCatalog = document.querySelector("#modelCatalog");
const modelSyncPanel = document.querySelector("#modelSyncPanel");
const modelCatalogSelector = document.querySelector("#modelCatalogSelector");
const modelCatalogNativeOnly = document.querySelector("#modelCatalogNativeOnly");
const modelCatalogSearch = document.querySelector("#modelCatalogSearch");
const modelCatalogReadyFilter = document.querySelector("#modelCatalogReadyFilter");
const modelCatalogCount = document.querySelector("#modelCatalogCount");
const modelCatalogFamilyFilter = document.querySelector("#modelCatalogFamilyFilter");
const modelCatalogQuantFilter = document.querySelector("#modelCatalogQuantFilter");
const envGoGenerateButton = document.querySelector("#envGoGenerateButton");
const downloadCenterGoGenerateButton = document.querySelector("#downloadCenterGoGenerate");
const saveDownloadSettingsButton = document.querySelector("#saveDownloadSettingsButton");
const testDownloadSourcesButton = document.querySelector("#testDownloadSourcesButton");
const downloadSourceStatus = document.querySelector("#downloadSourceStatus");
const refreshBootstrapButton = document.querySelector("#refreshBootstrapButton");
const installComfyButton = document.querySelector("#installComfyButton");
const startComfyButton = document.querySelector("#startComfyButton");
const detectEnvironmentButton = document.querySelector("#detectEnvironmentButton");
const runFullSetupButton = document.querySelector("#runFullSetupButton");
const runSelfTestButton = document.querySelector("#runSelfTestButton");
const runVideoSmokeButton = document.querySelector("#runVideoSmokeButton");
const installMissingButton = document.querySelector("#installMissingButton");
const enterWorkflowButton = document.querySelector("#enterWorkflowButton");
const installProfileSelector = document.querySelector("#installProfileSelector");
const modelStoragePreset = document.querySelector("#modelStoragePreset");
const modelDownloadPath = document.querySelector("#modelDownloadPath");
const modelStorageStatus = document.querySelector("#modelStorageStatus");
const modelSelector = document.querySelector("#modelSelector");
const modelCapabilityChips = document.querySelector("#modelCapabilityChips");
const videoModelInstallButton = document.querySelector("#videoModelInstallButton");
const modelChoiceHint = document.querySelector("#modelChoiceHint");
const workflowStatus = document.querySelector("#workflowStatus");
const modelLabelInput = document.querySelector("#modelLabel");
const modelProfileInput = document.querySelector("#modelProfile");
const upscaleModelInput = document.querySelector("#upscaleModel");
const upscaleScaleInput = document.querySelector("#upscaleScale");
const rifeMultiplierInput = document.querySelector("#rifeMultiplier");
const keyframeInputLabel = document.querySelector("#keyframeInputLabel");
const keyframeInputHelp = document.querySelector("#keyframeInputHelp");
const endImageField = document.querySelector("#endImageField");
const endImageInput = document.querySelector("#endImageInput");
const videoAdvancedPanel = document.querySelector('[data-section="advanced"]');
const videoAdvancedGroups = document.querySelector("#videoAdvancedGroups");
const videoAdvancedSummary = document.querySelector("#videoAdvancedSummary");
const videoAdvancedInput = document.querySelector("#videoAdvancedInput");
const videoAdvancedReset = document.querySelector("#videoAdvancedReset");
const primaryButton = document.querySelector("#primaryButton");
const validateButton = document.querySelector("#validateButton");
const backButton = document.querySelector("#backButton");
const continueButton = document.querySelector("#continueButton");
const repeatButton = document.querySelector("#repeatButton");
const copyDiagnosticsButton = document.querySelector("#copyDiagnosticsButton");
const downloadDiagnosticsButton = document.querySelector("#downloadDiagnosticsButton");
const jobStatus = document.querySelector("#jobStatus");
const jobMeta = document.querySelector("#jobMeta");
const resultHint = document.querySelector("#resultHint");
const resultView = document.querySelector("#resultView");
const progressBar = document.querySelector("#progressBar");
const videoProgressShell = document.querySelector("#videoProgressShell");
const videoProgressLabel = document.querySelector("#videoProgressLabel");
const videoProgressPercent = document.querySelector("#videoProgressPercent");
const videoTaskQueueCount = document.querySelector("#videoTaskQueueCount");
const videoTaskQueueList = document.querySelector("#videoTaskQueueList");
const videoCancelJobButton = document.querySelector("#videoCancelJobButton");
const logBox = document.querySelector("#logBox");
const keyframePreview = document.querySelector("#keyframePreview");
const servicePanel = document.querySelector("#servicePanel");
const serviceModeBadge = document.querySelector("#serviceModeBadge");
const serviceFirstRun = document.querySelector("#serviceFirstRun");
const serviceServerUrl = document.querySelector("#serviceServerUrl");
const serviceAccessToken = document.querySelector("#serviceAccessToken");
const serviceLocalUrl = document.querySelector("#serviceLocalUrl");
const serviceLanUrl = document.querySelector("#serviceLanUrl");
const serviceApiUrl = document.querySelector("#serviceApiUrl");
const saveServiceConfigButton = document.querySelector("#saveServiceConfigButton");
const reloadServiceConfigButton = document.querySelector("#reloadServiceConfigButton");
const serviceStatus = document.querySelector("#serviceStatus");
const serviceModeInputs = Array.from(document.querySelectorAll('input[name="serviceMode"]'));
const envProgressSummary = document.querySelector("#envProgressSummary");
const envInstallFiles = document.querySelector("#envInstallFiles");
const envInstallControls = document.querySelector("#envInstallControls");
const envPauseInstallButton = document.querySelector("#envPauseInstallButton");
const envResumeInstallButton = document.querySelector("#envResumeInstallButton");
const envCancelInstallButton = document.querySelector("#envCancelInstallButton");

let activeIndex = 1;
let activeJobId = null;
let activeJobEvents = null;
let sseHealthyJobId = null;
const ACTIVE_JOB_STORAGE_KEY = "local-ai-workbench.activeJob.v1";
const ACTIVE_JOBS_STORAGE_KEY = "local-ai-workbench.activeJobs.v2";
const INSTALL_JOB_STORAGE_KEY = "local-ai-workbench.installJob.v2";
const MODEL_DOWNLOAD_PATH_STORAGE_KEY = "modelDownloadPath.v1";
const VIDEO_CHARACTER_STORAGE_KEY = "local-ai-workbench.video.characterId";
const IMAGE_CHARACTER_STORAGE_KEY = "local-ai-workbench.image.characterId";
const ADULT_WIZARD_STORAGE_KEY = "local-ai-workbench.adult.wizardId";
const FACE_AUTH_STORAGE_KEY = "local-ai-workbench.face.authToken";

function migrateLocalStorageKey(nextKey, legacyKeys) {
  if (localStorage.getItem(nextKey) != null) return;
  const legacyKey = legacyKeys.find((key) => localStorage.getItem(key) != null);
  if (legacyKey) localStorage.setItem(nextKey, localStorage.getItem(legacyKey));
}

migrateLocalStorageKey(ACTIVE_JOB_STORAGE_KEY, ["wan22.activeJob.v1"]);
migrateLocalStorageKey(ACTIVE_JOBS_STORAGE_KEY, ["wan22.activeJobs.v2"]);
migrateLocalStorageKey(INSTALL_JOB_STORAGE_KEY, ["wan22.installJob.v2"]);
let completedSteps = new Set();
const workflowState = WorkbenchState.create();
const submissionContexts = new Map();
const stepParameters = new Map();
let environmentRequestId = 0;
let environmentRefreshPromise = null;
let preflightRequestId = 0;
let lastDraftVideo = null;
let lastFinalVideo = null;
let lastDeflickerVideo = null;
let lastRifeVideo = null;
let lastUpscaleVideo = null;
let lastStitchedVideo = null;
let lastFaceSwapVideo = null;
let currentVideoResolution = null;
let environmentData = null;
let socialPresetData = null;
let modelCatalogData = { items: [], families: [], quantizations: [], source_presets: [] };
let selectedCatalogModelId = "";
let syncingCatalogSelection = false;
let pendingCatalogModelId = "";
let pendingCatalogWorkflowOptionId = "";
let downloadSettingsDirty = false;
let selectedModels = {};
let currentVideoFps = 24;
let workflowCheckController = null;
let workflowPreflightTimer = null;
let bootstrapData = null;
let selectedInstallProfile = "auto";
let installPlanRequestId = 0;
let allowComfyInstall = false;
let allowFullSetup = false;
let allowWorkflowAssetInstall = false;
let stitchFiles = [];
let sourceModalReturnFocus = null;
let appInitialized = false;
let activeInstallControlJobId = "";
let oneClickInstallStarting = false;
const pendingInstallRequirementConfirms = new Set();
let modelStorageTimer = null;
let lastExtractedVideoFrame = null;
let batchKeyframeQueue = [];
const activeVideoJobIds = new Set();
const videoJobCache = new Map();
const videoJobSteps = new Map();
const processedVideoTerminalJobs = new Set();
let videoPollInFlight = false;
let videoSubmitting = false;
let activeVideoFaceSwapJobId = null;
let videoFaceSwapCapabilityReady = null;
let videoFaceSwapCapabilityLoading = false;
let videoFaceSwapSubmitting = false;

// 主视图 Tab：视频工作流 / 独立文生图 / 独立视频换脸 / 环境与安装。
let activeView = "environment";
let videoFaceSwapSavedTopModelLabel = "";
let videoFaceSwapSavedTopModelTitle = "";

let lastProcessingOperation = "deflicker";
let pendingSourceOperation = "";
let parameterLevel = "basic";
let creationDraftTimer = null;
let uploadedPreview = { file: null, url: "" };

// ---- 后期流水线：勾选的步骤在上一步成功后自动提交，失败即停 ----
const PIPELINE_STATE_KEY = "workbench.post_pipeline";
const PIPELINE_TOGGLES = [
  ["deflicker", pipelineTuneToggle],
  ["rife", pipelineRifeToggle],
  ["upscale", pipelineUpscaleToggle],
];

function persistPipelineState() {
  try {
    localStorage.setItem(
      PIPELINE_STATE_KEY,
      JSON.stringify(Object.fromEntries(PIPELINE_TOGGLES.map(([stepId, input]) => [stepId, Boolean(input?.checked)]))),
    );
  } catch (_) {
    /* ignore */
  }
}

function restorePipelineState() {
  let saved = {};
  try {
    saved = JSON.parse(localStorage.getItem(PIPELINE_STATE_KEY) || "{}") || {};
  } catch (_) {
    saved = {};
  }
  for (const [stepId, input] of PIPELINE_TOGGLES) {
    if (input && typeof saved[stepId] === "boolean") input.checked = saved[stepId];
  }
}

restorePipelineState();
PIPELINE_TOGGLES.forEach(([, input]) => input?.addEventListener("change", persistPipelineState));

function nextPipelineStep(afterStep) {
  const order = PIPELINE_TOGGLES.map(([stepId]) => stepId);
  const startIndex = afterStep === "draft" ? 0 : order.indexOf(afterStep) + 1;
  if (startIndex <= 0 && afterStep !== "draft") return null;
  for (let index = startIndex; index < PIPELINE_TOGGLES.length; index += 1) {
    if (PIPELINE_TOGGLES[index][1]?.checked) return PIPELINE_TOGGLES[index][0];
  }
  return null;
}

// 统一注册所有轮询定时器，便于按视图/步骤/卸载统一清理。
const POLL_TIMERS = {
  poll: null,
  install: null,
  bootstrap: null,
  fullSetup: null,
  selfTest: null,
  videoSmoke: null,
};

function clearPollTimer(key) {
  if (POLL_TIMERS[key]) {
    clearInterval(POLL_TIMERS[key]);
    POLL_TIMERS[key] = null;
  }
}

function closeJobEvents() {
  if (activeJobEvents) {
    activeJobEvents.close();
    activeJobEvents = null;
  }
  sseHealthyJobId = null;
}

function stopJobWatch() {
  clearPollTimer("poll");
  closeJobEvents();
}

function persistActiveVideoJobs() {
  try {
    const items = [...activeVideoJobIds].map((jobId) => ({
      jobId,
      stepId: videoJobSteps.get(jobId) || "draft",
    }));
    localStorage.setItem(ACTIVE_JOBS_STORAGE_KEY, JSON.stringify(items));
    if (activeJobId && activeVideoJobIds.has(activeJobId)) {
      localStorage.setItem(ACTIVE_JOB_STORAGE_KEY, JSON.stringify({
        jobId: activeJobId,
        stepId: videoJobSteps.get(activeJobId) || "draft",
      }));
    } else {
      localStorage.removeItem(ACTIVE_JOB_STORAGE_KEY);
    }
  } catch (_error) {
    // Private browsing can disable storage; live tracking still works.
  }
}

function rememberActiveJob(jobId, stepId, job = null) {
  if (!jobId) return;
  const normalizedStep = stepId === "final" ? "draft" : (stepId || "draft");
  activeVideoJobIds.add(jobId);
  videoJobSteps.set(jobId, normalizedStep);
  if (job) videoJobCache.set(jobId, job);
  if (normalizedStep === "face_swap" || job?.mode === "video_face_swap") {
    activeVideoFaceSwapJobId = jobId;
  }
  activeJobId = jobId;
  persistActiveVideoJobs();
  renderVideoTaskQueue();
  startActiveVideoPolling();
}

function readRememberedJobs() {
  try {
    const items = JSON.parse(localStorage.getItem(ACTIVE_JOBS_STORAGE_KEY) || "null");
    if (Array.isArray(items)) {
      return items
        .filter((item) => item && typeof item.jobId === "string")
        .map((item) => ({ ...item, stepId: item.stepId === "final" ? "draft" : (item.stepId || "draft") }));
    }
    const legacy = JSON.parse(localStorage.getItem(ACTIVE_JOB_STORAGE_KEY) || "null");
    return legacy && typeof legacy.jobId === "string"
      ? [{ ...legacy, stepId: legacy.stepId === "final" ? "draft" : (legacy.stepId || "draft") }]
      : [];
  } catch (_error) {
    return [];
  }
}

function readRememberedJob() {
  return readRememberedJobs().find((item) => item.jobId === activeJobId) || readRememberedJobs()[0] || null;
}

function forgetActiveJob(jobId = activeJobId) {
  if (!jobId) return;
  activeVideoJobIds.delete(jobId);
  videoJobSteps.delete(jobId);
  persistActiveVideoJobs();
  renderVideoTaskQueue();
  if (!activeVideoJobIds.size) clearPollTimer("poll");
}

function clearAllPollTimers(except = null) {
  for (const key of Object.keys(POLL_TIMERS)) {
    if (key !== except) clearPollTimer(key);
  }
  if (except !== "poll") closeJobEvents();
}

// 环境状态条：工作流 Tab 顶部显示环境就绪状态，点击跳转环境 Tab。
function updateEnvStatusBar() {
  const dot = document.getElementById("envStatusDot");
  const text = document.getElementById("envStatusText");
  if (!dot || !text) return;
  if (!environmentData) {
    dot.className = "env-status-dot pending";
    text.textContent = "环境未检测";
    return;
  }
  const connected = environmentData?.comfy?.connected === true;
  const option = selectedModelOption(currentStep().id === "keyframe" ? "draft" : currentStep().id);
  if (["deflicker", "stitch"].includes(option?.mode || currentStep().mode)) {
    dot.className = "env-status-dot pending";
    text.textContent = "本地后期 · 提交前检查 FFmpeg 和输入素材";
  } else if (option?.mode?.startsWith("fal_")) {
    dot.className = "env-status-dot pending";
    text.textContent = "云端模型 · 提交前检查密钥与计费条件";
  } else if (connected && option?.supported !== false && option?.status !== "blocked") {
    dot.className = "env-status-dot ok";
    text.textContent = "ComfyUI 已连接 · 当前模型提交前仍需工作流预检";
  } else if (connected) {
    dot.className = "env-status-dot warn";
    text.textContent = "ComfyUI 已连接 · 当前模型依赖待准备";
  } else {
    dot.className = "env-status-dot bad";
    text.textContent = "ComfyUI 未连接";
  }
}

function setView(view) {
  if (view === "process") { navigateWorkspace(view); return; }
  if (!document.querySelector(`.view[data-view="${view}"]`)) return;
  if (view === activeView) return;
  const previousView = activeView;
  if (previousView === "video-face-swap" && view !== "video-face-swap" && topModelLabel && videoFaceSwapSavedTopModelLabel) {
    topModelLabel.textContent = videoFaceSwapSavedTopModelLabel;
    topModelLabel.title = videoFaceSwapSavedTopModelTitle;
    videoFaceSwapSavedTopModelLabel = "";
    videoFaceSwapSavedTopModelTitle = "";
  }
  activeView = view;
  try { localStorage.setItem("workbench.active-view", view); } catch (_) {}
  if (topModelContext) {
    topModelContext.textContent =
      view === "image-studio"
        ? "文生图与视频联动"
        : view === "video-face-swap"
          ? "独立视频后期工具"
        : view === "download-center"
          ? "下载任务与本地资源"
        : view === "environment"
          ? "模型、下载与运行诊断"
          : "分镜生成与成片";
  }
  syncJourneyNavigation();
  document.querySelectorAll(".view").forEach((v) => {
    v.classList.toggle("hidden", v.dataset.view !== view);
  });
  if (view === "environment") {
    refreshEnvironmentWorkspace();
  } else if (view === "workflow" || view === "video-face-swap") {
    if (view === "workflow") { updateEnvStatusBar(); renderStepIdle(); }
    if (view === "video-face-swap") {
      renderVideoCharacterSelect();
      updateVideoFaceSwapSourceSummary();
      void refreshVideoFaceSwapCapability();
    }
    if (activeVideoJobIds.size && !activeJobEvents && !POLL_TIMERS.poll) {
      const preferredJobId = view === "video-face-swap" ? activeVideoFaceSwapJobId : activeJobId;
      const targetJobId = activeVideoJobIds.has(preferredJobId) ? preferredJobId : [...activeVideoJobIds][0];
      watchJob(targetJobId, videoJobSteps.get(targetJobId) || currentStep().id);
    }
  }
  // Task tracking belongs to the application, not the currently visible tab.
  if (activeVideoJobIds.size) startActiveVideoPolling();
  if (view === "library") loadOutputs();
  if (view === "tasks") loadRecentJobs(false);
  window.dispatchEvent(new CustomEvent("workspace:viewchange", { detail: { view } }));
  if (["tasks", "library"].includes(view) && topModelLabel) {
    topModelLabel.textContent = view === "tasks" ? "任务中心" : "作品库";
    topModelLabel.title = topModelLabel.textContent;
  } else if (view === "workflow") updateGlobalModelContext();
  if (view === "video-face-swap" && topModelLabel) {
    videoFaceSwapSavedTopModelLabel = topModelLabel.textContent;
    videoFaceSwapSavedTopModelTitle = topModelLabel.title;
    topModelLabel.textContent = "ReActor 视频换脸";
    topModelLabel.title = "ReActor 视频换脸";
  }
}

function requestStepChange(stepId) {
  setStep(stepId);
}

function navigateWorkspace(view) {
  const target = WorkbenchJourney.route(view, lastProcessingOperation);
  if (target.view === "workflow") setStep(target.step, { focus: false });
  setView(target.view);
  syncJourneyNavigation();
}

function syncJourneyNavigation() {
  const processing = WorkbenchJourney.tools.includes(currentStep().id);
  const view = activeView === "workflow" && processing ? "process" : activeView;
  const workspace = document.querySelector(".view-workflow");
  workspace.dataset.task = processing ? "process" : "video";
  workspace.dataset.parameters = parameterLevel;
  document.querySelector("#creationTaskTitle").textContent = processing ? "视频处理" : "视频生成";
  document.querySelectorAll(".view-tab").forEach((button) => {
    const active = button.dataset.view === view;
    button.classList.toggle("active", active);
    button.setAttribute("aria-current", active ? "page" : "false");
  });
  document.querySelectorAll("#parameterLevel button").forEach((button) => {
    const active = button.dataset.level === parameterLevel;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  if (activeView === "workflow" && topModelContext) topModelContext.textContent = processing ? "已有视频后期" : "文字、图片与参考素材";
  if (appInitialized) {
    try { localStorage.setItem(`${workflowStorageKey()}:journey`, JSON.stringify({ view, operation: lastProcessingOperation, parameterLevel })); } catch (_) {}
  }
}

function persistCreationDraft() {
  if (!appInitialized) return;
  saveStepParameters();
  try {
    localStorage.setItem(`${workflowStorageKey()}:draft`, JSON.stringify({
      parameters: [...stepParameters], models: selectedModels,
      fields: Object.fromEntries(["prompt", "negative", "projectTag"].map((id) => [id, document.getElementById(id)?.value || ""])),
    }));
  } catch (_) {}
}

function restoreCreationDraft() {
  try {
    const saved = JSON.parse(localStorage.getItem(`${workflowStorageKey()}:draft`) || "null");
    if (!saved) return;
    for (const [id, value] of saved.parameters || []) {
      if (steps.some((step) => step.id === id) && value?.values && Array.isArray(value.advanced)) stepParameters.set(id, value);
    }
    Object.assign(selectedModels, saved.models || {});
    for (const id of ["prompt", "negative", "projectTag"]) {
      if (typeof saved.fields?.[id] === "string") document.getElementById(id).value = saved.fields[id];
    }
  } catch (_) {}
}

function renderResultActions() {
  const result = workflowState.outputs[currentStep().id];
  const latest = workflowState.latest[currentStep().id];
  const ready = Boolean(result && (!latest || result.jobId === latest));
  document.querySelector("#resultActions").classList.toggle("hidden", !ready);
  document.querySelector("#resultActionSource").textContent = ready ? result.filename : "";
  continueButton.classList.toggle("hidden", !ready);
}

function useVideoForOperation(media, operation) {
  if (!media?.filename || !WorkbenchJourney.tools.includes(operation)) return;
  WorkbenchState.adopt(workflowState, media);
  videoInput.value = "";
  currentVideoResolution = media.width && media.height ? { width: media.width, height: media.height } : null;
  syncWorkflowOutputs();
  persistWorkflowState();
  setStep(operation);
  setView("workflow");
}

const comfyInstallButtonText = "安装/更新 ComfyUI";
const comfyInstallConfirmText = "确认安装/更新 ComfyUI";
const fullSetupButtonText = "一键准备环境";
const fullSetupConfirmText = "确认一键准备";
const workflowAssetButtonText = "一键安装/修复缺失项";
const workflowAssetConfirmText = "确认安装/修复缺失项";

function setComfyInstallConfirming(value) {
  allowComfyInstall = Boolean(value);
  if (installComfyButton) {
    installComfyButton.textContent = allowComfyInstall ? comfyInstallConfirmText : comfyInstallButtonText;
  }
}

function setFullSetupConfirming(value) {
  allowFullSetup = Boolean(value);
  if (runFullSetupButton) {
    runFullSetupButton.textContent = allowFullSetup ? fullSetupConfirmText : fullSetupButtonText;
  }
}

function setWorkflowAssetInstallConfirming(value) {
  allowWorkflowAssetInstall = Boolean(value);
  if (installMissingButton) {
    installMissingButton.textContent = allowWorkflowAssetInstall ? workflowAssetConfirmText : workflowAssetButtonText;
  }
}

function normalizeServicePayload(payload = {}) {
  const mode = serviceModeLabels[payload.mode] ? payload.mode : "both";
  return {
    ...serviceConfig,
    ...payload,
    mode,
    server_url: cleanBaseUrl(payload.server_url || ""),
    api_base_url: cleanBaseUrl(payload.api_base_url || (mode === "client" ? payload.server_url : "")),
    access_token: String(payload.access_token || ""),
  };
}

function selectedServiceMode() {
  return serviceModeInputs.find((input) => input.checked)?.value || serviceConfig.mode || "both";
}

function setServiceButtonsDisabled(disabled) {
  if (saveServiceConfigButton) saveServiceConfigButton.disabled = disabled;
  if (reloadServiceConfigButton) reloadServiceConfigButton.disabled = disabled;
}

function syncServiceInputs(config, { force = false } = {}) {
  serviceModeInputs.forEach((input) => {
    input.checked = input.value === config.mode;
    input.closest(".service-mode-card")?.classList.toggle("active", input.checked);
  });
  if (serviceServerUrl && (force || document.activeElement !== serviceServerUrl)) {
    serviceServerUrl.value = config.server_url || "";
  }
  if (serviceAccessToken && (force || document.activeElement !== serviceAccessToken)) {
    serviceAccessToken.value = config.access_token || "";
  }
  if (serviceServerUrl) {
    serviceServerUrl.disabled = config.mode !== "client";
    serviceServerUrl.required = config.mode === "client";
  }
}

function serviceStatusMessage(config) {
  if (config.mode === "client") {
    if (!config.server_url) return "客户端模式需要填写服务端地址，例如 http://192.168.1.20:7860。";
    return `客户端模式已启用。生成、安装、自检和诊断 API 会提交到 ${config.server_url}。`;
  }
  if (!config.mode_configured) {
    return "当前使用默认本机一体模式。保存后会固定为开箱入口，并自动准备局域网访问令牌。";
  }
  if (config.binds_lan) {
    return `服务端监听已配置。局域网电脑可打开 ${config.lan_url || "本机显示的 LAN 地址"}，写操作需要访问令牌。`;
  }
  return "服务端模式已保存；请重启 start.bat 让前端监听局域网地址。";
}

function renderServiceConfig(config = serviceConfig, { message = "", state = "" } = {}) {
  if (!servicePanel) return;
  serviceConfig = normalizeServicePayload(config);
  syncServiceInputs(serviceConfig);
  const label = serviceModeLabels[serviceConfig.mode] || "未知";
  if (serviceModeBadge) {
    serviceModeBadge.textContent = serviceConfig.mode_configured ? label : `${label} · 待保存`;
  }
  serviceFirstRun?.classList.toggle("hidden", !serviceConfig.first_run_required);
  // 第一次运行需要用户保存模式，自动展开收纳抽屉引导视线。
  if (serviceConfig.first_run_required) document.querySelector("#serviceDrawer")?.setAttribute("open", "");
  if (serviceLocalUrl) serviceLocalUrl.textContent = serviceConfig.local_url || "本机启动后显示";
  if (serviceLanUrl) {
    if (serviceConfig.first_run_required) {
      serviceLanUrl.textContent = "保存并重启后显示";
    } else if (serviceConfig.mode === "client") {
      serviceLanUrl.textContent = "客户端不监听局域网";
    } else {
      serviceLanUrl.textContent = serviceConfig.lan_url || "重启服务端模式后显示";
    }
  }
  if (serviceApiUrl) {
    serviceApiUrl.textContent = serviceConfig.mode === "client" ? serviceConfig.server_url || "未填写" : "本机后端";
  }
  if (serviceStatus) {
    const statusState =
      state ||
      (serviceConfig.mode === "client" && !serviceConfig.server_url
        ? "bad"
        : serviceConfig.first_run_required
          ? "pending"
          : "ok");
    serviceStatus.className = `workflow-status ${statusState}`;
    serviceStatus.textContent = message || serviceStatusMessage(serviceConfig);
  }
}

function previewServiceConfig() {
  renderServiceConfig({
    ...serviceConfig,
    mode: selectedServiceMode(),
    server_url: serviceServerUrl?.value.trim() || "",
    access_token: serviceAccessToken?.value.trim() || serviceConfig.access_token || "",
  });
}

async function loadClientConfig({ quiet = true, pingRemote = false } = {}) {
  try {
    const response = await nativeFetch("/api/client-config", { cache: "no-store" });
    const data = await response.json();
    if (!response.ok) throw new Error(formatError(data.detail || data));
    renderServiceConfig(data.service || {}, { state: data.service?.first_run_required ? "pending" : "ok" });
    if (!quiet) appendLog("运行入口配置已刷新。");
    if (pingRemote && serviceConfig.mode === "client" && serviceConfig.server_url) {
      await checkRemoteService();
    }
    return serviceConfig;
  } catch (error) {
    if (serviceStatus) {
      serviceStatus.className = "workflow-status bad";
      serviceStatus.textContent = `运行入口配置读取失败：${error.message}`;
    }
    if (!quiet) appendLog(`运行入口配置读取失败：${error.message}`);
    return serviceConfig;
  }
}

async function checkRemoteService() {
  if (serviceConfig.mode !== "client" || !serviceConfig.server_url) return;
  if (serviceStatus) {
    serviceStatus.className = "workflow-status pending";
    serviceStatus.textContent = `正在连接服务端 ${serviceConfig.server_url}。`;
  }
  try {
    const response = await fetch("/api/health", { cache: "no-store" });
    const data = await response.json();
    if (!response.ok) throw new Error(formatError(data.detail || data));
    if (serviceStatus) {
      serviceStatus.className = "workflow-status ok";
      serviceStatus.textContent = `服务端已连接：${data.service?.mode || "server"}，ComfyUI ${data.comfy_connected ? "已连接" : "未连接"}。`;
    }
  } catch (error) {
    if (serviceStatus) {
      serviceStatus.className = "workflow-status bad";
      serviceStatus.textContent = `服务端连接失败：${error.message}`;
    }
  }
}

async function saveServiceConfig() {
  if (!saveServiceConfigButton) return;
  setServiceButtonsDisabled(true);
  if (serviceStatus) {
    serviceStatus.className = "workflow-status pending";
    serviceStatus.textContent = "正在保存运行入口配置。";
  }
  const payload = {
    mode: selectedServiceMode(),
    server_url: serviceServerUrl?.value.trim() || "",
    access_token: serviceAccessToken?.value.trim() || "",
  };
  try {
    const response = await nativeFetch("/api/service-config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ service: payload }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(formatError(data.detail || data));
    const restartText = data.restart_required ? " 保存成功；请重启 start.bat 让监听地址生效。" : " 保存成功。";
    renderServiceConfig(data.service || {}, { state: data.restart_required ? "pending" : "ok", message: `${serviceStatusMessage(data.service || {})}${restartText}` });
    appendLog(`运行入口配置已保存：${serviceModeLabels[serviceConfig.mode] || serviceConfig.mode}。`);
    if (serviceConfig.mode === "client" && serviceConfig.server_url) {
      await checkRemoteService();
    }
  } catch (error) {
    if (serviceStatus) {
      serviceStatus.className = "workflow-status bad";
      serviceStatus.textContent = `运行入口配置保存失败：${error.message}`;
    }
    appendLog(`运行入口配置保存失败：${error.message}`);
  } finally {
    setServiceButtonsDisabled(false);
  }
}

function currentStep() {
  return steps[activeIndex];
}

function setLog(message) {
  logBox.textContent = message || "";
  if (envLogBox && envLogBox !== logBox) {
    envLogBox.textContent = message || "";
    envLogBox.scrollTop = envLogBox.scrollHeight;
  }
}

function appendLog(message) {
  const time = new Date().toLocaleTimeString();
  logBox.textContent = `${logBox.textContent}${logBox.textContent ? "\n" : ""}[${time}] ${message}`;
  logBox.scrollTop = logBox.scrollHeight;
  // 同步到环境 Tab 的日志区，让用户在环境 Tab 操作时也能看到任务进度。
  if (envLogBox && envLogBox !== logBox) {
    envLogBox.textContent = `${envLogBox.textContent}${envLogBox.textContent ? "\n" : ""}[${time}] ${message}`;
    envLogBox.scrollTop = envLogBox.scrollHeight;
  }
}

// 环境任务专用日志/进度：环境 Tab 内的一键准备、安装、自检、链路测试等任务
// 的进度展示写到这里，而不是工作流 Tab 的 logBox（用户在环境 Tab 操作时看不到工作流 Tab）。
const envLogBox = document.getElementById("envLogBox");
const envProgressBar = document.getElementById("envProgressBar");
const envJobStatus = document.getElementById("envJobStatus");

function setEnvLog(message) {
  if (!envLogBox) return;
  envLogBox.textContent = message || "";
  envLogBox.scrollTop = envLogBox.scrollHeight;
}

function appendEnvLog(message) {
  if (!envLogBox) return;
  const time = new Date().toLocaleTimeString();
  envLogBox.textContent = `${envLogBox.textContent}${envLogBox.textContent ? "\n" : ""}[${time}] ${message}`;
  envLogBox.scrollTop = envLogBox.scrollHeight;
}

function setEnvJobStatus(text, state = "") {
  if (!envJobStatus) return;
  envJobStatus.textContent = text || "空闲";
  envJobStatus.className = `env-job-status ${state}`;
}

function setEnvProgress(status) {
  setProgressInto(envProgressBar, status);
}

function formatInstallEta(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value) || value < 0) return "计算中";
  if (value < 60) return `${Math.max(1, Math.round(value))} 秒`;
  if (value < 3600) return `${Math.ceil(value / 60)} 分钟`;
  return `${Math.floor(value / 3600)} 小时 ${Math.ceil((value % 3600) / 60)} 分钟`;
}

function installStatusLabel(status) {
  const labels = {
    queued: "排队中",
    running: "下载中",
    pausing: "暂停中",
    paused: "已暂停",
    canceling: "取消中",
    canceled: "已取消",
    cancelled: "已取消",
    success: "已完成",
    failed: "失败",
    interrupted: "已中断",
  };
  return labels[status] || status || "等待中";
}

function renderEnvInstallProgress(job) {
  if (!job) return;
  const status = String(job.status || "queued").toLowerCase();
  const progress = job.progress || {};
  const percent = Math.max(0, Math.min(100, Number(progress.percent || 0)));
  activeInstallControlJobId = job.id || activeInstallControlJobId;
  if (envProgressBar) {
    envProgressBar.className = "progress-bar";
    envProgressBar.style.width = `${percent}%`;
    if (["running", "queued", "pausing", "canceling"].includes(status)) envProgressBar.classList.add("running");
    if (status === "success") envProgressBar.classList.add("success");
    if (["failed", "canceled", "cancelled", "interrupted"].includes(status)) envProgressBar.classList.add("failed");
  }
  const speed = Number(progress.speed_mb_s || 0);
  if (envProgressSummary) {
    envProgressSummary.textContent = progress.total_gb
      ? `${progress.current_file || "模型文件"} · ${Number(progress.downloaded_gb || 0).toFixed(2)} / ${Number(progress.total_gb || 0).toFixed(2)} GB · ${percent.toFixed(1)}%${speed > 0 ? ` · ${speed.toFixed(1)} MB/s · 剩余 ${formatInstallEta(progress.eta_seconds)}` : ""}`
      : `${installStatusLabel(status)}${progress.current_file ? ` · ${progress.current_file}` : ""}`;
  }
  if (envInstallFiles) {
    const files = progress.files || [];
    envInstallFiles.classList.toggle("hidden", !files.length);
    envInstallFiles.innerHTML = files
      .map(
        (item) => `<div class="install-file-row">
          <strong>${escapeHtml(item.label || item.name || "安装项")}</strong>
          <span>${item.percent == null ? escapeHtml(item.status || "等待") : `${Number(item.percent).toFixed(1)}%`}</span>
          <small>${item.expected_gb == null ? escapeHtml(item.status || "节点安装") : `${Number(item.downloaded_gb || 0).toFixed(3)} / ${Number(item.expected_gb || 0).toFixed(3)} GB · ${escapeHtml(item.status || "等待")}`}</small>
        </div>`,
      )
      .join("");
  }
  const resumable = ["paused", "interrupted"].includes(status) && Array.isArray(job.command_args);
  const controllable = Array.isArray(job.command_args);
  if (envInstallControls) envInstallControls.classList.toggle("hidden", !controllable || (job.completed && !resumable));
  envPauseInstallButton?.classList.toggle("hidden", !controllable || !["queued", "running"].includes(status));
  envResumeInstallButton?.classList.toggle("hidden", !resumable);
  envCancelInstallButton?.classList.toggle("hidden", !controllable || (job.completed && !resumable));
  if (status !== "success") hideGoGenerateButtons();
  setEnvJobStatus(installStatusLabel(status), status === "success" ? "success" : ["failed", "canceled", "interrupted"].includes(status) ? "failed" : "running");
}

function setProgressInto(bar, status) {
  if (!bar) return;
  bar.classList.remove("running");
  if (status === "success" || status === "failed") {
    bar.style.width = "100%";
  } else if (status === "running") {
    bar.style.width = "66%";
    bar.classList.add("running");
  } else if (status === "queued") {
    bar.style.width = "22%";
  } else if (status) {
    bar.style.width = "100%";
  } else {
    bar.style.width = "0";
  }
}

function setStatus(ok, text) {
  const dot = statusStrip.querySelector(".dot");
  dot.className = `dot ${ok ? "" : "bad"}`;
  statusText.textContent = text;
}

function showSections(sectionNames) {
  document.querySelectorAll("[data-section]").forEach((section) => {
    section.classList.toggle("hidden", !sectionNames.includes(section.dataset.section));
  });
}

function updateStepCopy() {
  const step = currentStep();
  const option = selectedModelOption(step.id);
  const strategy = environmentData?.hardware?.platform_strategy || (clientLooksLikeMac() ? "mac_mps" : "");
  let title = step.title;
  let subtitle = step.subtitle;
  let goal = step.goal;
  let primary = step.primary;

  if (step.id === "keyframe") {
    primary = `${hasKeyframeUpload() ? "使用关键帧" : "不使用关键帧"}，进入 ${selectedModelName("draft")}`;
  } else if (step.id === "draft") {
    const capabilities = optionCapabilities(option);
    if (option?.mode === "external_workflow") {
      title = option.label || "外部工作流";
      subtitle = "当前模型不由平台直接提交生成，请进入对应 ComfyUI 工作流。";
      goal = option.reason || "按模型目录中的来源与说明完成生成。";
      primary = selectedCatalogItem()?.platform_support === "official_workflow" ? "打开官方工作流" : "查看接入来源";
    } else if (capabilities.kind === "generation") {
      title = option?.label || "视频生成";
      const inputText = capabilities.image_input === "required"
        ? "需要关键帧"
        : capabilities.image_input === "optional"
          ? "关键帧可选"
          : "无需关键帧";
      const audioText = capabilities.native_audio ? "，并生成原生音频" : "";
      const constraintText = [
        capabilities.fixed_fps ? `固定 ${capabilities.fixed_fps}fps` : "",
        capabilities.frame_rule ? `帧数按 ${capabilities.frame_rule} 对齐` : "",
      ].filter(Boolean).join("，");
      subtitle = `${capabilities.engine_label || "当前模型"} 平台原生链路：${inputText}${audioText}${constraintText ? `；${constraintText}` : ""}。`;
      goal = option.reason || "先用推荐参数生成短镜头，确认效果后再提高分辨率或时长。";
    }
  } else if (step.id === "rife") {
    const multiplier = Number(selectedModelOption("rife")?.rife_multiplier || rifeMultiplierInput.value || 2);
    title = `流畅度增强 · ${multiplier}x 插帧`;
    subtitle = `把视频插到约 ${Number(fpsInput.value || currentVideoFps || 24) * multiplier}fps，运动更顺。`;
  } else if (step.id === "upscale") {
    const scale = getUpscaleScale();
    title = `清晰度增强 · ${scale}x`;
    subtitle = `目标分辨率会按输入视频实际尺寸放大 ${scale} 倍。`;
  } else if (step.id === "edit") {
    const previous = stitchSourceVideo();
    subtitle = previous
      ? "已把当前素材放在首位，可继续添加其他片段。"
      : "选择至少 2 个片段，调整顺序后输出完整 MP4。";
    primary = "开始拼接";
  }

  document.querySelector("#videoToolsTitle").textContent = step.id === "draft" ? "生成选项" : "输入视频";
  document.querySelector("#postVideoInputField").classList.toggle("hidden", step.id === "draft");
  document.querySelector(".video-tune-tools").classList.toggle("hidden", step.id !== "deflicker");
  document.querySelector("#batchVideoDrawer").classList.toggle("hidden", step.id !== "draft");
  document.querySelector(".video-temporal-stability").classList.toggle("hidden", step.id !== "draft");
  videoExtractFrameButton.classList.toggle("hidden", step.id === "draft");
  if (step.id === "deflicker") primary = "开始视频微调";

  stepTitle.textContent = title;
  stepSubtitle.textContent = subtitle;
  stepBadge.textContent = step.badge;
  stepGoal.textContent = goal;
  primaryButton.textContent = primary;
}

function setStep(stepId, { refresh = true, focus = true } = {}) {
  // Legacy image handoffs now enter generation with their keyframe already attached.
  if (stepId === "keyframe") stepId = "draft";
  const nextIndex = steps.findIndex((item) => item.id === stepId);
  if (nextIndex < 0) return;
  if (appInitialized) saveStepParameters();
  activeIndex = nextIndex;
  const step = currentStep();
  if (step.id === "edit" && videoInput.files?.[0]) {
    const file = videoInput.files[0];
    if (!stitchFiles.some((clip) => clip.name === file.name && clip.size === file.size && clip.lastModified === file.lastModified)) stitchFiles.push(file);
    videoInput.value = "";
  }
  if (WorkbenchJourney.tools.includes(step.id)) lastProcessingOperation = step.id;

  stepTitle.textContent = step.title;
  stepSubtitle.textContent = step.subtitle;
  stepBadge.textContent = step.badge;
  stepGoal.textContent = step.goal;
  modeInput.value = step.mode;
  primaryButton.textContent = step.primary;

  showSections(step.sections);
  const saved = stepParameters.get(stepId);
  if (!saved) applyStepDefaults(step);
  renderModelSelector({ applyDefaults: refresh && !saved });
  if (saved && saved.model === selectedModels[stepId]) restoreStepParameters(saved);
  updateStepCopy();
  updateStepper();
  updateNavigation();
  updateVideoSource();
  updateEnvStatusBar();
  renderStitchClipList();
  renderStepIdle();
  syncJourneyNavigation();
  persistCreationDraft();
  if (focus && appInitialized) {
    window.scrollTo({ top: 0, behavior: "smooth" });
    window.setTimeout(() => stepTitle?.focus({ preventScroll: true }), 180);
  }
  // 环境侦测已迁移到独立 Tab，setStep 不再触发环境刷新；改由 setView("environment") 负责。
}

function saveStepParameters() {
  if (currentStep().id === "keyframe") return;
  stepParameters.set(currentStep().id, {
    model: selectedModels[currentStep().id],
    values: Object.fromEntries([widthInput, heightInput, lengthInput, fpsInput, stepsInput, cfgInput, seedInput]
      .map((input) => [input.id, input.value])),
    advanced: [...advancedValues],
  });
}

function restoreStepParameters(saved) {
  advancedValues.clear();
  saved.advanced.forEach(([id, value]) => advancedValues.set(id, value));
  renderAdvancedParams(selectedModelOption());
  for (const id of ["width", "height", "length", "fps", "steps", "cfg", "seed"]) {
    if (saved.values[id] !== undefined) document.getElementById(id).value = saved.values[id];
  }
  syncAdvancedInput();
  scheduleWorkflowPreflight();
}

function applyStepDefaults(step) {
  if (!promptInput.value.trim() && defaultPrompt) promptInput.value = defaultPrompt;
  if (!negativeInput.value.trim()) negativeInput.value = defaultNegative;
  if (!step.defaults) return;
  if (step.defaults.steps !== undefined) stepsInput.value = step.defaults.steps;
  if (step.defaults.cfg !== undefined) cfgInput.value = step.defaults.cfg;
  if (step.defaults.fps !== undefined) fpsInput.value = step.defaults.fps;
}

function updateStepper() {
  document.querySelectorAll(".step-button").forEach((button) => {
    const id = button.dataset.step;
    button.classList.toggle("active", id === currentStep().id);
    button.classList.toggle("complete", completedSteps.has(id));
    button.setAttribute("aria-pressed", String(id === currentStep().id));
  });
}

function updateNavigation() {
  backButton.classList.add("hidden");
  continueButton.classList.add("hidden");
  repeatButton.classList.add("hidden");
  primaryButton.classList.remove("hidden");
}

function renderStepIdle() {
  const step = currentStep();
  const completed = completedSteps.has(step.id);
  setProgress(completed ? "success" : "");
  videoCancelJobButton?.classList.add("hidden");
  jobStatus.textContent = completed ? "已完成" : "空闲";
  renderResultActions();

  if (step.id === "keyframe") {
    jobMeta.innerHTML = `<span>${escapeHtml(selectedModelName())}</span><span>下一步：${escapeHtml(selectedModelName("draft"))}</span>`;
    resultHint.textContent = "关键帧可选；上传可稳定构图，不上传则直接进入文字生视频。";
    resultView.innerHTML = hasKeyframeUpload()
      ? "<p>已选择关键帧，进入视频生成后会使用这张图片。</p>"
      : "<p>未上传关键帧，将使用文字生视频路线。</p>";
  } else if (step.id === "draft") {
    jobMeta.innerHTML = `<span>${escapeHtml(selectedModelName())}</span><span>建议先用短镜头</span>`;
    resultHint.textContent = lastDraftVideo ? "视频已保存。" : "暂无生成结果。";
    renderMedia(lastDraftVideo ? [lastDraftVideo] : []);
  } else if (step.id === "deflicker") {
    const source = lastDraftVideo || lastFinalVideo;
    jobMeta.innerHTML = source
      ? `<span>${escapeHtml(selectedModelName())}</span><span>已选择输入视频</span>`
      : "<span>请上传待修复视频</span>";
    resultHint.textContent = lastDeflickerVideo ? "修复结果已保存。" : source ? "当前预览：输入素材" : "尚未选择输入素材";
    renderMedia(lastDeflickerVideo ? [lastDeflickerVideo] : source ? [source] : []);
  } else if (step.id === "rife") {
    const source = lastDeflickerVideo || lastDraftVideo || lastFinalVideo;
    jobMeta.innerHTML = source
      ? `<span>${escapeHtml(selectedModelName())}</span><span>已选择输入视频</span>`
      : "<span>请上传待插帧视频</span>";
    resultHint.textContent = lastRifeVideo ? "插帧结果已保存。" : source ? "当前预览：输入素材" : "尚未选择输入素材";
    renderMedia(lastRifeVideo ? [lastRifeVideo] : source ? [source] : []);
  } else if (step.id === "upscale") {
    const source = lastRifeVideo || lastDeflickerVideo || lastDraftVideo || lastFinalVideo;
    jobMeta.innerHTML = source
      ? `<span>${escapeHtml(selectedModelName())}</span><span>目标 ${getUpscaleScale()}x 超分</span>`
      : "<span>请上传待增强视频</span>";
    resultHint.textContent = lastUpscaleVideo ? "增强结果已保存。" : source ? "当前预览：输入素材" : "尚未选择输入素材";
    renderMedia(lastUpscaleVideo ? [lastUpscaleVideo] : source ? [source] : []);
  } else {
    const source = stitchSourceVideo();
    const clipCount = stitchFiles.length + (source ? 1 : 0);
    jobMeta.innerHTML = `<span>${clipCount} 个片段</span><span>${escapeHtml(`${widthInput.value || 1280} x ${heightInput.value || 704} · ${fpsInput.value || 24} fps`)}</span>`;
    resultHint.textContent = clipCount >= 2 ? "顺序确认后即可在本机拼接；输出会显示在这里。" : "请再添加片段，至少需要 2 个。";
    renderMedia(lastStitchedVideo ? [lastStitchedVideo] : source ? [source] : []);
    renderResultActions();
  }
  if (WorkbenchJourney.tools.includes(step.id) && videoInput.files?.[0]) resultHint.textContent = "当前预览：本机输入素材";
}

function setSize(width, height) {
  widthInput.value = width;
  heightInput.value = height;
  document.querySelectorAll("#sizePreset button").forEach((button) => {
    button.classList.toggle(
      "active",
      Number(button.dataset.width) === Number(width) &&
      Number(button.dataset.height) === Number(height),
    );
  });
  if (!currentVideoResolution) updateTargetResolution();
  refreshH3Tools();
  scheduleWorkflowPreflight();
}

function setLength(length) {
  lengthInput.value = length;
  document.querySelectorAll("#durationPreset button").forEach((button) => {
    button.classList.toggle("active", Number(button.dataset.length) === Number(length));
  });
  refreshH3Tools();
  scheduleWorkflowPreflight();
}

function setJobMeta(job) {
  if (job.mode === "stitch") {
    jobMeta.innerHTML = [
      job.title || "成片拼接",
      `${job.clip_count || stitchFiles.length} 个片段`,
      `${job.width || "-"} x ${job.height || "-"}`,
      `${job.fps || "-"} fps`,
    ]
      .map((part) => `<span>${escapeHtml(String(part))}</span>`)
      .join("");
    return;
  }
  const parts = [
    job.title || "任务",
    job.seed !== undefined && job.seed !== null ? `Seed ${job.seed}` : "",
    job.width && job.height ? `${job.width} x ${job.height}` : "",
    job.length ? `${job.length} 帧` : "",
    job.fps ? `${job.fps} fps` : "",
  ].filter(Boolean);
  jobMeta.innerHTML = parts.map((part) => `<span>${escapeHtml(String(part))}</span>`).join("");
}

function videoProgressDetail(status, progress = null) {
  const objectProgress = progress && typeof progress === "object" ? progress : null;
  const rawPercent = objectProgress ? Number(objectProgress.percent) : Number(progress);
  const hasPercent = Number.isFinite(rawPercent);
  const normalized = hasPercent ? Math.max(0, Math.min(100, rawPercent)) : 0;
  const labels = {
    success: "视频已完成",
    running: "正在处理视频",
    queued: "等待任务开始",
    reconnecting: "正在恢复连接",
    canceling: "正在中断任务",
    canceled: "任务已中断",
    failed: "任务失败",
  };
  return {
    percent: status === "success" ? 100 : normalized,
    label: objectProgress?.label || labels[status] || (status ? String(status) : "等待任务"),
    accurate: !status || status === "success" || Boolean(objectProgress?.accurate) || (hasPercent && progress !== null && typeof progress !== "object"),
  };
}

function applyVideoProgressUi(elements, status, progress = null) {
  const detail = videoProgressDetail(status, progress);
  const active = ["queued", "running", "reconnecting", "canceling"].includes(status);
  const failed = ["failed", "error", "lost"].includes(String(status || "").toLowerCase());
  const paused = ["canceled", "cancelled", "interrupted", "stopped"].includes(String(status || "").toLowerCase());
  if (elements.bar) {
    elements.bar.classList.toggle("running", active);
    elements.bar.classList.toggle("indeterminate", active && !detail.accurate);
    elements.bar.classList.toggle("success", status === "success");
    elements.bar.classList.toggle("failed", failed);
    elements.bar.classList.toggle("paused", paused);
    elements.bar.style.width = `${detail.percent}%`;
  }
  if (elements.label) elements.label.textContent = detail.label;
  if (elements.percent) elements.percent.textContent = detail.accurate ? `${detail.percent.toFixed(detail.percent % 1 ? 1 : 0)}%` : "--";
  if (elements.shell) {
    elements.shell.setAttribute("aria-valuenow", String(Math.round(detail.percent)));
    elements.shell.setAttribute("aria-valuetext", detail.label);
  }
  return detail;
}

function setProgress(status, progress = null) {
  applyVideoProgressUi({
    bar: progressBar,
    label: videoProgressLabel,
    percent: videoProgressPercent,
    shell: videoProgressShell,
  }, status, progress);
}

function setVideoFaceSwapProgress(status, progress = null) {
  const detail = applyVideoProgressUi({
    bar: videoFaceSwapProgressBar,
    label: videoFaceSwapProgressLabel,
    percent: videoFaceSwapProgressPercent,
    shell: videoFaceSwapProgressShell,
  }, status, progress);
  if (videoFaceSwapJobBadge) videoFaceSwapJobBadge.textContent = jobStatusLabel({ status, progress });
  return detail;
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function labelForStatus(status) {
  if (status === "ok") return "可用";
  if (status === "warn") return "建议调整";
  if (status === "blocked") return "需处理";
  return status || "未知";
}

function boolText(value) {
  return value ? "已就绪" : "未就绪";
}

function formatGb(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return `${Number(value).toFixed(Number(value) >= 10 ? 0 : 1)} GB`;
}

function downloadPresetById(id) {
  const presets = modelCatalogData?.source_presets || [];
  return presets.find((item) => item.id === id) || null;
}

function selectedDownloadRegion() {
  return downloadRegionOptions?.querySelector('input[name="downloadRegion"]:checked')?.value || "custom";
}

function openSourceConfig() {
  if (!sourceConfigModal) return;
  sourceModalReturnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  sourceConfigModal.classList.remove("hidden");
  document.body.classList.add("modal-open");
  window.setTimeout(() => {
    const checkedRegion = downloadRegionOptions?.querySelector('input[name="downloadRegion"]:checked');
    (checkedRegion || sourceConfigModal.querySelector(".source-modal-panel"))?.focus();
  }, 0);
}

function closeSourceConfig() {
  if (!sourceConfigModal) return;
  sourceConfigModal.classList.add("hidden");
  document.body.classList.remove("modal-open");
  sourceModalReturnFocus?.focus();
  sourceModalReturnFocus = null;
}

function trapModalFocus(event) {
  if (event.key !== "Tab" || !sourceConfigModal || sourceConfigModal.classList.contains("hidden")) return;
  const focusable = Array.from(
    sourceConfigModal.querySelectorAll(
      'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])',
    ),
  ).filter((element) => element instanceof HTMLElement && element.offsetParent !== null);
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

function setDownloadRegion(region, settings = {}) {
  if (!downloadRegionOptions) return;
  const value = region || settings.download_region || "international";
  const input = downloadRegionOptions.querySelector(`input[name="downloadRegion"][value="${CSS.escape(value)}"]`);
  if (input) input.checked = true;
}

function applyDownloadRegionPreset(region) {
  const preset = downloadPresetById(region);
  if (!preset || region === "custom") return;
  downloadSettingsDirty = true;
  if (hfEndpointInput) hfEndpointInput.value = preset.hf_endpoint || "";
  if (pipIndexInput) pipIndexInput.value = preset.pip_index_url || "";
  if (downloadSourceStatus) {
    downloadSourceStatus.className = "workflow-status pending";
    downloadSourceStatus.textContent = `下载区域：${preset.label}。已填入推荐源，点击“保存设置”或“保存并测试源”后生效。`;
  }
}

function sourceValueLabel(value, fallback) {
  return value ? value.replace(/^https?:\/\//, "") : fallback;
}

function renderDownloadSourceSummary(parts) {
  if (downloadSourceBrief) {
    downloadSourceBrief.textContent = parts.regionLabel;
  }
  if (downloadSourceDetail) {
    downloadSourceDetail.textContent = `模型 ${parts.modelSource} | pip ${parts.pipSource} | 代理 ${parts.proxySource}`;
  }
}

function renderDownloadSettings(settings = {}) {
  if (!downloadSourceStatus) return;
  modelCatalogData.source_presets = settings.source_presets || modelCatalogData.source_presets || [];
  const endpoint = settings.hf_endpoint || "";
  const saved = settings.saved_hf_endpoint || "";
  const envEndpoint = settings.env_hf_endpoint || "";
  const source = settings.source || (endpoint ? "saved" : "official");
  const proxyUrl = settings.proxy_url || "";
  const savedProxy = settings.saved_proxy_url || "";
  const envProxy = settings.env_proxy_url || "";
  const proxySource = settings.proxy_source || "none";
  const pipIndex = settings.pip_index_url || "";
  const savedPipIndex = settings.saved_pip_index_url || "";
  const envPipIndex = settings.env_pip_index_url || "";
  const pipIndexSource = settings.pip_index_source || "official";
  if (!downloadSettingsDirty) {
    setDownloadRegion(settings.download_region || (source === "official" ? "international" : "custom"), settings);
  }
  if (!downloadSettingsDirty && hfEndpointInput && document.activeElement !== hfEndpointInput) {
    hfEndpointInput.value = saved || endpoint || "";
  }
  if (!downloadSettingsDirty && pipIndexInput && document.activeElement !== pipIndexInput) {
    pipIndexInput.value = savedPipIndex || pipIndex || "";
  }
  if (!downloadSettingsDirty && settings.sensitive && proxyUrlInput && document.activeElement !== proxyUrlInput) {
    proxyUrlInput.value = savedProxy || proxyUrl || "";
  }
  let message = "当前使用官方 Hugging Face 下载源。";
  let state = "pending";
  if (source === "environment") {
    message = `当前由环境变量指定：${envEndpoint}。页面保存的地址会作为下次启动兜底，不会覆盖环境变量。`;
    state = "ok";
  } else if (source === "saved") {
    message = `当前使用已保存下载源：${endpoint}。一键准备、ComfyUI 安装、依赖安装、安装缺失项和网络预检都会使用它。`;
    state = "ok";
  }
  if (pipIndexSource === "environment") {
    message += ` pip 镜像由环境变量指定：${envPipIndex}。`;
    state = "ok";
  } else if (pipIndexSource === "saved") {
    message += ` 当前使用已保存 pip 镜像：${pipIndex}。`;
    state = "ok";
  } else {
    message += " pip 使用官方 PyPI。";
  }
  if (proxySource === "environment") {
    message += ` 代理由环境变量指定：${envProxy}。`;
    state = "ok";
  } else if (proxySource === "saved") {
    message += ` 当前使用已保存代理：${proxyUrl}。`;
    state = "ok";
  } else {
    message += " 当前未设置代理。";
  }
  const regionLabel = downloadPresetById(selectedDownloadRegion())?.label || "自定义";
  renderDownloadSourceSummary({
    regionLabel,
    modelSource: sourceValueLabel(endpoint || saved || envEndpoint, "官方 Hugging Face"),
    pipSource: sourceValueLabel(pipIndex || savedPipIndex || envPipIndex, "官方 PyPI"),
    proxySource: sourceValueLabel(proxyUrl || savedProxy || envProxy, "未设置"),
  });
  message = `下载区域：${regionLabel}。${message}`;
  downloadSourceStatus.className = `workflow-status ${state}`;
  downloadSourceStatus.textContent = message;
}

async function loadSettings() {
  try {
    const response = await fetch("/api/settings");
    const data = await response.json();
    if (!response.ok) throw new Error(formatError(data.detail || data));
    if (data.model_catalog) {
      modelCatalogData = data.model_catalog;
      syncCatalogSelectionFromData(modelCatalogData);
      renderModelCatalog();
    } else if (!catalogItems().length) {
      loadModelCatalog();
    }
    renderDownloadSettings(data.download);
    return data.download;
  } catch (error) {
    if (downloadSourceStatus) {
      downloadSourceStatus.className = "workflow-status bad";
      downloadSourceStatus.textContent = `网络设置读取失败：${error.message}`;
    }
    return null;
  }
}

function downloadSettingsPayloadFromInputs() {
  return {
    download_region: selectedDownloadRegion(),
    hf_endpoint: hfEndpointInput?.value.trim() || "",
    pip_index_url: pipIndexInput?.value.trim() || "",
    proxy_url: proxyUrlInput?.value.trim() || "",
  };
}

function setDownloadSettingsButtonsDisabled(disabled) {
  if (saveDownloadSettingsButton) saveDownloadSettingsButton.disabled = disabled;
  if (testDownloadSourcesButton) testDownloadSourcesButton.disabled = disabled;
}

async function persistDownloadSettings({ refreshAfterSave = true } = {}) {
  const response = await fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ download: downloadSettingsPayloadFromInputs() }),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(formatError(data.detail || data));
  if (environmentData) {
    environmentData.download_settings = data.download;
  }
  if (data.model_catalog) {
    modelCatalogData = data.model_catalog;
    syncCatalogSelectionFromData(modelCatalogData);
    renderModelCatalog();
  }
  downloadSettingsDirty = false;
  renderDownloadSettings(data.download);
  if (refreshAfterSave) {
    await loadBootstrap();
    if (environmentData) {
      await loadInstallPlan(selectedInstallProfile);
    }
  }
  return data.download;
}

async function saveDownloadSettings() {
  if (!saveDownloadSettingsButton || !hfEndpointInput) return;
  setDownloadSettingsButtonsDisabled(true);
  downloadSourceStatus.className = "workflow-status pending";
  downloadSourceStatus.textContent = "正在保存下载源设置。";
  try {
    await persistDownloadSettings();
    appendLog("下载源设置已保存。");
  } catch (error) {
    downloadSourceStatus.className = "workflow-status bad";
    downloadSourceStatus.textContent = `下载源保存失败：${error.message}`;
    appendLog(`下载源保存失败：${error.message}`);
  } finally {
    setDownloadSettingsButtonsDisabled(false);
  }
}

function renderDownloadSourceTest(report) {
  const networkCheck = (report?.checks || []).find((item) => item.id === "network");
  if (!downloadSourceStatus || !networkCheck) return;
  const targets = networkCheck.targets || {};
  const reachable = networkCheck.reachable || {};
  const details = Object.entries(targets)
    .map(([host, target]) => `${target.label || host}：${reachable[host] ? "可达" : "不可达"}`)
    .join("；");
  const state = networkCheck.status === "ok" ? "ok" : "bad";
  downloadSourceStatus.className = `workflow-status ${state}`;
  downloadSourceStatus.textContent = `${networkCheck.message || "下载源测试完成。"}${details ? ` ${details}` : ""}`;
}

async function testDownloadSources() {
  if (!testDownloadSourcesButton) return;
  setDownloadSettingsButtonsDisabled(true);
  if (downloadSourceStatus) {
    downloadSourceStatus.className = "workflow-status pending";
    downloadSourceStatus.textContent = "正在保存当前填写的下载源并测试连通性。";
  }
  try {
    await persistDownloadSettings({ refreshAfterSave: false });
    appendLog("下载源设置已保存，开始测试。");
    await loadBootstrap();
    if (environmentData) {
      await loadInstallPlan(selectedInstallProfile);
    }
    const response = await fetch("/api/prerequisites?network=true");
    const data = await response.json();
    if (!response.ok) throw new Error(formatError(data.detail || data));
    renderPrerequisites(data);
    renderDownloadSourceTest(data);
    appendLog("下载源测试完成。");
  } catch (error) {
    if (downloadSourceStatus) {
      downloadSourceStatus.className = "workflow-status bad";
      downloadSourceStatus.textContent = `下载源保存或测试失败：${error.message}`;
    }
    appendLog(`下载源保存或测试失败：${error.message}`);
  } finally {
    setDownloadSettingsButtonsDisabled(false);
  }
}

function platformStrategyLabel(strategy) {
  const labels = {
    cuda_multi_model: "CUDA 多模型工作站",
    cuda_wan_workflow: "CUDA 多模型工作站",
    mac_mps: "Apple Silicon 多模型模式",
    mac_post_only: "Mac 后期/轻量路线",
    post_only: "后期处理路线",
  };
  return labels[strategy] || strategy || "未识别";
}

function macTierLabel(tier) {
  const labels = {
    mac_ltx_low: "LTX 低档",
    mac_ltx_balanced: "LTX 均衡档",
    mac_ltx_quality: "LTX 质量档",
    mac_wan5b_480p: "高内存 480P 实验",
    mac_wan5b_720p_experimental: "高内存 720P 实验",
    mac_post_only: "后期处理",
  };
  return labels[tier] || tier || "-";
}

function clientLooksLikeMac() {
  return /Mac|iPhone|iPad/.test(navigator.platform || "") || /Mac OS/.test(navigator.userAgent || "");
}

function fallbackOptionsForStep(stepId) {
  return (clientLooksLikeMac() ? macFallbackModelOptions : fallbackModelOptions)[stepId] || [];
}

function fallbackRecommendedForStep(stepId) {
  return (clientLooksLikeMac() ? macFallbackRecommendedModels : fallbackRecommendedModels)[stepId] || "";
}

function rawModelOptionsForStep(stepId) {
  return environmentData?.model_options?.options?.[stepId] || fallbackOptionsForStep(stepId);
}

function modelOptionsForStep(stepId) {
  if (stepId !== "draft") return rawModelOptionsForStep(stepId);
  if (environmentData?.model_options?.unified_generation) {
    const options = rawModelOptionsForStep("draft");
    const runnable = options.filter((item) => item.mode !== "unsupported");
    return runnable.length ? runnable : options;
  }
  const merged = [...rawModelOptionsForStep("final"), ...rawModelOptionsForStep("draft")];
  const seen = new Set();
  const unique = merged.filter((item) => {
    if (!item?.id || seen.has(item.id)) return false;
    seen.add(item.id);
    return true;
  });
  const runnable = unique.filter((item) => item.mode !== "unsupported");
  return runnable.length ? runnable : unique;
}

function recommendedModelForStep(stepId) {
  if (stepId === "draft") {
    const unified = Boolean(environmentData?.model_options?.unified_generation);
    const candidate = unified
      ? environmentData?.model_options?.recommended?.draft || fallbackRecommendedForStep("draft")
      : environmentData?.model_options?.recommended?.final ||
        environmentData?.model_options?.recommended?.draft ||
        fallbackRecommendedForStep("final") ||
        fallbackRecommendedForStep("draft");
    if (modelOptionsForStep("draft").some((item) => item.id === candidate)) return candidate;
  }
  return (
    environmentData?.model_options?.recommended?.[stepId] ||
    fallbackRecommendedForStep(stepId) ||
    modelOptionsForStep(stepId)[0]?.id ||
    ""
  );
}

function selectedModelOption(stepId = currentStep().id) {
  const options = modelOptionsForStep(stepId);
  if (!options.length) return null;
  const selectedId = selectedModels[stepId] || recommendedModelForStep(stepId);
  return options.find((item) => item.id === selectedId) || options[0];
}

function optionCapabilities(option) {
  if (option?.capabilities) return option.capabilities;
  if (modeCapabilitiesByMode?.[option?.mode]) return modeCapabilitiesByMode[option.mode];
  const imageOptional = Boolean(option?.image_optional);
  const imageRequired = Boolean(option?.image_required || (option?.uses_image && !imageOptional));
  return {
    kind: option?.mode && !["unsupported", "external_workflow"].includes(option.mode) ? "generation" : "other",
    engine: option?.engine || "generic",
    text_to_video: Boolean(imageOptional || option?.uses_image === false),
    image_to_video: Boolean(option?.uses_image),
    image_input: imageRequired ? "required" : imageOptional ? "optional" : "none",
    first_frame: Boolean(option?.uses_image),
    last_frame: Boolean(option?.supports_end_image),
    native_audio: false,
    fixed_fps: null,
    frame_rule: "",
    frame_step: 1,
  };
}

function optionCanBeChosen(option) {
  return Boolean(option && option.supported !== false && (option.status !== "blocked" || option.install_profile));
}

function capabilityCounterpart(stepId, current, capability) {
  if (!current) return null;
  const options = modelOptionsForStep(stepId);
  const counterpartKey = capability === "text_to_video" ? "text" : "image";
  const declaredId = current.counterparts?.[counterpartKey];
  const declared = declaredId && options.find((item) => item.id === declaredId);
  if (optionCanBeChosen(declared)) return declared;

  const statusRank = { ok: 0, warn: 1, blocked: 2 };
  const candidates = options.filter(
    (item) => optionCapabilities(item)[capability] && optionCanBeChosen(item),
  );
  candidates.sort((left, right) => {
    const leftScore = [
      left.variant_group === current.variant_group ? 0 : 1,
      left.install_profile === current.install_profile ? 0 : 1,
      optionCapabilities(left).engine === optionCapabilities(current).engine ? 0 : 1,
      statusRank[left.status] ?? 3,
    ];
    const rightScore = [
      right.variant_group === current.variant_group ? 0 : 1,
      right.install_profile === current.install_profile ? 0 : 1,
      optionCapabilities(right).engine === optionCapabilities(current).engine ? 0 : 1,
      statusRank[right.status] ?? 3,
    ];
    for (let index = 0; index < leftScore.length; index += 1) {
      if (leftScore[index] !== rightScore[index]) return leftScore[index] - rightScore[index];
    }
    return String(left.id || "").localeCompare(String(right.id || ""));
  });
  return candidates[0] || null;
}

function hasKeyframeUpload() {
  return Boolean((imageInput.files && imageInput.files.length) || sourceImageFilename?.value);
}

function referenceMediaSummary() {
  const summary = { images: [], videos: [], audios: [], unsupported: [] };
  Array.from(referenceMediaInput?.files || []).forEach((file) => {
    const type = String(file.type || "");
    const extension = String(file.name || "").split(".").pop()?.toLowerCase() || "";
    if (type.startsWith("image/") || ["png", "jpg", "jpeg", "webp", "bmp"].includes(extension)) summary.images.push(file);
    else if (type.startsWith("video/") || ["mp4", "mov", "mkv", "webm", "avi"].includes(extension)) summary.videos.push(file);
    else if (type.startsWith("audio/") || ["wav", "mp3", "flac", "m4a", "aac", "ogg"].includes(extension)) summary.audios.push(file);
    else summary.unsupported.push(file);
  });
  summary.total = summary.images.length + summary.videos.length + summary.audios.length;
  summary.valid = summary.total > 0 && summary.images.length <= 9 && summary.videos.length <= 3 && summary.audios.length <= 3 && !summary.unsupported.length;
  return summary;
}

function renderReferenceMediaList() {
  if (!referenceMediaList || !referenceMediaCount) return;
  const summary = referenceMediaSummary();
  referenceMediaCount.textContent = `${summary.total} 个素材`;
  const rows = [
    ...summary.images.map((file, index) => ({ file, tag: `<Picture ${index + 1}>`, kind: "图片" })),
    ...summary.videos.map((file, index) => ({ file, tag: `<Video ${index + 1}>`, kind: "视频" })),
    ...summary.audios.map((file, index) => ({ file, tag: `<Audio ${index + 1}>`, kind: "音频" })),
    ...summary.unsupported.map((file) => ({ file, tag: "不支持", kind: "未知" })),
  ];
  if (!rows.length) {
    referenceMediaList.innerHTML = "<p>至少选择 1 个；最多 9 张图片、3 段视频、3 条音频。</p>";
    referenceMediaList.classList.remove("invalid");
    return;
  }
  referenceMediaList.innerHTML = rows
    .map((item) => `<div><span>${escapeHtml(item.kind)}</span><strong>${escapeHtml(item.file.name)}</strong><code>${escapeHtml(item.tag)}</code></div>`)
    .join("");
  referenceMediaList.classList.toggle("invalid", !summary.valid);
}

function modelRequiresKeyframe(option = selectedModelOption("draft")) {
  return currentStep().id === "draft" && optionCapabilities(option).image_input === "required";
}

function renderKeyframeRequirement(option) {
  const required = modelRequiresKeyframe(option);
  if (keyframeInputLabel) {
    keyframeInputLabel.textContent = required ? "首帧图片（必需）" : "关键帧图片（可选）";
  }
  if (keyframeInputHelp) {
    keyframeInputHelp.textContent = required
      ? "当前是 I2V 路线，必须上传首帧；支持首尾帧的模型还可以再上传一张尾帧。"
      : "需要锁定人物、场景或构图时再上传；不上传会使用 T2V 文字生视频路线。";
  }
  if (!hasKeyframeUpload() && keyframePreview) {
    keyframePreview.innerHTML = required
      ? "<p>当前 I2V 模型需要首帧图片，上传后才能生成。</p>"
      : "<p>未上传关键帧，将使用文字生视频路线。</p>";
  }
}

function clearLinkedKeyframe() {
  if (sourceImageFilename) sourceImageFilename.value = "";
  if (sourceImagePreviewUrl) sourceImagePreviewUrl.value = "";
  if (sourceImageLabel) sourceImageLabel.value = "";
}

function videoPlaybook() {
  return environmentData?.nsfw_playbook || bootstrapData?.nsfw_playbook || {};
}

function videoLinkage() {
  return videoPlaybook().linkage || {};
}

function rememberedAdultWizardId() {
  return localStorage.getItem(ADULT_WIZARD_STORAGE_KEY) || "";
}

function rememberAdultWizardId(id) {
  const value = String(id || "").trim();
  if (value) localStorage.setItem(ADULT_WIZARD_STORAGE_KEY, value);
  else localStorage.removeItem(ADULT_WIZARD_STORAGE_KEY);
}

function preferredIdList(source, singular, plural) {
  const many = Array.isArray(source?.[plural]) ? source[plural] : [];
  const one = source?.[singular] ? [source[singular]] : [];
  return [...new Set([...many, ...one].map((item) => String(item || "").trim()).filter(Boolean))];
}

function groupedPresetHtml(items, dataAttr, activeId = "") {
  if (!items.length) return `<span class="muted">无模板</span>`;
  const groups = [];
  const buckets = new Map();
  for (const item of items) {
    const group = String(item.group || "其他");
    if (!buckets.has(group)) {
      buckets.set(group, []);
      groups.push(group);
    }
    buckets.get(group).push(item);
  }
  return groups
    .map((group) => {
      const chips = buckets
        .get(group)
        .map((item) => {
          const title = item.note || item.prompt_suffix || item.prompt || "";
          const active = item.id === activeId ? " active" : "";
          return `<button type="button" class="chip${active}" data-${dataAttr}="${escapeHtml(item.id)}" title="${escapeHtml(title)}">${escapeHtml(item.label)}</button>`;
        })
        .join("");
      return `<div class="chip-group"><span class="chip-group-label">${escapeHtml(group)}</span><div class="chip-row">${chips}</div></div>`;
    })
    .join("");
}

function videoModelTargets(wizard) {
  const listed = preferredIdList(wizard, "preferred_video_model", "preferred_video_models");
  if (listed.length) return listed;
  const fallbacks = videoPlaybook().video_model_fallbacks || {};
  if (wizard?.pipeline === "t2v") return fallbacks.t2v || [];
  return fallbacks.i2v || [];
}

function findAdultWizard(wizardId) {
  return (videoPlaybook().wizard_modes || []).find((item) => item.id === wizardId) || null;
}

let lastAppliedVideoSceneId = "";
let lastAppliedVideoMotionId = "";
let lastAppliedMotionLoraPackId = "";
let lastPushedImagePrompt = "";

function promptDerivedFrom(current, source) {
  const left = String(current || "").trim();
  const right = String(source || "").trim();
  if (!left) return true;
  if (!right) return false;
  return left === right;
}

function stripPromptClause(text, clause) {
  const source = String(text || "").trim();
  const token = String(clause || "").trim();
  if (!source || !token || !source.includes(token)) return source;
  return source
    .split(token)
    .join("")
    .replace(/[。.]{2,}/g, "。")
    .replace(/^[。.\s]+|[。.\s]+$/g, "")
    .trim();
}

function stripLastPlaybookVideoClauses() {
  if (!promptInput) return;
  let text = String(promptInput.value || "");
  const scene = (videoPlaybook().video_scenes || []).find((item) => item.id === lastAppliedVideoSceneId);
  const motion = (videoPlaybook().video_motion || []).find((item) => item.id === lastAppliedVideoMotionId);
  const pack = (videoPlaybook().motion_lora_packs || []).find((item) => item.id === lastAppliedMotionLoraPackId);
  for (const clause of [scene?.prompt_suffix, scene?.prompt_suffix_en, motion?.prompt_suffix, motion?.prompt_suffix_en, pack?.trigger, pack?.prompt_suffix]) {
    text = stripPromptClause(text, clause);
  }
  promptInput.value = text;
}

function markActiveChips(container, dataAttr, activeId) {
  container?.querySelectorAll(`button[${dataAttr}]`).forEach((button) => {
    button.classList.toggle("active", button.getAttribute(dataAttr) === activeId);
  });
}

window.hasVideoKeyframe = () => hasKeyframeUpload();

function videoCharacterBox() {
  return environmentData?.character_box || bootstrapData?.character_box || { items: [] };
}

function selectedVideoCharacterId() {
  return (
    localStorage.getItem(VIDEO_CHARACTER_STORAGE_KEY) ||
    localStorage.getItem(IMAGE_CHARACTER_STORAGE_KEY) ||
    localStorage.getItem("wan22.video.characterId") ||
    localStorage.getItem("wan22.image.characterId") ||
    ""
  );
}

function setSelectedVideoCharacterId(id) {
  if (id) {
    localStorage.setItem(VIDEO_CHARACTER_STORAGE_KEY, id);
    if (videoLinkage().character_box_shared !== false) localStorage.setItem(IMAGE_CHARACTER_STORAGE_KEY, id);
  } else {
    localStorage.removeItem(VIDEO_CHARACTER_STORAGE_KEY);
  }
}

function effectiveVideoTrigger(option = selectedModelOption(currentStep().id)) {
  const custom = String(videoCustomTrigger?.value || "").trim();
  if (custom) return custom;
  return String(option?.unrestricted?.trigger || "").trim();
}

function updateVideoTriggerPreview(option) {
  const trigger = effectiveVideoTrigger(option);
  if (videoTriggerPreview) videoTriggerPreview.textContent = trigger ? `将使用：${trigger}` : "无默认触发词（可自定义）";
}

function renderVideoCharacterSelect() {
  if (!videoCharacterSelect) return;
  const items = Array.isArray(videoCharacterBox().items) ? videoCharacterBox().items : [];
  const selected = selectedVideoCharacterId();
  videoCharacterSelect.innerHTML = [`<option value="">不绑定角色</option>`]
    .concat(items.map((item) => `<option value="${escapeHtml(item.id)}"${item.id === selected ? " selected" : ""}>${escapeHtml(item.label || item.id)}</option>`))
    .join("");
  if (videoCharacterSelectHelp) {
    videoCharacterSelectHelp.textContent = items.length
      ? "与图片角色盒共用；可用于视频换脸身份参考，也可仅作记录。"
      : "与图片角色盒共用；导入角色后可作为视频换脸身份。";
  }
}

function renderVideoMotionLoraPacks() {
  if (!videoMotionLoraPack) return;
  const packs = (videoPlaybook().motion_lora_packs || []).filter(
    (item) => String(item.high || "").trim() && String(item.low || "").trim(),
  );
  const current = videoMotionLoraPack.value || "";
  videoMotionLoraPack.innerHTML = [`<option value="">不叠加动作 LoRA</option>`]
    .concat(
      packs.map(
        (item) =>
          `<option value="${escapeHtml(item.id)}" title="${escapeHtml(item.note || item.prompt_suffix || "")}">${escapeHtml(item.label)}</option>`,
      ),
    )
    .join("");
  videoMotionLoraPack.value = packs.some((item) => item.id === current) ? current : "";
  renderVideoMotionLoraChips();
}

function renderVideoMotionLoraChips() {
  if (!videoMotionLoraChips) return;
  const packs = (videoPlaybook().motion_lora_packs || []).filter(
    (item) => String(item.high || "").trim() && String(item.low || "").trim(),
  );
  const current = videoMotionLoraPack?.value || "";
  videoMotionLoraChips.innerHTML = packs.length
    ? packs
        .map(
          (item) =>
            `<button type="button" class="chip${item.id === current ? " active" : ""}" data-motion-lora="${escapeHtml(item.id)}" title="${escapeHtml(item.note || item.prompt_suffix || "")}">${escapeHtml(item.label)}</button>`,
        )
        .join("")
    : "";
}

function applyVideoMotionLoraPack(packId, { syncPrompt = true } = {}) {
  if (videoMotionLoraPack) videoMotionLoraPack.value = packId || "";
  renderVideoMotionLoraChips();
  const pack = (videoPlaybook().motion_lora_packs || []).find((item) => item.id === packId);
  if (!pack) {
    scheduleWorkflowPreflight();
    return;
  }
  if (pack.motion_hint) applyVideoMotion(pack.motion_hint, { syncParams: true, appendPrompt: false });
  if (syncPrompt && promptInput) {
    const extras = [pack.trigger, pack.prompt_suffix].filter((item) => String(item || "").trim());
    for (const clause of extras) {
      const text = String(clause).trim();
      const current = String(promptInput.value || "").trim();
      if (!text || current.includes(text)) continue;
      promptInput.value = current ? `${current.replace(/[。.\s]+$/, "")}。${text}` : text;
    }
  }
  lastAppliedMotionLoraPackId = packId || "";
  scheduleWorkflowPreflight();
}

window.setPreferredVideoModel = (modelModeOrId = "", { fallbacks = [], applyDefaults = false } = {}) => {
  const targets = (Array.isArray(modelModeOrId) ? modelModeOrId : [modelModeOrId, ...fallbacks])
    .map((item) => String(item || "").trim())
    .filter(Boolean);
  if (!targets.length) return { switched: [], selected: null, requested: "", usedFallback: false };
  const switched = [];
  let selected = null;
  ["draft", "keyframe"].forEach((stepId) => {
    const options = modelOptionsForStep(stepId);
    const match = targets
      .map((target) =>
        options.find(
          (item) => (item.mode === target || item.id === target) && item.supported !== false && item.status !== "blocked",
        ),
      )
      .find(Boolean);
    if (!match) return;
    selected = match;
    if (selectedModels[stepId] !== match.id) {
      selectedModels[stepId] = match.id;
      switched.push(match.label);
    }
  });
  const onGenerationStep = ["draft", "keyframe"].includes(currentStep().id);
  if (switched.length && onGenerationStep) {
    syncSelectedModel({ applyDefaults });
    renderVideoUnrestricted(selectedModelOption(currentStep().id));
    appendLog(`玩法向导已切换视频模型：${switched.join("、")}。`);
  } else if (switched.length) {
    appendLog(`玩法向导已记下视频模型：${switched.join("、")}。`);
  } else if (!selected && targets.length) {
    appendLog(`玩法想切到 ${targets[0]}，但当前环境没有可用的对应视频模型。`);
  }
  const requested = targets[0] || "";
  const usedFallback = Boolean(
    selected && requested && selected.mode !== requested && selected.id !== requested,
  );
  return { switched, selected, requested, usedFallback };
};

function renderVideoAdultRecipes() {
  if (!videoAdultRecipeChips) return;
  const wizards = videoPlaybook().wizard_modes || [];
  const active = rememberedAdultWizardId() || "manual";
  videoAdultRecipeChips.innerHTML = groupedPresetHtml(wizards, "adult-wizard", active);
  const current = findAdultWizard(active);
  if (videoAdultRecipeHint) {
    videoAdultRecipeHint.textContent = current?.note || "点选后切 H3 / LTX 2.5、开无限制并套动作；不会改静帧提示词。";
  }
}

function applyAdultPlaybookVideo(wizard = {}, { imagePrompt = "", replacePrompt = false } = {}) {
  if (!wizard || wizard.pipeline === "manual") {
    renderVideoAdultRecipes();
    return { switched: [], selected: null, notes: [], replacedPrompt: false };
  }
  if (currentStep().id !== "draft") {
    setStep("draft", { refresh: false, focus: false });
  }
  const notes = [];
  const modelResult = window.setPreferredVideoModel(videoModelTargets(wizard), { applyDefaults: false });
  const draftOption = selectedModelOption("draft");
  if (draftOption) applyModelDefaults(draftOption);
  if (hasKeyframeUpload()) alignVideoSizeToKeyframe(sourceImagePreviewUrl?.value || "");
  if (wizard.auto_inject_trigger != null && videoAutoInjectTrigger) {
    videoAutoInjectTrigger.checked = Boolean(wizard.auto_inject_trigger);
  }
  if (wizard.auto_strip_negative != null && videoAutoStripNegative) {
    videoAutoStripNegative.checked = Boolean(wizard.auto_strip_negative);
  }
  renderVideoUnrestricted(draftOption);
  if (wizard.auto_unrestricted && videoUnrestrictedToggle) {
    if (!videoUnrestrictedToggle.disabled) {
      videoUnrestrictedToggle.checked = true;
      renderVideoUnrestricted(selectedModelOption("draft"));
    } else {
      notes.push("当前视频模型无法打开无限制");
    }
  }
  if (modelResult.usedFallback && modelResult.selected) {
    notes.push(`视频模型已回退到 ${modelResult.selected.label}`);
  } else if (!modelResult.selected && videoModelTargets(wizard).length) {
    notes.push("没有可用的目标视频模型");
  }

  stripLastPlaybookVideoClauses();
  const sourcePrompt = String(imagePrompt || "").trim();
  let replacedPrompt = false;
  if (sourcePrompt && promptInput) {
    const current = String(promptInput.value || "").trim();
    const replace =
      !current ||
      current === defaultPrompt ||
      (replacePrompt && (promptDerivedFrom(current, sourcePrompt) || promptDerivedFrom(current, lastPushedImagePrompt)));
    if (replace) {
      promptInput.value = sourcePrompt;
      lastPushedImagePrompt = sourcePrompt;
      replacedPrompt = true;
    }
  }

  const scene = wizard.video_scene
    ? (videoPlaybook().video_scenes || []).find((item) => item.id === wizard.video_scene)
    : null;
  if (scene) {
    applyVideoScene(wizard.video_scene, { replacePrevious: false, appendMotionPrompt: false });
    if (!scene.motion_hint && wizard.video_motion) {
      applyVideoMotion(wizard.video_motion, { appendPrompt: false });
    }
  } else if (wizard.video_motion) {
    applyVideoMotion(wizard.video_motion, { appendPrompt: true });
  }

  const packId = String(wizard.video_motion_lora_pack || "").trim();
  const current = selectedModelOption("draft");
  if (!packId) {
    if (videoMotionLoraPack) videoMotionLoraPack.value = "";
    lastAppliedMotionLoraPackId = "";
    renderVideoMotionLoraChips();
  } else if (current?.unrestricted?.lora_enabled !== false) {
    applyVideoMotionLoraPack(packId);
    lastAppliedMotionLoraPackId = packId;
  } else {
    const pack = (videoPlaybook().motion_lora_packs || []).find((item) => item.id === packId);
    if (pack && promptInput) {
      const extras = [pack.trigger, pack.prompt_suffix].filter((item) => String(item || "").trim());
      for (const clause of extras) {
        const text = String(clause).trim();
        const currentPrompt = String(promptInput.value || "").trim();
        if (!text || currentPrompt.includes(text)) continue;
        promptInput.value = currentPrompt ? `${currentPrompt.replace(/[。.\s]+$/, "")}。${text}` : text;
      }
      lastAppliedMotionLoraPackId = packId;
      scheduleWorkflowPreflight();
    }
  }
  renderVideoAdultRecipes();
  return { switched: modelResult.switched || [], selected: modelResult.selected, notes, replacedPrompt };
}

window.applyAdultPlaybookVideo = applyAdultPlaybookVideo;

function applyVideoAdultRecipe(wizardId) {
  const wizard = findAdultWizard(wizardId);
  if (!wizard) return;
  rememberAdultWizardId(wizard.id);
  if (typeof window.applyAdultPlaybook === "function") {
    window.applyAdultPlaybook(wizard.id, { source: "video" });
    renderVideoAdultRecipes();
    return;
  }
  applyAdultPlaybookVideo(wizard);
  const extra = wizard.note || "";
  appendLog(`已套用视频玩法：${wizard.label}。${extra}`);
}

function renderVideoPlaybookControls(option) {
  const book = videoPlaybook();
  const motions = book.video_motion || [];
  const currentMotion = videoMotionPreset?.value || "medium";
  if (videoMotionSwitch) {
    videoMotionSwitch.innerHTML = motions.length
      ? motions
          .map(
            (item) =>
              `<button type="button" data-motion="${escapeHtml(item.id)}" class="${item.id === currentMotion ? "active" : ""}" title="${escapeHtml(item.prompt_suffix || "")}">${escapeHtml(item.label)}</button>`,
          )
          .join("")
      : `<span class="muted">无运动档位</span>`;
  }
  const scenes = book.video_scenes || [];
  if (videoSceneChips) {
    videoSceneChips.innerHTML = groupedPresetHtml(scenes, "video-scene", lastAppliedVideoSceneId);
  }
  renderVideoAdultRecipes();
  if (videoAutoInjectTrigger && videoAutoInjectTrigger.dataset.initialized !== "1") {
    videoAutoInjectTrigger.checked = videoLinkage().auto_inject_trigger !== false;
    videoAutoInjectTrigger.dataset.initialized = "1";
  }
  if (videoAutoStripNegative && videoAutoStripNegative.dataset.initialized !== "1") {
    videoAutoStripNegative.checked = videoLinkage().auto_strip_negative !== false;
    videoAutoStripNegative.dataset.initialized = "1";
  }
  renderVideoCharacterSelect();
  renderVideoMotionLoraPacks();
  updateVideoTriggerPreview(option);
}

function applyVideoMotion(motionId, { syncParams = true, appendPrompt } = {}) {
  if (videoMotionPreset) videoMotionPreset.value = motionId;
  lastAppliedVideoMotionId = motionId;
  videoMotionSwitch?.querySelectorAll("button[data-motion]").forEach((button) => {
    button.classList.toggle("active", button.dataset.motion === motionId);
  });
  if (!syncParams) return;
  const optionStep = ["draft", "keyframe"].includes(currentStep().id) ? "draft" : currentStep().id;
  const option = selectedModelOption(optionStep);
  const motion = (videoPlaybook().video_motion || []).find((item) => item.id === motionId);
  if (!motion || !option) return;
  const linkage = videoLinkage();
  const defaults = option.defaults || {};
  if (linkage.motion_updates_length !== false && lengthInput) {
    const base = Number(lengthInput.dataset.baseLength || lengthInput.value || defaults.length || 81);
    lengthInput.dataset.baseLength = String(base);
    const next = Math.max(9, Math.round(base * Number(motion.length_factor || 1)));
    lengthInput.value = String(next);
  }
  if (linkage.motion_updates_cfg !== false && cfgInput) {
    const base = Number(cfgInput.dataset.baseCfg || cfgInput.value || defaults.cfg || 1);
    cfgInput.dataset.baseCfg = String(base);
    const next = Math.max(0.1, Math.min(20, Number((base + Number(motion.cfg_delta || 0)).toFixed(3))));
    cfgInput.value = String(next);
  }
  if (linkage.motion_updates_unrestricted_strength !== false && videoUnrestrictedToggle?.checked && videoUnrestrictedStrength) {
    const base = Number(videoUnrestrictedStrength.dataset.baseStrength || videoUnrestrictedStrength.value || option.unrestricted?.strength_default || 0.8);
    videoUnrestrictedStrength.dataset.baseStrength = String(base);
    const next = Math.max(
      Number(videoUnrestrictedStrength.min || 0),
      Math.min(Number(videoUnrestrictedStrength.max || 1.2), Number((base * Number(motion.unrestricted_multiplier || 1)).toFixed(4))),
    );
    syncVideoUnrestrictedStrength(next, { preflight: false });
  }
  const shouldAppend = appendPrompt ?? linkage.motion_appends_prompt !== false;
  if (shouldAppend && promptInput) {
    const language = /[\u4e00-\u9fff]/.test(promptInput.value || motion.prompt_suffix || "") ? "zh" : "en";
    const suffix =
      language === "en"
        ? motion.prompt_suffix_en || motion.prompt_suffix
        : motion.prompt_suffix || motion.prompt_suffix_en;
    if (suffix) {
      const current = String(promptInput.value || "").trim();
      promptInput.value = current
        ? current.includes(suffix)
          ? current
          : `${current.replace(/[。.\s]+$/, "")}。${suffix}`
        : suffix;
    }
  }
  scheduleWorkflowPreflight();
}

function applyVideoScene(sceneId, { replacePrevious = true, appendMotionPrompt = false } = {}) {
  const scene = (videoPlaybook().video_scenes || []).find((item) => item.id === sceneId);
  if (!scene || !promptInput) return;
  if (replacePrevious && lastAppliedVideoSceneId && lastAppliedVideoSceneId !== sceneId) {
    const previous = (videoPlaybook().video_scenes || []).find((item) => item.id === lastAppliedVideoSceneId);
    let text = String(promptInput.value || "");
    for (const clause of [previous?.prompt_suffix, previous?.prompt_suffix_en]) {
      text = stripPromptClause(text, clause);
    }
    promptInput.value = text;
  }
  const language = /[\u4e00-\u9fff]/.test(promptInput.value || scene.prompt_suffix || "") ? "zh" : "en";
  const suffix = language === "en" ? scene.prompt_suffix_en || scene.prompt_suffix : scene.prompt_suffix || scene.prompt_suffix_en;
  if (suffix) {
    const current = String(promptInput.value || "").trim();
    promptInput.value = current ? (current.includes(suffix) ? current : `${current.replace(/[。.\s]+$/, "")}。${suffix}`) : suffix;
  }
  lastAppliedVideoSceneId = sceneId;
  markActiveChips(videoSceneChips, "data-video-scene", sceneId);
  if (scene.motion_hint) applyVideoMotion(scene.motion_hint, { appendPrompt: appendMotionPrompt });
  else scheduleWorkflowPreflight();
}

function syncVideoUnrestrictedStrength(value, { preflight = true } = {}) {
  const minimum = Number(videoUnrestrictedStrength?.min || 0);
  const maximum = Number(videoUnrestrictedStrength?.max || 1.2);
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return;
  const normalized = Math.max(minimum, Math.min(maximum, numeric));
  if (videoUnrestrictedStrength) videoUnrestrictedStrength.value = String(normalized);
  if (videoUnrestrictedStrengthRange) videoUnrestrictedStrengthRange.value = String(normalized);
  if (preflight) scheduleWorkflowPreflight();
}

function syncAdultContentAttestation(show) {
  adultContentAttestation?.classList.toggle("hidden", !show);
  if (!show && adultContentAck) adultContentAck.checked = false;
}

function renderVideoUnrestricted(option) {
  const panel = document.querySelector('[data-section="unrestricted"]');
  if (!panel || !videoUnrestrictedToggle) return;
  // 一键玩法预设只在无限制模式实际开启后展示，默认界面保持干净。
  const recipeBar = document.querySelector("#videoAdultRecipes");
  const stepAllows = currentStep().sections.includes("unrestricted");
  const config = option?.unrestricted || null;
  const hasRecipes = (videoPlaybook().wizard_modes || []).some((item) => item.one_click);
  panel.classList.toggle("hidden", !stepAllows || (!config && !hasRecipes));
  if (!stepAllows) {
    videoUnrestrictedToggle.checked = false;
    videoUnrestrictedToggle.disabled = true;
    videoUnrestrictedStrengthField?.classList.add("hidden");
    videoInstallUnrestrictedButton?.classList.add("hidden");
    videoUnrestrictedSource?.classList.add("hidden");
    videoNsfwExtras?.classList.add("hidden");
    recipeBar?.classList.add("hidden");
    syncAdultContentAttestation(false);
    return;
  }
  if (!config) {
    videoUnrestrictedToggle.checked = false;
    videoUnrestrictedToggle.disabled = true;
    videoUnrestrictedStrengthField?.classList.add("hidden");
    videoInstallUnrestrictedButton?.classList.add("hidden");
    videoUnrestrictedSource?.classList.add("hidden");
    videoNsfwExtras?.classList.add("hidden");
    recipeBar?.classList.add("hidden");
    syncAdultContentAttestation(false);
    if (videoUnrestrictedStatus) videoUnrestrictedStatus.textContent = "当前模型没有已验证的无限制方案。";
    renderVideoAdultRecipes();
    return;
  }

  const addonReady = Boolean(config.addon_ready);
  const available = Boolean(config.toggle_enabled && (config.lora_enabled === false || addonReady));
  videoUnrestrictedToggle.disabled = !available;
  if (!available) videoUnrestrictedToggle.checked = false;
  videoUnrestrictedStrengthField?.classList.toggle("hidden", !available || config.lora_enabled === false);
  const motionLoraField = videoMotionLoraPack?.closest("label");
  motionLoraField?.classList.toggle("hidden", config.lora_enabled === false);
  if (config.lora_enabled === false && videoMotionLoraPack) videoMotionLoraPack.value = "";
  const minimum = Number(config.strength_min ?? 0);
  const maximum = Number(config.strength_max ?? 1.2);
  const step = Number(config.strength_step ?? 0.05);
  const defaultValue = Number(config.strength_default ?? 0.8);
  for (const input of [videoUnrestrictedStrength, videoUnrestrictedStrengthRange].filter(Boolean)) {
    input.min = String(minimum);
    input.max = String(maximum);
    input.step = String(step);
  }
  if (videoUnrestrictedStrength && videoUnrestrictedStrength.dataset.profile !== option?.id) {
    videoUnrestrictedStrength.dataset.profile = option?.id || "";
    syncVideoUnrestrictedStrength(defaultValue, { preflight: false });
  }
  if (videoUnrestrictedStrengthHelp) {
    videoUnrestrictedStrengthHelp.textContent = config.strength_help || `推荐 ${config.strength_recommended || `${minimum}-${maximum}`}。`;
  }
  const needsAddon = Boolean(config.addon_profile && !addonReady);
  videoInstallUnrestrictedButton?.classList.toggle("hidden", !needsAddon);
  if (videoInstallUnrestrictedButton) videoInstallUnrestrictedButton.dataset.profile = config.addon_profile || "";
  videoUnrestrictedSource?.classList.toggle("hidden", !config.source);
  if (videoUnrestrictedSource && config.source) videoUnrestrictedSource.href = config.source;

  if (available) {
    videoUnrestrictedStatus.textContent = `${config.label || "社区附加包已就绪"}；${config.note || "社区附加包已就绪。"}`;
  } else if (config.toggle_enabled) {
    videoUnrestrictedStatus.textContent = `${config.label || "有兼容社区方案"}，需要先准备独立附加包；点击下方「准备社区附加包」后再开启。${config.note || ""}`;
  } else {
    videoUnrestrictedStatus.textContent = `${config.label || "当前模型不可用"}；${config.note || "暂无已验证的兼容方案。"}`;
  }
  const showExtras = Boolean(config && videoUnrestrictedToggle.checked && available);
  syncAdultContentAttestation(showExtras);
  videoNsfwExtras?.classList.toggle("hidden", !showExtras);
  recipeBar?.classList.toggle("hidden", !showExtras);
  renderVideoPlaybookControls(option);
}

function matchingTextToVideoOption(stepId) {
  const current = selectedModelOption(stepId);
  if (optionCapabilities(current).text_to_video) return current;
  return capabilityCounterpart(stepId, current, "text_to_video");
}

function switchImageModelsToTextVideo() {
  const switched = [];
  ["draft", "keyframe"].forEach((stepId) => {
    const current = selectedModelOption(stepId);
    if (optionCapabilities(current).text_to_video) return;
    const fallback = matchingTextToVideoOption(stepId);
    if (!fallback) return;
    selectedModels[stepId] = fallback.id;
    switched.push(fallback.label);
  });
  return switched;
}

function switchTextModelsToImageVideo() {
  const switched = [];
  ["draft", "keyframe"].forEach((stepId) => {
    const current = selectedModelOption(stepId);
    if (!current || optionCapabilities(current).image_to_video) return;
    const replacement = capabilityCounterpart(stepId, current, "image_to_video");
    if (!replacement) return;
    selectedModels[stepId] = replacement.id;
    switched.push(replacement.label);
  });
  return switched;
}

function pickPreferredUnrestrictedOption(options, { preferI2v = true } = {}) {
  const usable = (options || []).filter(
    (item) => item?.unrestricted && item.supported !== false && item.status !== "blocked",
  );
  const fallbacks = videoPlaybook().video_model_fallbacks || {};
  const ranked = preferI2v ? fallbacks.i2v || [] : [...(fallbacks.t2v || []), ...(fallbacks.i2v || [])];
  for (const target of ranked) {
    const match = usable.find((item) => item.mode === target || item.id === target);
    if (!match) continue;
    if (preferI2v && !optionCapabilities(match).image_to_video) continue;
    return match;
  }
  if (preferI2v) {
    return usable.find((item) => optionCapabilities(item).image_to_video) || usable[0] || null;
  }
  return usable[0] || null;
}

function ensureUnrestrictedVideoModels({ preferI2v = true } = {}) {
  const switched = [];
  ["draft", "keyframe"].forEach((stepId) => {
    const options = modelOptionsForStep(stepId);
    const current = selectedModelOption(stepId);
    if (current?.unrestricted && (!preferI2v || optionCapabilities(current).image_to_video)) {
      return;
    }
    const preferred = pickPreferredUnrestrictedOption(options, { preferI2v });
    if (!preferred || preferred.id === current?.id) return;
    selectedModels[stepId] = preferred.id;
    switched.push(preferred.label);
  });
  return switched;
}

function alignedFrameCount(target, capabilities) {
  const step = Math.max(1, Number(capabilities?.frame_step || 1));
  const offset = Number(capabilities?.frame_offset || 0);
  const minimum = Math.max(1, Number(capabilities?.min_frames || 1));
  const maximum = Math.max(minimum, Number(capabilities?.max_frames || 481));
  if (step === 1) return Math.max(minimum, Math.min(maximum, Math.round(target)));
  const minIndex = Math.max(0, Math.ceil((minimum - offset) / step));
  const maxIndex = Math.max(minIndex, Math.floor((maximum - offset) / step));
  const index = Math.max(minIndex, Math.min(maxIndex, Math.round((Number(target) - offset) / step)));
  return offset + index * step;
}

function formatPresetSeconds(frames, fps) {
  const seconds = Number(frames) / Math.max(1, Number(fps || 24));
  const rounded = Math.round(seconds * 10) / 10;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
}

function renderModelPresets(option) {
  const defaults = option?.defaults || {};
  const capabilities = optionCapabilities(option);
  const sizeContainer = document.querySelector("#sizePreset");
  const durationContainer = document.querySelector("#durationPreset");

  if (sizeContainer && defaults.width && defaults.height) {
    const configured = Array.isArray(capabilities.resolution_presets)
      ? capabilities.resolution_presets.filter((item) => item?.width && item?.height)
      : [];
    const presets = [];
    const addPreset = (item) => {
      const key = `${Number(item.width)}x${Number(item.height)}`;
      if (presets.some((preset) => preset.key === key)) return;
      presets.push({ ...item, key });
    };
    addPreset({ label: "当前推荐", width: defaults.width, height: defaults.height });
    configured.forEach(addPreset);
    sizeContainer.innerHTML = presets
      .slice(0, 4)
      .map((item) => `<button type="button" data-width="${Number(item.width)}" data-height="${Number(item.height)}">${escapeHtml(item.label || `${item.width} x ${item.height}`)}<small>${Number(item.width)} x ${Number(item.height)}</small></button>`)
      .join("");
  }

  if (durationContainer && defaults.length) {
    const fps = Number(defaults.fps || capabilities.fixed_fps || fpsInput.value || 24);
    const base = alignedFrameCount(Number(defaults.length), capabilities);
    const candidates = [
      { label: "短", frames: alignedFrameCount(base * 0.66, capabilities) },
      { label: "推荐", frames: base },
      { label: "长", frames: alignedFrameCount(base * 1.66, capabilities) },
    ].filter((item, index, rows) => rows.findIndex((candidate) => candidate.frames === item.frames) === index);
    durationContainer.innerHTML = candidates
      .map((item) => `<button type="button" data-length="${item.frames}">${item.label} ${formatPresetSeconds(item.frames, fps)} 秒<small>${item.frames} 帧</small></button>`)
      .join("");
    lengthInput.min = String(Number(capabilities.min_frames || 9));
    lengthInput.max = String(Number(capabilities.max_frames || 481));
    lengthInput.step = String(Math.max(1, Number(capabilities.frame_step || 1)));
  }
}

function applyModelDefaults(option) {
  const defaults = option?.defaults || {};
  if (lengthInput) delete lengthInput.dataset.baseLength;
  if (cfgInput) delete cfgInput.dataset.baseCfg;
  if (videoUnrestrictedStrength) delete videoUnrestrictedStrength.dataset.baseStrength;
  renderModelPresets(option);
  if (defaults.width && defaults.height) {
    setSize(defaults.width, defaults.height);
  }
  if (defaults.length) setLength(defaults.length);
  if (defaults.fps !== undefined) fpsInput.value = defaults.fps;
  if (defaults.steps !== undefined) stepsInput.value = defaults.steps;
  if (defaults.cfg !== undefined) cfgInput.value = defaults.cfg;
}

// ---------------------------------------------------------------------------
// 工作流高级参数
//
// 控件不是写死在 HTML 里的，而是照着后端 /api/status 下发的 option.advanced_params
// 动态渲染的。接新模型（含以后走 API 节点的云端模型）时只要后端 video_params 里
// 多一条声明，这里不用改。
// ---------------------------------------------------------------------------
let advancedSchema = [];
let advancedSchemaByMode = {};
let modeCapabilitiesByMode = {};
let endImageModes = new Set();
// 只存用户显式改过的项。不能存"当前生效值"——否则换模型时上一个模型的默认值
// 会被当成显式覆盖带过去（例如上一个模型的 VAE tile 默认值覆盖当前模型）。
const advancedValues = new Map();

const SOCIAL_TARGET_STORAGE_KEY = "local-ai-workbench.social.target";
const SOCIAL_QUALITY_STORAGE_KEY = "local-ai-workbench.social.quality";

function socialEngineForMode(mode) {
  const engine = modeCapabilitiesByMode?.[mode]?.engine || optionCapabilities(selectedModelOption("draft")).engine || "generic";
  if (engine === "minimax_h3") return "minimax_h3";
  if (engine === "ltx25") return "ltx25";
  return "generic";
}

function selectedSocialTarget() {
  const targetId = socialPlatformSelect?.value || socialPresetData?.default_target || "tiktok";
  return (socialPresetData?.targets || []).find((item) => item.id === targetId) || null;
}

function selectedSocialRecipe() {
  const mode = selectedModelOption("draft")?.mode || modeInput?.value || "";
  const engine = socialEngineForMode(mode);
  const targetId = socialPlatformSelect?.value || socialPresetData?.default_target || "tiktok";
  const qualityId = socialQualityInput?.value || socialPresetData?.default_quality || "balanced";
  return socialPresetData?.recipes?.[engine]?.[targetId]?.[qualityId] || null;
}

function updateSocialSafeZone() {
  if (!keyframePreview) return;
  const target = selectedSocialTarget();
  const zone = target?.safe_zone || {};
  keyframePreview.style.setProperty("--safe-top", `${Number(zone.top || 0)}%`);
  keyframePreview.style.setProperty("--safe-right", `${Number(zone.right || 0)}%`);
  keyframePreview.style.setProperty("--safe-bottom", `${Number(zone.bottom || 0)}%`);
  keyframePreview.style.setProperty("--safe-left", `${Number(zone.left || 0)}%`);
  keyframePreview.classList.toggle(
    "social-safe-zone-active",
    Boolean(socialSafeZoneToggle?.checked && currentStep().id === "draft" && target),
  );
}

function applySocialAdvancedHints(recipe) {
  const option = selectedModelOption("draft");
  const allowed = new Set(advancedSchemaFor(option).map((spec) => spec.id));
  Object.entries(recipe?.advanced || {}).forEach(([key, value]) => {
    if (allowed.has(key)) advancedValues.set(key, value);
  });
  renderAdvancedParams(option);
}

function renderSocialRecipe({ apply = false } = {}) {
  const recipe = selectedSocialRecipe();
  const target = selectedSocialTarget();
  if (!recipe || !target) {
    if (socialGenerationSize) socialGenerationSize.textContent = "等待平台预设";
    updateSocialSafeZone();
    return;
  }

  if (apply && socialAutoTune?.checked && currentStep().id === "draft") {
    const generation = recipe.generation || {};
    if (generation.width && generation.height) setSize(generation.width, generation.height);
    if (generation.length) setLength(generation.length);
    if (generation.fps) fpsInput.value = String(generation.fps);
    if (generation.steps) stepsInput.value = String(generation.steps);
    if (generation.cfg != null) cfgInput.value = String(generation.cfg);
    applySocialAdvancedHints(recipe);
    if (pipelineTuneToggle) pipelineTuneToggle.checked = Boolean(recipe.pipeline?.deflicker);
    if (pipelineRifeToggle) pipelineRifeToggle.checked = Boolean(recipe.pipeline?.rife);
    if (pipelineUpscaleToggle) pipelineUpscaleToggle.checked = Boolean(recipe.pipeline?.upscale);
  }

  const delivery = recipe.delivery || {};
  const seconds = Number(lengthInput?.value || recipe.generation?.length || 0) / Math.max(1, Number(fpsInput?.value || recipe.generation?.fps || 24));
  if (socialGenerationSize) {
    socialGenerationSize.textContent = `${widthInput?.value || recipe.generation?.width} x ${heightInput?.value || recipe.generation?.height} · ${fpsInput?.value || recipe.generation?.fps} FPS`;
  }
  if (socialDeliverySize) {
    socialDeliverySize.textContent = `${delivery.width} x ${delivery.height} · ${delivery.fps} FPS`;
  }
  if (socialDurationText) socialDurationText.textContent = `约 ${seconds.toFixed(seconds >= 10 ? 0 : 1)} 秒`;
  if (socialTargetNote) {
    const upscaleNote = (Number(widthInput?.value || 0) !== Number(delivery.width) || Number(heightInput?.value || 0) !== Number(delivery.height))
      ? " 生成后请在清晰度增强/拼接步骤输出目标尺寸。"
      : " 当前画布已接近交付尺寸。";
    socialTargetNote.textContent = `${target.note || ""}${upscaleNote}`;
  }
  if (socialSpecLink) {
    socialSpecLink.href = target.source || "#";
    socialSpecLink.classList.toggle("hidden", !target.source);
  }
  updateSocialSafeZone();
  scheduleWorkflowPreflight();
}

function renderSocialPresetControls() {
  if (!socialPresetData || !socialPlatformSelect || !socialQualitySwitch) return;
  const rememberedTarget = localStorage.getItem(SOCIAL_TARGET_STORAGE_KEY);
  const rememberedQuality = localStorage.getItem(SOCIAL_QUALITY_STORAGE_KEY);
  const targets = socialPresetData.targets || [];
  const groups = new Map();
  targets.forEach((target) => {
    const group = target.group || "其他";
    if (!groups.has(group)) groups.set(group, []);
    groups.get(group).push(target);
  });
  socialPlatformSelect.innerHTML = [...groups.entries()]
    .map(([group, items]) => `<optgroup label="${escapeHtml(group)}">${items.map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.label)} · ${escapeHtml(item.aspect_ratio)}</option>`).join("")}</optgroup>`)
    .join("");
  socialPlatformSelect.value = targets.some((item) => item.id === rememberedTarget)
    ? rememberedTarget
    : socialPresetData.default_target || targets[0]?.id || "tiktok";
  const qualityTiers = socialPresetData.quality_tiers || [];
  const quality = qualityTiers.some((item) => item.id === rememberedQuality)
    ? rememberedQuality
    : socialPresetData.default_quality || "balanced";
  if (socialQualityInput) socialQualityInput.value = quality;
  socialQualitySwitch.innerHTML = qualityTiers
    .map((item) => `<button type="button" data-social-quality="${escapeHtml(item.id)}" title="${escapeHtml(item.description || "")}">${escapeHtml(item.label)}</button>`)
    .join("");
  socialQualitySwitch.querySelectorAll("button").forEach((button) => {
    button.classList.toggle("active", button.dataset.socialQuality === quality);
  });
  renderSocialRecipe({ apply: Boolean(socialAutoTune?.checked) });
}

async function loadSocialPresets() {
  try {
    const response = await fetch("/api/social-presets");
    if (!response.ok) return;
    socialPresetData = await response.json();
    renderSocialPresetControls();
  } catch (_) {
    socialPresetData = null;
  }
}

function activeH3Recipe() {
  const profile = advancedSchema.find((item) => item.id === "h3_acceleration_profile");
  if (!profile) return null;
  const key = advancedValues.get(profile.id) ?? profile.default;
  return profile.choice_details?.[key] || null;
}

function h3LockedValue(spec) {
  const recipe = activeH3Recipe();
  if (!recipe) return undefined;
  return {
    sampler_name: recipe.sampler, scheduler: recipe.scheduler,
    h3_shift_video: recipe.shift_video, h3_shift_audio: recipe.shift_audio,
    denoise: 1,
  }[spec.id];
}

function advancedEffectiveValue(spec) {
  const locked = h3LockedValue(spec);
  if (locked !== undefined) return locked;
  return advancedValues.has(spec.id) ? advancedValues.get(spec.id) : spec.default;
}

async function loadAdvancedSchemas() {
  // schema 只跟 mode 有关，不依赖 ComfyUI 是否在线，所以单独拉一次缓存起来。
  try {
    const response = await fetch("/api/video-params");
    if (!response.ok) return;
    const data = await response.json();
    advancedSchemaByMode = data.modes || {};
    modeCapabilitiesByMode = data.capabilities || {};
    endImageModes = new Set(data.end_image_modes || []);
    renderAdvancedParams(selectedModelOption(currentStep().id));
  } catch (error) {
    // 拉不到就退化成"没有高级参数"，不影响主流程。
  }
  await loadSocialPresets();
}

function advancedSchemaFor(option) {
  if (Array.isArray(option?.advanced_params) && option.advanced_params.length) {
    return option.advanced_params;
  }
  return advancedSchemaByMode[option?.mode] || [];
}

function advancedIsDefault(spec, value) {
  if (spec.type === "bool") return Boolean(value) === Boolean(spec.default);
  if (spec.type === "select") return String(value) === String(spec.default);
  return Number(value) === Number(spec.default);
}

function collectAdvancedParams() {
  // 只提交和默认值不同的项：后端会补齐其余的，任务记录也更容易看出改了什么。
  const payload = {};
  advancedSchema.forEach((spec) => {
    const value = advancedEffectiveValue(spec);
    if (advancedIsDefault(spec, value)) return;
    payload[spec.id] = value;
  });
  return payload;
}

function syncAdvancedInput() {
  const payload = collectAdvancedParams();
  const changed = Object.keys(payload);
  if (videoAdvancedInput) videoAdvancedInput.value = changed.length ? JSON.stringify(payload) : "";
  if (videoAdvancedSummary) {
    const labels = changed
      .map((id) => advancedSchema.find((spec) => spec.id === id)?.label || id)
      .slice(0, 3);
    const suffix = changed.length > labels.length ? ` 等 ${changed.length} 项` : "";
    videoAdvancedSummary.textContent = changed.length
      ? `已调整 ${labels.join("、")}${suffix}`
      : advancedSchema.length
        ? `${advancedSchema.length} 项可调，当前全部为默认值`
        : "当前模型没有可调的高级参数";
  }
  if (videoAdvancedPanel) videoAdvancedPanel.dataset.changed = changed.length ? "true" : "false";
  if (videoAdvancedReset) videoAdvancedReset.disabled = changed.length === 0;
}

function setAdvancedValue(spec, value) {
  advancedValues.set(spec.id, value);
  if (spec.id === "h3_acceleration_profile") refreshH3ProfileControls();
  refreshH3Tools();
  syncAdvancedInput();
  scheduleWorkflowPreflight();
}

function refreshH3ProfileControls() {
  const recipe = activeH3Recipe();
  if (stepsInput) {
    const help = stepsInput.closest(".field")?.querySelector("small");
    if (help) {
      help.dataset.manualHelp ??= help.textContent;
      help.textContent = recipe
        ? `当前档位固定 ${recipe.steps} 步，不能单独调整。切回原生档可恢复手动步数。`
        : help.dataset.manualHelp;
    }
    if (recipe) {
      if (!stepsInput.dataset.h3Steps || stepsInput.value !== stepsInput.dataset.h3Steps) {
        stepsInput.dataset.h3ManualSteps = stepsInput.value;
      }
      stepsInput.value = String(recipe.steps);
      stepsInput.dataset.h3Steps = stepsInput.value;
      stepsInput.readOnly = true;
      stepsInput.title = "当前 H3 档位使用配套步数；选择原生档可手动调整";
    } else if (stepsInput.dataset.h3Steps) {
      if (stepsInput.value === stepsInput.dataset.h3Steps) stepsInput.value = stepsInput.dataset.h3ManualSteps;
      delete stepsInput.dataset.h3Steps;
      delete stepsInput.dataset.h3ManualSteps;
      stepsInput.readOnly = false;
      stepsInput.title = "";
    }
  }
  advancedSchema.forEach((spec) => {
    const card = videoAdvancedGroups?.querySelector(`[data-param="${spec.id}"]`);
    if (!card) return;
    const locked = h3LockedValue(spec) !== undefined;
    const value = advancedEffectiveValue(spec);
    card.querySelectorAll("input, select").forEach((control) => {
      control.disabled = locked;
      if (control.type !== "checkbox") control.value = value;
    });
    const badge = card.querySelector(".adv-param-value");
    if (badge) badge.textContent = `${advancedDisplayValue(spec, value)}${locked ? " · 档位固定" : ""}`;
    card.dataset.changed = advancedIsDefault(spec, value) ? "false" : "true";
    const status = card.querySelector(".adv-profile-status");
    if (status) {
      const info = spec.choice_status?.[value];
      status.textContent = [
        info ? `${info.label}：${info.message}` : "待环境检查，尚未验证此档位。",
        recipe ? `实际参数：${recipe.steps} 步 · ${recipe.sampler} / ${recipe.scheduler} · 视频 shift ${recipe.shift_video} / 音频 shift ${recipe.shift_audio} · 完整去噪。` : "原生档使用手动采样参数。",
        !info && recipe?.lora_name ? `需要：${recipe.lora_name}` : "",
      ].filter(Boolean).join("\n");
    }
  });
  refreshH3Tools();
}

function h3Value(id) {
  const spec = advancedSchema.find((item) => item.id === id);
  return spec ? advancedEffectiveValue(spec) : undefined;
}

function refreshH3Tools() {
  const panel = document.querySelector("#h3Tools");
  if (!panel) return;
  const visible = currentStep().id === "draft" && advancedSchema.some((spec) => spec.id === "h3_task");
  panel.classList.toggle("hidden", !visible);
  const task = h3Value("h3_task") || "generate";
  const upscale = Boolean(h3Value("h3_latent_upscale"));
  const taskControl = document.querySelector("#h3Task");
  taskControl.value = task;
  const reference = selectedModelOption(currentStep().id)?.mode === "minimax_h3_r2v";
  Array.from(taskControl.options).forEach((option) => { option.disabled = reference && option.value !== "generate"; });
  document.querySelector("#h3LatentUpscale").checked = upscale;
  document.querySelector("#h3ControlField").classList.toggle("hidden", task !== "control");
  document.querySelector("#h3InpaintFields").classList.toggle("hidden", task !== "inpaint");
  for (const [id, use] of [["h3ControlVideo", "control"], ["h3SourceVideo", "inpaint"], ["h3Mask", "inpaint"]]) {
    document.getElementById(id).disabled = !visible || task !== use;
  }
  for (const spec of advancedSchema.filter((item) => item.group === "h3_creative")) {
    const card = videoAdvancedGroups?.querySelector(`[data-param="${spec.id}"]`);
    const relevant = spec.id === "h3_control_type" ? task === "control"
      : spec.id === "h3_preserve_source_audio" ? task === "inpaint"
        : spec.id.startsWith("h3_control_") ? task !== "generate" : upscale;
    card?.classList.toggle("hidden", !relevant);
  }
  if (!visible) return;
  // Match Python's ties-to-even rounding used by normalize_dimension.
  const alignDimension = (value) => {
    const units = Math.min(2048, Math.max(256, Number(value) || 256)) / 32;
    const floor = Math.floor(units);
    return 32 * (units - floor === 0.5 ? floor + floor % 2 : Math.round(units));
  };
  const width = alignDimension(widthInput.value);
  const height = alignDimension(heightInput.value);
  const factor = Number(h3Value("h3_upscale_factor") || 1.5);
  const base = [width, height].map((value) => Math.max(32, Math.round(value / factor / 32) * 32));
  const delivery = width === 1920 && height === 1088 ? "1920 × 1080" : width === 1088 && height === 1920 ? "1080 × 1920" : `${width} × ${height}`;
  document.querySelector("#h3ResolutionSummary").textContent = upscale
    ? `起始 ${base.join(" × ")} → 精修 ${width} × ${height} → 输出 ${delivery} · 精修 ${h3Value("h3_refine_steps")} 步`
    : `目标输出 ${delivery}`;
  const notes = [];
  if ((task !== "generate" || upscale) && activeH3Recipe()) notes.push("请先恢复原生档：当前不叠加 LightX / Spectrum。");
  if (reference && task !== "generate") notes.push("Ref2VA 不支持 Fun ControlNet，请切回 FL2VA 或普通生成。");
  if (task !== "generate" && upscale) notes.push("控制 / 重绘不能与潜空间超分同时启用。");
  for (const id of [task !== "generate" && "h3_task", upscale && "h3_latent_upscale"].filter(Boolean)) {
    const status = advancedSchema.find((item) => item.id === id)?.dependency_status;
    notes.push(!status ? "尚未检查创作扩展。" : !status.asset_ok ? "缺少扩展权重，请安装创作扩展。"
      : !status.node_ok ? `权重已就绪，节点 ${status.node} 尚未加载；安装后需手动重启 ComfyUI 再预检。`
        : "扩展文件和节点已就绪，仍需预检及短片验证。");
  }
  if (upscale) notes.push("这是生成中的两段式超分，保留首段音轨；高分辨率精修仍可能占用大量显存。");
  const requestedFrames = Math.min(362, Math.max(9, Number(lengthInput.value) || 9));
  const alignedFrames = Math.min(362, 5 + 17 * Math.ceil((requestedFrames - 5) / 17));
  if (task !== "generate") notes.push(`素材至少覆盖 ${(alignedFrames / 24).toFixed(2)} 秒（H3 对齐后 ${alignedFrames} 帧），提交时会检查。`);
  document.querySelector("#h3ToolsStatus").textContent = [...new Set(notes)].join(" ");
}

for (const [id, param] of [["h3Task", "h3_task"], ["h3LatentUpscale", "h3_latent_upscale"]]) {
  document.getElementById(id)?.addEventListener("change", (event) => {
    const spec = advancedSchema.find((item) => item.id === param);
    if (spec) setAdvancedValue(spec, spec.type === "bool" ? event.target.checked : event.target.value);
  });
}
for (const id of ["h3ControlVideo", "h3SourceVideo", "h3Mask"]) {
  document.getElementById(id)?.addEventListener("change", () => { refreshH3Tools(); scheduleWorkflowPreflight(); });
}
document.querySelector("#h3NativeBaseline")?.addEventListener("click", () => {
  for (const [id, value] of Object.entries({ h3_acceleration_profile: "native", h3_attention_backend: "pytorch",
    h3_task: "generate", h3_latent_upscale: false, sampler_name: "res_multistep",
    scheduler: selectedModelOption(currentStep().id)?.mode === "minimax_h3_r2v" ? "beta" : "simple",
    h3_shift_video: 12, h3_shift_audio: 3, denoise: 1 })) advancedValues.set(id, value);
  renderAdvancedParams(selectedModelOption(currentStep().id));
  stepsInput.value = "20";
  syncAdvancedInput();
  scheduleWorkflowPreflight();
});
document.querySelector("#h3InstallCreative")?.addEventListener("click", async () => {
  try { await launchOneClickInstall("minimax-h3-creative-addon", "H3 创作扩展"); }
  catch (error) { appendLog(`扩展安装失败：${error.message}`); }
});

function advancedDisplayValue(spec, value) {
  if (spec.type === "bool") return value ? "已开启" : "已关闭";
  if (spec.type === "select") return spec.choice_labels?.[value] || String(value);
  return String(value);
}

// 每个参数渲染成一张小卡：标题 + 当前值徽标 + 控件 + 是什么 + 什么时候调。
// 改过默认值的卡会带 data-changed，靠 CSS 高亮出来，方便一眼看出动过哪些。
function buildAdvancedCard(spec) {
  const value = advancedEffectiveValue(spec);
  const card = document.createElement("div");
  card.className = `adv-param adv-param-${spec.type}`;
  card.dataset.param = spec.id;

  const head = document.createElement("div");
  head.className = "adv-param-head";
  const name = document.createElement("span");
  name.className = "adv-param-label";
  name.textContent = spec.label;
  const badge = document.createElement("span");
  badge.className = "adv-param-value";
  head.append(name, badge);
  card.append(head);

  const markState = (current) => {
    const isDefault = advancedIsDefault(spec, current);
    card.dataset.changed = isDefault ? "false" : "true";
    badge.textContent = advancedDisplayValue(spec, current);
    badge.title = isDefault ? "当前为默认值" : `默认值是 ${advancedDisplayValue(spec, spec.default)}`;
  };

  const commitValue = (next) => {
    markState(next);
    setAdvancedValue(spec, next);
  };

  if (spec.type === "bool") {
    const toggle = document.createElement("label");
    toggle.className = "adv-switch";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.checked = Boolean(value);
    input.setAttribute("aria-label", spec.label);
    const track = document.createElement("span");
    track.className = "adv-switch-track";
    const state = document.createElement("span");
    state.className = "adv-switch-state";
    state.textContent = input.checked ? "开启" : "关闭";
    input.addEventListener("change", () => {
      state.textContent = input.checked ? "开启" : "关闭";
      commitValue(input.checked);
    });
    toggle.append(input, track, state);
    card.append(toggle);
  } else if (spec.type === "select") {
    const select = document.createElement("select");
    select.className = "adv-select";
    select.setAttribute("aria-label", spec.label);
    (spec.choices || []).forEach((choice) => {
      const opt = document.createElement("option");
      opt.value = choice;
      const label = spec.choice_labels?.[choice] || choice;
      const status = spec.choice_status?.[choice];
      opt.textContent = (choice === spec.default ? `${label}（默认）` : label) + (status ? ` · ${status.label}` : "");
      select.append(opt);
    });
    select.value = value ?? spec.default;
    select.addEventListener("change", () => commitValue(select.value));
    card.append(select);
    if (spec.id === "h3_acceleration_profile") {
      const status = document.createElement("p");
      status.className = "adv-param-help adv-profile-status";
      status.setAttribute("role", "status");
      status.setAttribute("aria-live", "polite");
      status.style.overflowWrap = "anywhere";
      status.style.whiteSpace = "pre-line";
      card.append(status);
    }
  } else {
    const control = document.createElement("div");
    control.className = "adv-slider";
    const range = document.createElement("input");
    const number = document.createElement("input");
    [range, number].forEach((input) => {
      input.min = spec.min;
      input.max = spec.max;
      input.step = spec.step;
      input.value = value ?? spec.default;
    });
    range.type = "range";
    range.setAttribute("aria-label", spec.label);
    number.type = "number";
    number.setAttribute("aria-label", `${spec.label}数值`);
    number.className = "adv-number";
    const commit = (source, mirror) => {
      const parsed = Number(source.value);
      if (Number.isNaN(parsed)) return;
      const clamped = Math.min(Number(spec.max), Math.max(Number(spec.min), parsed));
      mirror.value = clamped;
      if (source === number) source.value = clamped;
      commitValue(clamped);
    };
    range.addEventListener("input", () => commit(range, number));
    number.addEventListener("change", () => commit(number, range));
    const scale = document.createElement("div");
    scale.className = "adv-slider-scale";
    scale.innerHTML = `<span>${escapeHtml(String(spec.min))}</span><span>${escapeHtml(String(spec.max))}</span>`;
    control.append(range, number);
    card.append(control, scale);
  }

  if (spec.help) {
    const help = document.createElement("p");
    help.className = "adv-param-help";
    help.textContent = spec.help;
    card.append(help);
  }
  if (spec.recommend) {
    const tip = document.createElement("p");
    tip.className = "adv-param-tip";
    tip.textContent = spec.recommend;
    card.append(tip);
  }

  markState(value);
  return card;
}

function renderAdvancedParams(option, { resetValues = false } = {}) {
  if (!videoAdvancedGroups || !videoAdvancedPanel) return;
  const schema = advancedSchemaFor(option);
  const stepAllows = currentStep().sections.includes("advanced");
  advancedSchema = schema;
  videoAdvancedPanel.classList.toggle("hidden", !stepAllows || schema.length === 0);
  if (!schema.length) {
    // 只清空面板和待提交值，保留用户改过的覆盖：切到关键帧步骤再切回来不该丢设置。
    videoAdvancedGroups.replaceChildren();
    refreshH3ProfileControls();
    syncAdvancedInput();
    return;
  }

  // 换模型时丢掉不属于新 schema 的覆盖，避免不同引擎的参数相互污染。
  // 仍然适用的覆盖会保留，未改过的项自动落到新模型自己的默认值。
  if (resetValues) {
    advancedValues.clear();
  } else {
    const allowed = new Set(schema.map((spec) => spec.id));
    Array.from(advancedValues.keys()).forEach((key) => {
      if (!allowed.has(key)) advancedValues.delete(key);
    });
    schema.forEach((spec) => {
      if (spec.type === "select" && advancedValues.has(spec.id) && !spec.choices.includes(advancedValues.get(spec.id))) {
        advancedValues.delete(spec.id);
      }
    });
  }

  const fragment = document.createDocumentFragment();
  let currentGroup = null;
  let body = null;
  let count = null;
  let inGroup = 0;
  schema.filter((spec) => spec.surface !== "h3_tools").forEach((spec) => {
    if (spec.group !== currentGroup) {
      if (count) count.textContent = `${inGroup} 项`;
      currentGroup = spec.group;
      inGroup = 0;
      const block = document.createElement("section");
      block.className = "adv-group";
      const head = document.createElement("header");
      head.className = "adv-group-head";
      const title = document.createElement("h4");
      title.textContent = spec.group_label || "其他";
      count = document.createElement("span");
      count.className = "adv-group-count";
      head.append(title, count);
      body = document.createElement("div");
      body.className = "adv-group-body";
      block.append(head, body);
      fragment.append(block);
    }
    inGroup += 1;
    body.append(buildAdvancedCard(spec));
  });
  if (count) count.textContent = `${inGroup} 项`;
  videoAdvancedGroups.replaceChildren(fragment);
  refreshH3ProfileControls();
  syncAdvancedInput();
}

videoAdvancedReset?.addEventListener("click", () => {
  renderAdvancedParams(selectedModelOption(currentStep().id), { resetValues: true });
  scheduleWorkflowPreflight();
});

// 换尾帧会改变模型的条件输入结构，因此需要重新预检。
endImageInput?.addEventListener("change", () => scheduleWorkflowPreflight());

function renderModelCapabilities(option) {
  if (!modelCapabilityChips) return;
  const capabilities = optionCapabilities(option);
  let labels = Array.isArray(option?.capability_labels) ? option.capability_labels.filter(Boolean) : [];
  if (!labels.length && capabilities.kind === "generation") {
    if (capabilities.text_to_video && capabilities.image_to_video) labels.push("文字 / 图片输入");
    else if (capabilities.text_to_video) labels.push("文字生视频");
    else if (capabilities.image_to_video) labels.push("图生视频");
    if (capabilities.last_frame) labels.push("支持首尾帧");
    if (capabilities.native_audio) labels.push("原生音频");
    const referenceCount = Number(capabilities.reference_images || 0) + Number(capabilities.reference_videos || 0) + Number(capabilities.reference_audios || 0);
    if (referenceCount) labels.push("多参考图片 / 视频 / 音频");
    if (capabilities.fixed_fps) labels.push(`固定 ${capabilities.fixed_fps} FPS`);
    if (capabilities.frame_rule) labels.push(`帧数 ${capabilities.frame_rule}`);
  }
  modelCapabilityChips.innerHTML = labels
    .map((label) => `<span class="model-capability-chip">${escapeHtml(label)}</span>`)
    .join("");
  modelCapabilityChips.classList.toggle("hidden", !labels.length);
}

function applyModelVisibility(option) {
  const step = currentStep();
  const capabilities = optionCapabilities(option);
  const maxDimension = capabilities.kind === "generation"
    ? Math.max(1536, Number(capabilities.max_dimension || 1536))
    : 4096;
  if (widthInput) widthInput.max = String(maxDimension);
  if (heightInput) heightInput.max = String(maxDimension);
  if (sizeHelp) {
    sizeHelp.textContent = maxDimension >= 2048
      ? "当前模型已开放 1080P 实验档：内部按 1920 x 1088 生成，再居中裁成标准 1920 x 1080。更慢且更吃显存，建议先跑短镜头。"
      : "横屏适合宣传片和横版剪辑；竖屏适合短视频平台。数值越大，显存和时间越高。";
  }
  const hideImage = step.id === "draft" && capabilities.kind === "generation" && !capabilities.image_to_video;
  document.querySelectorAll('[data-section="image"], [data-section="keyframePreview"]').forEach((section) => {
    section.classList.toggle("hidden", hideImage || !step.sections.includes(section.dataset.section));
  });
  const allowsReferences = step.id === "draft" && (
    Number(capabilities.reference_images || 0) +
    Number(capabilities.reference_videos || 0) +
    Number(capabilities.reference_audios || 0)
  ) > 0;
  document.querySelectorAll('[data-section="referenceMedia"]').forEach((section) => {
    section.classList.toggle("hidden", !allowsReferences || !step.sections.includes("referenceMedia"));
  });
  renderReferenceMediaList();
  // 尾帧只有部分模型支持。名单由后端声明：优先用模型选项自带的标记，
  // ComfyUI 没连上、选项走本地兜底时再退回 /api/video-params 给的 mode 名单。
  if (endImageField) {
    const modelAllowsEnd = capabilities.last_frame ?? option?.supports_end_image ?? endImageModes.has(option?.mode);
    const allowEnd = !hideImage && step.sections.includes("endImage") && Boolean(modelAllowsEnd);
    endImageField.classList.toggle("hidden", !allowEnd);
    if (!allowEnd && endImageInput) endImageInput.value = "";
  }
  const fixedFps = capabilities.kind === "generation" ? Number(capabilities.fixed_fps || 0) : 0;
  if (fpsInput) {
    if (fixedFps) fpsInput.value = String(fixedFps);
    fpsInput.readOnly = Boolean(fixedFps);
    fpsInput.setAttribute("aria-readonly", fixedFps ? "true" : "false");
  }
  if (fpsHelp) {
    fpsHelp.textContent = fixedFps
      ? `当前模型固定使用 ${fixedFps} FPS，切换模型后会自动恢复可调。`
      : "不同模型会自动带入推荐帧率；插帧步骤可以进一步提高流畅度。";
  }
  if (durationHelp) {
    durationHelp.textContent = capabilities.frame_rule
      ? `当前模型按 ${capabilities.frame_rule} 帧规则自动对齐。镜头越长越吃显存，也更容易发生漂移。`
      : "视频越长越吃显存，也更容易发生人物、物体或背景漂移。";
  }
  if (cfgHelp) {
    const recommendedCfg = option?.defaults?.cfg;
    cfgHelp.textContent = recommendedCfg == null
      ? "不同模型的 CFG 逻辑不同，切换模型会自动带入推荐值。"
      : `当前模型推荐值为 ${recommendedCfg}。数值越高不一定越好，切换模型会自动更新。`;
  }
  renderKeyframeRequirement(option);
  renderModelCapabilities(option);
  renderVideoUnrestricted(option);
  renderAdvancedParams(option);
  renderSocialRecipe({ apply: false });
}

function getUpscaleScale() {
  const option = selectedModelOption("upscale");
  return Number(option?.scale || upscaleScaleInput.value || 2);
}

function syncSelectedModel({ applyDefaults = false } = {}) {
  const step = currentStep();
  const option = selectedModelOption(step.id);
  if (!option) {
    modelLabelInput.value = "";
    modelProfileInput.value = "";
    renderAdvancedParams(null);
    return;
  }

  selectedModels[step.id] = option.id;
  modeInput.value = option.mode || step.mode || "";
  modelLabelInput.value = option.model_label || option.label || "";
  modelProfileInput.value = option.id || "";
  upscaleModelInput.value = option.upscale_model || "RealESRGAN_x2plus.pth";
  upscaleScaleInput.value = option.scale || 2;
  rifeMultiplierInput.value = option.rife_multiplier || 2;
  const capabilities = optionCapabilities(option);
  const keyframeRequirement = step.id === "draft" && capabilities.image_input === "required" && !hasKeyframeUpload()
    ? " 当前模型需要上传关键帧图片，或改选 T2V 模型。"
    : "";
  modelChoiceHint.textContent = `${option.reason || "已选择该模型。"} 状态：${labelForStatus(option.status)}。${keyframeRequirement}`;
  if (videoModelInstallButton) {
    const needsAction = option.status === "blocked" || option.supported === false;
    const profile = option.install_profile || "";
    videoModelInstallButton.classList.toggle("hidden", !needsAction);
    videoModelInstallButton.dataset.profile = profile;
    videoModelInstallButton.textContent = profile
      ? `一键下载/修复 ${option.label}`
      : option.mode === "external_workflow"
        ? "打开 ComfyUI 模板"
        : "查看环境处理方式";
  }

  if (applyDefaults) {
    applyModelDefaults(option);
  }
  applyModelVisibility(option);
  if (step.id === "draft") {
    renderSocialRecipe({ apply: Boolean(applyDefaults && socialAutoTune?.checked) });
  }
  updateGlobalModelContext();
  updateTargetResolution();
  updateStepCopy();
  scheduleWorkflowPreflight();
}

function renderModelSelector({ applyDefaults = true } = {}) {
  const step = currentStep();
  const options = modelOptionsForStep(step.id);
  if (!modelSelector || !options.length) return;

  if (!selectedModels[step.id]) {
    selectedModels[step.id] = recommendedModelForStep(step.id);
  }
  const optionMarkup = (item) => {
      const marker = item.id === recommendedModelForStep(step.id) ? "推荐" : labelForStatus(item.status);
      const nsfwMarker = item.unrestricted ? " · 支持无限制" : "";
      const actionMarker = item.status === "blocked" && item.install_profile ? " · 可一键下载" : "";
      return `<option value="${escapeHtml(item.id)}">${escapeHtml(item.label)} · ${escapeHtml(marker)}${nsfwMarker}${actionMarker}</option>`;
    };
  if (step.id === "draft") {
    const groups = new Map();
    options.forEach((item) => {
      const group = item.group || "其他模型";
      if (!groups.has(group)) groups.set(group, []);
      groups.get(group).push(item);
    });
    modelSelector.innerHTML = [...groups.entries()]
      .map(([group, items]) => `<optgroup label="${escapeHtml(group)}">${items.map(optionMarkup).join("")}</optgroup>`)
      .join("");
  } else {
    modelSelector.innerHTML = options.map(optionMarkup).join("");
  }
  modelSelector.value = selectedModels[step.id];
  if (modelSelector.value !== selectedModels[step.id]) {
    selectedModels[step.id] = options.find((item) => item.status !== "blocked")?.id || options[0].id;
    modelSelector.value = selectedModels[step.id];
  }
  syncSelectedModel({ applyDefaults });
}

function selectedModelName(stepId = currentStep().id) {
  const option = selectedModelOption(stepId);
  return option?.label || "默认模型";
}

function joinDisplayPath(base, ...parts) {
  if (!base) return ["ComfyUI 用户目录", ...parts].join("/");
  const separator = base.includes("\\") ? "\\" : "/";
  return [base.replace(/[\\/]+$/, ""), ...parts].join(separator);
}

function outputDirectoryText() {
  return joinDisplayPath(environmentData?.base_dir, "output", outputSubdirInput?.value || "local_ai_workbench");
}

function workflowStatusHtml(message, errors = []) {
  const safeMessage = escapeHtml(String(message || ""));
  const safeErrors = (errors || []).filter(Boolean).map((item) => `<li>${escapeHtml(String(item))}</li>`).join("");
  if (!safeErrors) return safeMessage;
  return `${safeMessage ? `<strong>${safeMessage}</strong>` : "<strong>workflow 预检未通过</strong>"}<ul>${safeErrors}</ul>`;
}

function setWorkflowStatus(state, message, errors = []) {
  if (!workflowStatus) return;
  workflowStatus.className = `workflow-status ${state || ""}`.trim();
  workflowStatus.innerHTML = workflowStatusHtml(message, errors);
}

function workflowParams() {
  return new URLSearchParams({
    mode: modeInput.value || "",
    model_profile: modelProfileInput.value || "",
    model_label: modelLabelInput.value || "",
    width: widthInput.value || "1280",
    height: heightInput.value || "704",
    length: lengthInput.value || "81",
    fps: fpsInput.value || "24",
    seed: seedInput.value || "-1",
    steps: stepsInput.value || "4",
    cfg: cfgInput.value || "1",
    upscale_model: upscaleModelInput.value || "RealESRGAN_x2plus.pth",
    upscale_scale: upscaleScaleInput.value || "2",
    rife_multiplier: rifeMultiplierInput.value || "2",
    has_image: hasKeyframeUpload() ? "1" : "0",
    has_end_image: endImageInput?.files?.length ? "1" : "0",
    has_reference_media: referenceMediaSummary().total ? "1" : "0",
    has_h3_control_video: !document.querySelector("#h3ControlVideo").disabled && document.querySelector("#h3ControlVideo").files.length ? "1" : "0",
    has_h3_source_video: !document.querySelector("#h3SourceVideo").disabled && document.querySelector("#h3SourceVideo").files.length ? "1" : "0",
    has_h3_mask: !document.querySelector("#h3Mask").disabled && document.querySelector("#h3Mask").files.length ? "1" : "0",
    h3_mask_is_video: /\.(mp4|mov|mkv|webm|avi)$/i.test(document.querySelector("#h3Mask").files[0]?.name || "") ? "1" : "0",
    unrestricted: videoUnrestrictedToggle?.checked ? "1" : "0",
    adult_content_ack: adultContentAck?.checked ? "1" : "0",
    unrestricted_strength: videoUnrestrictedStrength?.value || "1",
    auto_inject_trigger: videoAutoInjectTrigger?.checked ? "1" : "0",
    auto_strip_negative: videoAutoStripNegative?.checked ? "1" : "0",
    custom_trigger: videoCustomTrigger?.value || "",
    video_auto_inject_trigger: videoAutoInjectTrigger?.checked ? "1" : "0",
    video_auto_strip_negative: videoAutoStripNegative?.checked ? "1" : "0",
    video_custom_trigger: videoCustomTrigger?.value || "",
    video_motion: videoMotionPreset?.value || "medium",
    social_target: socialPlatformSelect?.value || "tiktok",
    social_quality: socialQualityInput?.value || "balanced",
    // 预检必须带上高级参数，否则预览的图和实际提交的图不是同一张。
    advanced: videoAdvancedInput?.value || "",
  });
}

async function preflightWorkflow({ quiet = true, params = null, step = currentStep(), independent = false } = {}) {
  if (!step.sections.includes("modelChoice")) return true;
  if (!independent && workflowCheckController) {
    workflowCheckController.abort();
  }
  const controller = new AbortController();
  if (!independent) workflowCheckController = controller;
  const requestId = independent ? null : ++preflightRequestId;
  const isCurrent = () => !independent && requestId === preflightRequestId && currentStep().id === step.id;
  const optionName = selectedModelName();
  if (isCurrent()) setWorkflowStatus("pending", `正在检查 ${optionName}。`);
  try {
    const response = await fetch(`/api/workflow?${(params || workflowParams()).toString()}`, {
      signal: controller.signal,
    });
    const data = await response.json();
    if (!response.ok) throw new Error(formatError(data.detail || data));
    if (data.ok) {
      const detail = data.local
        ? "本地处理，无需 ComfyUI 图。"
        : `${data.node_count || 0} 个节点，输出节点 ${data.output_nodes?.join(", ") || "-"}`;
      const warnings = (data.risk_checks || []).filter((item) => item.level === "warn");
      const warningText = warnings.length ? ` 提醒：${warnings.map((item) => item.title || item.message).join("、")}` : "";
      if (isCurrent()) setWorkflowStatus(warnings.length ? "pending" : "ok", `${data.message} ${detail}${warningText}`);
      return true;
    }
    const errors = data.errors || [];
    const message = data.message || "workflow 预检未通过";
    if (isCurrent()) setWorkflowStatus("bad", message, errors);
    const logMessage = errors.length ? `${message}\n${errors.join("\n")}` : message;
    if (!quiet) appendLog(`workflow 预检失败：${logMessage}`);
    return false;
  } catch (error) {
    if (error.name === "AbortError") return false;
    if (isCurrent()) setWorkflowStatus("bad", `workflow 拉取失败：${error.message}`);
    if (!quiet) appendLog(`workflow 拉取失败：${error.message}`);
    return false;
  }
}

function scheduleWorkflowPreflight() {
  if (videoSubmitting) return;
  if (!currentStep().sections.includes("modelChoice")) return;
  if (workflowPreflightTimer) clearTimeout(workflowPreflightTimer);
  workflowPreflightTimer = window.setTimeout(() => {
    workflowPreflightTimer = null;
    preflightWorkflow();
  }, 250);
}

function renderEnvironmentCards(data) {
  const os = data.os || {};
  const comfy = data.comfy || {};
  const paths = data.paths || {};
  const hardware = data.hardware || {};
  const mac = hardware.mac || {};
  const devices = hardware.devices || [];
  const firstDevice = devices[0] || {};
  const ffmpeg = (data.tools || []).find((item) => item.name === "ffmpeg");
  const missingCount = (data.missing_installable || []).length;
  const modelSync = data.model_sync || {};
  const syncModel = modelSync.selected_model || selectedCatalogItem() || {};
  const syncMissingCount = (modelSync.missing_files || []).length;
  const syncFoundCount = (modelSync.found_files || []).length;
  const syncLevel = modelSync.level || "warn";
  const gpuLabel = devices.length
    ? `${firstDevice.name}${devices.length > 1 ? ` +${devices.length - 1}` : ""}`
    : hardware.accelerator === "mps"
      ? "Apple Metal / MPS"
      : "未检测到独立 GPU";
  const vramLabel = hardware.max_vram_gb
    ? `最高单卡 ${formatGb(hardware.max_vram_gb)}`
    : hardware.system_memory_gb
      ? `内存 ${formatGb(hardware.system_memory_gb)}`
      : "显存未知";
  const ffmpegDetail = ffmpeg && ffmpeg.ok
    ? `${ffmpeg.source || "ffmpeg"} | ${ffmpeg.path || ffmpeg.version || "已就绪"}`
    : (ffmpeg && (ffmpeg.message || ffmpeg.install_hint)) || "闪烁修复需要 ffmpeg";

  const cards = [
    {
      label: "操作系统",
      value: `${os.name || "-"} ${os.release || ""}`.trim(),
      detail: `${os.machine || "-"} | Python ${os.python || "-"}`,
      state: "ok",
    },
    {
      label: "GPU / 显存",
      value: mac.is_macos && mac.chip ? mac.chip : gpuLabel,
      detail: mac.is_macos
        ? `统一内存 ${formatGb(mac.unified_memory_gb || hardware.system_memory_gb)} | MPS ${hardware.comfy_torch_mps_ready || hardware.front_torch_mps_ready ? "已确认" : "待确认"}`
        : `${vramLabel}${hardware.sum_vram_gb ? ` | 总计 ${formatGb(hardware.sum_vram_gb)}` : ""}`,
      state: hardware.accelerator === "cpu" ? "blocked" : hardware.max_vram_gb >= 80 ? "ok" : "warn",
    },
    {
      label: "平台策略",
      value: platformStrategyLabel(hardware.platform_strategy),
      detail: mac.is_macos ? `${macTierLabel(hardware.mac_video_tier)} | 安装 ${data.install_profile || "auto"}` : `安装 ${data.install_profile || "auto"}`,
      state: ["cuda_multi_model", "cuda_wan_workflow", "mac_mps"].includes(hardware.platform_strategy) ? "ok" : "warn",
    },
    {
      label: "关注模型",
      value: syncModel.label || "未选择",
      detail: syncMissingCount
        ? `未确认 ${syncMissingCount} 个文件，已找到 ${syncFoundCount} 个`
        : modelSync.message || "模型目录已同步",
      state: syncLevel === "blocked" ? "blocked" : syncLevel === "ok" ? "ok" : "warn",
    },
    {
      label: "ComfyUI",
      value: comfy.connected ? comfy.comfyui_version || "已连接" : "未连接",
      detail: comfy.connected ? `队列 ${comfy.queue?.running || 0}/${comfy.queue?.pending || 0}` : comfy.error || "请先启动 ComfyUI",
      state: comfy.connected ? "ok" : "blocked",
    },
    {
      label: "ffmpeg",
      value: boolText(ffmpeg && ffmpeg.ok),
      detail: ffmpegDetail,
      state: ffmpeg && ffmpeg.ok ? "ok" : "blocked",
    },
    {
      label: "缺失项",
      value: missingCount ? `${missingCount} 项` : "0 项",
      detail: data.repair_needed ? "可点击一键修复加载问题" : missingCount ? "可点击一键安装补齐" : "模型和节点已就绪",
      state: missingCount ? "warn" : "ok",
    },
    {
      label: "工作目录",
      value: paths.base_dir_mismatch ? "已跟随 ComfyUI" : "目录一致",
      detail: paths.active_base_dir || data.base_dir || "-",
      state: paths.base_dir_mismatch ? "warn" : "ok",
    },
  ];

  environmentCards.innerHTML = cards
    .map(
      (card) => `
        <div class="env-card ${card.state}">
          <small>${escapeHtml(card.label)}</small>
          <strong>${escapeHtml(card.value)}</strong>
          <span>${escapeHtml(card.detail)}</span>
        </div>
      `,
    )
    .join("");
}

function renderLoadDiagnostics(data) {
  if (!loadDiagnostics) return;
  const diagnostics = data.diagnostics || [];
  if (!diagnostics.length) {
    loadDiagnostics.innerHTML = `<p class="empty-state">暂无加载诊断结果。</p>`;
    return;
  }
  const paths = data.paths || {};
  const pathRows = [
    ["ComfyUI base", paths.active_base_dir || data.base_dir],
    ["input", paths.input_dir],
    ["output", paths.output_dir],
  ]
    .filter(([, value]) => value)
    .map(
      ([label, value]) => `
        <div class="path-row">
          <small>${escapeHtml(label)}</small>
          <span>${escapeHtml(value)}</span>
        </div>
      `,
    )
    .join("");
  const uniqueDiagnostics = diagnostics.filter((item, index, rows) => {
    const key = `${item.level || "warn"}|${item.message || item.title || ""}`;
    return rows.findIndex((candidate) => `${candidate.level || "warn"}|${candidate.message || candidate.title || ""}` === key) === index;
  });
  const diagnosticRows = uniqueDiagnostics
    .map(
      (item) => `
        <div class="diagnostic-row ${escapeHtml(item.level || "warn")}">
          <strong>${escapeHtml(item.title || "")}</strong>
          <small>${escapeHtml(item.message || "")}</small>
        </div>
      `,
    )
    .join("");
  loadDiagnostics.innerHTML = `
    <div class="path-stack">${pathRows}</div>
    ${diagnosticRows}
  `;
}

function renderModelRecommendations(data) {
  const sourceItems = data.recommendations || [];
  const generationItems = sourceItems.filter((item) => item.step === "视频生成");
  const items = sourceItems.filter((item) => item.step !== "视频生成");
  if (generationItems.length) {
    const statusOrder = { blocked: 1, warn: 2, ok: 3 };
    items.unshift({
      step: "视频生成",
      status: generationItems.reduce((best, item) => (statusOrder[item.status] > statusOrder[best] ? item.status : best), "blocked"),
      recommended: [...new Set(generationItems.flatMap((item) => item.recommended || []))],
      reason: [...new Set(generationItems.map((item) => item.reason).filter(Boolean))].join(" "),
    });
  }
  if (!items.length) {
    modelRecommendations.innerHTML = `<p class="empty-state">暂无推荐结果。</p>`;
    return;
  }
  modelRecommendations.innerHTML = items
    .map(
      (item) => `
        <article class="model-row ${item.status}">
          <div>
            <strong>${escapeHtml(item.step)}</strong>
            <small>${escapeHtml((item.recommended || []).join(" / "))}</small>
          </div>
          <p>${escapeHtml(item.reason || "")}</p>
          <span>${escapeHtml(labelForStatus(item.status))}</span>
        </article>
      `,
    )
    .join("");
}

function modelCatalogStatusLabel(status) {
  const labels = {
    stable: "已接入",
    official: "官方新模型",
    new: "新模型",
    candidate: "候选",
    experimental: "实验",
    reference: "参考",
  };
  return labels[status] || status || "未知";
}

function platformSupportLabel(support) {
  const labels = {
    native: "平台原生生成",
    cloud_api: "fal 云端 API",
    official_workflow: "官方 ComfyUI 工作流",
    manual: "手动接入",
  };
  return labels[support] || support || "接入方式待确认";
}

function catalogItems() {
  return modelCatalogData.items || [];
}

function isVideoCatalogItem(item) {
  const workflowSteps = Object.keys(item?.workflow_modes || {});
  return workflowSteps.some((step) => ["draft", "final"].includes(step));
}

function isImageCatalogItem(item) {
  const modes = item?.workflow_modes || {};
  return Boolean(modes.image) && !isVideoCatalogItem(item);
}

function catalogGenerationTarget(item) {
  if (item?.generation_target) return item.generation_target;
  if (item?.platform_support === "native" && Object.keys(item?.workflow_modes || {}).length) return "native";
  if (item?.platform_support === "cloud_api" && Object.keys(item?.workflow_modes || {}).length) return "cloud_api";
  if (item?.platform_support === "official_workflow") return "comfy_template";
  return "catalog_only";
}

function catalogGenerationTargetLabel(item) {
  return item?.generation_target_label || {
    native: "本页可生成",
    cloud_api: "本页云端生成",
    comfy_template: "只下载、去 ComfyUI 跑模板",
    catalog_only: "仅目录参考",
  }[catalogGenerationTarget(item)] || "仅目录参考";
}

function videoCatalogItems(items = catalogItems()) {
  return items.filter(isVideoCatalogItem);
}

function versionAtLeast(current, required) {
  const parts = (value) => String(value || "").match(/\d+/g)?.map(Number) || [];
  const left = parts(current);
  const right = parts(required);
  if (!left.length || !right.length) return false;
  const width = Math.max(left.length, right.length);
  for (let index = 0; index < width; index += 1) {
    const a = left[index] || 0;
    const b = right[index] || 0;
    if (a > b) return true;
    if (a < b) return false;
  }
  return true;
}

function selectedCatalogItem() {
  return catalogItems().find((item) => item.id === selectedCatalogModelId) || catalogItems()[0] || null;
}

function enrichedCatalogItem(item) {
  if (!item) return null;
  const catalogItem = catalogItems().find((candidate) => candidate.id === item.id);
  return catalogItem ? { ...item, ...catalogItem } : item;
}

function syncCatalogSelectionFromData(data = modelCatalogData) {
  const items = data.items || [];
  const fallback = items[0] || null;
  const selected = data.selected_model_id || selectedCatalogModelId || fallback?.id || "";
  selectedCatalogModelId = items.some((item) => item.id === selected) ? selected : fallback?.id || "";
  updateGlobalModelContext();
}

function updateGlobalModelContext() {
  const item = selectedCatalogItem();
  const workflowOption = selectedModelOption("draft");
  if (topModelLabel && !["image-studio", "video-face-swap", "tasks", "library"].includes(activeView)) {
    const currentOption = selectedModelOption(currentStep().id === "keyframe" ? "draft" : currentStep().id);
    const displayModel = activeView === "workflow" ? currentOption?.label || currentStep().title : item?.label;
    topModelLabel.textContent = displayModel || "模型待选择";
    topModelLabel.title = displayModel || "";
  }
  const draftSummary = document.querySelector('[data-step="draft"] [data-step-summary]');
  if (draftSummary) {
    if (workflowOption?.supported !== false) draftSummary.textContent = workflowOption.engine_label || "自由选择模型和质量";
    else if (item) draftSummary.textContent = platformSupportLabel(item.platform_support);
  }
}

function catalogItemForWorkflowOption(option) {
  if (!option) return null;
  const explicit = catalogItems().find((item) => item.id === option.catalog_id);
  if (explicit) return explicit;
  const profileMatch = catalogItems().find(
    (item) => item.default_install_profile === option.install_profile && ["native", "cloud_api"].includes(item.platform_support),
  );
  if (profileMatch) return profileMatch;
  return catalogItems().find(
    (item) => Object.values(item.workflow_modes || {}).includes(option.mode) && ["native", "cloud_api"].includes(item.platform_support),
  ) || null;
}

function renderModelCatalogFilters() {
  if (!modelCatalogFamilyFilter || !modelCatalogQuantFilter) return;
  syncCatalogSelectionFromData();
  const familyValue = modelCatalogFamilyFilter.value || "all";
  const quantValue = modelCatalogQuantFilter.value || "all";
  const items = catalogItems();
  const families = modelCatalogData.families || [];
  const quants = modelCatalogData.quantizations || [];
  // 默认只列“本页可生成”的模型，压缩 40+ 条目的选择噪音；当前选中项始终保留。
  const nativeOnly = modelCatalogNativeOnly ? modelCatalogNativeOnly.checked : false;
  const selectorItems = nativeOnly
    ? items.filter((item) => ["native", "cloud_api"].includes(catalogGenerationTarget(item)) || item.user_import || item.id === selectedCatalogModelId)
    : items;
  if (modelCatalogSelector) {
    if (items.length) {
      modelCatalogSelector.disabled = false;
      const targetGroups = [
        ["native", "本页可生成"],
        ["cloud_api", "本页云端生成"],
        ["comfy_template", "只下载、去 ComfyUI 跑模板"],
        ["catalog_only", "仅目录参考"],
      ];
      modelCatalogSelector.innerHTML = targetGroups
        .map(([target, label]) => {
          const groupItems = selectorItems.filter((item) => catalogGenerationTarget(item) === target);
          if (!groupItems.length) return "";
          return `<optgroup label="${escapeHtml(label)}">${groupItems
            .map((item) => {
              const stateMark = item.install_state === "ready" ? "✓ " : item.install_state === "partial" ? "◐ " : "";
              return `<option value="${escapeHtml(item.id)}">${stateMark}${escapeHtml(item.family || "")} · ${escapeHtml(item.label || item.id)}</option>`;
            })
            .join("")}</optgroup>`;
        })
        .join("");
      modelCatalogSelector.value = selectedCatalogModelId;
    } else {
      modelCatalogSelector.disabled = true;
      modelCatalogSelector.innerHTML = `<option value="">模型目录加载中</option>`;
    }
  }
  modelCatalogFamilyFilter.disabled = !items.length;
  modelCatalogQuantFilter.disabled = !items.length;
  modelCatalogFamilyFilter.innerHTML =
    `<option value="all">${items.length ? "全部系列" : "系列加载中"}</option>` +
    families.map((item) => `<option value="${escapeHtml(item)}">${escapeHtml(item)}</option>`).join("");
  modelCatalogQuantFilter.innerHTML =
    `<option value="all">${items.length ? "全部量化" : "量化加载中"}</option>` +
    quants.map((item) => `<option value="${escapeHtml(item)}">${escapeHtml(item)}</option>`).join("");
  modelCatalogFamilyFilter.value = families.includes(familyValue) ? familyValue : "all";
  modelCatalogQuantFilter.value = quants.includes(quantValue) ? quantValue : "all";
}

function modelInstallScopeText(item) {
  const target = catalogGenerationTarget(item);
  if (target === "cloud_api") return "无需下载本地权重 · 配置 FAL_KEY 后直接生成";
  if (target === "catalog_only" || !item?.one_click_install) return "需要按来源说明手动准备";
  const parts = [];
  if (Number(item.install_expected_gb || 0) > 0) parts.push(`本模型约 ${Number(item.install_expected_gb).toFixed(1)} GB`);
  if (Number(item.install_asset_count || 0) > 0) parts.push(`${Number(item.install_asset_count)} 个核心权重`);
  if (Number(item.install_custom_node_count || 0) > 0) parts.push(`${Number(item.install_custom_node_count)} 个必要节点`);
  const suffix = target === "comfy_template" ? "下载后请到 ComfyUI 跑模板" : "不含插帧/超分后期包";
  return parts.length ? `${parts.join(" · ")} · ${suffix}` : suffix;
}

function modelInstallActionHtml(item, compact = false) {
  const target = catalogGenerationTarget(item);
  if (target === "catalog_only" || !item?.one_click_install || !item.install_profile) return "";
  const label = item.label || item.id || "当前模型";
  const buttonText = target === "comfy_template" ? "只下载权重（去 ComfyUI 跑模板）" : "一键下载/修复";
  return `
    <button
      class="primary catalog-install-button${compact ? " compact" : ""}"
      type="button"
      data-catalog-install
      data-model-id="${escapeHtml(item.id || "")}"
      data-install-profile="${escapeHtml(item.install_profile)}"
      data-install-label="${escapeHtml(label)}"
      title="${escapeHtml(target === "comfy_template" ? "只下载权重，本页不能生成" : "下载该模型核心包，不含后期全家桶")}"
    >${buttonText}</button>
  `;
}

function catalogGoGenerateHtml(item) {
  const target = catalogGenerationTarget(item);
  if (target === "catalog_only") return "";
  const label = target === "comfy_template" ? "打开 ComfyUI 模板" : target === "cloud_api" ? "去云端生成" : "去生成";
  return `<button class="primary catalog-go-generate" type="button" data-catalog-go-generate data-model-id="${escapeHtml(item.id || "")}">${label}</button>`;
}

function catalogInstallStateLabel(item) {
  const state = String(item?.install_state || "unknown");
  const found = Number(item?.files_found || 0);
  const total = Number(item?.files_total || 0);
  if (state === "ready") return `已就绪 ${found}/${total}`;
  if (state === "partial") return `部分下载 ${found}/${total}`;
  if (state === "missing") return "未下载";
  return "";
}

function catalogMatchesKeyword(item, keyword) {
  if (!keyword) return true;
  const haystack = [
    item.label,
    item.id,
    item.family,
    item.quantization,
    item.task,
    item.vram_hint,
    item.recommended_for,
    item.workflow_support,
    ...(item.capability_labels || []),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return keyword
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .every((term) => haystack.includes(term));
}

function renderModelCatalog() {
  if (!modelCatalog) return;
  syncCatalogSelectionFromData();
  renderModelCatalogFilters();
  const family = modelCatalogFamilyFilter?.value || "all";
  const quant = modelCatalogQuantFilter?.value || "all";
  const keyword = (modelCatalogSearch?.value || "").trim();
  const readyState = modelCatalogReadyFilter?.value || "all";
  const nativeOnly = modelCatalogNativeOnly ? modelCatalogNativeOnly.checked : false;
  const allItems = catalogItems();
  const items = allItems.filter((item) => {
    const familyOk = family === "all" || item.family === family;
    const quantOk = quant === "all" || item.quantization === quant;
    const nativeOk = !nativeOnly || ["native", "cloud_api"].includes(catalogGenerationTarget(item)) || item.user_import || item.id === selectedCatalogModelId;
    const readyOk = readyState === "all" || String(item.install_state || "unknown") === readyState;
    return familyOk && quantOk && nativeOk && readyOk && catalogMatchesKeyword(item, keyword);
  });
  if (modelCatalogCount) {
    const readyCount = allItems.filter((item) => item.install_state === "ready").length;
    modelCatalogCount.textContent = allItems.length
      ? `显示 ${items.length} / ${allItems.length} 个模型 · 本机已就绪 ${readyCount} 个 · 点卡片设为目标模型`
      : "";
  }
  if (!items.length) {
    modelCatalog.innerHTML = `<p class="empty-state">没有匹配的模型。试试清空搜索词，或放宽就绪状态/系列/量化筛选。</p>`;
    return;
  }
  modelCatalog.innerHTML = items
    .map((item) => {
      const files = (item.files || []).slice(0, 6).join(" / ");
      const source = (item.sources || [])[0] || "";
      const comfyWorkflowUrl = catalogGenerationTarget(item) === "comfy_template" ? environmentData?.comfy?.url || "http://127.0.0.1:8188" : "";
      const selected = item.id === selectedCatalogModelId;
      const target = catalogGenerationTarget(item);
      const templateHint = item.template_search ? `打开 ComfyUI，搜索「${item.template_search}」模板` : "打开 ComfyUI 模板";
      return `
        <article class="catalog-row ${escapeHtml(item.status || "")}${selected ? " selected" : ""}" data-catalog-id="${escapeHtml(item.id || "")}">
          <div class="catalog-row-main">
            <div>
              <strong>${escapeHtml(item.label || item.id)}</strong>
              <small>${escapeHtml(item.family || "")} · ${escapeHtml(item.task || "")}</small>
            </div>
            <span>${escapeHtml(selected ? "当前关注" : modelCatalogStatusLabel(item.status))}</span>
          </div>
          <div class="catalog-tags">
            ${catalogInstallStateLabel(item) ? `<b class="catalog-state-${escapeHtml(item.install_state || "unknown")}">${escapeHtml(catalogInstallStateLabel(item))}</b>` : ""}
            <b class="catalog-tag-${escapeHtml(target)}">${escapeHtml(catalogGenerationTargetLabel(item))}</b>
            <b>${escapeHtml(item.quantization || "未知量化")}</b>
            <b>${escapeHtml(item.vram_hint || "显存待确认")}</b>
            <b>${escapeHtml(platformSupportLabel(item.platform_support))}</b>
            <b>${escapeHtml(item.install_profile_label || item.install_profile || "手动接入")}</b>
            ${(item.capability_labels || []).map((label) => `<b>${escapeHtml(label)}</b>`).join("")}
            ${item.released ? `<b>${escapeHtml(item.released)} 发布</b>` : ""}
            ${item.license ? `<b>${escapeHtml(item.license)}</b>` : ""}
          </div>
          <p>${escapeHtml(item.workflow_support || "")}</p>
          <small>${escapeHtml(item.recommended_for || "")}</small>
          ${item.external_requirement ? `<small class="model-sync-requirement">下载前：${escapeHtml(item.external_requirement)}</small>` : ""}
          ${item.required_comfy_version ? `<small>需要 ComfyUI ${escapeHtml(item.required_comfy_version)}+</small>` : ""}
          ${item.nsfw ? `<small>无限制模式社区方案：${escapeHtml(item.nsfw.label || item.nsfw.status || "未标注")}。${escapeHtml(item.nsfw.note || "")}</small>` : ""}
          ${files ? `<code>${escapeHtml(files)}</code>` : ""}
          <div class="catalog-install-scope">${escapeHtml(modelInstallScopeText(item))}</div>
          <div class="catalog-row-actions">
            ${catalogGoGenerateHtml(item)}
            ${modelInstallActionHtml(item)}
            ${item.user_import ? `<button class="primary catalog-install-button" type="button" data-user-download="${escapeHtml(item.id || "")}">下载/续传</button>` : ""}
            ${item.user_import ? `<button class="secondary" type="button" data-user-remove="${escapeHtml(item.id || "")}">从目录移除</button>` : ""}
            ${comfyWorkflowUrl ? `<a href="${escapeHtml(comfyWorkflowUrl)}" target="_blank" rel="noreferrer">${escapeHtml(templateHint)}</a>` : ""}
            ${source ? `<a href="${escapeHtml(source)}" target="_blank" rel="noreferrer">查看模型源</a>` : ""}
          </div>
        </article>
      `;
    })
    .join("");
}

function renderModelSync(data) {
  const sync = data.model_sync || {};
  const item = enrichedCatalogItem(sync.selected_model || selectedCatalogItem());
  if (!item || !missingItems) return "";
  const level = sync.level || (item.status === "stable" ? "good" : "warn");
  const state = level === "blocked" ? "blocked" : level === "ok" ? "good" : "warn";
  const missing = sync.missing_files || [];
  const found = sync.found_files || [];
  const detail = missing.length
    ? `已找到 ${found.length} 个，未确认 ${missing.length} 个：${missing.slice(0, 6).join(" / ")}`
    : sync.message || `已找到 ${found.length} 个关联文件。`;
  return `
    <div class="missing-row ${state}">
      <strong>当前关注模型：${escapeHtml(item.label || item.id || "")}</strong>
      <small>${escapeHtml(detail)}</small>
    </div>
  `;
}

function renderModelSyncPanel(data = environmentData || {}) {
  if (!modelSyncPanel) return;
  const sync = data.model_sync || {};
  const item = enrichedCatalogItem(sync.selected_model || selectedCatalogItem());
  if (!item) {
    modelSyncPanel.innerHTML = `<p class="empty-state">请选择一个关注模型。</p>`;
    return;
  }
  const missing = sync.missing_files || [];
  const found = sync.found_files || [];
  const level = sync.level || (item.status === "stable" ? "ok" : "warn");
  const state = level === "blocked" ? "blocked" : level === "ok" ? "ok" : "warn";
  const fileText = missing.length
    ? `未确认 ${missing.length} 个文件，已找到 ${found.length} 个`
    : sync.message || `已找到 ${found.length} 个关联文件`;
  const missingText = missing.length
    ? `<div class="model-sync-missing">${missing.slice(0, 8).map((name) => `<code>${escapeHtml(name)}</code>`).join("")}</div>`
    : "";
  modelSyncPanel.innerHTML = `
    <div class="model-sync-card ${state}">
      <div class="model-sync-title">
        <div>
          <strong>${escapeHtml(item.label || item.id || "")}</strong>
          <small>${escapeHtml(item.family || "")} · ${escapeHtml(item.task || "")}</small>
        </div>
        <span>${escapeHtml(modelCatalogStatusLabel(item.status))}</span>
      </div>
      <div class="model-sync-facts">
        <b class="catalog-tag-${escapeHtml(catalogGenerationTarget(item))}">${escapeHtml(catalogGenerationTargetLabel(item))}</b>
        <b>${escapeHtml(item.quantization || "量化未知")}</b>
        <b>${escapeHtml(item.vram_hint || "显存待确认")}</b>
        <b>${escapeHtml(platformSupportLabel(item.platform_support))}</b>
        <b>${escapeHtml(item.install_profile_label || item.install_profile || "手动接入")}</b>
        <b>${escapeHtml(fileText)}</b>
      </div>
      <p>${escapeHtml(item.workflow_support || "")}</p>
      <small>${escapeHtml(item.recommended_for || "")}</small>
      ${item.external_requirement ? `<small class="model-sync-requirement">外部要求：${escapeHtml(item.external_requirement)}</small>` : ""}
      ${missingText}
      <div class="model-sync-install-row">
        <small>${escapeHtml(modelInstallScopeText(item))}</small>
        ${catalogGoGenerateHtml(item)}
        ${modelInstallActionHtml(item, true)}
      </div>
    </div>
  `;
}

async function saveCatalogSelection(requestedId = "", { preserveWorkflowOptionId = "" } = {}) {
  if (!modelCatalogSelector) return;
  const selectedId = requestedId || modelCatalogSelector.value || "";
  if (!selectedId) return;
  if (syncingCatalogSelection) {
    pendingCatalogModelId = selectedId;
    pendingCatalogWorkflowOptionId = preserveWorkflowOptionId;
    selectedCatalogModelId = selectedId;
    renderModelCatalog();
    renderModelSyncPanel();
    return;
  }
  syncingCatalogSelection = true;
  selectedCatalogModelId = selectedId;
  renderModelCatalog();
  renderModelSyncPanel();
  try {
    const response = await fetch("/api/model-catalog/selection", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ selected_model_id: selectedId }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(formatError(data.detail || data));
    if (data.model_catalog) {
      modelCatalogData = data.model_catalog;
      syncCatalogSelectionFromData(modelCatalogData);
    }
    selectedInstallProfile = "auto";
    if (!preserveWorkflowOptionId) delete selectedModels.draft;
    appendLog(`当前关注模型已切换为：${selectedCatalogItem()?.label || selectedId}。`);
    await loadEnvironment({ forceRecommendations: !preserveWorkflowOptionId });
    if (preserveWorkflowOptionId && modelOptionsForStep("draft").some((item) => item.id === preserveWorkflowOptionId)) {
      selectedModels.draft = preserveWorkflowOptionId;
      renderModelSelector();
    }
  } catch (error) {
    appendLog(`模型选择同步失败：${error.message}`);
  } finally {
    syncingCatalogSelection = false;
    renderModelCatalog();
    const pendingId = pendingCatalogModelId;
    const pendingWorkflowId = pendingCatalogWorkflowOptionId;
    pendingCatalogModelId = "";
    pendingCatalogWorkflowOptionId = "";
    if (pendingId && pendingId !== selectedCatalogModelId) {
      await saveCatalogSelection(pendingId, { preserveWorkflowOptionId: pendingWorkflowId });
    } else if (pendingWorkflowId && modelOptionsForStep("draft").some((item) => item.id === pendingWorkflowId)) {
      selectedModels.draft = pendingWorkflowId;
      renderModelSelector();
    }
  }
}

async function syncCatalogSelectionForWorkflowOption(option) {
  const catalog = catalogItemForWorkflowOption(option);
  if (!catalog || catalog.id === selectedCatalogModelId) {
    if (catalog && syncingCatalogSelection) {
      pendingCatalogModelId = catalog.id;
      pendingCatalogWorkflowOptionId = option.id;
    }
    updateGlobalModelContext();
    return;
  }
  await saveCatalogSelection(catalog.id, { preserveWorkflowOptionId: option.id });
}

async function rememberCatalogSelectionForInstall(modelId) {
  const selectedId = String(modelId || "").trim();
  if (!selectedId) return;
  selectedCatalogModelId = selectedId;
  if (modelCatalogSelector) modelCatalogSelector.value = selectedId;
  renderModelCatalog();
  renderModelSyncPanel(environmentData || {});
  try {
    const response = await fetch("/api/model-catalog/selection", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ selected_model_id: selectedId }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(formatError(data.detail || data));
    if (data.model_catalog) {
      modelCatalogData = data.model_catalog;
      syncCatalogSelectionFromData(modelCatalogData);
      renderModelCatalog();
      renderModelSyncPanel(environmentData || {});
    }
    delete selectedModels.draft;
  } catch (error) {
    appendLog(`模型关注项同步失败，但下载任务仍可继续：${error.message}`);
  }
}

async function loadModelCatalog() {
  try {
    const response = await fetch("/api/model-catalog");
    const data = await response.json();
    if (!response.ok) throw new Error(formatError(data.detail || data));
    modelCatalogData = data;
    syncCatalogSelectionFromData(modelCatalogData);
    renderModelCatalog();
    renderModelSyncPanel(environmentData || {});
    return data;
  } catch (error) {
    if (modelCatalogSelector) {
      modelCatalogSelector.disabled = true;
      modelCatalogSelector.innerHTML = `<option value="">模型目录加载失败</option>`;
    }
    if (modelCatalogFamilyFilter) {
      modelCatalogFamilyFilter.disabled = true;
      modelCatalogFamilyFilter.innerHTML = `<option value="all">系列加载失败</option>`;
    }
    if (modelCatalogQuantFilter) {
      modelCatalogQuantFilter.disabled = true;
      modelCatalogQuantFilter.innerHTML = `<option value="all">量化加载失败</option>`;
    }
    if (modelCatalog) {
      modelCatalog.innerHTML = `<div class="empty-state">模型目录读取失败：${escapeHtml(error.message)} <button type="button" class="text-button" data-retry-model-catalog>重试</button></div>`;
    }
    if (modelSyncPanel) {
      modelSyncPanel.innerHTML = `<p class="empty-state">模型控制台暂不可用，请刷新页面或重启前端。</p>`;
    }
    appendLog(`模型目录读取失败：${error.message}`);
    return null;
  }
}

function renderDiskPlan(plan) {
  const disk = plan.disk || {};
  if (!disk || disk.ok === undefined) return "";
  const state = disk.ok === false ? "blocked" : disk.ok === true ? "good" : "warn";
  const title = disk.ok === false ? "磁盘空间不足" : disk.ok === true ? "磁盘空间充足" : "磁盘空间待确认";
  const detail =
    disk.ok === null
      ? disk.message || "无法读取磁盘空间。"
      : `目标磁盘剩余 ${formatGb(disk.free_gb)}；预计还需下载 ${formatGb(disk.required_gb)}；建议至少预留 ${formatGb(disk.recommended_free_gb)}。${
          disk.ok === false ? " 可切换到更轻量的模型档，或只安装后期工具。" : ""
        }`;
  return `
    <div class="missing-row ${state}">
      <strong>${escapeHtml(title)}</strong>
      <small>${escapeHtml(detail)}${disk.path ? ` | ${escapeHtml(disk.path)}` : ""}</small>
    </div>
  `;
}

function renderPrerequisites(report) {
  if (!prerequisiteChecks) return;
  if (!report || !Array.isArray(report.checks)) {
    prerequisiteChecks.innerHTML = `<p class="empty-state">暂未取得前置条件检测结果。</p>`;
    return;
  }
  const summaryState = report.ok ? "good" : "blocked";
  const summaryText = report.ok
    ? `可继续。${report.warning_count || 0} 个提示项不阻止安装。`
    : `有 ${report.blocked_count || 0} 个阻断项需要先处理。`;
  const rows = report.checks
    .map((item) => {
      const state = item.status === "ok" ? "good" : item.status === "blocked" ? "blocked" : "warn";
      const action = item.action ? `<small class="next-action">${escapeHtml(item.action)}</small>` : "";
      return `
        <div class="missing-row ${state}">
          <strong>${escapeHtml(item.label || item.id || "")}</strong>
          <small>${escapeHtml(item.message || "")}</small>
          ${action}
        </div>
      `;
    })
    .join("");
  prerequisiteChecks.innerHTML = `
    <div class="missing-row ${summaryState}">
      <strong>${report.ok ? "基础环境可继续" : "基础环境需要处理"}</strong>
      <small>${escapeHtml(summaryText)}</small>
    </div>
    ${rows}
  `;
}

function installProfileOptions() {
  return (
    environmentData?.install_profiles || [
      { id: "auto", label: "自动推荐", description: "按当前硬件自动选择。" },
      { id: "post-only", label: "仅后期工具", description: "只装 RIFE、超分等后期工具。" },
    ]
  );
}

function installProfileLabel(profile) {
  const option = installProfileOptions().find((item) => item.id === profile);
  return option?.label || profile || "auto";
}

function renderSetupActionGuide(data = environmentData) {
  const profileLabel = installProfileLabel(selectedInstallProfile);
  const plan = data?.install_plan || {};
  const installable = plan.installable !== false;
  const externalRequirement = plan.external_requirement || "";
  const missingCount = (data?.missing_installable || []).length;
  const missingGb = formatGb(plan.missing_expected_gb || 0);
  const totalGb = formatGb(plan.total_expected_gb || 0);
  const comfyConnected = Boolean(bootstrapData?.comfy_connected || data?.comfy?.connected);
  const targetPath = currentModelDownloadPath() || data?.base_dir || "模型目录";
  const targetLabel = data?.custom_target ? `自定义模型目录 ${targetPath}` : `ComfyUI 当前目录 ${targetPath}`;
  if (installProfileHint) {
    installProfileHint.textContent = installable
      ? `当前档位：${profileLabel}。一键准备和一键安装使用同一份计划；前者还负责 ComfyUI，后者只补当前缺失项。${externalRequirement ? ` 外部要求：${externalRequirement}` : ""}`
      : `当前档位：${profileLabel}。该模型只提供目录参考，需要手动准备，平台不会把它伪装成一键可安装。`;
  }
  if (fullSetupScope) {
    fullSetupScope.textContent = !installable
      ? `${profileLabel}：不支持一键准备，请按模型目录中的来源和工作流说明手动接入。`
      : comfyConnected
      ? `${profileLabel}：检测到 ComfyUI 已运行，会跳过源码安装；模型写入 ${targetLabel}，节点仍写入当前 ComfyUI。`
      : `${profileLabel}：安装/更新 ComfyUI，再把档位资源写入 ${targetLabel}；完整档位约 ${totalGb}。`;
  }
  if (workflowInstallScope) {
    workflowInstallScope.textContent = !installable
      ? `${profileLabel}：没有平台可执行的自动安装计划。`
      : missingCount
      ? `${profileLabel}：只处理 ${targetLabel} 中的 ${missingCount} 个缺失/加载异常项，预计还需下载 ${missingGb}；完成后重启 ComfyUI。`
      : `${profileLabel}：当前没有可一键安装的缺失项；需要重建 ComfyUI 时用“一键准备环境”。`;
  }
}

function hostnameFromUrl(value) {
  try {
    return value ? new URL(value).hostname || "" : "";
  } catch {
    return "";
  }
}

function activeDownloadSettings() {
  return bootstrapData?.download_settings || environmentData?.download_settings || {};
}

function friendlyDownloadHostLabel(host) {
  const settings = activeDownloadSettings();
  if (host === "huggingface.co") {
    const mirrorHost = hostnameFromUrl(settings.hf_endpoint || settings.saved_hf_endpoint);
    return mirrorHost && mirrorHost !== host ? `Hugging Face 镜像 ${mirrorHost}` : "Hugging Face";
  }
  if (host === "pypi.org") {
    const pipHost = hostnameFromUrl(settings.pip_index_url || settings.saved_pip_index_url);
    return pipHost && pipHost !== host ? `pip 镜像 ${pipHost}` : "PyPI";
  }
  if (host === "github.com") return "GitHub";
  if (host === "download.pytorch.org") return "PyTorch 下载源";
  return host || "未知下载源";
}

function workflowAssetDownloadHosts() {
  const hosts = new Set();
  const missing = environmentData?.missing_installable || [];
  for (const item of missing) {
    if (item.local_available) continue;
    if (item.download_host) hosts.add(item.download_host);
  }
  const selectedHasCustomNodes = (environmentData?.install_plan?.items || []).some((item) => item.item_type === "custom_node");
  if (missing.length && selectedHasCustomNodes && bootstrapData?.venv_ready) {
    hosts.add("pypi.org");
  }
  return hosts;
}

function fullSetupDownloadHosts() {
  const hosts = workflowAssetDownloadHosts();
  if (!bootstrapData?.comfy_connected) {
    hosts.add("github.com");
    hosts.add("pypi.org");
    const backend = String(bootstrapData?.install_disk?.backend || "").toLowerCase();
    if (backend === "cuda" || backend === "cpu") hosts.add("download.pytorch.org");
  }
  return hosts;
}

function downloadHostListText(hosts) {
  const labels = [...hosts].map(friendlyDownloadHostLabel).filter(Boolean);
  return labels.length ? labels.join("、") : "无需外网下载源";
}

function currentModelDownloadPath() {
  return String(modelDownloadPath?.value || localStorage.getItem(MODEL_DOWNLOAD_PATH_STORAGE_KEY) || "").trim();
}

async function loadModelStorageLocations() {
  if (!modelStoragePreset || !modelDownloadPath) return;
  try {
    const response = await fetch("/api/storage-locations");
    const data = await response.json();
    if (!response.ok) throw new Error(formatError(data.detail || data));
    const locations = data.locations || [];
    const current = currentModelDownloadPath() || data.selected_path || data.active_base_dir || "";
    modelStoragePreset.innerHTML = locations
      .map((item) => `<option value="${escapeHtml(item.path)}">${escapeHtml(item.label)}${item.free_gb == null ? "" : ` · ${Number(item.free_gb).toFixed(1)} GB 可用`}</option>`)
      .join("");
    if (current && !locations.some((item) => item.path === current)) {
      modelStoragePreset.insertAdjacentHTML("beforeend", `<option value="${escapeHtml(current)}">自定义路径</option>`);
    }
    modelStoragePreset.value = current;
    modelDownloadPath.value = current;
    localStorage.setItem(MODEL_DOWNLOAD_PATH_STORAGE_KEY, current);
    const selected = locations.find((item) => item.path === current);
    modelStorageStatus.textContent = `${current}${selected?.free_gb == null ? "" : ` · 可用 ${Number(selected.free_gb).toFixed(2)} GB`}${current === data.active_base_dir ? " · ComfyUI 当前目录" : " · 将自动注册到 extra_model_paths.yaml，重启 8188 后生效"}`;
  } catch (error) {
    modelStorageStatus.textContent = `模型目录读取失败：${error.message}`;
  }
}

function renderInstallProfileSelector(data) {
  if (!installProfileSelector) return;
  const options = data.install_profiles || installProfileOptions();
  const values = options.map((item) => item.id);
  if (!values.includes(selectedInstallProfile)) selectedInstallProfile = "auto";
  installProfileSelector.innerHTML = options
    .map((item) => {
      const effective = item.id === "auto" ? ` -> ${item.effective_profile || data.install_profile || "auto"}` : "";
      const marker = item.recommended && item.id !== "auto" ? " · 推荐" : "";
      const installableMarker = item.installable === false ? " · 手动" : "";
      return `<option value="${escapeHtml(item.id)}">${escapeHtml(item.label || item.id)}${escapeHtml(effective)}${marker}${installableMarker}</option>`;
    })
    .join("");
  installProfileSelector.value = selectedInstallProfile;
  const selected = options.find((item) => item.id === selectedInstallProfile) || options[0];
  installProfileSelector.title = selected?.description || "";
}

function renderMissingItems(data) {
  const items = data.missing_installable || [];
  const plan = data.install_plan || {};
  const diskBlocked = plan.disk?.ok === false;
  const installable = plan.installable !== false;
  const modelSyncSummary = renderModelSync(data);
  renderInstallProfileSelector(data);
  renderSetupActionGuide(data);
  installMissingButton.disabled = !installable || !items.length || diskBlocked;
  if (installMissingButton.disabled) {
    setWorkflowAssetInstallConfirming(false);
  } else {
    installMissingButton.textContent = allowWorkflowAssetInstall ? workflowAssetConfirmText : workflowAssetButtonText;
  }
  if (!installable) {
    missingItems.innerHTML =
      modelSyncSummary +
      `<p class="empty-state">当前模型需要手动接入。请使用模型目录中的来源和工作流说明；一键准备与一键安装均不会执行。</p>`;
    return;
  }
  if (!items.length) {
    missingItems.innerHTML =
      modelSyncSummary +
      renderDiskPlan(plan) +
      `<p class="empty-state good">没有可一键安装的缺失项。当前档位：${escapeHtml(installProfileLabel(selectedInstallProfile))}。</p>`;
    return;
  }
  const planSummary = `
    <div class="missing-row plan-row">
      <strong>${escapeHtml(installProfileLabel(selectedInstallProfile))} 安装计划</strong>
      <small>本档位共 ${plan.asset_count || 0} 个模型/权重、${plan.custom_node_count || 0} 个节点；缺失约 ${formatGb(plan.missing_expected_gb || 0)}，完整档位约 ${formatGb(plan.total_expected_gb || 0)}。</small>
    </div>
  `;
  missingItems.innerHTML = modelSyncSummary + planSummary + renderDiskPlan(plan) + items
    .map(
      (item) => {
        const resumeInfo = item.partial_exists
          ? ` | 已下载 ${formatGb(item.partial_gb || 0)}，剩余 ${formatGb(item.remaining_gb || 0)}，可断点续传`
          : "";
        const localInfo = item.local_available
          ? ` | 本地缓存可用，点击安装会复用：${item.local_path || ""}`
          : "";
        const sizeInfo = item.expected_gb ? ` | 完整大小 ${formatGb(item.expected_gb)}` : "";
        return `
          <div class="missing-row">
            <strong>${escapeHtml(item.label || item.id)}</strong>
            <small>${escapeHtml(item.path || "")}${escapeHtml(sizeInfo + resumeInfo + localInfo)}</small>
          </div>
        `;
      },
    )
    .join("");
}

function updateFullSetupAvailability(data = environmentData) {
  if (!runFullSetupButton) return;
  renderSetupActionGuide(data);
  const diskBlocked = data?.install_plan?.disk?.ok === false;
  const installable = data?.install_plan?.installable !== false;
  runFullSetupButton.disabled = Boolean(diskBlocked || !installable);
  runFullSetupButton.title = !installable
    ? "当前模型需要手动接入，不能执行一键准备。"
    : diskBlocked
    ? "当前安装档位磁盘空间不足，请降档或清理磁盘。"
    : "自动安装/更新 ComfyUI，并安装当前档位模型、节点和后期权重。";
  if (diskBlocked || !installable) setFullSetupConfirming(false);
}

async function loadInstallPlan(profile = selectedInstallProfile) {
  if (!environmentData) return;
  selectedInstallProfile = profile || "auto";
  const requestId = ++installPlanRequestId;
  setFullSetupConfirming(false);
  setWorkflowAssetInstallConfirming(false);
  if (installMissingButton) installMissingButton.disabled = true;
  if (runFullSetupButton) {
    runFullSetupButton.disabled = true;
    runFullSetupButton.title = "正在刷新当前档位安装计划。";
  }
  if (missingItems) {
    missingItems.innerHTML = `<div class="missing-row plan-row"><strong>正在刷新安装计划</strong><small>${escapeHtml(installProfileLabel(selectedInstallProfile))}</small></div>`;
  }
  try {
    const params = new URLSearchParams({ profile: selectedInstallProfile });
    const target = currentModelDownloadPath();
    if (target) params.set("target_dir", target);
    const response = await fetch(`/api/install-plan?${params}`);
    const data = await response.json();
    if (!response.ok) throw new Error(formatError(data.detail || data));
    if (requestId !== installPlanRequestId) return;
    environmentData = {
      ...environmentData,
      install_profile: data.profile,
      requested_install_profile: data.requested_profile,
      recommended_install_profile: data.recommended_profile,
      install_profiles: data.install_profiles || environmentData.install_profiles,
      install_plan: data.install_plan,
      missing_installable: data.missing_installable,
      base_dir: data.base_dir || environmentData.base_dir,
      active_base_dir: data.active_base_dir || environmentData.active_base_dir,
      custom_target: Boolean(data.custom_target),
      paths: data.paths || environmentData.paths,
    };
    if (modelStorageStatus) {
      const disk = data.install_plan?.disk || {};
      modelStorageStatus.textContent = `${data.base_dir || currentModelDownloadPath()}${disk.free_gb == null ? "" : ` · 可用 ${Number(disk.free_gb).toFixed(2)} GB`}${data.custom_target ? " · 自定义目录，重启 ComfyUI 8188 后生效" : " · ComfyUI 当前目录"}`;
    }
    renderMissingItems(environmentData);
    updateFullSetupAvailability(environmentData);
  } catch (error) {
    if (requestId !== installPlanRequestId) return;
    if (missingItems) {
      missingItems.innerHTML = `<div class="missing-row blocked"><strong>安装计划刷新失败</strong><small>${escapeHtml(error.message)}</small></div>`;
    }
    if (runFullSetupButton) {
      runFullSetupButton.disabled = true;
      runFullSetupButton.title = "安装计划刷新失败，请重新侦测后再一键准备。";
    }
    appendLog(`安装计划刷新失败：${error.message}`);
  }
}

function renderBootstrap(data) {
  bootstrapData = data;
  if (!bootstrapCards) return;
  renderPrerequisites(data.prerequisites);
  renderDownloadSettings(data.download_settings);
  renderSetupActionGuide();
  const installDisk = data.install_disk || {};
  const comfyUrlMode = data.comfy_url_configured ? "手动配置" : "自动检测";
  const comfyUrlDetail = data.comfy_connected
    ? `${data.comfy_url} | ${comfyUrlMode}`
    : `${data.comfy_error || data.comfy_url} | 已尝试 ${(data.comfy_candidate_urls || []).join(" / ")}`;
  const diskValue =
    installDisk.ok === false ? "空间不足" : installDisk.ok === true ? "空间充足" : "待确认";
  const diskDetail =
    installDisk.ok === null || installDisk.ok === undefined
      ? installDisk.message || data.install_dir || "-"
      : `后端 ${installDisk.backend || "auto"}；剩余 ${formatGb(installDisk.free_gb)}，建议预留 ${formatGb(installDisk.recommended_free_gb)} | ${installDisk.path || data.install_dir || "-"}`;
  const runtimeLabel = data.runtime_label || "ComfyUI runtime";
  const runtimeReady = Boolean(data.runtime_source_ready);
  const runtimeDetail = data.bundled_main
    ? `${data.bundled_main} | ${data.venv_python || "-"}`
    : data.comfy_main || data.install_dir || "-";
  const cards = [
    {
      label: "ComfyUI 连接",
      value: data.comfy_connected ? "已连接" : "未连接",
      detail: comfyUrlDetail,
      state: data.comfy_connected ? "ok" : "blocked",
    },
    {
      label: "ComfyUI runtime",
      value: runtimeReady ? "可启动" : data.desktop_available ? "Desktop 可启动" : "未就绪",
      detail: `${runtimeLabel} | ${runtimeDetail}`,
      state: runtimeReady ? "ok" : data.desktop_available ? "warn" : "blocked",
    },
    {
      label: "当前工作目录",
      value: data.paths?.base_dir_mismatch ? "运行目录不同" : "已确认",
      detail: data.active_base_dir || data.base_dir || "-",
      state: data.paths?.base_dir_mismatch ? "warn" : "ok",
    },
    {
      label: "运行环境",
      value: data.venv_ready ? "venv 就绪" : "venv 未就绪",
      detail: data.venv_python || "-",
      state: data.venv_ready ? "ok" : "warn",
    },
    {
      label: "Git",
      value: data.git_ready ? "可用" : "未检测到",
      detail: data.git_ready ? "可 clone/update ComfyUI" : "会改用 GitHub ZIP 下载源码",
      state: data.git_ready ? "ok" : "warn",
    },
    {
      label: "安装磁盘",
      value: diskValue,
      detail: diskDetail,
      state: installDisk.ok === false ? "blocked" : installDisk.ok === true ? "ok" : "warn",
    },
  ];
  bootstrapCards.innerHTML = cards
    .map(
      (card) => `
        <div class="env-card ${card.state}">
          <small>${escapeHtml(card.label)}</small>
          <strong>${escapeHtml(card.value)}</strong>
          <span>${escapeHtml(card.detail)}</span>
        </div>
      `,
    )
    .join("");
  installComfyButton.disabled = !data.can_install_comfyui || installDisk.ok === false;
  if (installComfyButton.disabled) {
    setComfyInstallConfirming(false);
  } else {
    installComfyButton.textContent = allowComfyInstall ? comfyInstallConfirmText : comfyInstallButtonText;
  }
  if (data.comfy_connected) {
    startComfyButton.disabled = true;
    startComfyButton.textContent = "ComfyUI 已运行";
  } else {
    startComfyButton.disabled = !data.can_start_comfyui;
    startComfyButton.textContent = data.can_start_comfyui ? "启动 ComfyUI" : "先安装/选择 ComfyUI";
  }
}

async function loadBootstrap() {
  if (!bootstrapCards) return;
  refreshBootstrapButton.disabled = true;
  try {
    const response = await fetch("/api/bootstrap");
    const data = await response.json();
    if (!response.ok) throw new Error(formatError(data.detail || data));
    renderBootstrap(data);
  } catch (error) {
    bootstrapCards.innerHTML = `<div class="env-card blocked"><small>ComfyUI 安装状态</small><strong>检测失败</strong><span>${escapeHtml(error.message)}</span></div>`;
    if (prerequisiteChecks) {
      prerequisiteChecks.innerHTML = `<div class="missing-row blocked"><strong>前置条件检测失败</strong><small>${escapeHtml(error.message)}</small></div>`;
    }
    appendLog(`ComfyUI 安装状态检测失败：${error.message}`);
  } finally {
    refreshBootstrapButton.disabled = false;
  }
}

async function startBootstrapJob(url, button, confirmText) {
  if (confirmText && !allowComfyInstall) {
    setComfyInstallConfirming(true);
    setLog(`${confirmText} 确认继续请再点击一次“${comfyInstallConfirmText}”。`);
    return;
  }
  setComfyInstallConfirming(false);
  button.disabled = true;
  setLog("正在启动后台任务。");
  try {
    const response = await fetch(url, { method: "POST" });
    const job = await response.json();
    if (!response.ok) throw new Error(formatError(job.detail || job));
    pollBootstrapJob(job.id);
    clearPollTimer('bootstrap');
    POLL_TIMERS.bootstrap = window.setInterval(() => pollBootstrapJob(job.id), 2500);
  } catch (error) {
    appendLog(`后台任务启动失败：${error.message}`);
    button.disabled = false;
    if (button === installComfyButton) {
      setComfyInstallConfirming(false);
    }
  }
}

async function pollBootstrapJob(jobId) {
  try {
    const response = await fetch(`/api/install/${jobId}`);
    const job = await response.json();
    if (!response.ok) throw new Error(formatError(job.detail || job));
    setLog((job.log || []).join("\n"));
    await loadBootstrap();
    if (job.completed || job.status === "success" || job.status === "failed" || job.status === "stopped") {
      clearPollTimer('bootstrap');
      installComfyButton.disabled = !(
        bootstrapData &&
        bootstrapData.can_install_comfyui &&
        bootstrapData.install_disk?.ok !== false
      );
      if (bootstrapData?.comfy_connected) {
        startComfyButton.disabled = true;
        startComfyButton.textContent = "ComfyUI 已运行";
      } else {
        startComfyButton.disabled = !(bootstrapData && bootstrapData.can_start_comfyui);
        startComfyButton.textContent = bootstrapData?.can_start_comfyui ? "启动 ComfyUI" : "先安装 ComfyUI";
      }
      if (job.status === "failed") {
        appendLog(formatJobFailureHint(job));
      }
      await loadEnvironment();
    }
  } catch (error) {
    clearPollTimer('bootstrap');
    appendLog(`后台任务轮询失败：${error.message}`);
    await loadBootstrap();
  }
}

async function startFullSetup() {
  if (!runFullSetupButton) return;
  if (!allowFullSetup) {
    setFullSetupConfirming(true);
    const targetPath = currentModelDownloadPath() || "ComfyUI 当前目录";
    const setupScope = bootstrapData?.comfy_connected
      ? `已检测到 ComfyUI 正在运行，本次会跳过源码版安装/更新，并把当前档位资源写入 ${targetPath}。`
      : `一键准备会安装/更新 ComfyUI，并把当前档位资源写入 ${targetPath}。`;
    const sourceText = downloadHostListText(fullSetupDownloadHosts());
    setLog(
      `${setupScope} 档位：${installProfileLabel(selectedInstallProfile)}。开始前会先检查本次需要的下载源：${sourceText}；首次运行可能下载数 GB 到数十 GB。确认继续请再点击一次“${fullSetupConfirmText}”。`,
    );
    return;
  }
  setFullSetupConfirming(false);
  runFullSetupButton.disabled = true;
  detectEnvironmentButton.disabled = true;
  installMissingButton.disabled = true;
  setLog("正在启动一键准备环境任务。");
  setEnvJobStatus("一键准备环境中", "running");
  setEnvProgress("running");
  try {
    const params = new URLSearchParams({ backend: "auto", profile: selectedInstallProfile || "auto" });
    const target = currentModelDownloadPath();
    if (target) params.set("target_dir", target);
    const response = await fetch(`/api/bootstrap/full-setup?${params}`, { method: "POST" });
    const job = await response.json();
    if (!response.ok) throw new Error(formatError(job.detail || job));
    localStorage.setItem(INSTALL_JOB_STORAGE_KEY, job.id);
    renderEnvInstallProgress(job);
    await pollFullSetupJob(job.id);
    clearPollTimer('fullSetup');
    POLL_TIMERS.fullSetup = window.setInterval(() => pollFullSetupJob(job.id), 2500);
  } catch (error) {
    appendLog(`一键准备环境启动失败：${error.message}`);
    setEnvJobStatus("启动失败", "failed");
    setEnvProgress("failed");
    runFullSetupButton.disabled = false;
    detectEnvironmentButton.disabled = false;
    await loadBootstrap();
    await loadEnvironment();
  }
}

async function pollFullSetupJob(jobId) {
  try {
    const response = await fetch(`/api/install/${jobId}`);
    const job = await response.json();
    if (!response.ok) throw new Error(formatError(job.detail || job));
    setLog((job.log || []).join("\n"));
    renderEnvInstallProgress(job);
    await loadBootstrap();
    if (job.completed || job.status === "success" || job.status === "failed" || job.status === "stopped") {
      clearPollTimer('fullSetup');
      runFullSetupButton.disabled = false;
      detectEnvironmentButton.disabled = false;
      await loadEnvironment();
      if (job.status === "success") {
        localStorage.removeItem(INSTALL_JOB_STORAGE_KEY);
        setEnvJobStatus("一键准备完成", "success");
        setEnvProgress("success");
        appendLog(job.dry_run ? "一键准备 dry-run 通过。" : "一键准备完成。建议点击“生成链路测试”验证真实出片。");
      } else {
        localStorage.removeItem(INSTALL_JOB_STORAGE_KEY);
        setEnvJobStatus("一键准备失败", "failed");
        setEnvProgress("failed");
        appendLog(formatJobFailureHint(job));
      }
    }
  } catch (error) {
    clearPollTimer('fullSetup');
    runFullSetupButton.disabled = false;
    detectEnvironmentButton.disabled = false;
    setEnvJobStatus("轮询失败", "failed");
    setEnvProgress("failed");
    appendLog(`一键准备环境轮询失败：${error.message}`);
    await loadBootstrap();
    await loadEnvironment();
  }
}

function formatJobFailureHint(job) {
  const hint = job?.failure_hint;
  if (!hint) return "任务失败。请点击“复制诊断信息”，把诊断 JSON 发给维护者。";
  const actions = (hint.actions || []).map((item, index) => `${index + 1}. ${item}`).join("\n");
  return [
    "",
    `失败原因：${hint.title || "安装任务失败"}`,
    hint.message || "",
    actions ? `下一步：\n${actions}` : "",
  ]
    .filter(Boolean)
    .join("\n");
}

function renderSmallModelRoutes(data) {
  const routes = data.model_options?.small_model_routes || [];
  if (!smallModelRoutes) return;
  if (!routes.length) {
    smallModelRoutes.innerHTML = `<p class="empty-state">暂无低配路线建议。</p>`;
    return;
  }
  smallModelRoutes.innerHTML = routes
    .map(
      (item) => `
        <div class="route-row">
          <strong>${escapeHtml(item.hardware || "")}</strong>
          <small>${escapeHtml(item.route || "")}</small>
        </div>
      `,
    )
    .join("");
}

function applyRecommendedModelSelections(data, { force = false } = {}) {
  const recommended = data.model_options?.recommended || {};
  let currentChanged = false;
  Object.entries(recommended).forEach(([stepId, modelId]) => {
    const valid = modelOptionsForStep(stepId).some((option) => option.id === selectedModels[stepId]);
    if (force || !valid) {
      currentChanged ||= stepId === currentStep().id && selectedModels[stepId] !== modelId;
      selectedModels[stepId] = modelId;
    }
  });
  if (currentStep().id !== "environment") {
    renderModelSelector({ applyDefaults: force || currentChanged });
    if (!activeJobId) renderStepIdle();
  }
}

function renderEnvironment(data, { forceRecommendations = false } = {}) {
  environmentData = data;
  if (data.model_catalog) {
    modelCatalogData = data.model_catalog;
    syncCatalogSelectionFromData(modelCatalogData);
  }
  applyRecommendedModelSelections(data, { force: forceRecommendations });
  renderDownloadSettings(data.download_settings);
  const missingCount = (data.missing_installable || []).length;
  const blockedCount = (data.blocked || []).length;
  const modelSync = data.model_sync || {};
  const modelMissingCount = (modelSync.missing_files || []).length;
  const modelLabel = modelSync.selected_model?.label || selectedCatalogItem()?.label || "";
  if (enterWorkflowButton) {
    enterWorkflowButton.disabled = false;
    enterWorkflowButton.textContent = data.ok
      ? "环境就绪，进入视频工作流"
      : missingCount || blockedCount
        ? "保留当前建议，进入视频工作流"
        : "进入视频工作流";
  }
  environmentSummary.textContent = modelMissingCount
    ? `当前关注模型 ${modelLabel} 还有 ${modelMissingCount} 个文件未确认。`
    : data.ok
      ? "环境通过，可以开始创作。"
      : missingCount
        ? `检测到 ${missingCount} 个可一键安装的缺失项。`
        : blockedCount
          ? `还有 ${blockedCount} 个核心步骤需要处理。`
          : "环境有警告，请查看下方建议。";
  renderEnvironmentCards(data);
  renderModelRecommendations(data);
  renderModelCatalog();
  renderModelSyncPanel(data);
  renderLoadDiagnostics(data);
  renderMissingItems(data);
  renderSmallModelRoutes(data);
  updateFullSetupAvailability(data);
  if (runVideoSmokeButton) {
    const canSmokeTest = Boolean(data.comfy?.connected) && !missingCount && !blockedCount;
    runVideoSmokeButton.disabled = !canSmokeTest;
    runVideoSmokeButton.title = canSmokeTest
      ? "提交一个最保守的短视频任务，验证模型、节点、队列和输出。"
      : "请先连接 ComfyUI，并处理缺失项/阻断项。";
  }
}

async function loadEnvironment({ forceRecommendations = false, refresh = false } = {}) {
  if (!environmentCards) return;
  const requestId = ++environmentRequestId;
  setFullSetupConfirming(false);
  setWorkflowAssetInstallConfirming(false);
  detectEnvironmentButton.disabled = true;
  if (enterWorkflowButton) enterWorkflowButton.disabled = true;
  installMissingButton.disabled = true;
  if (runFullSetupButton) runFullSetupButton.disabled = true;
  if (runVideoSmokeButton) runVideoSmokeButton.disabled = true;
  environmentSummary.textContent = "正在检测系统、GPU、ComfyUI、ffmpeg 和模型文件。";
  try {
    const response = await fetch(refresh ? "/api/environment?refresh=true" : "/api/environment");
    const data = await response.json();
    if (requestId !== environmentRequestId) return;
    if (!response.ok) throw new Error(formatError(data.detail || data));
    renderEnvironment(data, { forceRecommendations });
    await loadInstallPlan(selectedInstallProfile);
    const comfy = data.comfy || {};
    if (comfy.connected) {
      setStatus(true, `${comfy.comfyui_version || "ComfyUI"} | ${data.hardware?.max_vram_gb || "-"} GB 单卡`);
    } else {
      setStatus(false, "ComfyUI 未连接");
    }
    setLog(data.ok ? "环境侦测通过，可以进入关键帧。" : "环境侦测完成，请查看缺失项和模型建议。");
  } catch (error) {
    if (requestId !== environmentRequestId) return;
    environmentData = null;
    updateEnvStatusBar();
    environmentSummary.textContent = "环境侦测失败。";
    environmentCards.innerHTML = `<div class="env-card blocked"><small>错误</small><strong>侦测失败</strong><span>${escapeHtml(error.message)}</span></div>`;
    modelRecommendations.innerHTML = "";
    if (loadDiagnostics) loadDiagnostics.innerHTML = "";
    missingItems.innerHTML = "";
    if (smallModelRoutes) smallModelRoutes.innerHTML = "";
    setLog(`环境侦测失败：${error.message}`);
    if (enterWorkflowButton) enterWorkflowButton.disabled = true;
    if (runFullSetupButton) runFullSetupButton.disabled = false;
    if (runVideoSmokeButton) runVideoSmokeButton.disabled = true;
  } finally {
    if (requestId !== environmentRequestId) return;
    detectEnvironmentButton.disabled = false;
    if (environmentData) {
      installMissingButton.disabled =
        environmentData.install_plan?.installable === false ||
        !(environmentData.missing_installable || []).length ||
        environmentData.install_plan?.disk?.ok === false;
    }
  }
}

async function refreshEnvironmentWorkspace({ forceRecommendations = false } = {}) {
  if (environmentRefreshPromise) return environmentRefreshPromise;
  environmentRefreshPromise = refreshEnvironmentWorkspaceOnce({ forceRecommendations });
  try { return await environmentRefreshPromise; }
  finally { environmentRefreshPromise = null; }
}

async function refreshEnvironmentWorkspaceOnce({ forceRecommendations = false } = {}) {
  await loadClientConfig();
  await loadSettings();
  await loadBootstrap();
  await loadModelStorageLocations();
  const result = await loadEnvironment({ forceRecommendations });
  updateEnvStatusBar();
  return result;
}

function formatSelfTestSummary(job) {
  const selfTest = job?.self_test || {};
  const results = selfTest.results || [];
  if (!results.length) {
    return job.status === "success" ? "本机自检通过。" : formatJobFailureHint(job);
  }
  const lines = results.map((item) => {
    const name = (item.command || "").includes("prerequisite_doctor.py") ? "前置条件" : (item.command || "").includes("self_check.py") ? "项目自检" : "检查";
    return `${name}：${item.ok ? "通过" : "未通过"}（退出码 ${item.return_code}）`;
  });
  return [`本机自检${selfTest.ok ? "通过" : "发现问题"}。`, ...lines, selfTest.ok ? "" : "请点击“复制诊断信息”，把 JSON 发给维护者。"].filter(Boolean).join("\n");
}

async function startSelfTest() {
  if (!runSelfTestButton) return;
  runSelfTestButton.disabled = true;
  setLog("正在启动本机自检。该检查不会下载模型，也不会启动真实生成。");
  try {
    const response = await fetch("/api/self-test", { method: "POST" });
    const job = await response.json();
    if (!response.ok) throw new Error(formatError(job.detail || job));
    pollSelfTest(job.id);
    clearPollTimer('selfTest');
    POLL_TIMERS.selfTest = window.setInterval(() => pollSelfTest(job.id), 1800);
  } catch (error) {
    runSelfTestButton.disabled = false;
    appendLog(`本机自检启动失败：${error.message}`);
  }
}

async function pollSelfTest(jobId) {
  try {
    const response = await fetch(`/api/install/${jobId}`);
    const job = await response.json();
    if (!response.ok) throw new Error(formatError(job.detail || job));
    setLog((job.log || []).join("\n"));
    if (job.completed) {
      clearPollTimer('selfTest');
      runSelfTestButton.disabled = false;
      appendLog(formatSelfTestSummary(job));
    }
  } catch (error) {
    clearPollTimer('selfTest');
    runSelfTestButton.disabled = false;
    appendLog(`本机自检轮询失败：${error.message}`);
  }
}

function smokeStatusLabel(status) {
  if (status === "success") return "生成链路测试通过";
  if (status === "running") return "生成链路测试运行中";
  if (status === "queued") return "生成链路测试排队中";
  if (status === "reconnecting") return "生成链路测试连接恢复中";
  return status || "生成链路测试";
}

async function startVideoSmokeTest() {
  if (!runVideoSmokeButton) return;
  clearPollTimer('videoSmoke');
  runVideoSmokeButton.disabled = true;
  continueButton.classList.add("hidden");
  repeatButton.classList.add("hidden");
  jobStatus.textContent = "提交生成链路测试";
  resultHint.textContent = "正在提交一个低成本短视频，用来验证 ComfyUI 真实生成链路。";
  resultView.innerHTML = "<p>任务提交后，生成结果会显示在这里。</p>";
  setProgress("queued");
  setLog("正在提交生成链路测试。它会使用当前环境可用的最保守视频模型。");
  try {
    const response = await fetch("/api/video-smoke-test", { method: "POST" });
    const job = await response.json();
    if (!response.ok) throw new Error(formatError(job.detail || job));
    activeJobId = job.id;
    rememberActiveJob(job.id, "draft", job);
    setJobMeta(job);
    appendLog(`已提交生成链路测试：${job.title || job.prompt_id || job.id}`);
    watchJob(job.id, "draft");
    await pollVideoSmokeJob(job.id);
    POLL_TIMERS.videoSmoke = window.setInterval(() => pollVideoSmokeJob(job.id), 2500);
  } catch (error) {
    setProgress("failed");
    jobStatus.textContent = "生成链路测试失败";
    appendLog(`生成链路测试启动失败：${error.message}`);
    runVideoSmokeButton.disabled = false;
  }
}

async function pollVideoSmokeJob(jobId) {
  try {
    const response = await fetch(`/api/jobs/${jobId}`);
    const job = await response.json();
    if (!response.ok) throw new Error(formatError(job.detail || job));

    setJobMeta(job);
    setProgress(job.status, job.progress);
    jobStatus.textContent = smokeStatusLabel(job.status);
    if (job.media && job.media.length) {
      renderMedia(job.media);
    }

    if (job.status === "success") {
      clearPollTimer('videoSmoke');
      runVideoSmokeButton.disabled = false;
      resultHint.textContent = "生成链路测试通过。现在可以从关键帧进入视频生成。";
      appendLog("生成链路测试通过：ComfyUI 队列、模型、节点和输出目录都完成了一次真实视频生成。");
      return;
    }

    if (job.completed || terminalJobFailed(job) || (job.status && !["queued", "running", "reconnecting"].includes(job.status))) {
      clearPollTimer('videoSmoke');
      runVideoSmokeButton.disabled = false;
      jobStatus.textContent = terminalJobFailed(job) ? "生成链路测试失败" : smokeStatusLabel(job.status);
      setProgress("failed");
      const detail = formatJobMessages(job);
      appendLog(detail ? `生成链路测试失败：${job.status}\n${detail}` : `生成链路测试状态：${job.status}`);
    }
  } catch (error) {
    jobStatus.textContent = "生成链路测试连接恢复中";
    setProgress("reconnecting");
    appendLog(`生成链路测试状态暂时不可用，仍会重试：${error.message}`);
  }
}

async function startInstall() {
  const missing = environmentData?.missing_installable || [];
  const plan = environmentData?.install_plan || {};
  if (plan.installable === false) {
    setWorkflowAssetInstallConfirming(false);
    setLog("当前目标模型需要手动接入，没有可执行的一键安装计划。请查看模型目录中的来源与工作流说明。");
    return;
  }
  if (!missing.length) {
    setWorkflowAssetInstallConfirming(false);
    setLog("没有需要一键安装的缺失项。");
    return;
  }
  if (plan.disk?.ok === false) {
    setWorkflowAssetInstallConfirming(false);
    setLog(
      `磁盘空间不足，已取消安装。当前剩余 ${formatGb(plan.disk.free_gb)}，预计还需下载 ${formatGb(plan.disk.required_gb)}，建议至少预留 ${formatGb(plan.disk.recommended_free_gb)}。可以切换到更轻量的模型档，或只安装后期工具。`,
    );
    return;
  }
  if (!allowWorkflowAssetInstall) {
    setWorkflowAssetInstallConfirming(true);
    const sourceText = downloadHostListText(workflowAssetDownloadHosts());
    const requirementText = plan.external_requirement ? ` 下载前还需要：${plan.external_requirement}。` : "";
    setLog(
      `将按 ${installProfileLabel(selectedInstallProfile)} 把 ${missing.length} 个缺失/异常项写入 ${currentModelDownloadPath()}，预计下载约 ${formatGb(plan.missing_expected_gb || 0)}，建议预留 ${formatGb(plan.disk?.recommended_free_gb)}。开始前会检查下载源：${sourceText}。${requirementText}完成后需要重启 ComfyUI。确认继续请再点击一次“${workflowAssetConfirmText}”。`,
    );
    return;
  }
  setWorkflowAssetInstallConfirming(false);

  installMissingButton.disabled = true;
  detectEnvironmentButton.disabled = true;
  setLog("正在启动安装任务。");
  setEnvJobStatus("正在创建下载任务", "running");
  setEnvProgress("queued");
  try {
    const params = new URLSearchParams({ profile: selectedInstallProfile || "auto", confirm_requirement: "true" });
    const target = currentModelDownloadPath();
    if (target) params.set("target_dir", target);
    const response = await fetch(`/api/install?${params}`, { method: "POST" });
    const job = await response.json();
    if (!response.ok) throw new Error(formatError(job.detail || job));
    localStorage.setItem(INSTALL_JOB_STORAGE_KEY, job.id);
    renderEnvInstallProgress(job);
    pollInstall(job.id);
    POLL_TIMERS.install = window.setInterval(() => pollInstall(job.id), 2500);
  } catch (error) {
    setLog(`安装任务启动失败：${error.message}`);
    setEnvJobStatus("启动失败", "failed");
    setEnvProgress("failed");
    installMissingButton.disabled = false;
    detectEnvironmentButton.disabled = false;
    setWorkflowAssetInstallConfirming(false);
  }
}

function setOneClickInstallButtonsBusy(profile, busy, text = "") {
  document.querySelectorAll("[data-catalog-install]").forEach((button) => {
    if ((button.dataset.installProfile || "") !== profile) return;
    button.disabled = Boolean(busy);
    if (busy) {
      button.dataset.idleText = button.dataset.idleText || button.textContent;
      button.textContent = text || "正在创建下载任务";
    } else if (button.dataset.idleText) {
      button.textContent = button.dataset.idleText;
      delete button.dataset.idleText;
    }
  });
  if (videoModelInstallButton?.dataset.profile === profile) {
    videoModelInstallButton.disabled = Boolean(busy);
    if (busy) {
      videoModelInstallButton.dataset.idleText = videoModelInstallButton.dataset.idleText || videoModelInstallButton.textContent;
      videoModelInstallButton.textContent = text || "正在创建下载任务";
    } else if (videoModelInstallButton.dataset.idleText) {
      videoModelInstallButton.textContent = videoModelInstallButton.dataset.idleText;
      delete videoModelInstallButton.dataset.idleText;
    }
  }
}

function showInstallInDownloadCenter(job, label) {
  setView("download-center");
  window.dispatchEvent(new CustomEvent("workspace:downloadchange", {
    detail: {
      jobId: job?.id || "",
      message: job?.completed
        ? `${label} 已完成检查，下载中心已显示结果。`
        : `${label} 已加入下载中心，可在这里查看逐文件进度、暂停或取消。`,
    },
  }));
}

function catalogWantsImageEdit(item) {
  return /edit|微调/i.test(`${item?.id || ""} ${item?.default_install_profile || ""} ${item?.workflow_modes?.image || ""}`);
}

function selectWorkflowOptionForCatalog(item) {
  if (!item) return;
  const options = modelOptionsForStep("draft");
  const catalogId = item.id || "";
  const installProfile = item.default_install_profile || item.install_profile || "";
  const modes = new Set(Object.values(item.workflow_modes || {}));
  const byCatalog = options.filter((opt) => catalogId && opt.catalog_id === catalogId);
  const byProfile = options.filter((opt) => installProfile && opt.install_profile === installProfile);
  const byMode = options.filter((opt) => modes.has(opt.mode));
  const pool = byCatalog.length ? byCatalog : byProfile.length ? byProfile : byMode;
  if (!pool.length) return;
  const preferImage = hasKeyframeUpload();
  const match = pool.find((opt) => (preferImage ? opt.uses_image : !opt.uses_image)) || pool[0];
  if (!match) return;
  selectedModels.draft = match.id;
  renderModelSelector({ applyDefaults: true });
}

async function goGenerateFromCatalog(modelId = "") {
  const item = catalogItems().find((entry) => entry.id === modelId) || selectedCatalogItem();
  if (!item) {
    appendLog("还没有可跳转的模型。");
    return;
  }
  const target = catalogGenerationTarget(item);
  if (target === "catalog_only") {
    appendLog(`${item.label || item.id} 仅目录参考，本页不能生成。`);
    return;
  }
  if (target === "comfy_template") {
    const url = environmentData?.comfy?.url || "http://127.0.0.1:8188";
    const search = item.template_search ? ` 可搜索「${item.template_search}」。` : "";
    appendLog(`${item.label || item.id} 请到 ComfyUI 打开官方模板运行，本页不能直接生成。${search}`);
    window.open(url, "_blank", "noreferrer");
    return;
  }
  if (item.id && item.id !== selectedCatalogModelId) {
    await saveCatalogSelection(item.id);
  }
  if (isImageCatalogItem(item)) {
    setView("image-studio");
    window.dispatchEvent(new CustomEvent("workspace:select-image-profile", {
      detail: {
        catalogId: item.id,
        profile: String(item.workflow_modes?.image || ""),
        installProfile: String(item.default_install_profile || item.install_profile || ""),
        editMode: catalogWantsImageEdit(item),
      },
    }));
    appendLog(`已打开图片生成：${item.label || item.id}`);
    return;
  }
  setView("workflow");
  setStep("draft", { refresh: true });
  selectWorkflowOptionForCatalog(item);
  appendLog(`已打开视频生成：${item.label || item.id}`);
}

function goGenerateButtons() {
  return [envGoGenerateButton, downloadCenterGoGenerateButton].filter(Boolean);
}

function hideGoGenerateButtons() {
  goGenerateButtons().forEach((button) => button.classList.add("hidden"));
}

function updateGoGenerateButton(job = null, item = null) {
  const catalogItem = item || catalogItems().find((entry) => entry.id === (job?.catalog_model_id || selectedCatalogModelId)) || selectedCatalogItem();
  const canGo = catalogGenerationTarget(catalogItem) !== "catalog_only";
  const visible = Boolean(canGo && job?.status === "success");
  const label = catalogGenerationTarget(catalogItem) === "comfy_template"
    ? "打开 ComfyUI 模板"
    : catalogGenerationTarget(catalogItem) === "cloud_api"
      ? "去云端生成"
      : "去生成";
  goGenerateButtons().forEach((button) => {
    button.classList.toggle("hidden", !visible);
    if (!canGo) return;
    button.dataset.modelId = catalogItem?.id || "";
    button.textContent = label;
  });
}

async function finishCatalogInstall(job) {
  await loadEnvironment({ forceRecommendations: true, refresh: true });
  const item = catalogItems().find((entry) => entry.id === (job?.catalog_model_id || selectedCatalogModelId)) || selectedCatalogItem();
  updateGoGenerateButton(job, item);
  if (job?.status !== "success") {
    appendLog(formatJobFailureHint(job));
    return;
  }
  const label = item?.label || job?.install_profile || "当前模型";
  const target = catalogGenerationTarget(item);
  const sync = environmentData?.model_sync || {};
  const missing = sync.missing_files || [];
  const upgrade = Boolean(environmentData?.comfy_upgrade_required);
  const customTarget = Boolean(job.custom_target || job.extra_model_paths_config);
  const graphBlocked = (environmentData?.diagnostics || []).some((entry) => entry.level === "blocked");
  if (target === "comfy_template") {
    appendLog(`${label} 权重已就绪。本页不能直接生成，请打开 ComfyUI 跑官方模板。`);
    return;
  }
  if (!["native", "cloud_api"].includes(target)) {
    appendLog(`${label} 下载完成。该项仅目录参考，不会接入本页生成。`);
    return;
  }
  if (upgrade) {
    appendLog(`${label} 权重已下载，但 ComfyUI 版本不够。请先更新并重启 8188。`);
    return;
  }
  if (customTarget || (!missing.length && graphBlocked)) {
    appendLog(`${label} 已下载到磁盘。请重启 ComfyUI 8188 后再点「去生成」。`);
    return;
  }
  if (missing.length) {
    appendLog(`安装任务完成，但仍缺 ${missing.length} 个文件。请查看模型控制台。`);
    return;
  }
  appendLog(`${label} 已就绪，可点「去生成」。`);
}

async function launchOneClickInstall(profile, label = "当前功能", options = {}) {
  if (!profile) {
    setView("environment");
    setLog(`${label}没有平台可执行的自动下载档位，已打开环境诊断与手动接入说明。`);
    return;
  }
  if (oneClickInstallStarting) {
    setLog("正在创建上一条下载任务，请稍候；已运行的任务可在下载中心查看。");
    return;
  }
  const item = catalogItems().find((entry) => entry.id === options.modelId)
    || (!options.modelId ? catalogItems().find((entry) => entry.install_profile === profile) : null)
    || null;
  const requirement = item?.external_requirement || "";
  const requiredVersion = item?.required_comfy_version || "";
  const currentVersion = environmentData?.comfy?.comfyui_version || "";
  if (requiredVersion && environmentData?.comfy?.connected && !versionAtLeast(currentVersion, requiredVersion)) {
    setLog(`当前 ComfyUI 为 ${currentVersion || "未知版本"}，${label} 至少需要 ${requiredVersion}。请先更新并重启 ComfyUI，再下载模型。`);
    return;
  }
  const confirmKey = `${profile}::${options.modelId || ""}`;
  if (requirement && !pendingInstallRequirementConfirms.has(confirmKey)) {
    pendingInstallRequirementConfirms.add(confirmKey);
    setLog(`下载前需要：${requirement} 确认后请再点一次「${label}」下载。`);
    return;
  }
  pendingInstallRequirementConfirms.delete(confirmKey);
  oneClickInstallStarting = true;
  selectedInstallProfile = profile;
  setOneClickInstallButtonsBusy(profile, true);
  setLog(`正在为 ${label} 创建下载任务；任务建立后会自动打开下载中心。`);
  try {
    const params = new URLSearchParams({
      profile,
      include_post: "false",
      confirm_requirement: "true",
    });
    if (options.modelId) params.set("model_id", options.modelId);
    const target = currentModelDownloadPath();
    if (target) params.set("target_dir", target);
    const response = await fetch(`/api/install?${params}`, { method: "POST" });
    const job = await response.json();
    if (!response.ok) {
      const error = new Error(formatError(job.detail || job));
      error.status = response.status;
      throw error;
    }
    if (options.modelId) void rememberCatalogSelectionForInstall(options.modelId);
    localStorage.setItem(INSTALL_JOB_STORAGE_KEY, job.id);
    renderEnvInstallProgress(job);
    clearPollTimer("install");
    if (job.completed) {
      if (job.status !== "interrupted") localStorage.removeItem(INSTALL_JOB_STORAGE_KEY);
      if (job.status === "success") await finishCatalogInstall(job);
    } else {
      void pollInstall(job.id);
      POLL_TIMERS.install = window.setInterval(() => pollInstall(job.id), 1500);
    }
    showInstallInDownloadCenter(job, label);
  } catch (error) {
    setLog(`${label} 下载任务启动失败：${error.message}`);
    if (error.status === 409 || String(error.message || "").includes("已有安装任务")) {
      setView("download-center");
      window.dispatchEvent(new CustomEvent("workspace:downloadchange", {
        detail: { message: "已有下载任务正在处理，已打开下载中心。" },
      }));
    }
  } finally {
    oneClickInstallStarting = false;
    setOneClickInstallButtonsBusy(profile, false);
  }
}

async function pollInstall(jobId) {
  try {
    const response = await fetch(`/api/install/${jobId}`);
    const job = await response.json();
    if (!response.ok) throw new Error(formatError(job.detail || job));
    setLog((job.log || []).join("\n"));
    renderEnvInstallProgress(job);
    if (job.completed) {
      clearPollTimer('install');
      detectEnvironmentButton.disabled = false;
      if (job.status === "success") await finishCatalogInstall(job);
      else {
        await loadEnvironment({ forceRecommendations: true, refresh: true });
        appendLog(formatJobFailureHint(job));
      }
      if (job.status !== "interrupted") localStorage.removeItem(INSTALL_JOB_STORAGE_KEY);
    }
  } catch (error) {
    clearPollTimer('install');
    detectEnvironmentButton.disabled = false;
    installMissingButton.disabled = false;
    appendLog(`安装轮询失败：${error.message}`);
  }
}

async function controlEnvInstall(action) {
  const jobId = activeInstallControlJobId || localStorage.getItem(INSTALL_JOB_STORAGE_KEY);
  if (!jobId) return;
  try {
    const response = await fetch(`/api/install/${encodeURIComponent(jobId)}/${action}`, { method: "POST" });
    const job = await response.json();
    if (!response.ok) throw new Error(formatError(job.detail || job));
    renderEnvInstallProgress(job);
    setLog((job.log || []).join("\n"));
    if (action === "resume") {
      clearPollTimer('install');
      POLL_TIMERS.install = window.setInterval(() => pollInstall(jobId), 1200);
    }
  } catch (error) {
    appendEnvLog(`${action === "pause" ? "暂停" : action === "resume" ? "继续" : "取消"}安装失败：${error.message}`);
  }
}

async function resumeRememberedInstall() {
  const jobId = localStorage.getItem(INSTALL_JOB_STORAGE_KEY);
  if (!jobId) return;
  try {
    const response = await fetch(`/api/install/${encodeURIComponent(jobId)}`);
    const job = await response.json();
    if (!response.ok) throw new Error(formatError(job.detail || job));
    renderEnvInstallProgress(job);
    setLog((job.log || []).join("\n"));
    const resumable = ["paused", "interrupted"].includes(job.status) && Array.isArray(job.command_args);
    if (job.completed && !resumable) {
      localStorage.removeItem(INSTALL_JOB_STORAGE_KEY);
      return;
    }
    if (job.kind === "full_setup") {
      clearPollTimer('fullSetup');
      POLL_TIMERS.fullSetup = window.setInterval(() => pollFullSetupJob(jobId), 2500);
    } else {
      clearPollTimer('install');
      POLL_TIMERS.install = window.setInterval(() => pollInstall(jobId), 1200);
    }
  } catch (_error) {
    localStorage.removeItem(INSTALL_JOB_STORAGE_KEY);
  }
}

function renderMediaInto(container, media, emptyMessage) {
  if (!container) return;
  if (!media || media.length === 0) {
    container.innerHTML = `<p>${escapeHtml(emptyMessage)}</p>`;
    return;
  }
  const first = media[0];
  const firstUrl = mediaUrl(first.url);
  const preview =
    first.kind === "video"
      ? `<video src="${escapeHtml(firstUrl)}" controls playsinline></video>`
      : `<img src="${escapeHtml(firstUrl)}" alt="生成结果" />`;
  const links = media
    .map((item, index) => {
      const label = item.kind === "video" ? `视频 ${index + 1}` : `图片 ${index + 1}`;
      return `<a href="${escapeHtml(mediaUrl(item.url))}" target="_blank" rel="noreferrer">${label}</a>`;
    })
    .join("");
  container.innerHTML = `${preview}<div class="result-links">${links}</div>`;
}

function renderMedia(media) {
  const file = WorkbenchJourney.tools.includes(currentStep().id) ? videoInput.files?.[0] : null;
  if (uploadedPreview.file !== file) {
    if (uploadedPreview.url) URL.revokeObjectURL(uploadedPreview.url);
    uploadedPreview = { file, url: file ? URL.createObjectURL(file) : "" };
  }
  if (!media?.length && uploadedPreview.url) {
    renderMediaInto(resultView, [{ kind: "video", url: uploadedPreview.url }], "");
    return;
  }
  renderMediaInto(resultView, media, "当前步骤完成后，结果会显示在这里。");
}

function renderVideoFaceSwapMedia(media) {
  renderMediaInto(videoFaceSwapResultView, media, "换脸结果会显示在这里。");
}

function pickVideo(media) {
  return (media || []).find((item) => item.kind === "video") || null;
}

function stitchSourceVideo() {
  return lastUpscaleVideo || lastRifeVideo || lastDeflickerVideo || lastDraftVideo || lastFinalVideo;
}

function formatFileSize(bytes) {
  const value = Number(bytes || 0);
  if (value >= 1024 ** 3) return `${(value / 1024 ** 3).toFixed(1)} GB`;
  if (value >= 1024 ** 2) return `${(value / 1024 ** 2).toFixed(1)} MB`;
  if (value >= 1024) return `${(value / 1024).toFixed(0)} KB`;
  return `${value} B`;
}

function renderStitchClipList() {
  if (!stitchClipList) return;
  const previous = stitchSourceVideo();
  const rows = [];
  if (previous) {
    rows.push(`
      <div class="clip-order-row fixed">
        <span class="clip-index">1</span>
        <div><strong>${escapeHtml(previous.filename || "当前素材")}</strong><small>当前素材 · 固定在首位</small></div>
      </div>
    `);
  }
  stitchFiles.forEach((file, index) => {
    const displayIndex = index + (previous ? 2 : 1);
    rows.push(`
      <div class="clip-order-row">
        <span class="clip-index">${displayIndex}</span>
        <div><strong>${escapeHtml(file.name)}</strong><small>${escapeHtml(formatFileSize(file.size))}</small></div>
        <div class="clip-order-actions">
          <button type="button" data-clip-action="up" data-clip-index="${index}" title="上移" aria-label="上移 ${escapeHtml(file.name)}" ${index === 0 ? "disabled" : ""}>↑</button>
          <button type="button" data-clip-action="down" data-clip-index="${index}" title="下移" aria-label="下移 ${escapeHtml(file.name)}" ${index === stitchFiles.length - 1 ? "disabled" : ""}>↓</button>
          <button type="button" data-clip-action="remove" data-clip-index="${index}" title="移除" aria-label="移除 ${escapeHtml(file.name)}">×</button>
        </div>
      </div>
    `);
  });
  const total = stitchFiles.length + (previous ? 1 : 0);
  stitchClipList.innerHTML = rows.length
    ? `${rows.join("")}<p class="clip-order-summary ${total >= 2 ? "good" : "warn"}">当前 ${total} 个片段${total >= 2 ? "，可以开始拼接。" : "，还需至少 1 个。"}</p>`
    : "<p>至少选择 2 个片段。选择后可在这里调整顺序。</p>";
  if (currentStep().id === "edit") {
    updateStepCopy();
  }
}

function updateStitchFiles() {
  const key = (file) => `${file.name}/${file.size}/${file.lastModified}`;
  stitchFiles = [...new Map([...stitchFiles, ...Array.from(clipsInput?.files || [])].map((file) => [key(file), file])).values()];
  if (clipsInput) clipsInput.value = "";
  invalidateStitchResult();
  renderStitchClipList();
  renderStepIdle();
}

function invalidateStitchResult() {
  delete workflowState.outputs.edit;
  delete workflowState.latest.edit;
  syncWorkflowOutputs();
  persistWorkflowState();
}

function handleClipOrderAction(event) {
  const button = event.target.closest("[data-clip-action]");
  if (!button) return;
  const index = Number(button.dataset.clipIndex);
  if (!Number.isInteger(index) || index < 0 || index >= stitchFiles.length) return;
  if (button.dataset.clipAction === "remove") {
    stitchFiles.splice(index, 1);
  } else {
    const nextIndex = button.dataset.clipAction === "up" ? index - 1 : index + 1;
    if (nextIndex < 0 || nextIndex >= stitchFiles.length) return;
    [stitchFiles[index], stitchFiles[nextIndex]] = [stitchFiles[nextIndex], stitchFiles[index]];
  }
  invalidateStitchResult();
  renderStitchClipList();
  renderStepIdle();
}

function readProjectResolution() {
  const width = Number(widthInput.value) || 1280;
  const height = Number(heightInput.value) || 704;
  return { width, height };
}

function getUpscaleSourceResolution() {
  const record = WorkbenchState.sourceFor(workflowState, "upscale");
  const source = videoInput?.files?.[0] ? currentVideoResolution || readProjectResolution()
    : record?.width && record?.height ? record : readProjectResolution();
  const draftMode = selectedModelOption("draft")?.mode || "";
  const usesH3Aligned1080 =
    !videoInput?.files?.[0] &&
    draftMode.startsWith("minimax_h3_") &&
    source.width === 1920 &&
    source.height === 1088;
  return usesH3Aligned1080 ? { width: 1920, height: 1080 } : source;
}

function updateTargetResolution() {
  if (!sourceResolutionText || !targetResolutionText || !targetResolutionNote) return;

  const source = getUpscaleSourceResolution();
  const scale = getUpscaleScale();
  const target = {
    width: source.width * scale,
    height: source.height * scale,
  };

  sourceResolutionText.textContent = `${source.width} x ${source.height}`;
  if (targetResolutionLabel) targetResolutionLabel.textContent = `${scale}x 输出目标`;
  targetResolutionText.textContent = `${target.width} x ${target.height}`;

  if (currentVideoResolution) {
    targetResolutionNote.textContent =
      `目标分辨率按当前输入视频的实际尺寸计算，放大 ${scale} 倍。`;
  } else {
    targetResolutionNote.textContent =
      `尚未取得素材尺寸，目标仅为估算；选择视频后按实际尺寸放大 ${scale} 倍。`;
  }
}

function updateVideoSource() {
  const sourceLabel = document.querySelector("#workflowSourceLabel");
  if (sourceLabel) {
    const selected = WorkbenchState.sourceFor(workflowState, currentStep().id);
    sourceLabel.textContent = videoInput?.files?.[0]?.name || selected?.filename ||
      (currentStep().id === "edit" && stitchFiles.length ? `${stitchFiles.length} 个本机片段` : "未选择视频素材");
  }
  if (videoInput?.files?.[0]) {
    sourceVideoFilename.value = "";
    sourceVideoSubfolder.value = "";
    sourceVideoType.value = "";
    updateTargetResolution();
    return;
  }
  let source = null;
  if (currentStep().id === "deflicker") {
    source = lastDraftVideo || lastFinalVideo;
  } else if (currentStep().id === "rife") {
    source = lastDeflickerVideo || lastDraftVideo || lastFinalVideo;
    if (source) fpsInput.value = currentVideoFps || Number(fpsInput.value || 24);
  } else if (currentStep().id === "upscale") {
    source = lastRifeVideo || lastDeflickerVideo || lastDraftVideo || lastFinalVideo;
    if (source) fpsInput.value = currentVideoFps || Number(fpsInput.value || 24);
  } else if (currentStep().id === "edit") {
    source = stitchSourceVideo();
    if (source) {
      fpsInput.value = currentVideoFps || Number(fpsInput.value || 24);
      if (currentVideoResolution) setSize(currentVideoResolution.width, currentVideoResolution.height);
    }
  }

  if (!source) {
    sourceVideoFilename.value = "";
    sourceVideoSubfolder.value = "";
    sourceVideoType.value = "";
    updateTargetResolution();
    return;
  }
  sourceVideoFilename.value = source.filename || "";
  sourceVideoSubfolder.value = source.subfolder || "";
  sourceVideoType.value = source.type || "output";
  if (source.width && source.height) currentVideoResolution = { width: source.width, height: source.height };
  if (source.fps) { currentVideoFps = source.fps; fpsInput.value = source.fps; }
  updateTargetResolution();
}

function goNext() {
  renderResultActions();
  document.querySelector("#resultActions").focus();
  document.querySelector("#resultActions").scrollIntoView({ behavior: "smooth", block: "center" });
}

function goBack() {
  navigateWorkspace("workflow");
}

async function refreshStatus() {
  try {
    const response = await fetch("/api/status");
    if (!response.ok) throw new Error(await response.text());
    const data = await response.json();
    if (data.connected === false) {
      setStatus(false, "ComfyUI 未连接");
    } else {
      setStatus(true, `${data.comfyui_version} | 空闲显存 ${data.vram_free_gb} GB`);
    }
    if (environmentData?.comfy) environmentData.comfy.connected = data.connected !== false;
  } catch (error) {
    setStatus(false, "ComfyUI 未连接");
    if (environmentData?.comfy) environmentData.comfy.connected = false;
  }
  updateEnvStatusBar();
  loadRecentJobs(false);
}

async function validateSetup() {
  validateButton.disabled = true;
  setLog("正在检查 ComfyUI 节点、模型文件和工作流图。");
  try {
    const response = await fetch("/api/validate");
    const data = await response.json();
    if (!response.ok) throw new Error(JSON.stringify(data, null, 2));
    const missingNodes = data.nodes.filter((item) => !item.ok).map((item) => item.name);
    const missingFiles = data.files.filter((item) => !item.ok).map((item) => item.path);
    const brokenGraphs = data.graphs.filter((item) => !item.ok).map((item) => item.name);
    const missingTools = (data.tools || []).filter((item) => !item.ok && item.required !== false).map((item) => item.name);
    if (data.ok) {
      setLog("检查通过：节点、模型文件、输出节点和 API 图都已就绪。");
    } else {
      setLog(
        [
          "检查未通过：",
          missingNodes.length ? `缺少节点：${missingNodes.join(", ")}` : "",
          missingFiles.length ? `缺少文件：\n${missingFiles.join("\n")}` : "",
          brokenGraphs.length ? `工作流图异常：${brokenGraphs.join(", ")}` : "",
          missingTools.length ? `缺少本地工具：${missingTools.join(", ")}` : "",
        ]
          .filter(Boolean)
          .join("\n"),
      );
    }
  } catch (error) {
    setLog(`检查失败：${error.message}`);
  } finally {
    validateButton.disabled = false;
  }
}

async function handlePrimary() {
  const step = currentStep();
  const option = selectedModelOption(step.id);
  if (step.id === "deflicker") { await submitVideoTune(); return; }
  if (step.id === "keyframe") {
    const hasImage = hasKeyframeUpload();
    const switched = hasImage ? switchTextModelsToImageVideo() : switchImageModelsToTextVideo();
    const draftOption = selectedModelOption("draft");
    completedSteps.add("keyframe");
    if (hasImage && switched.length) {
      appendLog(`已使用上传的关键帧，并切换到图生视频路线：${switched.join("、")}。`);
    } else if (hasImage) {
      appendLog(`已使用上传的关键帧，进入 ${selectedModelName("draft")}。`);
    } else if (switched.length) {
      appendLog(`未上传关键帧，已切换到文字生视频路线：${switched.join("、")}。`);
    } else if (optionCapabilities(draftOption).image_input === "required") {
      appendLog(`未上传关键帧，已跳过此步。${selectedModelName("draft")} 需要图片，请在下一步上传，或切换到 T2V 模型。`);
    } else {
      appendLog(`未上传关键帧，将使用 ${selectedModelName("draft")} 文字生视频路线。`);
    }
    void syncCatalogSelectionForWorkflowOption(draftOption);
    setStep("draft", { refresh: false });
    return;
  }
  if (option?.mode === "external_workflow") {
    const catalog = selectedCatalogItem();
    if (catalog?.platform_support === "official_workflow") {
      const comfyUrl = environmentData?.comfy?.url || "http://127.0.0.1:8188";
      window.open(comfyUrl, "_blank", "noopener,noreferrer");
      const template = catalog.template_search || catalog.label || "当前模型";
      setLog(`${option.reason || "请使用 ComfyUI 官方工作流。"} 已打开 ComfyUI；在 Workflow > Browse Templates 中搜索“${template}”。`);
      return;
    }
    const sources = catalog?.sources || [];
    const workflowSource = sources.find((url) => String(url).includes("github.com")) || sources[0];
    if (workflowSource) window.open(workflowSource, "_blank", "noopener,noreferrer");
    setLog(option.reason || "请按模型目录中的来源与工作流说明继续。");
    return;
  }
  if (option?.mode === "unsupported" || option?.status === "blocked") {
    videoModelInstallButton?.focus();
    setLog(option.install_profile
      ? `当前模型依赖未就绪。点击“一键下载/修复 ${option.label}”即可拉起对应安装计划。`
      : `${option.reason || "当前选项暂不可运行。"} 请使用上方处理按钮查看环境诊断。`);
    return;
  }
  if (step.id === "edit") {
    const clipCount = stitchFiles.length + (stitchSourceVideo() ? 1 : 0);
    if (clipCount < 2) {
      setLog("成片拼接至少需要 2 个视频片段。请继续选择片段，或先完成前面的生成/后期步骤。 ");
      clipsInput?.focus();
      return;
    }
  }
  const batchFiles = step.id === "draft" && batchKeyframeInput?.files?.length > 1
    ? Array.from(batchKeyframeInput.files)
    : [];
  if (batchFiles.length > 1) {
    appendLog(`批量关键帧：将追加 ${batchFiles.length} 个独立图生视频任务。`);
    for (let index = 0; index < batchFiles.length; index += 1) {
      appendLog(`批量 ${index + 1}/${batchFiles.length}：${batchFiles[index].name}`);
      await submitJob({ keyframeFile: batchFiles[index] });
    }
    return;
  }
  await submitJob();
}

async function submitJob(options = {}) {
  const { keyframeFile = null } = options;
  const step = currentStep();
  if (videoSubmitting) return false;
  if (step.id === "draft" && !promptInput.value.trim()) {
    promptInput.focus();
    setLog("请先填写视频画面与镜头提示词；平台不会自动注入默认场景。 ");
    return false;
  }
  const draftMode = selectedModelOption("draft")?.mode || "";
  if (step.id === "draft" && draftMode === "minimax_h3_r2v") {
    const references = referenceMediaSummary();
    if (!references.valid) {
      referenceMediaInput?.focus();
      setLog(
        references.total === 0
          ? "MiniMax H3 多参考模式至少需要 1 个参考图片、视频或音频。"
          : "参考素材数量超出限制：最多 9 张图片、3 段视频、3 条音频，并且不能包含未知格式。",
      );
      return false;
    }
  }
  if (step.id === "draft" && videoUnrestrictedToggle?.checked && !adultContentAck?.checked) {
    adultContentAck?.focus();
    setLog("开启成人内容模式前，请先确认所有人物均为明确成年且自愿，并且你拥有素材与肖像授权。");
    return false;
  }
  syncSelectedModel({ applyDefaults: false });
  updateVideoSource();
  syncAdvancedInput();
  if (workflowPreflightTimer) {
    clearTimeout(workflowPreflightTimer);
    workflowPreflightTimer = null;
  }
  // Snapshot before the first await: changing a model during preflight must not
  // submit a different graph, and repeated clicks must not create duplicate jobs.
  const params = workflowParams();
  if (keyframeFile) params.set("has_image", "1");
  const payload = new FormData(form);
  if (keyframeFile) {
    payload.set("image", keyframeFile, keyframeFile.name);
  }
  if (step.id === "edit") {
    payload.delete("clips");
    stitchFiles.forEach((file) => payload.append("clips", file, file.name));
  }
  payload.set("unrestricted", step.id === "draft" && videoUnrestrictedToggle?.checked ? "true" : "false");
  payload.set("adult_content_ack", adultContentAck?.checked ? "true" : "false");
  payload.set("video_auto_inject_trigger", videoAutoInjectTrigger?.checked ? "true" : "false");
  payload.set("video_auto_strip_negative", videoAutoStripNegative?.checked ? "true" : "false");
  payload.set("temporal_stability", videoTemporalStability?.checked ? "true" : "false");
  payload.set("video_custom_trigger", videoCustomTrigger?.value || "");
  payload.set("video_motion", videoMotionPreset?.value || "medium");
  payload.set("social_target", socialPlatformSelect?.value || "tiktok");
  payload.set("social_quality", socialQualityInput?.value || "balanced");
  if (videoMotionLoraPack?.value) payload.set("video_motion_lora_pack", videoMotionLoraPack.value);
  else payload.delete("video_motion_lora_pack");
  const characterId = selectedVideoCharacterId();
  if (characterId) payload.set("character_id", characterId);
  else payload.delete("character_id");
  if (step.id !== "draft") {
    params.set("unrestricted", "0");
    ["image", "source_image_filename", "end_image", "reference_media", "h3_control_video", "h3_source_video", "h3_mask"].forEach((key) => payload.delete(key));
  } else {
    ["video", "clips", "source_video_filename", "source_video_subfolder", "source_video_type"].forEach((key) => payload.delete(key));
    const caps = optionCapabilities(selectedModelOption("draft"));
    if (!caps.image_to_video) { payload.delete("image"); payload.delete("source_image_filename"); }
  }
  const context = captureSubmissionContext(step.id, payload);
  videoSubmitting = true;
  primaryButton.disabled = true;
  continueButton.classList.add("hidden");
  repeatButton.classList.add("hidden");
  jobStatus.textContent = "提交中";
  resultView.innerHTML = "<p>任务已提交，等待 ComfyUI 接收。</p>";
  setProgress("queued");
  if (!activeVideoJobIds.size) setLog("");
  else appendLog("正在追加一个新视频任务；已有任务会继续运行。 ");

  try {
    const workflowReady = await preflightWorkflow({ quiet: false, params, step, independent: true });
    if (!workflowReady) throw new Error("工作流预检未通过，未提交任务。");
    if (step.id !== currentStep().id || payload.get("model_profile") !== modelProfileInput.value) {
      throw new Error("预检期间已切换步骤或模型，请确认当前设置后重新提交。");
    }
    const response = await fetch("/api/generate", {
      method: "POST",
      body: payload,
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(formatError(data.detail || data));
    }

    activeJobId = data.id;
    submissionContexts.set(data.id, WorkbenchState.begin(workflowState, data.id, context));
    syncWorkflowOutputs();
    persistWorkflowState();
    if (projectTagInput) rememberProjectTag(projectTagInput.value);
    rememberActiveJob(activeJobId, step.id, data);
    setJobMeta(data);
    if (data.completed || data.status === "success") {
      handleJobUpdate(data, step.id, { focus: true });
      return true;
    }
    jobStatus.textContent = "排队中";
    appendLog(data.local ? "本地处理已进入后台队列。" : `已进入队列：${data.prompt_id || "已提交"}`);
    watchJob(activeJobId, step.id);
    return true;
  } catch (error) {
    jobStatus.textContent = "失败";
    setProgress("failed");
    appendLog(error.message);
    repeatButton.classList.remove("hidden");
    return false;
  } finally {
    videoSubmitting = false;
    primaryButton.disabled = false;
  }
}

function formatError(detail) {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") {
    if (Array.isArray(detail.errors) || Array.isArray(detail.actions)) {
      const title = detail.message || "请求失败";
      const errors = Array.isArray(detail.errors) ? detail.errors : [];
      const actions = Array.isArray(detail.actions)
        ? ["下一步：", ...detail.actions.map((item, index) => `${index + 1}. ${item}`)]
        : [];
      return [title, ...errors, ...actions].filter(Boolean).join("\n");
    }
    if (detail.message) return detail.message;
  }
  return JSON.stringify(detail, null, 2);
}

async function copyDiagnostics() {
  if (!copyDiagnosticsButton) return;
  copyDiagnosticsButton.disabled = true;
  try {
    const response = await fetch("/api/diagnostics");
    const data = await response.json();
    if (!response.ok) throw new Error(formatError(data.detail || data));
    const text = JSON.stringify(data, null, 2);
    if (navigator.clipboard?.writeText) {
      try {
        await navigator.clipboard.writeText(text);
        appendLog("诊断信息已复制到剪贴板。");
      } catch (clipboardError) {
        setLog(text);
        appendLog(`浏览器阻止剪贴板写入，诊断信息已显示在日志框：${clipboardError.message}`);
      }
    } else {
      setLog(text);
      appendLog("浏览器不允许写入剪贴板，诊断信息已显示在日志框。");
    }
  } catch (error) {
    appendLog(`复制诊断信息失败：${error.message}`);
  } finally {
    copyDiagnosticsButton.disabled = false;
  }
}

function diagnosticsFilename(data = {}) {
  const stamp = String(data.generated_at || new Date().toISOString())
    .replaceAll(":", "-")
    .replaceAll(" ", "_")
    .replaceAll("/", "-");
  return `local-ai-workbench-diagnostics-${stamp}.json`;
}

async function downloadDiagnostics() {
  if (!downloadDiagnosticsButton) return;
  downloadDiagnosticsButton.disabled = true;
  try {
    const response = await fetch("/api/diagnostics");
    const data = await response.json();
    if (!response.ok) throw new Error(formatError(data.detail || data));
    const text = JSON.stringify(data, null, 2);
    const blob = new Blob([text], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = diagnosticsFilename(data);
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    appendLog("诊断包已下载。");
  } catch (error) {
    appendLog(`下载诊断包失败：${error.message}`);
  } finally {
    downloadDiagnosticsButton.disabled = false;
  }
}

function terminalJobFailed(job) {
  return ["failed", "error", "lost", "stopped", "canceled", "cancelled", "interrupted"].includes(String(job.status || "").toLowerCase());
}

function videoJobIsTerminal(job) {
  return job?.status === "success" || Boolean(job?.completed) || terminalJobFailed(job);
}

function formatJobMessages(job) {
  const lines = [];
  if (job.error) lines.push(job.error);
  if (Array.isArray(job.friendly_messages) && job.friendly_messages.length) {
    lines.push(...job.friendly_messages);
  } else if (Array.isArray(job.messages) && job.messages.length) {
    lines.push(...job.messages.slice(-5).map((item) => (typeof item === "string" ? item : JSON.stringify(item))));
  }
  return lines.filter(Boolean).join("\n");
}

function jobStatusLabel(job) {
  const terminalLabels = { failed: "失败", error: "错误", canceled: "已取消", cancelled: "已取消", interrupted: "已中断", lost: "状态丢失" };
  if (terminalLabels[job.status]) return terminalLabels[job.status];
  if (job.status === "success") return "完成";
  if (job.status === "running") {
    const detail = videoProgressDetail(job.status, job.progress);
    return detail.accurate ? `运行中 ${Math.round(detail.percent)}%` : "运行中";
  }
  if (job.status === "queued") return "排队中";
  if (job.status === "reconnecting") return "连接恢复中";
  if (job.status === "canceling") return "正在中断";
  return job.status || "未知";
}

function isVideoFaceSwapJob(job) {
  return job?.mode === "video_face_swap" || videoJobSteps.get(job?.id) === "face_swap";
}

function videoTaskQueueMarkup(jobs, focusedJobId, emptyMessage) {
  if (!jobs.length) {
    return `<p>${escapeHtml(emptyMessage)}</p>`;
  }
  return jobs.map((job) => {
    const detail = videoProgressDetail(job.status, job.progress);
    const percentText = detail.accurate ? `${detail.percent.toFixed(detail.percent % 1 ? 1 : 0)}%` : "实时等待";
    return `<article class="video-task-row${job.id === focusedJobId ? " is-focused" : ""}" data-video-task-id="${escapeHtml(String(job.id))}">
      <div><strong>${escapeHtml(job.title || "视频任务")}</strong><small>${escapeHtml(jobStatusLabel(job))} · ${escapeHtml(detail.label)}</small></div>
      <div class="video-task-row-progress"><span style="width:${detail.percent}%"></span></div>
      <b>${escapeHtml(percentText)}</b>
      <div class="video-task-row-actions">
        <button class="ghost-button" type="button" data-video-task-view="${escapeHtml(String(job.id))}">查看</button>
        <button class="ghost-button danger" type="button" data-video-task-cancel="${escapeHtml(String(job.id))}" ${job.status === "canceling" ? "disabled" : ""}>中断</button>
      </div>
    </article>`;
  }).join("");
}

function renderVideoTaskQueue() {
  const jobs = [...activeVideoJobIds]
    .map((jobId) => videoJobCache.get(jobId) || {
      id: jobId,
      status: "queued",
      title: videoJobSteps.get(jobId) === "face_swap" ? "ReActor · 视频换脸" : "视频任务",
    })
    .sort((left, right) => Number(right.created_at || 0) - Number(left.created_at || 0));
  const workflowJobs = jobs.filter((job) => !isVideoFaceSwapJob(job));
  if (videoTaskQueueCount) videoTaskQueueCount.textContent = `${workflowJobs.length} 个进行中`;
  if (videoTaskQueueList) {
    videoTaskQueueList.innerHTML = videoTaskQueueMarkup(workflowJobs, activeJobId, "没有正在进行的任务，可以继续提交新任务。");
  }

  const faceSwapJobs = jobs.filter(isVideoFaceSwapJob);
  if (videoFaceSwapQueueCount) videoFaceSwapQueueCount.textContent = `${faceSwapJobs.length} 个进行中`;
  if (videoFaceSwapQueueList) {
    videoFaceSwapQueueList.innerHTML = videoTaskQueueMarkup(faceSwapJobs, activeVideoFaceSwapJobId, "没有正在进行的换脸任务，可以继续添加视频。");
  }
}

function workflowStorageKey() {
  return `workbench.workflow.v2:${serviceConfig.mode === "client" ? cleanBaseUrl(serviceConfig.server_url) : "local"}`;
}

function persistWorkflowState() {
  try {
    localStorage.setItem(workflowStorageKey(), JSON.stringify({ state: workflowState,
      contexts: [...submissionContexts].slice(-100), models: selectedModels }));
  } catch (_) {}
}

function restoreWorkflowState() {
  try {
    const saved = JSON.parse(localStorage.getItem(workflowStorageKey()) || "null");
    if (!saved || !saved.state || typeof saved.state.outputs !== "object" || !Array.isArray(saved.state.processed)) return;
    Object.assign(workflowState, saved.state);
    (saved.contexts || []).forEach(([id, context]) => submissionContexts.set(id, context));
    Object.assign(selectedModels, saved.models || {});
    syncWorkflowOutputs();
  } catch (_) {}
}

function syncWorkflowOutputs() {
  lastDraftVideo = workflowState.outputs.draft || null;
  lastFinalVideo = lastDraftVideo;
  lastDeflickerVideo = workflowState.outputs.deflicker || null;
  lastRifeVideo = workflowState.outputs.rife || null;
  lastUpscaleVideo = workflowState.outputs.upscale || null;
  lastStitchedVideo = workflowState.outputs.edit || null;
  for (const step of WorkbenchState.order) {
    if (workflowState.outputs[step]) completedSteps.add(step);
    else completedSteps.delete(step);
  }
  updateStepper();
  updateVideoSource();
}

function captureSubmissionContext(stepId, payload) {
  const file = stepId !== "draft" && videoInput?.files?.[0];
  const source = file ? { filename: file.name, ...currentVideoResolution, fps: Number(payload.get("fps")) }
    : WorkbenchState.sourceFor(workflowState, stepId);
  const pipeline = PIPELINE_TOGGLES.filter(([, input]) => stepId === "draft" && input?.checked).map(([id]) => {
    const option = selectedModelOption(id);
    const saved = stepParameters.get(id);
    return { stepId: id, mode: option.mode, model_profile: option.id,
      model_label: option.model_label || option.label, upscale_model: option.upscale_model || "RealESRGAN_x2plus.pth",
      upscale_scale: option.scale || 2, rife_multiplier: option.rife_multiplier || 2,
      advanced: JSON.stringify(saved?.model === option.id ? Object.fromEntries(saved.advanced) : {}),
      project: payload.get("project") || "", temporal_stability: payload.get("temporal_stability") || "true",
      ...(id === "deflicker" ? { flicker_preset: videoTuneFlickerPreset.value,
        brightness: videoTuneBrightness.value, contrast: videoTuneContrast.value,
        saturation: videoTuneSaturation.value, sharpness: videoTuneSharpness.value } : {}) };
  }).filter((item) => WorkbenchState.order.indexOf(item.stepId) > WorkbenchState.order.indexOf(stepId));
  return { stepId, source, newSource: Boolean(file), pipeline, expectedRevision: workflowState.revision,
    uploadToken: file ? `${file.name}/${file.size}/${file.lastModified}` : "",
    width: Number(payload.get("width")), height: Number(payload.get("height")), fps: Number(payload.get("fps")),
    scale: Number(payload.get("upscale_scale")), multiplier: Number(payload.get("rife_multiplier")) };
}

async function continueCapturedPipeline(job, context) {
  if (!context?.pipeline?.length) return;
  const [next, ...remaining] = context.pipeline;
  const source = workflowState.outputs[context.stepId];
  if (!source || source.jobId !== job.id) return;
  const payload = new FormData();
  Object.entries(next).filter(([key]) => key !== "stepId").forEach(([key, value]) => payload.set(key, String(value)));
  Object.entries({ source_video_filename: source.filename, source_video_subfolder: source.subfolder || "",
    source_video_type: source.type || "output", width: source.width || 1280, height: source.height || 720,
    fps: source.fps || 24, seed: -1 }).forEach(([key, value]) => payload.set(key, String(value)));
  try {
    const params = new URLSearchParams([...payload]);
    if (!await preflightWorkflow({ params, step: steps.find((step) => step.id === next.stepId), independent: true, quiet: false })) {
      throw new Error("后期依赖未就绪");
    }
    if (context.revision !== workflowState.revision || workflowState.outputs[context.stepId]?.jobId !== job.id) {
      throw new Error("当前镜头已更换");
    }
    const endpoint = next.stepId === "deflicker" ? "/api/video/tune" : "/api/generate";
    const response = await fetch(endpoint, { method: "POST", body: payload });
    const child = await response.json();
    if (!response.ok) throw new Error(formatError(child.detail || child));
    const childContext = { stepId: next.stepId, source, pipeline: remaining, expectedRevision: context.revision,
      fps: source.fps, width: source.width, height: source.height,
      scale: next.upscale_scale, multiplier: next.rife_multiplier };
    submissionContexts.set(child.id, WorkbenchState.begin(workflowState, child.id, childContext));
    persistWorkflowState();
    rememberActiveJob(child.id, next.stepId, child);
    appendLog(`按提交时的后期计划继续：${next.model_label}。`);
    if (activeView === "workflow" && currentStep().id === context.stepId) {
      if (videoInput) videoInput.value = "";
      setStep(next.stepId, { refresh: true, focus: false });
    }
    watchJob(child.id, next.stepId);
  } catch (error) {
    appendLog(`自动后期已停止：${error.message}。原视频已保留，可在作品中选择后重试。`);
  }
}

function applyCompletedVideoJob(job, stepId) {
  const effectiveStep = job.mode === "video_tune" || job.mode === "deflicker"
    ? "deflicker"
    : job.mode === "video_face_swap"
      ? "face_swap"
      : (stepId === "final" ? "draft" : stepId);
  const video = pickVideo(job.media);
  const context = submissionContexts.get(job.id);
  const accepted = WorkbenchState.complete(workflowState, job, context);
  if (accepted) {
    const uploaded = videoInput?.files?.[0];
    if (uploaded && context.uploadToken === `${uploaded.name}/${uploaded.size}/${uploaded.lastModified}`) videoInput.value = "";
    syncWorkflowOutputs();
    persistWorkflowState();
    void continueCapturedPipeline(job, context);
  }
  if (effectiveStep === "face_swap" && video) {
    lastFaceSwapVideo = video;
    renderVideoFaceSwapMedia(job.media || []);
  }
  if (video) updateVideoFaceSwapSourceSummary();
  updateStepper();
  updateTargetResolution();
  return { effectiveStep, accepted };
}

function updateVideoFaceSwapJobDisplay(job, terminal = videoJobIsTerminal(job)) {
  if (!isVideoFaceSwapJob(job)) return;
  if (!activeVideoFaceSwapJobId) activeVideoFaceSwapJobId = job.id;
  if (job.id !== activeVideoFaceSwapJobId) return;
  setVideoFaceSwapProgress(job.status, job.progress);
  if (job.media?.length) renderVideoFaceSwapMedia(job.media);
  if (videoFaceSwapCancelButton) {
    videoFaceSwapCancelButton.classList.toggle("hidden", terminal);
    videoFaceSwapCancelButton.disabled = job.status === "canceling";
    videoFaceSwapCancelButton.dataset.jobId = terminal ? "" : job.id;
  }
  const detail = videoProgressDetail(job.status, job.progress);
  if (job.status === "success") {
    setVideoFaceSwapStatus("换脸任务已完成，结果已写入本地输出目录。", "ok");
  } else if (terminal) {
    setVideoFaceSwapStatus(formatJobMessages(job) || `换脸任务未完成：${job.status || "失败"}`, "bad");
  } else {
    setVideoFaceSwapStatus(detail.label, ["running", "canceling"].includes(job.status) ? "running" : "pending");
  }
}

function handleJobUpdate(job, stepId = videoJobSteps.get(job?.id) || "draft", { focus = job?.id === activeJobId } = {}) {
  if (!job?.id) return false;
  const normalizedStep = stepId === "final" ? "draft" : (stepId || "draft");
  videoJobCache.set(job.id, job);
  videoJobSteps.set(job.id, normalizedStep);
  const terminal = videoJobIsTerminal(job);
  const faceSwapJob = isVideoFaceSwapJob(job);
  const workflowFocus = focus && !faceSwapJob && currentStep().id === normalizedStep;
  if (!terminal) activeVideoJobIds.add(job.id);
  if (faceSwapJob) updateVideoFaceSwapJobDisplay(job, terminal);

  if (workflowFocus) {
    setJobMeta(job);
    setProgress(job.status, job.progress);
    jobStatus.textContent = jobStatusLabel(job);
    if (job.media && job.media.length) renderMedia(job.media);
    if (videoCancelJobButton) {
      videoCancelJobButton.classList.toggle("hidden", terminal);
      videoCancelJobButton.disabled = job.status === "canceling";
      videoCancelJobButton.dataset.jobId = terminal ? "" : job.id;
    }
  }

  if (terminal) {
    const wasActiveFaceSwap = faceSwapJob && activeVideoFaceSwapJobId === job.id;
    forgetActiveJob(job.id);
    if (focus) closeJobEvents();
    if (wasActiveFaceSwap) {
      const nextFaceSwapJobId = [...activeVideoJobIds].find((jobId) => {
        const cached = videoJobCache.get(jobId);
        return cached?.mode === "video_face_swap" || videoJobSteps.get(jobId) === "face_swap";
      });
      if (nextFaceSwapJobId) {
        activeVideoFaceSwapJobId = nextFaceSwapJobId;
        const nextJob = videoJobCache.get(nextFaceSwapJobId);
        if (nextJob) updateVideoFaceSwapJobDisplay(nextJob, false);
      }
    }
  }

  if (job.status === "success") {
    const { effectiveStep, accepted } = applyCompletedVideoJob(job, normalizedStep);
    if (!processedVideoTerminalJobs.has(job.id)) {
      processedVideoTerminalJobs.add(job.id);
      appendLog(effectiveStep === "edit" ? `成片拼接完成。输出目录：${outputDirectoryText()}` : `${job.title || "视频任务"}完成。`);
      if (faceSwapJob) appendVideoFaceSwapLog(`${job.title || "视频换脸"}完成。`);
      loadRecentJobs(true);
      loadOutputs();
    }
    if (workflowFocus) {
      renderMedia(job.media || []);
      renderResultActions();
      repeatButton.classList.remove("hidden");
    }
    renderVideoTaskQueue();
    return true;
  }

  if (terminal) {
    if (!processedVideoTerminalJobs.has(job.id)) {
      processedVideoTerminalJobs.add(job.id);
      const detail = formatJobMessages(job);
      appendLog(detail ? `任务未完成：${job.status}\n${detail}` : `任务状态：${job.status}`);
      if (faceSwapJob) appendVideoFaceSwapLog(detail ? `任务未完成：${job.status} · ${detail}` : `任务状态：${job.status}`);
      loadRecentJobs(true);
    }
    if (workflowFocus) {
      repeatButton.classList.remove("hidden");
      setProgress(job.status || "failed", job.progress);
    }
    renderVideoTaskQueue();
    return true;
  }

  persistActiveVideoJobs();
  renderVideoTaskQueue();
  return false;
}

async function pollJob(jobId, stepId) {
  try {
    const response = await fetch(`/api/jobs/${jobId}`);
    const job = await response.json();
    if (!response.ok) throw new Error(formatError(job.detail || job));
    handleJobUpdate(job, stepId, { focus: jobId === activeJobId });
  } catch (error) {
    if (jobId === activeVideoFaceSwapJobId) {
      setVideoFaceSwapProgress("reconnecting");
      setVideoFaceSwapStatus("正在恢复视频换脸任务连接。", "pending");
    }
    if (jobId === activeJobId && videoJobSteps.get(jobId) !== "face_swap") {
      jobStatus.textContent = "连接恢复中";
      setProgress("reconnecting");
    }
  }
}

async function pollActiveVideoJobs() {
  if (videoPollInFlight || !activeVideoJobIds.size) return;
  videoPollInFlight = true;
  try {
    await Promise.all(
      [...activeVideoJobIds]
        .filter((jobId) => jobId !== sseHealthyJobId)
        .map((jobId) => pollJob(jobId, videoJobSteps.get(jobId) || "draft")),
    );
  } finally {
    videoPollInFlight = false;
  }
}

function startActiveVideoPolling() {
  if (!activeVideoJobIds.size || POLL_TIMERS.poll) return;
  void pollActiveVideoJobs();
  POLL_TIMERS.poll = window.setInterval(pollActiveVideoJobs, 1800);
}

function startJobPollingFallback(jobId, stepId) {
  if (jobId) {
    activeVideoJobIds.add(jobId);
    videoJobSteps.set(jobId, stepId === "final" ? "draft" : (stepId || "draft"));
  }
  startActiveVideoPolling();
  void pollJob(jobId, stepId);
}

function watchJob(jobId, stepId) {
  closeJobEvents();
  activeJobId = jobId;
  const normalizedStep = stepId === "final" ? "draft" : (stepId || "draft");
  activeVideoJobIds.add(jobId);
  videoJobSteps.set(jobId, normalizedStep);
  persistActiveVideoJobs();
  const cached = videoJobCache.get(jobId);
  if (cached) handleJobUpdate(cached, normalizedStep, { focus: true });
  if (cached && videoJobIsTerminal(cached)) return;
  startActiveVideoPolling();
  if (!window.EventSource) {
    startJobPollingFallback(jobId, normalizedStep);
    return;
  }
  const eventsUrl = new URL(
    apiUrl(`/api/jobs/${encodeURIComponent(jobId)}/events`),
    window.location.origin,
  );
  if (serviceConfig?.access_token) {
    eventsUrl.searchParams.set("token", serviceConfig.access_token);
  }
  const source = new EventSource(eventsUrl.toString());
  activeJobEvents = source;
  source.onopen = () => {
    if (activeJobEvents === source) sseHealthyJobId = jobId;
  };
  source.onmessage = (event) => {
    if (activeJobEvents !== source) return;
    try {
      handleJobUpdate(JSON.parse(event.data), normalizedStep, { focus: true });
    } catch (error) {
      appendLog(`任务状态解析失败：${error.message}`);
    }
  };
  source.onerror = () => {
    if (sseHealthyJobId === jobId) sseHealthyJobId = null;
    if (activeJobEvents !== source) return;
    source.close();
    activeJobEvents = null;
    appendLog("实时状态连接已断开，已切换到兼容轮询。 ");
    startJobPollingFallback(jobId, normalizedStep);
  };
  void pollJob(jobId, normalizedStep);
  renderVideoTaskQueue();
}

async function cancelVideoJob(jobId) {
  if (!jobId) return;
  const cached = videoJobCache.get(jobId);
  if (cached) {
    cached.status = "canceling";
    cached.completed = false;
    cached.progress = { ...(cached.progress || {}), label: "正在中断任务", accurate: false };
    handleJobUpdate(cached, videoJobSteps.get(jobId) || "draft", { focus: jobId === activeJobId });
  }
  try {
    const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, { method: "POST" });
    const data = await response.json();
    if (!response.ok) throw new Error(formatError(data.detail || data));
    handleJobUpdate(data, videoJobSteps.get(jobId) || "draft", { focus: jobId === activeJobId });
  } catch (error) {
    appendLog(`中断任务失败：${error.message}`);
    if (videoJobSteps.get(jobId) === "face_swap" || videoJobCache.get(jobId)?.mode === "video_face_swap") {
      appendVideoFaceSwapLog(`中断任务失败：${error.message}`);
      setVideoFaceSwapStatus(`中断任务失败：${error.message}`, "bad");
    }
    void pollJob(jobId, videoJobSteps.get(jobId) || "draft");
  }
}

async function resumeRememberedJob() {
  const storedJobs = readRememberedJobs();
  if (!storedJobs.length) {
    renderVideoTaskQueue();
    return;
  }
  storedJobs.forEach((item) => {
    activeVideoJobIds.add(item.jobId);
    videoJobSteps.set(item.jobId, item.stepId || "draft");
  });
  const storedFaceSwapJob = [...storedJobs].reverse().find((item) => item.stepId === "face_swap");
  if (storedFaceSwapJob) activeVideoFaceSwapJobId = storedFaceSwapJob.jobId;
  const stored = storedJobs[storedJobs.length - 1];
  const stepIndex = steps.findIndex((item) => item.id === stored.stepId);
  if (stepIndex >= 0) {
    setStep(stored.stepId, { refresh: false, focus: false });
  }
  activeJobId = stored.jobId;
  appendLog(`已恢复 ${storedJobs.length} 个未完成视频任务的状态跟踪。`);
  startActiveVideoPolling();
  watchJob(activeJobId, stored.stepId || currentStep().id);
}

function updateKeyframePreview() {
  const file = imageInput.files && imageInput.files[0];
  const linkedPreview = sourceImagePreviewUrl?.value || "";
  const linkedLabel = sourceImageLabel?.value || "文生图输出";
  if (!file && !linkedPreview) {
    keyframePreview.innerHTML = modelRequiresKeyframe()
      ? "<p>当前 I2V 模型需要首帧图片，上传后才能生成。</p>"
      : "<p>未上传关键帧，将使用文字生视频路线。</p>";
  } else if (file) {
    const url = URL.createObjectURL(file);
    keyframePreview.innerHTML = `<img src="${url}" alt="上传的关键帧预览" />`;
    const image = keyframePreview.querySelector("img");
    if (image) image.addEventListener("load", () => URL.revokeObjectURL(url), { once: true });
  } else {
    keyframePreview.innerHTML = `<img src="${escapeHtml(mediaUrl(linkedPreview))}" alt="文生图关键帧预览" /><div class="keyframe-origin"><strong>来自文生图</strong><span>${escapeHtml(linkedLabel)}</span><button class="ghost-button" type="button" data-clear-linked-keyframe>移除</button></div>`;
  }
  updateSocialSafeZone();
  updateStepCopy();
  if (currentStep().id === "draft") {
    syncSelectedModel();
  } else if (!activeVideoJobIds.size) {
    renderStepIdle();
    scheduleWorkflowPreflight();
  }
}

function alignVideoSizeToKeyframe(previewUrl) {
  if (!previewUrl) return;
  const probe = new Image();
  probe.onload = () => {
    if (!probe.naturalWidth || !probe.naturalHeight) return;
    const defaults = selectedModelOption("draft")?.defaults || {};
    const baseWidth = Number(defaults.width || 832);
    const baseHeight = Number(defaults.height || 480);
    const area = Math.max(256 * 256, baseWidth * baseHeight);
    const ratio = Math.max(0.4, Math.min(2.5, probe.naturalWidth / probe.naturalHeight));
    const align = (value) => Math.max(256, Math.min(1536, Math.round(value / 32) * 32));
    let width = align(Math.sqrt(area * ratio));
    let height = align(width / ratio);
    if (width >= 1536) height = align(width / ratio);
    if (height >= 1536) width = align(height * ratio);
    setSize(width, height);
    appendLog(`已按关键帧 ${probe.naturalWidth} × ${probe.naturalHeight} 的画幅匹配视频尺寸 ${width} × ${height}。`);
  };
  probe.src = mediaUrl(previewUrl);
}

function currentVideoSourceForTools() {
  const uploaded = videoInput?.files?.[0];
  if (uploaded) return { file: uploaded };
  updateVideoSource();
  if (sourceVideoFilename?.value) {
    return {
      filename: sourceVideoFilename.value,
      subfolder: sourceVideoSubfolder?.value || "",
      type: sourceVideoType?.value || "output",
    };
  }
  const generated = stitchSourceVideo();
  if (generated?.filename) return generated;
  return null;
}

function currentVideoFaceSwapFallbackSource() {
  return currentVideoSourceForTools() || (lastFaceSwapVideo?.filename ? lastFaceSwapVideo : null);
}

function videoSourceDisplayName(source) {
  if (source?.file?.name) return source.file.name;
  if (source?.filename) return [source.subfolder, source.filename].filter(Boolean).join("/");
  return "";
}

function updateVideoFaceSwapSourceSummary() {
  const files = Array.from(videoFaceSwapBatchInput?.files || []);
  if (files.length) {
    const names = files.slice(0, 3).map((file) => file.name).join("、");
    const suffix = files.length > 3 ? ` 等 ${files.length} 个文件` : "";
    if (videoFaceSwapBatchSummary) videoFaceSwapBatchSummary.textContent = `已选择 ${files.length} 个目标视频，将分别创建任务。`;
    if (videoFaceSwapFallbackSource) {
      videoFaceSwapFallbackSource.textContent = `${names}${suffix}`;
      videoFaceSwapFallbackSource.classList.add("available");
    }
    return;
  }
  const fallback = currentVideoFaceSwapFallbackSource();
  const label = videoSourceDisplayName(fallback);
  if (videoFaceSwapBatchSummary) {
    videoFaceSwapBatchSummary.textContent = fallback
      ? "未选择新文件，将沿用下方最近视频。"
      : "未选择时使用最近完成的视频；可一次选择多个视频。";
  }
  if (videoFaceSwapFallbackSource) {
    videoFaceSwapFallbackSource.textContent = label ? `最近视频：${label}` : "当前没有可自动沿用的视频。";
    videoFaceSwapFallbackSource.classList.toggle("available", Boolean(label));
  }
}

function setVideoFaceSwapStatus(message, state = "pending") {
  if (!videoFaceSwapStandaloneStatus) return;
  videoFaceSwapStandaloneStatus.textContent = message;
  videoFaceSwapStandaloneStatus.className = `video-face-module-status ${state}`;
}

function appendVideoFaceSwapLog(message) {
  if (!videoFaceSwapLog || !message) return;
  const time = new Date().toLocaleTimeString();
  videoFaceSwapLog.textContent = `${videoFaceSwapLog.textContent}${videoFaceSwapLog.textContent ? "\n" : ""}[${time}] ${message}`;
  videoFaceSwapLog.scrollTop = videoFaceSwapLog.scrollHeight;
}

function syncVideoFaceSwapWeight(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return;
  const normalized = Math.max(0, Math.min(1, numeric));
  if (videoFaceSwapWeightRange) videoFaceSwapWeightRange.value = String(normalized);
  if (videoFaceSwapWeight) videoFaceSwapWeight.value = String(normalized);
}

function updateVideoFaceSwapSubmitState() {
  if (!videoFaceSwapSubmitButton) return;
  videoFaceSwapSubmitButton.disabled = videoFaceSwapSubmitting || videoFaceSwapCapabilityReady !== true;
  videoFaceSwapSubmitButton.textContent = videoFaceSwapSubmitting ? "正在加入队列" : "加入换脸队列";
}

async function refreshVideoFaceSwapCapability() {
  if (videoFaceSwapCapabilityLoading) return;
  videoFaceSwapCapabilityLoading = true;
  if (videoFaceSwapModuleBadge) {
    videoFaceSwapModuleBadge.textContent = "检查中";
    videoFaceSwapModuleBadge.classList.remove("ok", "bad");
  }
  setVideoFaceSwapStatus("正在检查 ReActor 节点与换脸模型。", "pending");
  try {
    const response = await fetch("/api/nsfw-extensions/capabilities");
    const data = await response.json();
    if (!response.ok) throw new Error(formatError(data.detail || data));
    const capability = data.capabilities?.video_face_swap || {};
    videoFaceSwapCapabilityReady = Boolean(data.connected && capability.ready);
    if (videoFaceSwapModuleBadge) {
      videoFaceSwapModuleBadge.textContent = videoFaceSwapCapabilityReady ? "组件已就绪" : "组件待准备";
      videoFaceSwapModuleBadge.classList.toggle("ok", videoFaceSwapCapabilityReady);
      videoFaceSwapModuleBadge.classList.toggle("bad", !data.connected);
    }
    if (videoFaceSwapInstallButton) {
      videoFaceSwapInstallButton.disabled = videoFaceSwapCapabilityReady;
      videoFaceSwapInstallButton.textContent = videoFaceSwapCapabilityReady ? "换脸组件已就绪" : "一键准备换脸组件";
      videoFaceSwapInstallButton.dataset.profile = capability.install_profile || "face-swap-reactor";
    }
    if (videoFaceSwapCapabilityReady) {
      setVideoFaceSwapStatus(capability.note || "ReActor 与换脸模型已加载，可以提交任务。", "ok");
    } else {
      const message = data.connected
        ? `${capability.note || "ReActor 或换脸模型尚未就绪。"} 可点击一键准备，完成后重启 ComfyUI。`
        : `ComfyUI 未连接，暂时无法检查换脸组件。${data.error ? ` ${data.error}` : ""}`;
      setVideoFaceSwapStatus(message, data.connected ? "pending" : "bad");
    }
  } catch (error) {
    videoFaceSwapCapabilityReady = false;
    if (videoFaceSwapModuleBadge) {
      videoFaceSwapModuleBadge.textContent = "检查失败";
      videoFaceSwapModuleBadge.classList.add("bad");
    }
    if (videoFaceSwapInstallButton) videoFaceSwapInstallButton.disabled = false;
    setVideoFaceSwapStatus(`换脸能力检查失败：${error.message}`, "bad");
  } finally {
    videoFaceSwapCapabilityLoading = false;
    updateVideoFaceSwapSubmitState();
  }
}

function renderExtractedFramePreview(frame = {}) {
  if (!videoExtractPreview) return;
  if (!frame.preview_url) {
    videoExtractPreview.classList.add("hidden");
    videoExtractPreview.innerHTML = "<p>抽帧结果会显示在这里。</p>";
    videoExtractFrameToImageButton?.classList.add("hidden");
    return;
  }
  videoExtractPreview.classList.remove("hidden");
  videoExtractPreview.innerHTML = `<img src="${escapeHtml(frame.preview_url)}" alt="视频抽帧预览" /><p>${escapeHtml(frame.message || "抽帧完成")}</p>`;
  videoExtractFrameToImageButton?.classList.remove("hidden");
}

async function extractFrameFromCurrentVideo() {
  if (!videoExtractFrameButton) return;
  const source = currentVideoSourceForTools();
  if (!source) {
    setLog("请先完成视频步骤、绑定 source_video，或上传待处理视频。");
    return;
  }
  videoExtractFrameButton.disabled = true;
  try {
    const payload = new FormData();
    payload.append("position", "0.5");
    if (source.file) payload.append("video", source.file, source.file.name);
    else {
      payload.append("source_video_filename", source.filename || "");
      payload.append("source_video_subfolder", source.subfolder || "");
      payload.append("source_video_type", source.type || "output");
    }
    const response = await fetch("/api/video/extract-frame", { method: "POST", body: payload });
    const data = await response.json();
    if (!response.ok) throw new Error(formatError(data.detail || data));
    lastExtractedVideoFrame = data;
    imageInput.value = "";
    sourceImageFilename.value = data.input_name || "";
    sourceImagePreviewUrl.value = data.preview_url || "";
    sourceImageLabel.value = "视频抽帧";
    updateKeyframePreview();
    renderExtractedFramePreview(data);
    appendLog(data.message || "已从视频抽帧并设为关键帧。");
  } catch (error) {
    appendLog(`抽帧失败：${error.message}`);
  } finally {
    videoExtractFrameButton.disabled = false;
  }
}

function appendVideoSource(payload, source) {
  if (source?.file) payload.append("video", source.file, source.file.name);
  else {
    payload.append("source_video_filename", source?.filename || "");
    payload.append("source_video_subfolder", source?.subfolder || "");
    payload.append("source_video_type", source?.type || "output");
  }
}

function acceptSubmittedVideoJob(data, stepId) {
  activeJobId = data.id;
  rememberActiveJob(activeJobId, stepId, data);
  if (stepId === "face_swap" || data.mode === "video_face_swap") {
    activeVideoFaceSwapJobId = data.id;
    setVideoFaceSwapProgress(data.status || "queued", data.progress);
    setVideoFaceSwapStatus("任务已加入视频换脸队列。", "pending");
  } else {
    setJobMeta(data);
    jobStatus.textContent = "排队中";
    setProgress(data.status || "queued", data.progress);
  }
  watchJob(activeJobId, stepId);
}

async function submitVideoTune() {
  if (!videoTuneSubmitButton || videoSubmitting) return;
  const source = currentVideoSourceForTools();
  if (!source) {
    setLog("请先生成一个视频，或在视频工具中上传待微调视频。 ");
    return;
  }
  videoTuneSubmitButton.disabled = true;
  videoSubmitting = true;
  primaryButton.disabled = true;
  try {
    const payload = new FormData();
    appendVideoSource(payload, source);
    payload.append("flicker_preset", videoTuneFlickerPreset?.value || "balanced");
    payload.append("brightness", videoTuneBrightness?.value || "0");
    payload.append("contrast", videoTuneContrast?.value || "1");
    payload.append("saturation", videoTuneSaturation?.value || "1");
    payload.append("sharpness", videoTuneSharpness?.value || "0");
    const context = captureSubmissionContext("deflicker", payload);
    context.source = source.file ? { filename: source.file.name, ...currentVideoResolution, fps: currentVideoFps }
      : { ...source, ...currentVideoResolution, fps: currentVideoFps };
    const response = await fetch("/api/video/tune", { method: "POST", body: payload });
    const data = await response.json();
    if (!response.ok) throw new Error(formatError(data.detail || data));
    submissionContexts.set(data.id, WorkbenchState.begin(workflowState, data.id, context));
    syncWorkflowOutputs(); persistWorkflowState();
    acceptSubmittedVideoJob(data, "deflicker");
    appendLog("视频微调已加入队列；ffmpeg 会按实际处理时间更新进度。 ");
  } catch (error) {
    appendLog(`视频微调提交失败：${error.message}`);
  } finally {
    videoTuneSubmitButton.disabled = false;
    videoSubmitting = false;
    primaryButton.disabled = false;
  }
}

async function submitVideoFaceSwap() {
  if (!videoFaceSwapSubmitButton) return;
  if (videoFaceSwapCapabilityReady !== true) {
    setVideoFaceSwapStatus("换脸组件尚未就绪，请先点击“一键准备换脸组件”。", "bad");
    return;
  }
  const batchSources = Array.from(videoFaceSwapBatchInput?.files || []).map((file) => ({ file }));
  const currentSource = currentVideoFaceSwapFallbackSource();
  const sources = batchSources.length ? batchSources : currentSource ? [currentSource] : [];
  if (!sources.length) {
    setVideoFaceSwapStatus("请先选择一个或多个待换脸视频。", "bad");
    appendVideoFaceSwapLog("没有可提交的目标视频。");
    return;
  }
  const characterId = selectedVideoCharacterId();
  const character = (videoCharacterBox().items || []).find((item) => item.id === characterId);
  const identityFile = videoFaceSwapIdentityFile?.files?.[0] || null;
  if (!character?.identity_filename && !identityFile) {
    setVideoFaceSwapStatus("请选择角色盒身份或上传身份参考图。", "bad");
    return;
  }
  if (!window.confirm(`请确认已取得相关人员的明确授权。将提交 ${sources.length} 个视频换脸任务，是否继续？`)) return;
  videoFaceSwapSubmitting = true;
  updateVideoFaceSwapSubmitState();
  setVideoFaceSwapStatus(`正在提交 ${sources.length} 个视频换脸任务。`, "running");
  let submitted = 0;
  const errors = [];
  try {
    for (let index = 0; index < sources.length; index += 1) {
      const payload = new FormData();
      payload.append("authorization_confirmed", "true");
      const authToken = localStorage.getItem(FACE_AUTH_STORAGE_KEY) || localStorage.getItem("wan22.face.authToken") || "";
      if (authToken) payload.append("face_authorization_token", authToken);
      payload.append("faceswap_weight", videoFaceSwapWeight?.value || "0.85");
      payload.append("fps", videoFaceSwapFps?.value || "24");
      appendVideoSource(payload, sources[index]);
      if (identityFile) payload.append("identity_image", identityFile, identityFile.name);
      else if (character?.identity_filename) {
        payload.append("identity_image_filename", character.identity_filename);
        payload.append("identity_image_subfolder", character.identity_subfolder || "");
        payload.append("identity_image_type", character.identity_type || "input");
      }
      try {
        const response = await fetch("/api/video/face-swap", { method: "POST", body: payload });
        const data = await response.json();
        if (!response.ok) throw new Error(formatError(data.detail || data));
        if (data.face_authorization_token) localStorage.setItem(FACE_AUTH_STORAGE_KEY, data.face_authorization_token);
        submitted += 1;
        acceptSubmittedVideoJob(data, "face_swap");
        appendLog(`视频换脸 ${index + 1}/${sources.length} 已加入队列。`);
        appendVideoFaceSwapLog(`${videoSourceDisplayName(sources[index]) || `视频 ${index + 1}`} 已加入队列。`);
      } catch (error) {
        errors.push(`${sources[index].file?.name || sources[index].filename || `第 ${index + 1} 个视频`}：${error.message}`);
      }
    }
    if (errors.length) {
      appendLog(`视频换脸有 ${errors.length} 项提交失败：\n${errors.join("\n")}`);
      appendVideoFaceSwapLog(`${errors.length} 项提交失败：\n${errors.join("\n")}`);
    }
    if (submitted) {
      appendLog(`共 ${submitted} 个视频换脸任务正在并行排队。`);
      setVideoFaceSwapStatus(`已提交 ${submitted} 个任务${errors.length ? `，${errors.length} 个失败` : ""}。`, errors.length ? "pending" : "running");
    } else if (errors.length) {
      setVideoFaceSwapStatus("视频换脸任务提交失败，请查看下方日志。", "bad");
    }
  } finally {
    videoFaceSwapSubmitting = false;
    updateVideoFaceSwapSubmitState();
  }
}

window.acceptImageStudioKeyframe = (handoff = {}, options = {}) => {
  const { focus = true, queueVideo = false } = options;
  const inputName = String(handoff.input_name || "").trim();
  if (!inputName || !sourceImageFilename) return false;
  imageInput.value = "";
  sourceImageFilename.value = inputName;
  sourceImagePreviewUrl.value = String(handoff.preview_url || "");
  sourceImageLabel.value = String(handoff.source_label || handoff.source_profile || handoff.source_filename || "文生图输出");
  const switched = switchTextModelsToImageVideo();
  const linkage = videoLinkage();
  const wizardId = String(handoff.wizard_id || rememberedAdultWizardId() || "").trim();
  const wizard = wizardId ? findAdultWizard(wizardId) : null;
  if (wizardId) rememberAdultWizardId(wizardId);
  const sourcePrompt = String(handoff.source_prompt || "").trim();
  const useWizard = Boolean(wizard && wizard.pipeline !== "manual" && linkage.handoff_apply_video_scene !== false);
  if (handoff.character_id) setSelectedVideoCharacterId(String(handoff.character_id));
  if (!queueVideo) setView("workflow");
  setStep("draft", { refresh: false, focus: false });

  let nsfwSwitched = [];
  let importedPrompt = false;
  if (useWizard) {
    const i2vFallbacks = videoPlaybook().video_model_fallbacks?.i2v || ["minimax_h3_i2v", "ltx25_i2v"];
    const handoffWizard =
      wizard.pipeline === "t2v"
        ? { ...wizard, pipeline: "keyframe", preferred_video_models: i2vFallbacks, preferred_video_model: i2vFallbacks[0] }
        : wizard;
    const videoResult = applyAdultPlaybookVideo(handoffWizard, {
      imagePrompt: linkage.handoff_carry_prompt !== false ? sourcePrompt : "",
      replacePrompt: Boolean(linkage.handoff_carry_prompt !== false && sourcePrompt),
    });
    nsfwSwitched = videoResult.switched || [];
    importedPrompt = Boolean(videoResult.replacedPrompt);
  } else {
    nsfwSwitched = handoff.nsfw ? ensureUnrestrictedVideoModels({ preferI2v: true }) : [];
    if (nsfwSwitched.length) syncSelectedModel({ applyDefaults: true });
    importedPrompt = Boolean(
      linkage.handoff_carry_prompt !== false && sourcePrompt && (!promptInput.value.trim() || promptInput.value.trim() === defaultPrompt),
    );
    if (importedPrompt) {
      const motionNote = linkage.handoff_append_motion === false ? "" : "。镜头运动自然连贯，主体外观和构图保持稳定";
      promptInput.value = `${sourcePrompt}${motionNote}`;
      lastPushedImagePrompt = sourcePrompt;
    }
  }

  updateKeyframePreview();
  alignVideoSizeToKeyframe(sourceImagePreviewUrl.value);
  if (!queueVideo) setStep("keyframe", { refresh: false, focus });

  const option = selectedModelOption("draft") || selectedModelOption("keyframe");
  void syncCatalogSelectionForWorkflowOption(selectedModelOption("draft"));
  renderVideoUnrestricted(option);
  if (linkage.handoff_carry_unrestricted !== false && handoff.nsfw && videoUnrestrictedToggle && !videoUnrestrictedToggle.disabled) {
    videoUnrestrictedToggle.checked = true;
    if (handoff.nsfw_lora_strength != null) syncVideoUnrestrictedStrength(handoff.nsfw_lora_strength, { preflight: false });
    renderVideoUnrestricted(option);
  }
  renderVideoAdultRecipes();
  const modelNote = [...switched, ...nsfwSwitched];
  appendLog(
    `${handoff.message || "文生图输出已设为视频关键帧。"}${modelNote.length ? ` 已切换到图生视频路线：${modelNote.join("、")}。` : ""}${importedPrompt ? " 已把图片描述转换为视频 Prompt，并套上当前玩法动作。" : " 已保留现有视频 Prompt。"}${handoff.nsfw ? " 已同步无限制模式参数。" : ""}${wizard?.label ? ` 已套用玩法「${wizard.label}」。` : ""}`,
  );
  return true;
};

window.queueVideoFromKeyframe = async () => {
  if (!hasKeyframeUpload()) {
    throw new Error("还没有视频关键帧。");
  }
  if (!promptInput.value.trim()) {
    throw new Error("视频提示词为空，无法自动排队图生视频。");
  }
  if (videoSubmitting) {
    throw new Error("视频工作流正在提交，请稍后再点「送入并生成视频」。");
  }
  completedSteps.add("keyframe");
  if (currentStep().id !== "draft") {
    setStep("draft", { refresh: false, focus: false });
  }
  const submitted = await submitJob();
  if (!submitted) {
    throw new Error("图生视频没有提交成功，请到视频工作流查看原因后手动生成。");
  }
  setView("workflow");
};

function updateUploadedVideoMetadata() {
  const file = videoInput.files && videoInput.files[0];
  if (!file) {
    updateTargetResolution();
    return;
  }
  const url = URL.createObjectURL(file);
  const video = document.createElement("video");
  video.preload = "metadata";
  video.onloadedmetadata = () => {
    if (videoInput.files?.[0] !== file) { URL.revokeObjectURL(url); return; }
    if (video.videoWidth && video.videoHeight) {
      currentVideoResolution = { width: video.videoWidth, height: video.videoHeight };
      updateTargetResolution();
      appendLog(`已读取上传视频尺寸：${video.videoWidth} x ${video.videoHeight}。`);
    }
    URL.revokeObjectURL(url);
  };
  video.onerror = () => {
    URL.revokeObjectURL(url);
    updateTargetResolution();
  };
  video.src = url;
}

document.querySelectorAll(".step-button").forEach((button) => {
  button.addEventListener("click", () => requestStepChange(button.dataset.step));
});

document.querySelectorAll(".view-tab").forEach((button) => {
  button.addEventListener("click", () => navigateWorkspace(button.dataset.view));
});

document.querySelector("#parameterLevel").addEventListener("click", (event) => {
  const level = event.target.closest("button[data-level]")?.dataset.level;
  if (!["basic", "full"].includes(level)) return;
  parameterLevel = level;
  syncJourneyNavigation();
});
document.querySelector("#resultActions").addEventListener("click", (event) => {
  const operation = event.target.closest("button[data-result-step]")?.dataset.resultStep;
  if (operation) useVideoForOperation(workflowState.outputs[currentStep().id], operation);
});
document.querySelector("#generateForm").addEventListener("input", () => {
  window.clearTimeout(creationDraftTimer);
  creationDraftTimer = window.setTimeout(persistCreationDraft, 350);
});
document.querySelector("#generateForm").addEventListener("change", () => {
  window.clearTimeout(creationDraftTimer);
  creationDraftTimer = window.setTimeout(persistCreationDraft, 0);
});

const openEnvironmentTabButton = document.getElementById("openEnvironmentTabButton");
if (openEnvironmentTabButton) {
  openEnvironmentTabButton.addEventListener("click", () => setView("environment"));
}
enterWorkflowButton?.addEventListener("click", () => {
  setView("workflow");
  setStep("keyframe", { refresh: false, focus: true });
});

document.querySelector("#sizePreset")?.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-width][data-height]");
  if (button) setSize(button.dataset.width, button.dataset.height);
});

document.querySelector("#durationPreset")?.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-length]");
  if (button) setLength(button.dataset.length);
});

form.addEventListener("submit", (event) => event.preventDefault());
primaryButton.addEventListener("click", handlePrimary);
validateButton.addEventListener("click", validateSetup);
detectEnvironmentButton.addEventListener("click", () => loadEnvironment({ refresh: true }));
runFullSetupButton?.addEventListener("click", startFullSetup);
runSelfTestButton?.addEventListener("click", startSelfTest);
runVideoSmokeButton?.addEventListener("click", startVideoSmokeTest);
installMissingButton.addEventListener("click", startInstall);
openSourceConfigButton?.addEventListener("click", openSourceConfig);
openSourceConfigInlineButton?.addEventListener("click", openSourceConfig);
closeSourceConfigButton?.addEventListener("click", closeSourceConfig);
sourceConfigBackdrop?.addEventListener("click", closeSourceConfig);
saveDownloadSettingsButton?.addEventListener("click", saveDownloadSettings);
testDownloadSourcesButton?.addEventListener("click", testDownloadSources);
downloadRegionOptions?.querySelectorAll('input[name="downloadRegion"]').forEach((input) => {
  input.addEventListener("change", () => {
    downloadSettingsDirty = true;
    applyDownloadRegionPreset(input.value);
  });
});
hfEndpointInput?.addEventListener("input", () => {
  downloadSettingsDirty = true;
  setDownloadRegion("custom");
});
pipIndexInput?.addEventListener("input", () => {
  downloadSettingsDirty = true;
  setDownloadRegion("custom");
});
proxyUrlInput?.addEventListener("input", () => {
  downloadSettingsDirty = true;
});
modelCatalogFamilyFilter?.addEventListener("change", renderModelCatalog);
modelCatalogQuantFilter?.addEventListener("change", renderModelCatalog);
modelCatalogReadyFilter?.addEventListener("change", renderModelCatalog);
let modelCatalogSearchTimer = null;
modelCatalogSearch?.addEventListener("input", () => {
  if (modelCatalogSearchTimer) clearTimeout(modelCatalogSearchTimer);
  modelCatalogSearchTimer = window.setTimeout(renderModelCatalog, 160);
});
modelCatalogSelector?.addEventListener("change", () => saveCatalogSelection());
if (modelCatalogNativeOnly) {
  try {
    const savedNativeOnly = localStorage.getItem("workbench.catalog_native_only");
    if (savedNativeOnly != null) modelCatalogNativeOnly.checked = savedNativeOnly !== "0";
  } catch (_) {
    /* ignore */
  }
  modelCatalogNativeOnly.addEventListener("change", () => {
    try {
      localStorage.setItem("workbench.catalog_native_only", modelCatalogNativeOnly.checked ? "1" : "0");
    } catch (_) {
      /* ignore */
    }
    renderModelCatalog();
  });
}

function handleCatalogInstallAction(event) {
  const button = event.target.closest("[data-catalog-install]");
  if (!button) return false;
  const profile = button.dataset.installProfile || "";
  const label = button.dataset.installLabel || "当前模型";
  const modelId = button.dataset.modelId || "";
  void launchOneClickInstall(profile, label, { modelId, trigger: button });
  return true;
}

modelCatalog?.addEventListener("click", (event) => {
  const go = event.target.closest("[data-catalog-go-generate]");
  if (go) {
    void goGenerateFromCatalog(go.dataset.modelId || "");
    return;
  }
  const userDownload = event.target.closest("[data-user-download]");
  if (userDownload) {
    void downloadUserImportedModel(userDownload.dataset.userDownload || "", userDownload);
    return;
  }
  const userRemove = event.target.closest("[data-user-remove]");
  if (userRemove) {
    void removeUserImportedModel(userRemove.dataset.userRemove || "");
    return;
  }
  if (handleCatalogInstallAction(event)) return;
  if (event.target.closest("[data-retry-model-catalog]")) {
    loadModelCatalog();
    return;
  }
  if (event.target.closest("a, button")) return;
  const row = event.target.closest("[data-catalog-id]");
  if (row?.dataset.catalogId) void saveCatalogSelection(row.dataset.catalogId);
});
modelSyncPanel?.addEventListener("click", (event) => {
  const go = event.target.closest("[data-catalog-go-generate]");
  if (go) {
    void goGenerateFromCatalog(go.dataset.modelId || "");
    return;
  }
  handleCatalogInstallAction(event);
});

// ---- 在线搜索新模型（Hugging Face / Civitai）并入库 ----
const onlineSearchInput = document.querySelector("#onlineSearchInput");
const onlineSearchButton = document.querySelector("#onlineSearchButton");
const onlineSearchStatus = document.querySelector("#onlineSearchStatus");
const onlineSearchResults = document.querySelector("#onlineSearchResults");
const onlineSearchSource = document.querySelector("#onlineSearchSource");
let onlineSearchSourceValue = "hf";
let onlineSearchData = [];

const USER_IMPORT_SUBDIRS = [
  ["checkpoints", "Checkpoint 大模型"],
  ["diffusion_models", "Diffusion / UNet 权重"],
  ["loras", "LoRA"],
  ["vae", "VAE"],
  ["text_encoders", "文本编码器"],
  ["clip", "CLIP"],
  ["clip_vision", "CLIP Vision"],
  ["controlnet", "ControlNet"],
  ["upscale_models", "超分模型"],
  ["embeddings", "Embedding"],
];

function guessImportSubdir(result) {
  const type = String(result.type || "").toLowerCase();
  if (type.includes("lora") || type.includes("locon") || type.includes("dora")) return "loras";
  if (type.includes("textualinversion") || type.includes("embedding")) return "embeddings";
  if (type.includes("vae")) return "vae";
  if (type.includes("controlnet")) return "controlnet";
  if (type.includes("upscaler") || type.includes("upscale")) return "upscale_models";
  if (type.includes("to-video") || type.includes("video")) return "diffusion_models";
  return "checkpoints";
}

function setOnlineSearchStatus(text, tone = "") {
  if (!onlineSearchStatus) return;
  onlineSearchStatus.textContent = text || "";
  onlineSearchStatus.dataset.tone = tone;
}

function formatSearchSize(bytes) {
  const value = Number(bytes || 0);
  if (!value) return "大小未知";
  if (value >= 1024 ** 3) return `${(value / 1024 ** 3).toFixed(1)} GB`;
  return `${Math.max(1, Math.round(value / 1024 ** 2))} MB`;
}

function onlineFilesHtml(result, index) {
  const files = result.files || [];
  if (!files.length) {
    return `<p class="online-files-empty">${result.source === "hf" ? "展开时会自动拉取仓库权重文件列表。" : "该模型没有可下载的权重文件。"}</p>`;
  }
  const rows = files
    .map(
      (file, fileIndex) => `
        <label class="online-file-row">
          <input type="checkbox" data-file-index="${fileIndex}" ${fileIndex === 0 ? "checked" : ""} />
          <span>${escapeHtml(file.name)}</span>
          <small>${formatSearchSize(file.size_bytes)}</small>
        </label>`,
    )
    .join("");
  const subdirOptions = USER_IMPORT_SUBDIRS.map(
    ([value, label]) => `<option value="${value}"${value === guessImportSubdir(result) ? " selected" : ""}>${label} · models/${value}</option>`,
  ).join("");
  return `
    <div class="online-file-list">${rows}</div>
    <div class="online-import-row">
      <label><span>下载到</span><select data-import-subdir>${subdirOptions}</select></label>
      <button class="primary" type="button" data-import-download="${index}">导入并下载</button>
      <button class="secondary" type="button" data-import-only="${index}">仅入库</button>
    </div>`;
}

function renderOnlineSearchResults() {
  if (!onlineSearchResults) return;
  if (!onlineSearchData.length) {
    onlineSearchResults.innerHTML = "";
    return;
  }
  onlineSearchResults.innerHTML = onlineSearchData
    .map((result, index) => {
      const stats = [
        result.type ? escapeHtml(result.type) : "",
        result.downloads ? `${Number(result.downloads).toLocaleString()} 下载` : "",
        result.likes ? `${Number(result.likes).toLocaleString()} 赞` : "",
        result.updated ? `更新 ${escapeHtml(result.updated)}` : "",
        result.gated ? "需授权 gated" : "",
      ]
        .filter(Boolean)
        .join(" · ");
      return `
        <details class="online-result" data-search-index="${index}">
          <summary>
            <span class="online-result-name">${escapeHtml(result.name || result.id)}</span>
            <small>${escapeHtml(result.author || "")}${stats ? ` · ${stats}` : ""}</small>
          </summary>
          <div class="online-result-body" data-result-body="${index}">
            <a href="${escapeHtml(result.page_url || "#")}" target="_blank" rel="noreferrer">打开模型页面</a>
            <div data-files-area="${index}">${onlineFilesHtml(result, index)}</div>
          </div>
        </details>`;
    })
    .join("");
}

async function runOnlineSearch() {
  const query = (onlineSearchInput?.value || "").trim();
  if (!query) {
    setOnlineSearchStatus("请输入关键词，例如模型名、风格或用途。");
    return;
  }
  if (onlineSearchButton) onlineSearchButton.disabled = true;
  setOnlineSearchStatus(`正在搜索 ${onlineSearchSourceValue === "hf" ? "Hugging Face" : "Civitai"}…`, "pending");
  try {
    const response = await fetch(`/api/model-search?source=${onlineSearchSourceValue}&q=${encodeURIComponent(query)}&limit=12`);
    const data = await response.json();
    if (!response.ok) throw new Error(formatError(data.detail || data));
    onlineSearchData = data.results || [];
    renderOnlineSearchResults();
    setOnlineSearchStatus(onlineSearchData.length ? `找到 ${onlineSearchData.length} 个结果；展开选择文件后可导入。` : "没有找到匹配结果，换个关键词试试。");
  } catch (error) {
    setOnlineSearchStatus(`搜索失败：${error.message}`, "failed");
  } finally {
    if (onlineSearchButton) onlineSearchButton.disabled = false;
  }
}

async function loadOnlineResultFiles(index) {
  const result = onlineSearchData[index];
  if (!result || result.source !== "hf" || (result.files || []).length || result._filesLoaded) return;
  const area = onlineSearchResults?.querySelector(`[data-files-area="${index}"]`);
  if (area) area.innerHTML = '<p class="online-files-empty">正在读取仓库权重文件…</p>';
  try {
    const response = await fetch(`/api/model-search/files?source=hf&id=${encodeURIComponent(result.id)}`);
    const data = await response.json();
    if (!response.ok) throw new Error(formatError(data.detail || data));
    result.files = data.files || [];
    result.gated = Boolean(data.gated);
    result._filesLoaded = true;
    if (area) {
      area.innerHTML = result.files.length
        ? onlineFilesHtml(result, index)
        : '<p class="online-files-empty">仓库里没有找到权重文件（safetensors/gguf/ckpt 等）。</p>';
    }
  } catch (error) {
    if (area) area.innerHTML = `<p class="online-files-empty">读取文件失败：${escapeHtml(error.message)}</p>`;
    result._filesLoaded = false;
  }
}

function trackUserImportJob(job, label) {
  if (!job) return;
  localStorage.setItem(INSTALL_JOB_STORAGE_KEY, job.id);
  renderEnvInstallProgress(job);
  clearPollTimer("install");
  if (!job.completed) {
    void pollInstall(job.id);
    POLL_TIMERS.install = window.setInterval(() => pollInstall(job.id), 1500);
  }
  showInstallInDownloadCenter(job, label);
}

async function importOnlineModel(index, { download }) {
  const result = onlineSearchData[index];
  if (!result) return;
  const body = onlineSearchResults?.querySelector(`[data-result-body="${index}"]`);
  const checked = [...(body?.querySelectorAll('input[type="checkbox"]:checked') || [])];
  const files = checked
    .map((input) => (result.files || [])[Number(input.dataset.fileIndex)])
    .filter((file) => file && file.url);
  if (!files.length) {
    setOnlineSearchStatus("请先勾选至少一个模型文件。", "failed");
    return;
  }
  const subdir = body?.querySelector("[data-import-subdir]")?.value || guessImportSubdir(result);
  setOnlineSearchStatus(`正在${download ? "导入并创建下载任务" : "入库"}：${result.name}…`, "pending");
  try {
    const response = await fetch("/api/model-search/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source: result.source,
        model_id: result.id,
        label: result.name || result.id,
        page_url: result.page_url || "",
        task: result.type || "",
        quantization: result.version || "",
        target_subdir: subdir,
        files,
        download: Boolean(download),
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(formatError(data.detail || data));
    if (data.model_catalog) {
      modelCatalogData = data.model_catalog;
      renderModelCatalog();
      renderModelSyncPanel();
    }
    if (download && data.job) {
      trackUserImportJob(data.job, result.name || "导入模型");
      setOnlineSearchStatus(`已入库并开始下载：${result.name}。进度见环境任务/下载中心。`);
    } else {
      setOnlineSearchStatus(`已入库：${result.name}。可稍后在模型卡片上点「下载」。`);
    }
  } catch (error) {
    setOnlineSearchStatus(`导入失败：${error.message}`, "failed");
  }
}

onlineSearchButton?.addEventListener("click", () => void runOnlineSearch());
onlineSearchInput?.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    void runOnlineSearch();
  }
});
onlineSearchSource?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-search-source]");
  if (!button) return;
  onlineSearchSourceValue = button.dataset.searchSource || "hf";
  onlineSearchSource.querySelectorAll("button").forEach((item) => item.classList.toggle("active", item === button));
  if ((onlineSearchInput?.value || "").trim()) void runOnlineSearch();
});
onlineSearchResults?.addEventListener("toggle", (event) => {
  const details = event.target.closest("[data-search-index]");
  if (details?.open) void loadOnlineResultFiles(Number(details.dataset.searchIndex));
}, true);
onlineSearchResults?.addEventListener("click", (event) => {
  const downloadButton = event.target.closest("[data-import-download]");
  if (downloadButton) {
    void importOnlineModel(Number(downloadButton.dataset.importDownload), { download: true });
    return;
  }
  const importButton = event.target.closest("[data-import-only]");
  if (importButton) void importOnlineModel(Number(importButton.dataset.importOnly), { download: false });
});

async function removeUserImportedModel(entryId) {
  try {
    const response = await fetch("/api/model-search/remove", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: entryId }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(formatError(data.detail || data));
    if (data.model_catalog) {
      modelCatalogData = data.model_catalog;
      renderModelCatalog();
      renderModelSyncPanel();
    }
    setLog("已从模型目录移除该导入模型；已下载的文件保留在 models/ 目录。");
  } catch (error) {
    setLog(`移除导入模型失败：${error.message}`);
  }
}

async function downloadUserImportedModel(entryId, button) {
  if (button) button.disabled = true;
  try {
    const response = await fetch("/api/model-search/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: entryId }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(formatError(data.detail || data));
    trackUserImportJob(data.job, "导入模型下载");
  } catch (error) {
    setLog(`导入模型下载失败：${error.message}`);
  } finally {
    if (button) button.disabled = false;
  }
}
installProfileSelector?.addEventListener("change", () => {
  loadInstallPlan(installProfileSelector.value || "auto");
});
modelStoragePreset?.addEventListener("change", () => {
  modelDownloadPath.value = modelStoragePreset.value;
  localStorage.setItem(MODEL_DOWNLOAD_PATH_STORAGE_KEY, modelDownloadPath.value);
  modelStorageStatus.textContent = `${modelDownloadPath.value} · 正在刷新容量与缺失项`;
  loadInstallPlan(selectedInstallProfile);
});
modelDownloadPath?.addEventListener("input", () => {
  window.clearTimeout(modelStorageTimer);
  modelStorageTimer = window.setTimeout(() => {
    localStorage.setItem(MODEL_DOWNLOAD_PATH_STORAGE_KEY, modelDownloadPath.value.trim());
    modelStorageStatus.textContent = `${modelDownloadPath.value.trim()} · 正在刷新容量与缺失项`;
    loadInstallPlan(selectedInstallProfile);
  }, 650);
});
envPauseInstallButton?.addEventListener("click", () => controlEnvInstall("pause"));
envResumeInstallButton?.addEventListener("click", () => controlEnvInstall("resume"));
envCancelInstallButton?.addEventListener("click", () => controlEnvInstall("cancel"));
goGenerateButtons().forEach((button) => {
  button.addEventListener("click", () => {
    void goGenerateFromCatalog(button.dataset.modelId || selectedCatalogModelId);
  });
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && sourceConfigModal && !sourceConfigModal.classList.contains("hidden")) {
    closeSourceConfig();
    return;
  }
  trapModalFocus(event);
});
refreshBootstrapButton.addEventListener("click", loadBootstrap);
installComfyButton.addEventListener("click", () =>
  startBootstrapJob(
    "/api/bootstrap/install-comfyui?backend=auto",
    installComfyButton,
    "将安装或更新 ComfyUI，并创建 venv、安装 PyTorch 和 ComfyUI 依赖。这个过程可能下载数 GB 文件，是否继续？",
  ),
);
startComfyButton.addEventListener("click", () =>
  startBootstrapJob("/api/bootstrap/start-comfyui", startComfyButton, ""),
);
modelSelector.addEventListener("change", async () => {
  selectedModels[currentStep().id] = modelSelector.value;
  syncSelectedModel({ applyDefaults: true });
  renderStepIdle();
  if (currentStep().id === "draft") {
    await syncCatalogSelectionForWorkflowOption(selectedModelOption("draft"));
  }
});
socialPlatformSelect?.addEventListener("change", () => {
  localStorage.setItem(SOCIAL_TARGET_STORAGE_KEY, socialPlatformSelect.value);
  renderSocialRecipe({ apply: Boolean(socialAutoTune?.checked) });
});
socialQualitySwitch?.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-social-quality]");
  if (!button || !socialQualityInput) return;
  socialQualityInput.value = button.dataset.socialQuality;
  localStorage.setItem(SOCIAL_QUALITY_STORAGE_KEY, socialQualityInput.value);
  socialQualitySwitch.querySelectorAll("button").forEach((item) => item.classList.toggle("active", item === button));
  renderSocialRecipe({ apply: Boolean(socialAutoTune?.checked) });
});
socialAutoTune?.addEventListener("change", () => renderSocialRecipe({ apply: socialAutoTune.checked }));
socialSafeZoneToggle?.addEventListener("change", updateSocialSafeZone);
videoModelInstallButton?.addEventListener("click", () => {
  const option = selectedModelOption(currentStep().id);
  const catalog = catalogItemForWorkflowOption(option);
  const profile = videoModelInstallButton.dataset.profile || option?.install_profile || "";
  if (!profile && (option?.mode === "external_workflow" || catalogGenerationTarget(catalog) === "comfy_template")) {
    void goGenerateFromCatalog(catalog?.id || selectedCatalogModelId);
    return;
  }
  void launchOneClickInstall(
    profile,
    option?.label || "当前视频模型",
    { trigger: videoModelInstallButton, modelId: catalog?.id || selectedCatalogModelId },
  );
});
videoUnrestrictedToggle?.addEventListener("change", () => {
  renderVideoUnrestricted(selectedModelOption(currentStep().id));
  scheduleWorkflowPreflight();
});
adultContentAck?.addEventListener("change", scheduleWorkflowPreflight);
videoUnrestrictedStrengthRange?.addEventListener("input", () => syncVideoUnrestrictedStrength(videoUnrestrictedStrengthRange.value));
videoUnrestrictedStrength?.addEventListener("input", () => syncVideoUnrestrictedStrength(videoUnrestrictedStrength.value));
videoUnrestrictedStrength?.addEventListener("change", () => syncVideoUnrestrictedStrength(videoUnrestrictedStrength.value));
videoMotionSwitch?.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-motion]");
  if (!button) return;
  applyVideoMotion(button.dataset.motion);
});
videoSceneChips?.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-video-scene]");
  if (!button) return;
  applyVideoScene(button.dataset.videoScene);
});
videoAdultRecipeChips?.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-adult-wizard]");
  if (!button) return;
  applyVideoAdultRecipe(button.dataset.adultWizard);
});
videoMotionLoraChips?.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-motion-lora]");
  if (!button) return;
  applyVideoMotionLoraPack(button.dataset.motionLora);
});
videoAutoInjectTrigger?.addEventListener("change", () => {
  updateVideoTriggerPreview(selectedModelOption(currentStep().id));
  scheduleWorkflowPreflight();
});
videoAutoStripNegative?.addEventListener("change", scheduleWorkflowPreflight);
videoMotionLoraPack?.addEventListener("change", () => applyVideoMotionLoraPack(videoMotionLoraPack.value));
videoCustomTrigger?.addEventListener("input", () => {
  updateVideoTriggerPreview(selectedModelOption(currentStep().id));
  scheduleWorkflowPreflight();
});
videoCharacterSelect?.addEventListener("change", () => setSelectedVideoCharacterId(videoCharacterSelect.value));
videoFaceSwapWeightRange?.addEventListener("input", () => syncVideoFaceSwapWeight(videoFaceSwapWeightRange.value));
videoFaceSwapWeight?.addEventListener("input", () => syncVideoFaceSwapWeight(videoFaceSwapWeight.value));
videoExtractFrameButton?.addEventListener("click", () => void extractFrameFromCurrentVideo());
videoExtractFrameToImageButton?.addEventListener("click", () => {
  if (!lastExtractedVideoFrame) return;
  if (typeof window.acceptExtractedFrameToImageStudio === "function") {
    const ok = window.acceptExtractedFrameToImageStudio({
      ...lastExtractedVideoFrame,
      label: "视频抽帧",
    });
    if (ok) setView("image-studio");
    else appendLog("图片工作室未加载抽帧交接接口。");
  }
});
videoFaceSwapSubmitButton?.addEventListener("click", () => void submitVideoFaceSwap());
videoTuneSubmitButton?.addEventListener("click", () => void submitVideoTune());
videoFaceSwapInstallButton?.addEventListener("click", () => {
  const profile = videoFaceSwapInstallButton.dataset.profile || "face-swap-reactor";
  void launchOneClickInstall(profile, "ReActor 视频换脸组件");
});
videoFaceSwapBatchInput?.addEventListener("change", updateVideoFaceSwapSourceSummary);
videoInstallUnrestrictedButton?.addEventListener("click", () => {
  const profile = videoInstallUnrestrictedButton.dataset.profile || "";
  if (!profile) return;
  void launchOneClickInstall(profile, "视频无限制社区附加包");
});
backButton.addEventListener("click", goBack);
continueButton.addEventListener("click", goNext);
repeatButton.addEventListener("click", handlePrimary);
videoCancelJobButton?.addEventListener("click", () => void cancelVideoJob(videoCancelJobButton.dataset.jobId || activeJobId));
videoFaceSwapCancelButton?.addEventListener("click", () => void cancelVideoJob(videoFaceSwapCancelButton.dataset.jobId || activeVideoFaceSwapJobId));

function handleVideoTaskQueueClick(event, faceSwapOnly = false) {
  const viewButton = event.target.closest("[data-video-task-view]");
  const cancelButton = event.target.closest("[data-video-task-cancel]");
  if (viewButton) {
    const jobId = viewButton.dataset.videoTaskView;
    if (faceSwapOnly) activeVideoFaceSwapJobId = jobId;
    else setStep(videoJobSteps.get(jobId) || "draft", { refresh: false });
    watchJob(jobId, videoJobSteps.get(jobId) || (faceSwapOnly ? "face_swap" : "draft"));
  } else if (cancelButton) {
    void cancelVideoJob(cancelButton.dataset.videoTaskCancel);
  }
}

videoTaskQueueList?.addEventListener("click", (event) => handleVideoTaskQueueClick(event));
videoFaceSwapQueueList?.addEventListener("click", (event) => handleVideoTaskQueueClick(event, true));
copyDiagnosticsButton?.addEventListener("click", copyDiagnostics);
downloadDiagnosticsButton?.addEventListener("click", downloadDiagnostics);

// ---- 便捷工具：复制提示词 / 清空日志 / 最近任务 --------------------
const copyPromptButton = document.querySelector("#copyPromptButton");
const clearLogButton = document.querySelector("#clearLogButton");
const recentJobsList = document.querySelector("#recentJobsList");
const recentJobsRefreshButton = document.querySelector("#recentJobsRefreshButton");
const recentJobsFilter = document.querySelector("#recentJobsFilter");
const recentJobsMoreButton = document.querySelector("#recentJobsMoreButton");

document.addEventListener("toggle", (event) => {
  const current = event.target;
  if (!(current instanceof HTMLDetailsElement) || !current.open || !current.classList.contains("secondary-drawer")) return;
  const group = current.closest(".secondary-accordion");
  if (!group) return;
  for (const sibling of group.querySelectorAll(":scope > details.secondary-drawer[open]")) {
    if (sibling !== current) sibling.open = false;
  }
}, true);
const outputGrid = document.querySelector("#outputGrid");
const outputDirLabel = document.querySelector("#outputDirLabel");
const outputRefreshButton = document.querySelector("#outputRefreshButton");
const outputClearButton = document.querySelector("#outputClearButton");
const outputDirForm = document.querySelector("#outputDirForm");
const outputSubdirInput = document.querySelector("#outputSubdirInput");
const outputDirSaveButton = document.querySelector("#outputDirSaveButton");
const outputSelectButton = document.querySelector("#outputSelectButton");
const outputSelectionBar = document.querySelector("#outputSelectionBar");
const outputSelectAll = document.querySelector("#outputSelectAll");
const outputSelectionCount = document.querySelector("#outputSelectionCount");
const outputDeleteSelectedButton = document.querySelector("#outputDeleteSelectedButton");
const outputCancelSelectButton = document.querySelector("#outputCancelSelectButton");

const outputSelection = { active: false, selected: new Set() };

const recentJobsState = { filter: "all", project: "", limit: 5, step: 10, max: 100 };

// ---- 项目标签：记忆当前值和历史候选，输出会按标签归档到子目录 ----
const projectTagInput = document.querySelector("#projectTag");
const projectTagOptions = document.querySelector("#projectTagOptions");
const PROJECT_TAG_KEY = "workbench.project_tag";
const PROJECT_TAG_HISTORY_KEY = "workbench.project_tags";

function readProjectTagHistory() {
  try {
    const parsed = JSON.parse(localStorage.getItem(PROJECT_TAG_HISTORY_KEY) || "[]");
    return Array.isArray(parsed) ? parsed.filter((item) => typeof item === "string" && item.trim()) : [];
  } catch (_) {
    return [];
  }
}

function renderProjectTagOptions() {
  if (!projectTagOptions) return;
  projectTagOptions.innerHTML = readProjectTagHistory()
    .map((name) => `<option value="${escapeHtml(name)}"></option>`)
    .join("");
}

function rememberProjectTag(value) {
  const tag = String(value || "").trim();
  try {
    localStorage.setItem(PROJECT_TAG_KEY, tag);
    if (tag) {
      const history = readProjectTagHistory().filter((item) => item !== tag);
      history.unshift(tag);
      localStorage.setItem(PROJECT_TAG_HISTORY_KEY, JSON.stringify(history.slice(0, 12)));
    }
  } catch (_) {
    /* localStorage 不可用时静默跳过 */
  }
  renderProjectTagOptions();
}

if (projectTagInput) {
  try {
    projectTagInput.value = localStorage.getItem(PROJECT_TAG_KEY) || "";
  } catch (_) {
    /* ignore */
  }
  renderProjectTagOptions();
  projectTagInput.addEventListener("change", () => rememberProjectTag(projectTagInput.value));
}

async function copyTextToClipboard(text, okMessage) {
  if (!navigator.clipboard?.writeText) {
    appendLog("浏览器不允许写入剪贴板。");
    return false;
  }
  try {
    await navigator.clipboard.writeText(text);
    appendLog(okMessage);
    return true;
  } catch (error) {
    appendLog(`写入剪贴板失败：${error.message}`);
    return false;
  }
}

function flashButton(button, label, restoreDelay = 1400) {
  if (!button) return;
  const original = button.dataset.originalLabel || button.textContent;
  button.dataset.originalLabel = original;
  button.textContent = label;
  button.disabled = true;
  window.setTimeout(() => {
    button.textContent = original;
    button.disabled = false;
  }, restoreDelay);
}

copyPromptButton?.addEventListener("click", async () => {
  const text = promptInput.value.trim();
  if (!text) {
    appendLog("提示词为空，无法复制。");
    return;
  }
  if (await copyTextToClipboard(text, "提示词已复制到剪贴板。")) {
    flashButton(copyPromptButton, "已复制");
  }
});

clearLogButton?.addEventListener("click", () => {
  setLog("");
  appendLog("日志已清空。");
});

function jobStatusClass(status) {
  const value = String(status || "").toLowerCase();
  if (["success", "succeeded", "done", "completed", "complete", "ok", "cached"].includes(value)) return "ok";
  if (["failed", "error", "canceled", "cancelled", "interrupted", "stopped", "lost"].includes(value)) return "bad";
  if (["running", "processing", "downloading", "started"].includes(value)) return "running";
  if (["queued", "pending", "paused", "blocked", "partial"].includes(value)) return "pending";
  return "muted";
}

function formatJobTime(createdAt) {
  const numeric = Number(createdAt);
  if (!Number.isFinite(numeric) || numeric <= 0) return "";
  const date = new Date(numeric > 10_000_000_000 ? numeric : numeric * 1000);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString([], { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

const recentJobsProjectFilter = document.querySelector("#recentJobsProjectFilter");

function updateRecentJobsProjectFilter(jobs) {
  if (!recentJobsProjectFilter) return;
  const projects = [...new Set(jobs.map((job) => String(job.project || "").trim()).filter(Boolean))].sort();
  const current = recentJobsState.project;
  const options = ['<option value="">全部项目</option>'];
  for (const name of projects) {
    options.push(`<option value="${escapeHtml(name)}"${name === current ? " selected" : ""}>${escapeHtml(name)}</option>`);
  }
  if (current && !projects.includes(current)) {
    options.push(`<option value="${escapeHtml(current)}" selected>${escapeHtml(current)}</option>`);
  }
  recentJobsProjectFilter.innerHTML = options.join("");
  recentJobsProjectFilter.classList.toggle("hidden", !projects.length && !current);
}

recentJobsProjectFilter?.addEventListener("change", () => {
  recentJobsState.project = recentJobsProjectFilter.value;
  loadRecentJobs(true);
});

function jobMatchesFilter(job) {
  if (recentJobsState.project && String(job.project || "") !== recentJobsState.project) return false;
  const filter = recentJobsState.filter;
  if (filter === "all") return true;
  const status = String(job.status || "").toLowerCase();
  if (filter === "success") return ["success", "succeeded", "done", "completed", "complete", "ok", "cached"].includes(status);
  if (filter === "failed") return ["failed", "error", "canceled", "cancelled", "interrupted", "stopped", "lost"].includes(status);
  if (filter === "video") return String(job.kind || "").startsWith("video") || (Array.isArray(job.media) && job.media.some((m) => m.kind === "video"));
  return true;
}

function renderRecentJobs(jobs, totalCount) {
  if (!recentJobsList) return;
  updateRecentJobsProjectFilter(jobs);
  const filtered = jobs.filter(jobMatchesFilter);
  if (!filtered.length) {
    const label = { all: "暂无任务记录。", success: "没有成功的任务。", failed: "没有失败的任务。", video: "没有视频任务。" }[recentJobsState.filter] || "暂无任务记录。";
    recentJobsList.innerHTML = `<p class="recent-jobs-empty">${label}</p>`;
  } else {
    recentJobsList.innerHTML = "";
    filtered.forEach((job) => {
      const row = document.createElement("button");
      row.type = "button";
      row.className = "recent-job-row";
      row.setAttribute("role", "listitem");
      if (job.id) row.dataset.jobId = String(job.id);
      row.title = "点击在右侧预览该任务输出";

      const statusClass = jobStatusClass(job.status);
      const statusText = jobStatusLabel(job);
      const label = job.title || job.label || job.model_label || job.kind || job.mode || "生成任务";
      const time = formatJobTime(job.created_at);
      const rawProgress = job.progress && typeof job.progress === "object" ? job.progress.percent : job.progress;
      const progress = Number.isFinite(Number(rawProgress)) ? Math.round(Number(rawProgress)) : null;

      const badge = document.createElement("span");
      badge.className = `recent-job-status ${statusClass}`;
      badge.textContent = statusText;

      const main = document.createElement("div");
      main.className = "recent-job-main";
      const title = document.createElement("strong");
      title.textContent = label;
      const detail = document.createElement("small");
      const parts = [];
      if (job.project) parts.push(`项目 ${job.project}`);
      if (time) parts.push(time);
      if (progress !== null && statusClass === "running") parts.push(`${progress}%`);
      if ((job.error || job.message) && statusClass === "bad") parts.push(String(job.error || job.message).slice(0, 60));
      detail.textContent = parts.join(" · ") || job.id || "";
      main.append(title, detail);

      row.append(badge, main);
      row.addEventListener("click", () => previewJobFromList(job.id, row));
      recentJobsList.append(row);
    });
  }
  if (recentJobsMoreButton) {
    const total = Number.isFinite(Number(totalCount)) ? Number(totalCount) : jobs.length;
    const canMore = jobs.length < total && recentJobsState.limit < recentJobsState.max;
    recentJobsMoreButton.classList.toggle("hidden", !canMore);
  }
}

async function previewJobFromList(jobId, row) {
  if (!jobId) return;
  document.querySelectorAll(".recent-job-row.selected").forEach((el) => el.classList.remove("selected"));
  if (row) row.classList.add("selected");
  try {
    const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}?refresh=false`, { cache: "no-store" });
    const job = await response.json();
    if (!response.ok) throw new Error(formatError(job.detail || job));
    document.querySelector("#taskPreviewTitle").textContent = job.title || job.mode || "任务详情";
    renderMediaInto(document.querySelector("#taskPreviewMedia"), job.media || [], "此任务尚无输出。");
    document.querySelector("#taskPreviewDetail").textContent = [
      `状态：${jobStatusLabel(job)}`, `任务：${job.id}`, job.model_profile ? `模型：${job.model_profile}` : "",
      job.width && job.height ? `生成参数：${job.width} × ${job.height} · ${job.fps || "-"} fps` : "",
      job.source_video_filename ? `输入：${job.source_video_filename}` : "", formatJobMessages(job),
    ].filter(Boolean).join("\n");
    const video = pickVideo(job.media);
    const use = document.querySelector("#taskUseVideo");
    use.classList.toggle("hidden", !video);
    use.onclick = () => adoptWorkflowVideo({ ...video, ...(job.output_metadata || video.metadata || {}) });
    const cancel = document.querySelector("#taskCancel");
    cancel.classList.toggle("hidden", videoJobIsTerminal(job));
    cancel.onclick = async () => { cancel.disabled = true; try { await cancelVideoJob(job.id); await loadRecentJobs(false); }
      finally { cancel.disabled = false; } };
    document.querySelector(".task-preview").scrollIntoView({ behavior: "smooth", block: "nearest" });
  } catch (error) {
    document.querySelector("#taskPreviewDetail").textContent = `加载任务失败：${error.message}`;
  }
}

let recentJobsRequestId = 0;
async function loadRecentJobs(reset = false) {
  if (!recentJobsList) return;
  if (reset) recentJobsState.limit = 20;
  const requestId = ++recentJobsRequestId;
  try {
    const query = new URLSearchParams({ limit: recentJobsState.limit, status: recentJobsState.filter, project: recentJobsState.project });
    const response = await fetch(`/api/jobs?${query}`, { cache: "no-store" });
    const data = await response.json();
    if (requestId !== recentJobsRequestId) return;
    if (!response.ok) throw new Error(formatError(data.detail || data));
    renderRecentJobs(data.items || [], data.count);
    document.querySelector("#taskCountSummary").textContent = `${data.active_count || 0} 个进行中 · ${data.count || 0} 条匹配记录`;
    if (Array.isArray(data.projects)) {
      recentJobsProjectFilter.innerHTML = '<option value="">全部项目</option>' + data.projects
        .map((project) => `<option value="${escapeHtml(project)}">${escapeHtml(project)}</option>`).join("");
      recentJobsProjectFilter.value = recentJobsState.project;
      recentJobsProjectFilter.classList.toggle("hidden", !data.projects.length);
    }
  } catch (error) {
    if (requestId !== recentJobsRequestId) return;
    recentJobsList.innerHTML = `<p class="recent-jobs-empty">读取任务失败：${escapeHtml(error.message)}</p>`;
  }
}

recentJobsRefreshButton?.addEventListener("click", () => loadRecentJobs(true));
recentJobsMoreButton?.addEventListener("click", () => {
  recentJobsState.limit = Math.min(recentJobsState.limit + recentJobsState.step, recentJobsState.max);
  loadRecentJobs(false);
});
recentJobsFilter?.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-filter]");
  if (!button) return;
  recentJobsState.filter = button.dataset.filter;
  recentJobsFilter.querySelectorAll("button").forEach((b) => b.classList.toggle("active", b === button));
  loadRecentJobs(true);
});

// ---- 历史输出管理：目录设置 + 文件列表/删除/清空 --------------------
function formatBytes(bytes) {
  const value = Number(bytes);
  if (!Number.isFinite(value) || value < 0) return "";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 * 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MB`;
  return `${(value / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

async function loadOutputConfig() {
  try {
    const response = await fetch("/api/outputs/config", { cache: "no-store" });
    const data = await response.json();
    if (!response.ok) throw new Error(formatError(data.detail || data));
    if (outputSubdirInput && !outputSubdirInput.matches(":focus")) outputSubdirInput.value = data.subdir || "";
    if (outputDirLabel) outputDirLabel.textContent = data.dir || "";
  } catch (_) {
    /* 配置读取失败不阻塞页面 */
  }
}

outputDirForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!outputSubdirInput) return;
  const subdir = outputSubdirInput.value.trim();
  outputDirSaveButton.disabled = true;
  try {
    const response = await fetch("/api/outputs/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ subdir }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(formatError(data.detail || data));
    if (outputSubdirInput) outputSubdirInput.value = data.subdir || subdir;
    if (outputDirLabel) outputDirLabel.textContent = data.dir || "";
    appendLog(`输出子目录已设为 ${data.subdir}（${data.dir}）。`);
    loadOutputs();
  } catch (error) {
    appendLog(`保存输出目录失败：${error.message}`);
  } finally {
    outputDirSaveButton.disabled = false;
  }
});

function renderOutputs(items) {
  if (!outputGrid) return;
  if (!Array.isArray(items) || !items.length) {
    outputGrid.innerHTML = '<p class="output-empty">暂无输出文件。</p>';
    updateOutputSelectionUI();
    return;
  }
  outputGrid.innerHTML = "";
  items.forEach((item) => {
    const card = document.createElement("div");
    card.className = "output-card";
    card.setAttribute("role", "listitem");
    card.dataset.rel = item.rel;

    const thumb = document.createElement(item.kind === "video" ? "video" : "img");
    thumb.className = "output-thumb";
    thumb.src = mediaUrl(item.url);
    if (item.kind === "video") {
      thumb.muted = true;
      thumb.preload = "metadata";
      thumb.playsInline = true;
    } else {
      thumb.alt = item.filename;
      thumb.loading = "lazy";
    }
    thumb.addEventListener("click", () => {
      if (outputSelection.active) {
        toggleOutputCardSelection(card, item.rel);
        return;
      }
      document.querySelector("#libraryPreviewSection").classList.remove("hidden");
      document.querySelector("#libraryPreviewTitle").textContent = item.filename;
      renderMediaInto(document.querySelector("#libraryPreview"), [item], "暂无预览");
      document.querySelector("#libraryPreviewSection").scrollIntoView({ behavior: "smooth", block: "nearest" });
    });

    const check = document.createElement("input");
    check.type = "checkbox";
    check.className = "output-check";
    check.checked = outputSelection.selected.has(item.rel);
    check.setAttribute("aria-label", `选择 ${item.filename}`);
    check.addEventListener("click", (event) => event.stopPropagation());
    check.addEventListener("change", () => toggleOutputCardSelection(card, item.rel, check.checked));

    const meta = document.createElement("div");
    meta.className = "output-meta";
    const name = document.createElement("strong");
    name.textContent = item.filename;
    name.title = item.filename;
    const sub = document.createElement("small");
    const bits = [item.kind === "video" ? "视频" : "图片", formatBytes(item.size)];
    const time = formatJobTime(item.modified_at);
    if (time) bits.push(time);
    sub.textContent = bits.join(" · ");
    meta.append(name, sub);

    const del = document.createElement("button");
    del.type = "button";
    del.className = "output-delete";
    del.title = "删除该文件";
    del.textContent = "删除";
    del.addEventListener("click", async (event) => {
      event.stopPropagation();
      if (outputSelection.active) return;
      if (!window.confirm(`确定删除文件「${item.filename}」吗？会移入 _trash 回收目录保留 7 天。`)) return;
      del.disabled = true;
      try {
        const response = await fetch("/api/outputs/delete", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ rel: item.rel }),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(formatError(data.detail || data));
        appendLog(`已删除输出文件 ${data.deleted}。`);
        outputSelection.selected.delete(item.rel);
        card.remove();
        updateOutputSelectionUI();
        if (!outputGrid.querySelector(".output-card")) {
          outputGrid.innerHTML = '<p class="output-empty">暂无输出文件。</p>';
        }
      } catch (error) {
        appendLog(`删除失败：${error.message}`);
        del.disabled = false;
      }
    });

    card.append(thumb, meta, del, check);
    if (item.kind === "video") {
      const use = document.createElement("button");
      use.type = "button"; use.className = "secondary output-use"; use.textContent = "用于视频后期";
      use.onclick = () => adoptWorkflowVideo(item);
      card.append(use);
    }
    card.classList.toggle("selected", outputSelection.selected.has(item.rel));
    outputGrid.append(card);
  });
  updateOutputSelectionUI();
}

async function loadOutputs() {
  if (!outputGrid) return;
  try {
    const response = await fetch("/api/outputs?limit=60", { cache: "no-store" });
    const data = await response.json();
    if (!response.ok) throw new Error(formatError(data.detail || data));
    if (outputDirLabel) outputDirLabel.textContent = data.dir || "";
    renderOutputs(data.items || []);
  } catch (error) {
    outputGrid.innerHTML = `<p class="output-empty">读取输出失败：${escapeHtml(error.message)}</p>`;
  }
}

outputRefreshButton?.addEventListener("click", loadOutputs);
document.querySelector("#openOutputManagerButton")?.addEventListener("click", () => setView("library"));
document.querySelector("#openTaskManagerButton")?.addEventListener("click", () => setView("tasks"));
document.querySelector("#chooseWorkflowSource")?.addEventListener("click", () => {
  pendingSourceOperation = WorkbenchJourney.operation(currentStep().id);
  setView("library");
});
document.querySelector("#clearProcessingSource")?.addEventListener("click", () => {
  Object.assign(workflowState, { ...WorkbenchState.create(), revision: workflowState.revision + 1 });
  videoInput.value = "";
  currentVideoResolution = null;
  currentVideoFps = 24;
  if (currentStep().id === "edit") { stitchFiles = []; clipsInput.value = ""; renderStitchClipList(); }
  syncWorkflowOutputs(); persistWorkflowState(); renderStepIdle();
});
document.querySelector("#newWorkflowShot")?.addEventListener("click", () => {
  if (!window.confirm("开始新镜头？仅清除当前步骤关联，已有文件和运行中的任务都会保留。")) return;
  Object.assign(workflowState, { ...WorkbenchState.create(), revision: workflowState.revision + 1 });
  videoInput.value = "";
  [imageInput, referenceMediaInput, endImageInput, batchKeyframeInput, clipsInput,
    document.querySelector("#h3ControlVideo"), document.querySelector("#h3SourceVideo"), document.querySelector("#h3Mask")]
    .forEach((input) => { if (input) input.value = ""; });
  clearLinkedKeyframe();
  stitchFiles = [];
  currentVideoResolution = null;
  updateKeyframePreview();
  completedSteps.clear();
  syncWorkflowOutputs(); persistWorkflowState();
  setStep("draft", { refresh: false });
});

let adoptVideoRequestId = 0;
async function adoptWorkflowVideo(item) {
  if (!item?.filename) return;
  const requestId = ++adoptVideoRequestId;
  const revision = workflowState.revision;
  const media = { ...item, type: item.type || "output" };
  if (item.media_subfolder !== undefined) media.subfolder = item.media_subfolder;
  else if (item.url) {
    try { media.subfolder = new URL(item.url, location.href).searchParams.get("subfolder") || ""; } catch (_) {}
  }
  try {
    const query = new URLSearchParams({ filename: media.filename, subfolder: media.subfolder || "", type: media.type });
    const response = await fetch(`/api/media/metadata?${query}`);
    const result = await response.json();
    if (!response.ok) throw new Error(formatError(result.detail || result));
    Object.assign(media, result.metadata || {});
  } catch (error) {
    appendLog(`未能读取视频尺寸，后期尺寸暂为估算：${error.message}`);
  }
  if (requestId !== adoptVideoRequestId || revision !== workflowState.revision) return;
  const operation = pendingSourceOperation || "deflicker";
  pendingSourceOperation = "";
  useVideoForOperation(media, operation);
  appendLog(`已选择 ${media.filename}。可以微调、插帧或直接超分。`);
}

// 页面内二次确认（与安装按钮同一模式），不再使用浏览器系统确认弹窗。
const outputClearButtonText = outputClearButton?.textContent || "一键清空";
let outputClearConfirming = false;
let outputClearConfirmTimer = null;

function resetOutputClearConfirm() {
  outputClearConfirming = false;
  if (outputClearConfirmTimer) {
    clearTimeout(outputClearConfirmTimer);
    outputClearConfirmTimer = null;
  }
  if (outputClearButton) outputClearButton.textContent = outputClearButtonText;
}

outputClearButton?.addEventListener("click", async () => {
  if (!outputClearConfirming) {
    outputClearConfirming = true;
    outputClearButton.textContent = "确认清空全部输出";
    appendLog("再次点击「确认清空全部输出」执行；文件会移入输出目录下的 _trash 回收目录，保留 7 天。");
    outputClearConfirmTimer = window.setTimeout(resetOutputClearConfirm, 8000);
    return;
  }
  resetOutputClearConfirm();
  outputClearButton.disabled = true;
  try {
    const response = await fetch("/api/outputs/clear", { method: "POST" });
    const data = await response.json();
    if (!response.ok) throw new Error(formatError(data.detail || data));
    appendLog(`已清空输出目录，共移入回收目录 ${data.removed} 个文件（${data.trash || "_trash"} 内保留 7 天，可手动找回）。`);
    exitOutputSelectionMode();
    loadOutputs();
  } catch (error) {
    appendLog(`清空输出失败：${error.message}`);
  } finally {
    outputClearButton.disabled = false;
  }
});

// ---- 历史输出：批量选择删除 ----
function updateOutputSelectionUI() {
  if (!outputGrid) return;
  const cards = [...outputGrid.querySelectorAll(".output-card")];
  const total = cards.length;
  const count = outputSelection.selected.size;
  if (outputSelectionBar) outputSelectionBar.classList.toggle("hidden", !outputSelection.active);
  if (outputGrid) outputGrid.classList.toggle("select-mode", outputSelection.active);
  if (outputSelectionCount) outputSelectionCount.textContent = `已选 ${count} 项`;
  if (outputDeleteSelectedButton) outputDeleteSelectedButton.disabled = count === 0;
  if (outputSelectAll) {
    outputSelectAll.checked = total > 0 && count === total;
    outputSelectAll.indeterminate = count > 0 && count < total;
  }
  cards.forEach((card) => {
    const rel = card.dataset.rel;
    const check = card.querySelector(".output-check");
    const on = outputSelection.selected.has(rel);
    card.classList.toggle("selected", on);
    if (check) check.checked = on;
  });
  if (outputSelectButton) outputSelectButton.textContent = outputSelection.active ? "完成" : "批量管理";
}

function toggleOutputCardSelection(card, rel, force) {
  const on = typeof force === "boolean" ? force : !outputSelection.selected.has(rel);
  if (on) outputSelection.selected.add(rel);
  else outputSelection.selected.delete(rel);
  updateOutputSelectionUI();
}

function enterOutputSelectionMode() {
  outputSelection.active = true;
  updateOutputSelectionUI();
}

function exitOutputSelectionMode() {
  outputSelection.active = false;
  outputSelection.selected.clear();
  updateOutputSelectionUI();
}

outputSelectButton?.addEventListener("click", () => {
  if (outputSelection.active) exitOutputSelectionMode();
  else enterOutputSelectionMode();
});

outputCancelSelectButton?.addEventListener("click", exitOutputSelectionMode);

outputSelectAll?.addEventListener("change", () => {
  const cards = [...outputGrid.querySelectorAll(".output-card")];
  if (outputSelectAll.checked) {
    cards.forEach((card) => outputSelection.selected.add(card.dataset.rel));
  } else {
    outputSelection.selected.clear();
  }
  updateOutputSelectionUI();
});

outputDeleteSelectedButton?.addEventListener("click", async () => {
  const rels = [...outputSelection.selected];
  if (!rels.length) return;
  if (!window.confirm(`确定删除所选 ${rels.length} 个输出文件吗？会移入 _trash 回收目录保留 7 天。`)) return;
  outputDeleteSelectedButton.disabled = true;
  try {
    const response = await fetch("/api/outputs/delete-batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rels }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(formatError(data.detail || data));
    appendLog(`已删除 ${data.removed} 个输出文件。${data.errors && data.errors.length ? `（${data.errors.length} 个失败）` : ""}`);
    exitOutputSelectionMode();
    loadOutputs();
  } catch (error) {
    appendLog(`批量删除失败：${error.message}`);
    outputDeleteSelectedButton.disabled = false;
  }
});
imageInput.addEventListener("change", () => {
  if (imageInput.files?.length) clearLinkedKeyframe();
  updateKeyframePreview();
});
referenceMediaInput?.addEventListener("change", () => {
  renderReferenceMediaList();
  scheduleWorkflowPreflight();
});
keyframePreview?.addEventListener("click", (event) => {
  if (!event.target.closest("[data-clear-linked-keyframe]")) return;
  clearLinkedKeyframe();
  updateKeyframePreview();
  appendLog("已移除文生图关键帧，可继续上传其他图片或使用文字生视频。");
});
videoInput.addEventListener("change", () => {
  // Selecting a new source detaches prior jobs before they can repopulate the form.
  Object.assign(workflowState, { ...WorkbenchState.create(), revision: workflowState.revision + 1 });
  currentVideoResolution = null;
  syncWorkflowOutputs();
  persistWorkflowState();
  renderStepIdle();
  updateUploadedVideoMetadata();
  updateVideoFaceSwapSourceSummary();
});
clipsInput?.addEventListener("change", updateStitchFiles);
stitchClipList?.addEventListener("click", handleClipOrderAction);
widthInput.addEventListener("input", () => {
  refreshH3Tools();
  if (!currentVideoResolution) updateTargetResolution();
  renderSocialRecipe({ apply: false });
  scheduleWorkflowPreflight();
});
heightInput.addEventListener("input", () => {
  refreshH3Tools();
  if (!currentVideoResolution) updateTargetResolution();
  renderSocialRecipe({ apply: false });
  scheduleWorkflowPreflight();
});
lengthInput.addEventListener("input", () => {
  refreshH3Tools();
  renderSocialRecipe({ apply: false });
  scheduleWorkflowPreflight();
});
fpsInput.addEventListener("input", () => {
  renderSocialRecipe({ apply: false });
  scheduleWorkflowPreflight();
});
stepsInput.addEventListener("input", scheduleWorkflowPreflight);
cfgInput.addEventListener("input", scheduleWorkflowPreflight);
serviceModeInputs.forEach((input) => input.addEventListener("change", previewServiceConfig));
serviceServerUrl?.addEventListener("input", previewServiceConfig);
serviceAccessToken?.addEventListener("input", previewServiceConfig);
saveServiceConfigButton?.addEventListener("click", saveServiceConfig);
reloadServiceConfigButton?.addEventListener("click", () => loadClientConfig({ quiet: false, pingRemote: true }));

async function initApp() {
  promptInput.value = defaultPrompt;
  negativeInput.value = defaultNegative;
  updateKeyframePreview();
  updateTargetResolution();
  await loadAdvancedSchemas();
  setStep("draft", { refresh: false, focus: false });
  await loadClientConfig();
  restoreWorkflowState();
  restoreCreationDraft();
  await refreshEnvironmentWorkspace({ forceRecommendations: !Object.keys(selectedModels).length });
  updateEnvStatusBar();
  await refreshVideoFaceSwapCapability();
  updateVideoFaceSwapSourceSummary();
  await resumeRememberedJob();
  await resumeRememberedInstall();
  appInitialized = true;
  let savedJourney = null;
  try { savedJourney = JSON.parse(localStorage.getItem(`${workflowStorageKey()}:journey`) || "null"); } catch (_) {}
  const target = WorkbenchJourney.restore(savedJourney);
  parameterLevel = savedJourney?.parameterLevel === "full" ? "full" : "basic";
  lastProcessingOperation = WorkbenchJourney.operation(savedJourney?.operation);
  if (target.view === "workflow") setStep(target.step, { refresh: false, focus: false });
  setView(target.view);
  syncJourneyNavigation();
  refreshStatus();
  loadRecentJobs(true);
  loadOutputConfig();
  loadOutputs();
  window.setInterval(refreshStatus, 15000);
  // 页面卸载时清理所有轮询定时器，避免刷新后泄漏残留轮询。
  window.addEventListener("beforeunload", () => { persistCreationDraft(); clearAllPollTimers(); });
}

initApp();
