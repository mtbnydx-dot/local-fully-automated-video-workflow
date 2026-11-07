(() => {
  "use strict";

  const form = document.querySelector("#imageStudioForm");
  if (!form) return;

  const refs = {
    viewTab: document.querySelector('.view-tab[data-view="image-studio"]'),
    workflowTab: document.querySelector('.view-tab[data-view="workflow"]'),
    environmentTab: document.querySelector('.view-tab[data-view="environment"]'),
    topModel: document.querySelector("#topModelLabel"),
    badge: document.querySelector("#imageStudioBadge"),
    taskModeSwitch: document.querySelector("#imageTaskModeSwitch"),
    editMode: document.querySelector("#imageEditMode"),
    taskModeNote: document.querySelector("#imageTaskModeNote"),
    editOperationSwitch: document.querySelector("#imageEditOperationSwitch"),
    editOperation: document.querySelector("#imageEditOperation"),
    editOperationNote: document.querySelector("#imageEditOperationNote"),
    modelBar: document.querySelector("#imageModelBar"),
    profile: document.querySelector("#imageProfile"),
    sourceButton: document.querySelector("#imageSourceButton"),
    refreshButton: document.querySelector("#imageRefreshButton"),
    installButton: document.querySelector("#imageInstallButton"),
    modelStatus: document.querySelector("#imageModelStatus"),
    profileName: document.querySelector("#imageProfileName"),
    profileDescription: document.querySelector("#imageProfileDescription"),
    profileTags: document.querySelector("#imageProfileTags"),
    profileFacts: document.querySelector("#imageProfileFacts"),
    compatibilityNote: document.querySelector("#imageCompatibilityNote"),
    workflowLink: document.querySelector("#imageWorkflowLink"),
    profileDetails: document.querySelector("#imageProfileDetails"),
    editPanel: document.querySelector("#imageEditPanel"),
    editMethodNote: document.querySelector("#imageEditMethodNote"),
    editSourceTitle: document.querySelector("#imageEditSourceTitle"),
    editFile: document.querySelector("#imageEditFile"),
    editPreview: document.querySelector("#imageEditPreview"),
    editClear: document.querySelector("#imageEditClearButton"),
    editSourceFilename: document.querySelector("#imageEditSourceFilename"),
    editSourceSubfolder: document.querySelector("#imageEditSourceSubfolder"),
    editSourceType: document.querySelector("#imageEditSourceType"),
    referencePanel: document.querySelector("#imageReferencePanel"),
    referenceFiles: document.querySelector("#imageReferenceFiles"),
    referenceHint: document.querySelector("#imageReferenceHint"),
    referenceSummary: document.querySelector("#imageReferenceSummary"),
    referenceList: document.querySelector("#imageReferenceList"),
    referenceClear: document.querySelector("#imageReferenceClearButton"),
    sourceProcessing: document.querySelector("#imageSourceProcessing"),
    instructionEditSettings: document.querySelector("#imageInstructionEditSettings"),
    faceOptions: document.querySelector("#imageFaceOptions"),
    faceCropMode: document.querySelector("#imageFaceCropMode"),
    faceRetry: document.querySelector("#imageFaceRetryButton"),
    faceStatus: document.querySelector("#imageFaceStatus"),
    faceCandidates: document.querySelector("#imageFaceCandidates"),
    faceAuthorization: document.querySelector("#imageFaceAuthorization"),
    faceExtractId: document.querySelector("#imageFaceExtractId"),
    faceIndex: document.querySelector("#imageFaceIndex"),
    faceAnalyze: document.querySelector("#imageFaceAnalyzeButton"),
    faceInstall: document.querySelector("#imageFaceInstallButton"),
    faceEngineNote: document.querySelector("#imageFaceEngineNote"),
    faceEngineSource: document.querySelector("#imageFaceEngineSource"),
    identityFaceFile: document.querySelector("#imageIdentityFaceFile"),
    identityFacePreview: document.querySelector("#imageIdentityFacePreview"),
    identityFaceClear: document.querySelector("#imageIdentityFaceClearButton"),
    identityFaceRetry: document.querySelector("#imageIdentityFaceRetryButton"),
    identityFaceCandidates: document.querySelector("#imageIdentityFaceCandidates"),
    identityFaceExtractId: document.querySelector("#imageIdentityFaceExtractId"),
    identityFaceIndex: document.querySelector("#imageIdentityFaceIndex"),
    faceSwapStrengthRange: document.querySelector("#imageFaceSwapStrengthRange"),
    faceSwapStrength: document.querySelector("#imageFaceSwapStrength"),
    faceRestoreModel: document.querySelector("#imageFaceRestoreModel"),
    faceRestoreVisibility: document.querySelector("#imageFaceRestoreVisibility"),
    faceRestoreNote: document.querySelector("#imageFaceRestoreNote"),
    faceLicenseNote: document.querySelector("#imageFaceLicenseNote"),
    faceBatchTargets: document.querySelector("#imageFaceBatchTargets"),
    faceBatchSummary: document.querySelector("#imageFaceBatchSummary"),
    faceBatchSubmit: document.querySelector("#imageFaceBatchSubmitButton"),
    faceBatchStatus: document.querySelector("#imageFaceBatchStatus"),
    editFollowSize: document.querySelector("#imageEditFollowSize"),
    editResizeField: document.querySelector("#imageEditResizeField"),
    editResizeMode: document.querySelector("#imageEditResizeMode"),
    editStrengthField: document.querySelector("#imageEditStrengthField"),
    editStrengthRange: document.querySelector("#imageEditStrengthRange"),
    editStrength: document.querySelector("#imageEditStrength"),
    editStrengthHelp: document.querySelector("#imageEditStrengthHelp"),
    editAdherenceStatus: document.querySelector("#imageEditAdherenceStatus"),
    storagePreset: document.querySelector("#imageStoragePreset"),
    downloadPath: document.querySelector("#imageDownloadPath"),
    storageNote: document.querySelector("#imageStorageNote"),
    installPanel: document.querySelector("#imageInstallPanel"),
    installState: document.querySelector("#imageInstallState"),
    installProgress: document.querySelector("#imageInstallProgress"),
    installProgressBar: document.querySelector("#imageInstallProgressBar"),
    installSummary: document.querySelector("#imageInstallSummary"),
    installMetrics: document.querySelector("#imageInstallMetrics"),
    installFiles: document.querySelector("#imageInstallFiles"),
    pauseInstall: document.querySelector("#imagePauseInstallButton"),
    resumeInstall: document.querySelector("#imageResumeInstallButton"),
    cancelInstall: document.querySelector("#imageCancelInstallButton"),
    nsfw: document.querySelector("#imageNsfwToggle"),
    nsfwStatus: document.querySelector("#imageNsfwStatus"),
    nsfwStrengthField: document.querySelector("#imageNsfwStrengthField"),
    nsfwStrengthRange: document.querySelector("#imageNsfwStrengthRange"),
    nsfwStrength: document.querySelector("#imageNsfwStrength"),
    nsfwStrengthHelp: document.querySelector("#imageNsfwStrengthHelp"),
    installNsfw: document.querySelector("#imageInstallNsfwButton"),
    nsfwSource: document.querySelector("#imageNsfwSource"),
    nsfwPanel: document.querySelector("#imageNsfwPanel"),
    nsfwExtras: document.querySelector("#imageNsfwExtras"),
    nsfwWizard: document.querySelector("#imageNsfwWizard"),
    adultRecipeChips: document.querySelector("#imageAdultRecipeChips"),
    adultRecipeHint: document.querySelector("#imageAdultRecipeHint"),
    adultApplyGenerate: document.querySelector("#imageAdultApplyGenerateButton"),
    adultApplyVideo: document.querySelector("#imageAdultApplyVideoButton"),
    nsfwIntensitySwitch: document.querySelector("#imageNsfwIntensitySwitch"),
    nsfwIntensity: document.querySelector("#imageNsfwIntensity"),
    nsfwScenes: document.querySelector("#imageNsfwScenes"),
    faceStrengthPresets: document.querySelector("#imageFaceStrengthPresets"),
    advancedModuleList: document.querySelector("#imageAdvancedModuleList"),
    advancedModulesSummary: document.querySelector("#imageAdvancedModulesSummary"),
    autoInjectTrigger: document.querySelector("#imageAutoInjectTrigger"),
    autoStripNegative: document.querySelector("#imageAutoStripNegative"),
    triggerPreview: document.querySelector("#imageTriggerPreview"),
    customTrigger: document.querySelector("#imageCustomTrigger"),
    tripleCompare: document.querySelector("#imageTripleCompare"),
    promptExpand: document.querySelector("#imagePromptExpand"),
    secondaryLoraName: document.querySelector("#imageSecondaryLoraName"),
    secondaryLoraStrength: document.querySelector("#imageSecondaryLoraStrength"),
    regionalPanel: document.querySelector("#imageRegionalPanel"),
    regionalFacePrompt: document.querySelector("#imageRegionalFacePrompt"),
    regionalBodyPrompt: document.querySelector("#imageRegionalBodyPrompt"),
    regionalStatus: document.querySelector("#imageRegionalStatus"),
    poseControlPanel: document.querySelector("#imagePoseControlPanel"),
    poseMapFile: document.querySelector("#imagePoseMapFile"),
    poseMapFilename: document.querySelector("#imagePoseMapFilename"),
    poseMapStatus: document.querySelector("#imagePoseMapStatus"),
    controlnetName: document.querySelector("#imageControlnetName"),
    controlnetStrength: document.querySelector("#imageControlnetStrength"),
    editStrengthPresetField: document.querySelector("#imageEditStrengthPresetField"),
    editStrengthSwitch: document.querySelector("#imageEditStrengthSwitch"),
    editStrengthInlineSwitch: document.querySelector("#imageEditStrengthInlineSwitch"),
    editStrengthPreset: document.querySelector("#imageEditStrengthPreset"),
    compareWallButton: document.querySelector("#imageCompareWallButton"),
    historyFilters: document.querySelector("#imageHistoryFilters"),
    characterBoxSummary: document.querySelector("#imageCharacterBoxSummary"),
    characterBoxList: document.querySelector("#imageCharacterBoxList"),
    characterSave: document.querySelector("#imageCharacterSaveButton"),
    characterClear: document.querySelector("#imageCharacterClearButton"),
    characterStatus: document.querySelector("#imageCharacterBoxStatus"),
    characterPanel: document.querySelector("#imageCharacterPanel"),
    characterIdentityFile: document.querySelector("#imageCharacterIdentityFile"),
    characterIdentityPreview: document.querySelector("#imageCharacterIdentityPreview"),
    characterExtract: document.querySelector("#imageCharacterExtractButton"),
    characterGotoFaceSwap: document.querySelector("#imageCharacterUseFaceSwapButton"),
    promptSection: document.querySelector("#imagePromptSection"),
    prompt: document.querySelector("#imagePrompt"),
    promptLabel: document.querySelector("#imagePromptLabel"),
    promptCount: document.querySelector("#imagePromptCount"),
    promptModes: document.querySelector("#imagePromptModes"),
    exactText: document.querySelector("#imageExactText"),
    style: document.querySelector("#imageStylePreset"),
    batchSwitch: document.querySelector("#imageBatchSwitch"),
    batchSize: document.querySelector("#imageBatchSize"),
    generationModeSwitch: document.querySelector("#imageGenerationModeSwitch"),
    generationMode: document.querySelector("#imageGenerationMode"),
    batchModeNote: document.querySelector("#imageBatchModeNote"),
    aspectGrid: document.querySelector("#imageAspectGrid"),
    aspect: document.querySelector("#imageAspect"),
    width: document.querySelector("#imageWidth"),
    height: document.querySelector("#imageHeight"),
    swapSize: document.querySelector("#imageSwapSizeButton"),
    resolutionNote: document.querySelector("#imageResolutionNote"),
    qualityPresets: document.querySelector("#imageQualityPresets"),
    stepsRange: document.querySelector("#imageStepsRange"),
    stepsNote: document.querySelector("#imageStepsNote"),
    negative: document.querySelector("#imageNegative"),
    steps: document.querySelector("#imageSteps"),
    cfg: document.querySelector("#imageCfg"),
    sampler: document.querySelector("#imageSampler"),
    scheduler: document.querySelector("#imageScheduler"),
    seed: document.querySelector("#imageSeed"),
    randomSeed: document.querySelector("#imageRandomSeedButton"),
    effectivePrompt: document.querySelector("#imageEffectivePrompt"),
    generate: document.querySelector("#imageGenerateButton"),
    reuse: document.querySelector("#imageReuseButton"),
    resultHint: document.querySelector("#imageResultHint"),
    jobStatus: document.querySelector("#imageJobStatus"),
    jobMeta: document.querySelector("#imageJobMeta"),
    outputForm: document.querySelector("#imageOutputForm"),
    outputSubdir: document.querySelector("#imageOutputSubdir"),
    outputPath: document.querySelector("#imageOutputPath"),
    outputPathButton: document.querySelector("#imageOutputPathButton"),
    outputSave: document.querySelector("#imageOutputSaveButton"),
    openOutput: document.querySelector("#imageOpenOutputButton"),
    progressShell: document.querySelector("#imageProgressShell"),
    progress: document.querySelector("#imageProgressBar"),
    progressLabel: document.querySelector("#imageProgressLabel"),
    progressPercent: document.querySelector("#imageProgressPercent"),
    cancelJob: document.querySelector("#imageCancelJobButton"),
    taskQueueCount: document.querySelector("#imageTaskQueueCount"),
    taskQueueList: document.querySelector("#imageTaskQueueList"),
    resultStage: document.querySelector("#imageResultStage"),
    resultActions: document.querySelector("#imageResultActions"),
    editResult: document.querySelector("#imageEditResultButton"),
    faceSwapResult: document.querySelector("#imageFaceSwapResultButton"),
    toVideo: document.querySelector("#imageToVideoButton"),
    stillToVideo: document.querySelector("#imageStillToVideoButton"),
    downloadAll: document.querySelector("#imageDownloadAllButton"),
    repeat: document.querySelector("#imageRepeatButton"),
    log: document.querySelector("#imageStudioLog"),
    historyRefresh: document.querySelector("#imageHistoryRefreshButton"),
    historySelectAll: document.querySelector("#imageHistorySelectAll"),
    historyDelete: document.querySelector("#imageHistoryDeleteButton"),
    historyGrid: document.querySelector("#imageHistoryGrid"),
    historySection: document.querySelector(".image-history-section"),
    historyPagination: document.querySelector("#imageHistoryPagination"),
    historyPageSummary: document.querySelector("#imageHistoryPageSummary"),
    historyPageNumbers: document.querySelector("#imageHistoryPageNumbers"),
    historyPrev: document.querySelector("#imageHistoryPrevButton"),
    historyNext: document.querySelector("#imageHistoryNextButton"),
    faceAuthModal: document.querySelector("#imageFaceAuthModal"),
    faceAuthBackdrop: document.querySelector("#imageFaceAuthBackdrop"),
    faceAuthClose: document.querySelector("#imageFaceAuthCloseButton"),
    faceAuthCancel: document.querySelector("#imageFaceAuthCancelButton"),
    faceAuthCheckbox: document.querySelector("#imageFaceAuthCheckbox"),
    faceAuthConfirm: document.querySelector("#imageFaceAuthConfirmButton"),
  };

  const STORAGE = {
    activeJob: "imageStudio.activeJob.v1",
    activeJobs: "imageStudio.activeJobs.v2",
    lastParams: "imageStudio.lastParams.v1",
    installJob: "imageStudio.installJob.v1",
    downloadPath: "modelDownloadPath.v1",
    advancedModules: "local-ai-workbench.image.advancedModules",
    faceAuthToken: "local-ai-workbench.face.authToken",
    adultWizard: "local-ai-workbench.adult.wizardId",
  };
  const LEGACY_STORAGE = {
    advancedModules: "wan22.image.advancedModules",
    faceAuthToken: "wan22.face.authToken",
  };
  Object.entries(LEGACY_STORAGE).forEach(([name, legacyKey]) => {
    if (localStorage.getItem(STORAGE[name]) == null && localStorage.getItem(legacyKey) != null) {
      localStorage.setItem(STORAGE[name], localStorage.getItem(legacyKey));
    }
  });
  const TERMINAL = new Set(["success", "failed", "error", "lost", "canceled", "cancelled", "interrupted"]);
  const HISTORY_PAGE_SIZE = 20;

  let bootstrap = null;
  let activeJobId = "";
  const activeJobIds = new Set();
  const jobCache = new Map();
  let activeEvents = null;
  let pollTimer = null;
  let pollInFlight = false;
  let submitting = false;
  let installTimer = null;
  let promptTimer = null;
  let workflowTimer = null;
  let latestMedia = [];
  let latestJob = null;
  let initialized = false;
  let savedTopModel = "";
  let savedTopModelTitle = "";
  let installArmed = false;
  let installArmedProfile = "";
  let installArmTimer = null;
  let storageTimer = null;
  const selectedHistoryItems = new Set();
  const historySelectionPayload = new Map();
  let historyPage = 1;
  let historyPagination = { page: 1, page_size: HISTORY_PAGE_SIZE, total: 0, total_pages: 1 };
  let historyLoading = false;
  let historyDeleteArmed = false;
  let historyDeleteArmTimer = null;
  let editSource = null;
  let editObjectUrl = "";
  let editReferenceFiles = [];
  let editStrengthProfile = "";
  let identityFaceSource = null;
  let identityFaceObjectUrl = "";
  let targetFaceExtraction = null;
  let identityFaceExtraction = null;
  let faceExtractionBusy = false;
  let faceAuthorizationConfirmed = false;
  let batchFaceTargets = [];
  let batchFaceSubmitting = false;
  let pendingBatchFaceSwap = false;
  let pendingCharacterExtract = false;
  let pendingCharacterSave = false;
  let faceModalReturnFocus = null;
  let faceStatusOverride = null;
  let imageModelDownloadPath = "";
  let activeInstallJob = null;
  let compareWallEnabled = false;
  let historyFilter = "all";
  let poseMapUploadBusy = false;

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function formatError(detail) {
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object") {
      const parts = [detail.message, ...(detail.errors || []), ...(detail.actions || [])].filter(Boolean);
      if (parts.length) return parts.join("\n");
    }
    return JSON.stringify(detail, null, 2);
  }

  async function jsonRequest(url, options = {}) {
    const response = await fetch(url, options);
    let data;
    try {
      data = await response.json();
    } catch (_error) {
      data = { detail: "接口返回了无法解析的响应。" };
    }
    if (!response.ok) throw new Error(formatError(data.detail || data));
    return data;
  }

  function setLog(message = "") {
    refs.log.textContent = message;
  }

  function setModelStatus(state, message) {
    refs.modelStatus.className = `workflow-status ${state}`;
    refs.modelStatus.textContent = message;
  }

  function setProgress(jobOrStatus = {}) {
    const job = typeof jobOrStatus === "string" ? { status: jobOrStatus } : jobOrStatus;
    const status = String(job.status || "idle").toLowerCase();
    const detail = job.progress || {};
    let percent = Number(detail.percent);
    if (!Number.isFinite(percent)) percent = status === "success" ? 100 : 0;
    percent = Math.max(0, Math.min(100, percent));
    refs.progress.className = "progress-bar";
    refs.progress.style.width = `${percent}%`;
    if (status === "success") {
      refs.progress.classList.add("success");
    } else if (TERMINAL.has(status)) {
      refs.progress.classList.add("failed");
    } else if (status === "running" || status === "queued" || status === "reconnecting") {
      refs.progress.classList.add("running");
    }
    const fallbackLabel = {
      queued: "等待 ComfyUI 开始采样",
      running: "正在生成",
      reconnecting: "正在恢复 ComfyUI 连接",
      success: "图片生成完成",
      failed: "图片生成失败",
      idle: "等待生成",
    }[status] || "等待生成";
    refs.progressLabel.textContent = detail.label || fallbackLabel;
    refs.progressPercent.textContent = `${percent.toFixed(percent % 1 ? 1 : 0)}%`;
    refs.progressShell.setAttribute("aria-valuenow", String(Math.round(percent)));
  }

  function activeProfile() {
    return (bootstrap?.profiles || []).find((item) => item.id === refs.profile.value) || bootstrap?.profiles?.[0] || null;
  }

  function isEditMode() {
    return refs.editMode.value === "true";
  }

  function isFaceSwap() {
    return isEditMode() && refs.editOperation.value === "face_swap";
  }

  function activeEditCapability() {
    return activeProfile()?.image_edit || { supported: false, ready: false, label: "暂不支持", graph_errors: [] };
  }

  function activeProfileReady() {
    if (isFaceSwap()) return Boolean(bootstrap?.face_swap?.ready);
    return Boolean(isEditMode() ? activeEditCapability().ready : activeProfile()?.ready);
  }

  function hasEditSource() {
    return Boolean(editSource?.file || refs.editSourceFilename.value);
  }

  function maximumAdditionalReferences() {
    return Math.max(0, Number(activeEditCapability().max_reference_images || 1) - 1);
  }

  function supportsAdditionalReferences() {
    return isEditMode() && !isFaceSwap() && maximumAdditionalReferences() > 0;
  }

  function hasIdentityFaceSource() {
    return Boolean(identityFaceSource?.file || identityFaceSource?.filename);
  }

  function faceSourceReady() {
    return !isFaceSwap() || Boolean(
      faceAuthorizationConfirmed
      && targetFaceExtraction?.id
      && identityFaceExtraction?.id
      && Number(refs.faceIndex.value) >= 0
      && Number(refs.identityFaceIndex.value) >= 0
    );
  }

  function fitImageDimensions(width, height, maximum = Number(activeProfile()?.max_dimension || 2048)) {
    const profile = activeProfile() || {};
    const maximumPixels = Number(profile.max_pixels || 0);
    const multiple = Math.max(1, Number(profile.dimension_multiple || 16));
    const requestedWidth = Math.max(512, Number(width) || 512);
    const requestedHeight = Math.max(512, Number(height) || 512);
    let scale = Math.min(1, maximum / requestedWidth, maximum / requestedHeight);
    if (maximumPixels > 0 && requestedWidth * requestedHeight > maximumPixels) {
      scale = Math.min(scale, Math.sqrt(maximumPixels / (requestedWidth * requestedHeight)));
    }
    const align = (value) => Math.max(512, Math.min(maximum, Math.round(value / multiple) * multiple));
    let fittedWidth = align(requestedWidth * scale);
    let fittedHeight = align(requestedHeight * scale);
    if (maximumPixels > 0 && fittedWidth * fittedHeight > maximumPixels) {
      const pixelScale = Math.sqrt(maximumPixels / (fittedWidth * fittedHeight));
      fittedWidth = Math.max(512, Math.min(maximum, Math.floor((fittedWidth * pixelScale) / multiple) * multiple));
      fittedHeight = Math.max(512, Math.min(maximum, Math.floor((fittedHeight * pixelScale) / multiple) * multiple));
    }
    return {
      width: fittedWidth,
      height: fittedHeight,
    };
  }

  function clearEditObjectUrl() {
    if (editObjectUrl) URL.revokeObjectURL(editObjectUrl);
    editObjectUrl = "";
  }

  function applyEditSourceDimensions(width, height) {
    const numericWidth = Number(width);
    const numericHeight = Number(height);
    if (!refs.editFollowSize.checked || !numericWidth || !numericHeight) return;
    const fitted = fitImageDimensions(numericWidth, numericHeight);
    selectAspect("custom", fitted.width, fitted.height);
  }

  function renderEditSource() {
    if (!editSource?.url) {
      refs.editPreview.innerHTML = '<p>也可以在下方“最近生成”中点击“微调”。</p>';
      refs.editClear.classList.add("hidden");
      updateGenerateState();
      return;
    }
    const size = editSource.width && editSource.height ? ` · ${editSource.width} × ${editSource.height}` : "";
    refs.editPreview.innerHTML = `<img src="${escapeHtml(editSource.url)}" alt="源图片预览" /><figcaption>${escapeHtml(editSource.label || "源图片")}${escapeHtml(size)}</figcaption>`;
    refs.editClear.classList.remove("hidden");
    updateGenerateState();
  }

  function renderReferenceImages() {
    if (!refs.referencePanel) return;
    const visible = supportsAdditionalReferences();
    const maximum = maximumAdditionalReferences();
    refs.referencePanel.classList.toggle("hidden", !visible);
    if (!visible) return;
    if (editReferenceFiles.length > maximum) editReferenceFiles = editReferenceFiles.slice(0, maximum);
    const total = editReferenceFiles.length;
    refs.referenceHint.textContent = `目标图固定为 <image1>；最多再选 ${maximum} 张，依次对应 <image2> 到 <image${maximum + 1}>。`;
    refs.referenceSummary.textContent = total
      ? `已选择 ${total} 张附加参考图；连同目标图共 ${total + 1} 张。提示词可直接引用对应的 <imageN>。`
      : "尚未添加附加参考图。只改目标图时可以留空。";
    refs.referenceList.innerHTML = editReferenceFiles
      .map((file, index) => `<span title="${escapeHtml(file.name)}">&lt;image${index + 2}&gt; · ${escapeHtml(file.name)}</span>`)
      .join("");
    refs.referenceClear.classList.toggle("hidden", total === 0);
  }

  function inspectEditSource(source) {
    const image = new Image();
    image.onload = () => {
      if (editSource !== source) return;
      source.width = image.naturalWidth;
      source.height = image.naturalHeight;
      renderEditSource();
      applyEditSourceDimensions(source.width, source.height);
    };
    image.onerror = () => {
      if (editSource === source) setLog("源图片预览读取失败，请重新选择图片。");
    };
    image.src = source.url;
  }

  function faceCapability() {
    return bootstrap?.face_extraction || { available: false, error: "面部提取能力尚未加载。" };
  }

  function faceSwapCapability() {
    return bootstrap?.face_swap || {
      ready: false,
      errors: ["换脸组件状态尚未加载。"],
      restore_models: [],
      strength_options: ["0%", "12.5%", "25%", "37.5%", "50%", "62.5%", "75%", "87.5%", "100%"],
    };
  }

  function cloneEditSource(source) {
    if (!source) return null;
    const clone = { ...source };
    if (clone.file) delete clone.url;
    return clone;
  }

  function setFaceStatus(kind, message, source = "manual") {
    faceStatusOverride = { kind, message, source };
    refs.faceStatus.className = `workflow-status ${kind}`;
    refs.faceStatus.textContent = message;
  }

  function renderFaceCandidates(role) {
    const identity = role === "identity";
    const container = identity ? refs.identityFaceCandidates : refs.faceCandidates;
    const extraction = identity ? identityFaceExtraction : targetFaceExtraction;
    const selected = Number(identity ? refs.identityFaceIndex.value : refs.faceIndex.value);
    const faces = extraction?.faces || [];
    if (!faces.length) {
      container.innerHTML = `<p>${faceExtractionBusy ? "正在本机检测面部。" : identity ? "等待检测身份参考图。" : "等待检测目标图。"}</p>`;
      return;
    }
    container.innerHTML = faces.map((face) => `
      <button class="image-face-candidate${Number(face.index) === selected ? " active" : ""}" type="button" role="listitem" data-face-role="${identity ? "identity" : "target"}" data-face-index="${Number(face.index)}" aria-pressed="${Number(face.index) === selected ? "true" : "false"}">
        <img src="${escapeHtml(face.url)}" alt="${escapeHtml(face.label || `面部 ${Number(face.index) + 1}`)}" />
        <span><strong>${escapeHtml(face.label || `面部 ${Number(face.index) + 1}`)}</strong><small>${Number(face.width) || "?"} × ${Number(face.height) || "?"}</small></span>
      </button>
    `).join("");
  }

  function clearIdentityFaceObjectUrl() {
    if (identityFaceObjectUrl) URL.revokeObjectURL(identityFaceObjectUrl);
    identityFaceObjectUrl = "";
  }

  function renderIdentityFaceSource() {
    if (!identityFaceSource?.url) {
      refs.identityFacePreview.innerHTML = "<p>尚未选择身份参考图。</p>";
      refs.identityFaceClear.classList.add("hidden");
      return;
    }
    refs.identityFacePreview.innerHTML = `<img src="${escapeHtml(identityFaceSource.url)}" alt="身份参考图预览" /><figcaption>${escapeHtml(identityFaceSource.label || "身份参考图")}</figcaption>`;
    refs.identityFaceClear.classList.remove("hidden");
  }

  function clearFaceExtractionState({ target = true, identity = true, resetAuthorization = true } = {}) {
    if (target) {
      targetFaceExtraction = null;
      refs.faceExtractId.value = "";
      refs.faceIndex.value = "-1";
    }
    if (identity) {
      identityFaceExtraction = null;
      refs.identityFaceExtractId.value = "";
      refs.identityFaceIndex.value = "-1";
    }
    if (resetAuthorization) {
      faceAuthorizationConfirmed = false;
      refs.faceAuthorization.value = "false";
    }
    faceStatusOverride = null;
    renderFaceSwapPanel();
  }

  function setIdentityFaceSource(source = null) {
    clearIdentityFaceObjectUrl();
    identityFaceSource = source;
    refs.identityFaceFile.value = "";
    if (source?.file) {
      identityFaceObjectUrl = URL.createObjectURL(source.file);
      source.url = identityFaceObjectUrl;
    }
    clearFaceExtractionState({ target: false, identity: true, resetAuthorization: true });
    renderIdentityFaceSource();
    renderCharacterIdentityPreview();
    updateGenerateState();
  }

  function setEditSource(source = null) {
    refs.sourceProcessing.value = "full";
    clearFaceExtractionState({ target: true, identity: false, resetAuthorization: true });
    clearEditObjectUrl();
    editSource = source;
    if (!source) {
      refs.editFile.value = "";
      refs.editSourceFilename.value = "";
      refs.editSourceSubfolder.value = "";
      refs.editSourceType.value = "";
      renderEditSource();
      scheduleWorkflowCheck();
      return;
    }
    if (source.file) {
      editObjectUrl = URL.createObjectURL(source.file);
      source.url = editObjectUrl;
      refs.editSourceFilename.value = "";
      refs.editSourceSubfolder.value = "";
      refs.editSourceType.value = "";
    } else {
      refs.editFile.value = "";
      refs.editSourceFilename.value = source.filename || "";
      refs.editSourceSubfolder.value = source.subfolder || "";
      refs.editSourceType.value = source.type || "output";
    }
    renderEditSource();
    inspectEditSource(source);
    scheduleWorkflowCheck();
  }

  function faceInstallIsActive(capability = faceSwapCapability()) {
    const profile = String(activeInstallJob?.profile || activeInstallJob?.install_profile || "");
    const status = String(activeInstallJob?.status || "").toLowerCase();
    return profile === String(capability.install_profile || "")
      && (!activeInstallJob?.completed || ["paused", "interrupted"].includes(status));
  }

  function renderFaceSwapPanel() {
    const active = isFaceSwap();
    const capability = faceSwapCapability();
    const extraction = faceCapability();
    if (capability.ready && faceStatusOverride?.source === "install") faceStatusOverride = null;
    refs.faceOptions.classList.toggle("hidden", !active);
    refs.instructionEditSettings.classList.toggle("hidden", active);
    if (!active) return;
    refs.faceEngineSource.href = capability.source_url || "https://github.com/Gourieff/ComfyUI-ReActor";
    refs.faceEngineNote.textContent = capability.ready
      ? `已加载 ${capability.swap_models?.[0] || "换脸模型"}`
      : (capability.errors || [])[0] || "换脸组件待准备。";
    refs.faceLicenseNote.textContent = capability.license_note || "";
    const installActive = faceInstallIsActive(capability);
    const installStatus = String(activeInstallJob?.status || "").toLowerCase();
    refs.faceInstall.disabled = Boolean(capability.ready || installActive);
    refs.faceInstall.textContent = capability.ready
      ? "换脸组件已就绪"
      : installArmed && installArmedProfile === capability.install_profile
        ? "确认下载换脸组件"
        : installActive
          ? ["paused", "interrupted"].includes(installStatus) ? "换脸组件下载已暂停" : "换脸组件准备中"
          : "准备换脸组件";
    const currentRestore = refs.faceRestoreModel.value || capability.default_restore_model || "none";
    const restoreModels = [...new Set(["none", ...(capability.restore_models || [])])];
    refs.faceRestoreModel.innerHTML = restoreModels
      .map((name) => `<option value="${escapeHtml(name)}">${name === "none" ? "不额外修复" : escapeHtml(name)}</option>`)
      .join("");
    refs.faceRestoreModel.value = restoreModels.includes(currentRestore) ? currentRestore : "none";
    const restoreEnabled = refs.faceRestoreModel.value !== "none";
    refs.faceRestoreVisibility.disabled = !restoreEnabled;
    refs.faceRestoreNote.textContent = restoreEnabled
      ? "仅控制修复结果与换脸结果的融合比例。"
      : "选择面部修复模型后生效。";
    const strengthValues = (capability.strength_options || [])
      .map((item) => Number.parseFloat(String(item)))
      .filter((item) => Number.isFinite(item));
    if (strengthValues.length) {
      const minimum = Math.min(...strengthValues);
      const maximum = Math.max(...strengthValues);
      refs.faceSwapStrength.min = String(minimum);
      refs.faceSwapStrength.max = String(maximum);
      refs.faceSwapStrengthRange.min = String(minimum);
      refs.faceSwapStrengthRange.max = String(maximum);
    }
    refs.faceRetry.disabled = faceExtractionBusy || !faceAuthorizationConfirmed || !hasEditSource() || !extraction.available;
    refs.identityFaceRetry.disabled = faceExtractionBusy || !faceAuthorizationConfirmed || !hasIdentityFaceSource() || !extraction.available;
    refs.faceAnalyze.disabled = faceExtractionBusy || !hasEditSource() || !hasIdentityFaceSource() || !extraction.available;
    if (refs.faceBatchSubmit) {
      refs.faceBatchSubmit.disabled = batchFaceSubmitting || !batchFaceTargets.length || !hasIdentityFaceSource() || !extraction.available || !capability.ready;
      refs.faceBatchSubmit.textContent = batchFaceSubmitting
        ? "正在检测并提交批量任务"
        : `确认授权并批量提交${batchFaceTargets.length ? `（${batchFaceTargets.length} 张）` : ""}`;
    }
    renderFaceCandidates("target");
    renderFaceCandidates("identity");
    if (faceStatusOverride) {
      refs.faceStatus.className = `workflow-status ${faceStatusOverride.kind}`;
      refs.faceStatus.textContent = faceStatusOverride.message;
    } else if (faceExtractionBusy) {
      refs.faceStatus.className = "workflow-status pending";
      refs.faceStatus.textContent = "正在本机检测目标图与身份参考图。";
    } else if (!extraction.available) {
      refs.faceStatus.className = "workflow-status bad";
      refs.faceStatus.textContent = extraction.error || "当前前端环境无法检测面部。";
    } else if (installActive) {
      refs.faceStatus.className = "workflow-status pending";
      refs.faceStatus.textContent = ["paused", "interrupted"].includes(installStatus)
        ? "换脸组件下载已暂停，可在模型下载区域继续。"
        : "正在准备换脸节点和本地模型，当前不会提交换脸任务。";
    } else if (!capability.ready) {
      refs.faceStatus.className = "workflow-status pending";
      refs.faceStatus.textContent = `${(capability.errors || [])[0] || "换脸组件待准备。"} 可先选择图片，组件完成后再提交。`;
    } else if (!hasEditSource() || !hasIdentityFaceSource()) {
      refs.faceStatus.className = "workflow-status pending";
      refs.faceStatus.textContent = "请准备目标图和身份参考图。";
    } else if (!faceSourceReady()) {
      refs.faceStatus.className = "workflow-status pending";
      refs.faceStatus.textContent = "确认授权并检测双方，然后分别选择一张脸。";
    } else {
      refs.faceStatus.className = "workflow-status ok";
      refs.faceStatus.textContent = "目标脸与身份参考脸均已选定，可以提交换脸。";
    }
  }

  function closeFaceAuthorizationModal({ returnFocus = true } = {}) {
    refs.faceAuthModal.classList.add("hidden");
    if (!document.querySelector(".source-modal:not(.hidden)")) document.body.classList.remove("modal-open");
    if (returnFocus) faceModalReturnFocus?.focus?.({ preventScroll: true });
    faceModalReturnFocus = null;
  }

  function openFaceAuthorizationModal(trigger = null) {
    faceModalReturnFocus = trigger || document.activeElement;
    refs.faceAuthCheckbox.checked = false;
    refs.faceAuthConfirm.disabled = true;
    refs.faceAuthModal.classList.remove("hidden");
    document.body.classList.add("modal-open");
    window.setTimeout(() => refs.faceAuthCheckbox.focus(), 0);
  }

  function selectFaceCandidate(role, index) {
    const identity = role === "identity";
    const extraction = identity ? identityFaceExtraction : targetFaceExtraction;
    const face = (extraction?.faces || []).find((item) => Number(item.index) === Number(index));
    if (!face) return;
    if (identity) {
      refs.identityFaceExtractId.value = extraction.id;
      refs.identityFaceIndex.value = String(face.index);
    } else {
      refs.faceExtractId.value = extraction.id;
      refs.faceIndex.value = String(face.index);
    }
    faceStatusOverride = null;
    renderFaceCandidates(identity ? "identity" : "target");
    renderFaceSwapPanel();
    updateGenerateState();
  }

  async function requestFaceExtraction(source) {
    const payload = new FormData();
    payload.append("authorization_confirmed", "true");
    payload.append("crop_mode", "face");
    if (source.file) {
      payload.append("source_image", source.file, source.file.name);
    } else {
      payload.append("source_image_filename", source.filename || "");
      payload.append("source_image_subfolder", source.subfolder || "");
      payload.append("source_image_type", source.type || "output");
    }
    return jsonRequest("/api/image-studio/face-extract", { method: "POST", body: payload });
  }

  async function extractFaces(role = "both") {
    if (faceExtractionBusy || !faceAuthorizationConfirmed) return;
    const detectTarget = role === "both" || role === "target";
    const detectIdentity = role === "both" || role === "identity";
    if ((detectTarget && !hasEditSource()) || (detectIdentity && !hasIdentityFaceSource())) {
      setFaceStatus("bad", "请先准备目标图和身份参考图。 ");
      return;
    }
    faceExtractionBusy = true;
    faceStatusOverride = null;
    renderFaceSwapPanel();
    updateGenerateState();
    try {
      const requests = [];
      if (detectTarget) requests.push(requestFaceExtraction(editSource).then((data) => ({ role: "target", data })));
      if (detectIdentity) requests.push(requestFaceExtraction(identityFaceSource).then((data) => ({ role: "identity", data })));
      const results = await Promise.all(requests);
      for (const result of results) {
        if (result.data.authorization?.token) storeFaceAuthToken(result.data.authorization.token);
        if (result.role === "target") {
          targetFaceExtraction = result.data;
          refs.faceExtractId.value = result.data.id;
          refs.faceIndex.value = String(result.data.selected_index ?? result.data.faces?.[0]?.index ?? -1);
        } else {
          identityFaceExtraction = result.data;
          refs.identityFaceExtractId.value = result.data.id;
          refs.identityFaceIndex.value = String(result.data.selected_index ?? result.data.faces?.[0]?.index ?? -1);
          if (result.data.original?.filename) {
            identityFaceSource = {
              ...(identityFaceSource || {}),
              filename: result.data.original.filename,
              subfolder: result.data.original.subfolder || "",
              type: result.data.original.type || "input",
              url: result.data.original.url || identityFaceSource?.url || "",
              label: identityFaceSource?.label || result.data.original.filename,
              file: undefined,
            };
            renderIdentityFaceSource();
            renderCharacterIdentityPreview();
          }
        }
      }
      setFaceStatus("ok", "双方人脸检测完成，请确认目标脸与身份参考脸。 ");
      setLog("目标图与身份参考图已在本机完成面部检测。 ");
    } catch (error) {
      setFaceStatus("bad", error.message);
      setLog(`人脸检测失败：${error.message}`);
    } finally {
      faceExtractionBusy = false;
      renderFaceSwapPanel();
      updateGenerateState();
    }
  }

  function requestFaceAuthorization(trigger = null) {
    if (!hasEditSource()) {
      refs.editFile.focus();
      setLog("请先选择目标图。 ");
      return;
    }
    if (!hasIdentityFaceSource()) {
      refs.identityFaceFile.focus();
      setLog("请再选择一张身份参考图。 ");
      return;
    }
    if (!faceCapability().available) {
      setLog(faceCapability().error || "当前环境不支持面部检测。 ");
      return;
    }
    if (faceAuthorizationConfirmed) {
      void extractFaces("both");
      return;
    }
    openFaceAuthorizationModal(trigger);
  }

  function setBatchFaceStatus(message, kind = "pending") {
    if (!refs.faceBatchStatus) return;
    refs.faceBatchStatus.classList.remove("hidden", "ok", "bad", "pending");
    refs.faceBatchStatus.classList.add(kind);
    refs.faceBatchStatus.textContent = message;
  }

  function requestBatchFaceAuthorization() {
    if (!batchFaceTargets.length) {
      refs.faceBatchTargets?.focus();
      setLog("请先选择至少一张批量目标图。 ");
      return;
    }
    if (!hasIdentityFaceSource()) {
      refs.identityFaceFile.focus();
      setLog("批量换脸需要先选择一张身份参考图。 ");
      return;
    }
    if (!faceCapability().available || !faceSwapCapability().ready) {
      setBatchFaceStatus((faceSwapCapability().errors || [faceCapability().error || "换脸组件尚未就绪。"]).join(" "), "bad");
      return;
    }
    pendingBatchFaceSwap = true;
    if (faceAuthorizationConfirmed) {
      void submitBatchFaceSwaps();
      return;
    }
    openFaceAuthorizationModal(refs.faceBatchSubmit);
  }

  async function ensureBatchIdentityExtraction() {
    if (identityFaceExtraction?.id && Number(refs.identityFaceIndex.value) >= 0) return true;
    const data = await requestFaceExtraction(identityFaceSource);
    if (data.authorization?.token) storeFaceAuthToken(data.authorization.token);
    identityFaceExtraction = data;
    refs.identityFaceExtractId.value = data.id;
    refs.identityFaceIndex.value = String(data.selected_index ?? data.faces?.[0]?.index ?? -1);
    renderFaceCandidates("identity");
    return Boolean(data.id && Number(refs.identityFaceIndex.value) >= 0);
  }

  async function submitBatchFaceSwaps() {
    if (batchFaceSubmitting || !batchFaceTargets.length || !faceAuthorizationConfirmed) return;
    batchFaceSubmitting = true;
    pendingBatchFaceSwap = false;
    renderFaceSwapPanel();
    let submitted = 0;
    const failures = [];
    let lastJob = null;
    try {
      setBatchFaceStatus("正在提取身份参考脸。", "pending");
      if (!(await ensureBatchIdentityExtraction())) throw new Error("身份参考图中没有检测到可用人脸。");
      for (let index = 0; index < batchFaceTargets.length; index += 1) {
        const target = batchFaceTargets[index];
        setBatchFaceStatus(`正在处理 ${index + 1}/${batchFaceTargets.length}：${target.file.name}`, "pending");
        try {
          const extraction = await requestFaceExtraction(target);
          if (extraction.authorization?.token) storeFaceAuthToken(extraction.authorization.token);
          const targetIndex = extraction.selected_index ?? extraction.faces?.[0]?.index ?? -1;
          if (!extraction.id || Number(targetIndex) < 0) throw new Error("未检测到可用目标脸");
          const payload = new FormData();
          payload.append("authorization_confirmed", "true");
          const authToken = faceAuthTokenValue();
          if (authToken) payload.append("face_authorization_token", authToken);
          payload.append("target_face_extract_id", extraction.id);
          payload.append("target_face_index", String(targetIndex));
          payload.append("identity_face_extract_id", refs.identityFaceExtractId.value);
          payload.append("identity_face_index", refs.identityFaceIndex.value);
          payload.append("face_swap_strength", refs.faceSwapStrength.value);
          payload.append("face_restore_model", refs.faceRestoreModel.value || "none");
          payload.append("face_restore_visibility", refs.faceRestoreVisibility.value || "0.8");
          const job = await jsonRequest("/api/image-studio/face-swap", { method: "POST", body: payload });
          rememberActiveJob(job.id, job);
          lastJob = job;
          submitted += 1;
        } catch (error) {
          failures.push(`${target.file.name}：${error.message}`);
        }
      }
      if (lastJob) watchJob(lastJob.id);
      if (failures.length) {
        setBatchFaceStatus(`已提交 ${submitted} 张，${failures.length} 张失败。详情见日志。`, submitted ? "pending" : "bad");
        setLog(failures.join("\n"));
      } else {
        setBatchFaceStatus(`已提交 ${submitted} 个独立换脸任务，可在任务队列逐个查看或中断。`, "ok");
      }
    } catch (error) {
      setBatchFaceStatus(error.message, "bad");
      setLog(`批量换脸提交失败：${error.message}`);
    } finally {
      batchFaceSubmitting = false;
      renderFaceSwapPanel();
      renderTaskQueue();
    }
  }

  function selectEditOperation(value, { schedule = true } = {}) {
    const wasFaceSwap = form.classList.contains("is-face-swap");
    const operation = value === "face_swap" ? "face_swap" : "instruction";
    if (operation === "face_swap" && !wasFaceSwap) {
      imageModelDownloadPath = refs.downloadPath.value.trim() || localStorage.getItem(STORAGE.downloadPath) || "";
    }
    refs.editOperation.value = operation;
    refs.editOperationSwitch.querySelectorAll("button[data-image-edit-operation]").forEach((button) => {
      button.classList.toggle("active", button.dataset.imageEditOperation === operation);
    });
    form.classList.toggle("is-face-swap", operation === "face_swap" && isEditMode());
    refs.editSourceTitle.textContent = operation === "face_swap" ? "目标图片" : "源图片";
    refs.editOperationNote.textContent = operation === "face_swap"
      ? "保留目标图，只把选中的目标脸替换为另一张身份参考图中的脸。"
      : "按编辑要求重绘源图片，并控制对原图的遵循程度。";
    refs.editMethodNote.textContent = operation === "face_swap"
      ? "完整目标图不会进入扩散重绘；请选择身份参考图并分别选脸。"
      : `${activeEditCapability().label || "图片微调"}：${activeEditCapability().description || "使用源图片和编辑要求生成新图。"}`;
    refs.modelBar.classList.toggle("hidden", isFaceSwap());
    refs.modelStatus.classList.toggle("hidden", isFaceSwap());
    refs.profileDetails.classList.toggle("hidden", isFaceSwap());
    refs.installPanel.classList.remove("hidden");
    refs.nsfwPanel.classList.toggle("hidden", isFaceSwap());
    refs.promptSection.classList.toggle("hidden", isFaceSwap());
    refs.reuse.classList.toggle("hidden", isFaceSwap());
    refs.storagePreset.disabled = isFaceSwap();
    refs.downloadPath.disabled = isFaceSwap();
    if (isFaceSwap()) {
      const activePath = faceSwapCapability().install_base_dir || bootstrap?.active_base_dir || "";
      refs.downloadPath.value = activePath;
      refs.storageNote.textContent = "换脸组件必须安装到当前 ComfyUI 目录，完成后重启 8188 才会加载。";
    } else if (bootstrap) {
      if (wasFaceSwap && imageModelDownloadPath) refs.downloadPath.value = imageModelDownloadPath;
      renderStorageLocations(bootstrap);
    }
    renderFaceSwapPanel();
    renderReferenceImages();
    renderEditStrengthPresetSwitches();
    renderModelReadiness();
    updateGenerateState();
    if (schedule && !isFaceSwap()) scheduleWorkflowCheck();
  }

  function syncEditStrength(value, { schedule = true } = {}) {
    const minimum = Number(refs.editStrength.min || 0.05);
    const maximum = Number(refs.editStrength.max || 0.95);
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return;
    const normalized = Math.max(minimum, Math.min(maximum, numeric));
    refs.editStrength.value = String(normalized);
    refs.editStrengthRange.value = String(normalized);
    renderEditAdherenceStatus();
    if (schedule) {
      schedulePromptPreview();
      scheduleWorkflowCheck();
    }
  }

  function renderEditAdherenceStatus() {
    const capability = activeEditCapability();
    const adherence = Number(refs.editStrength.value || capability.adherence_default || 0.65);
    const percent = Math.round(adherence * 100);
    if (capability.adherence_mode === "numeric_inverse_denoise") {
      const denoise = Math.max(0, Math.min(1, 1 - adherence));
      refs.editAdherenceStatus.className = "workflow-status ok image-edit-adherence-status";
      refs.editAdherenceStatus.textContent = `数值遵循 ${percent}% · 实际 denoise ${denoise.toFixed(2)}；这是工作流中的真实采样参数，但扩散重绘仍不承诺逐像素不变。`;
    } else {
      refs.editAdherenceStatus.className = "workflow-status pending image-edit-adherence-status";
      refs.editAdherenceStatus.textContent = `语义遵循 ${percent}% · 当前模型没有像素级 denoise 控制，该值用于加强保留指令与参考图条件。`;
    }
  }

  function renderEditControls({ resetStrength = false } = {}) {
    const profile = activeProfile();
    const capability = activeEditCapability();
    if (!profile) return;
    const resizeSupported = Boolean(capability.resize_supported);
    const profileChanged = editStrengthProfile !== profile.id;
    editStrengthProfile = profile.id;
    refs.editPanel.classList.toggle("is-native-edit", capability.adherence_mode !== "numeric_inverse_denoise");
    refs.editStrength.disabled = false;
    refs.editStrengthRange.disabled = false;
    refs.editResizeMode.disabled = !resizeSupported;
    if (!isFaceSwap()) refs.editMethodNote.textContent = `${capability.label || "图片微调"}：${capability.description || "使用源图片和编辑要求生成新图。"}`;
    refs.editStrengthHelp.textContent = capability.adherence_help || "数值越高，未要求修改的内容越接近原图。";
    const minimum = Number(capability.adherence_min ?? 0.05);
    const maximum = Number(capability.adherence_max ?? 0.95);
    const step = Number(capability.adherence_step ?? 0.01);
    [refs.editStrength, refs.editStrengthRange].forEach((input) => {
      input.min = String(minimum);
      input.max = String(maximum);
      input.step = String(step);
    });
    if (resetStrength || profileChanged) syncEditStrength(capability.adherence_default ?? 0.65, { schedule: false });
    renderEditAdherenceStatus();
    renderReferenceImages();
    renderEditStrengthPresetSwitches();
  }

  function selectTaskMode(value, { schedule = true, refreshOptions = true } = {}) {
    const mode = value === "edit" ? "edit" : "t2i";
    if (mode !== "edit" && !refs.faceAuthModal.classList.contains("hidden")) {
      closeFaceAuthorizationModal({ returnFocus: false });
    }
    refs.editMode.value = mode === "edit" ? "true" : "false";
    refs.taskModeSwitch.querySelectorAll("button[data-image-task-mode]").forEach((button) => {
      button.classList.toggle("active", button.dataset.imageTaskMode === mode);
    });
    refs.editPanel.classList.toggle("hidden", mode !== "edit");
    refs.promptLabel.textContent = mode === "edit" ? "编辑要求" : "画面描述";
    refs.prompt.placeholder = mode === "edit" ? "例如：保留人物、机位和构图，只把背景改为雨夜霓虹街道" : "描述要生成的主体、场景、构图和光线";
    refs.taskModeNote.textContent = mode === "edit"
      ? "选择提示词重绘或换脸；目标图可从本机导入，也可直接使用最近生成结果。"
      : "只使用文字描述创建一张新图片。";
    if (refreshOptions) refreshProfileOptions();
    renderEditControls();
    selectEditOperation(mode === "edit" ? refs.editOperation.value : "instruction", { schedule: false });
    renderProfileDetails();
    renderModelReadiness();
    if (!isFaceSwap()) schedulePromptPreview();
    updateGenerateState();
    if (schedule && !isFaceSwap()) scheduleWorkflowCheck();
  }

  function updateResolutionNote() {
    const profile = activeProfile() || {};
    const maximum = Number(profile.max_dimension || 2048);
    const maximumPixels = Number(profile.max_pixels || 0);
    const multiple = Math.max(1, Number(profile.dimension_multiple || 16));
    const width = Number(refs.width.value) || 0;
    const height = Number(refs.height.value) || 0;
    const megapixels = width > 0 && height > 0 ? (width * height) / 1_000_000 : 0;
    const overLimit = width > maximum || height > maximum || (maximumPixels > 0 && width * height > maximumPixels);
    const mode = refs.aspect.value === "custom" ? "自定义尺寸" : "当前预设";
    const highResolution = megapixels >= 4 ? "；高分辨率会明显增加显存占用和生成时间" : "";
    const pixelLimit = maximumPixels > 0 ? `，像素上限约 ${(maximumPixels / 1_000_000).toFixed(2)} MP` : "";
    refs.resolutionNote.classList.toggle("warning", overLimit);
    refs.resolutionNote.textContent = `${mode} ${width || "-"} × ${height || "-"} · ${megapixels.toFixed(2)} MP；当前模型最大边 ${maximum} px${pixelLimit}，按 ${multiple} px 对齐${overLimit ? "，提交前将等比缩小" : ""}${highResolution}。`;
  }

  function updateResolutionAvailability(fitCurrent = true) {
    const profile = activeProfile() || {};
    const maximum = Number(profile.max_dimension || 2048);
    const maximumPixels = Number(profile.max_pixels || 0);
    refs.aspectGrid.querySelectorAll("button[data-aspect]").forEach((button) => {
      if (button.dataset.aspect === "custom") {
        button.disabled = false;
        return;
      }
      const presetWidth = Number(button.dataset.width);
      const presetHeight = Number(button.dataset.height);
      const unavailable = presetWidth > maximum || presetHeight > maximum || (maximumPixels > 0 && presetWidth * presetHeight > maximumPixels);
      button.disabled = unavailable;
      button.classList.toggle("unavailable", unavailable);
      button.title = unavailable ? `超出当前模型的尺寸或像素上限` : "";
    });
    const selectedButton = refs.aspectGrid.querySelector(`button[data-aspect="${CSS.escape(refs.aspect.value || "custom")}"]`);
    const currentPixels = Number(refs.width.value) * Number(refs.height.value);
    const overLimit = Number(refs.width.value) > maximum || Number(refs.height.value) > maximum || (maximumPixels > 0 && currentPixels > maximumPixels);
    if (fitCurrent && (selectedButton?.disabled || overLimit)) {
      const fitted = fitImageDimensions(refs.width.value, refs.height.value, maximum);
      refs.aspect.value = "custom";
      refs.width.value = String(fitted.width);
      refs.height.value = String(fitted.height);
      refs.aspectGrid.querySelectorAll("button[data-aspect]").forEach((button) => button.classList.toggle("active", button.dataset.aspect === "custom"));
    }
    updateResolutionNote();
  }

  function qualityStepPresets(profile) {
    if (profile.fixed_steps != null) return [{ label: "模型固定", value: Number(profile.fixed_steps) }];
    const minimum = Number(profile.min_steps || 1);
    const recommended = Number(profile.default_steps || minimum);
    const maximum = Number(profile.max_steps || Math.max(recommended, 100));
    const candidates = [
      ["快速", minimum],
      ["均衡", Math.round((minimum + recommended) / 2)],
      ["推荐", recommended],
      ["高质量", Math.round((recommended + maximum) / 2)],
      ["极致", maximum],
    ];
    const seen = new Set();
    return candidates
      .map(([label, value]) => ({ label, value: Math.max(minimum, Math.min(maximum, Number(value))) }))
      .filter((item) => !seen.has(item.value) && seen.add(item.value));
  }

  function syncQualityControls() {
    const profile = activeProfile();
    if (!profile) return;
    const fixed = profile.fixed_steps != null;
    const minimum = fixed ? Number(profile.fixed_steps) : Number(profile.min_steps || 1);
    const maximum = fixed ? Number(profile.fixed_steps) : Number(profile.max_steps || Math.max(profile.default_steps || 1, 100));
    const requested = fixed ? Number(profile.fixed_steps) : Number(refs.steps.value || profile.default_steps || minimum);
    const steps = Math.max(minimum, Math.min(maximum, Math.round(requested)));
    refs.steps.value = String(steps);
    refs.stepsRange.value = String(steps);
    refs.qualityPresets.querySelectorAll("button[data-steps]").forEach((button) => {
      button.classList.toggle("active", Number(button.dataset.steps) === steps);
    });
    refs.stepsNote.textContent = fixed
      ? `当前模型固定 ${steps} 步。`
      : `当前 ${steps} 步；可在 ${minimum} 到 ${maximum} 之间选择任意整数。`;
  }

  function previewQualityInput() {
    const profile = activeProfile();
    const value = Number(refs.steps.value);
    if (!profile || !Number.isFinite(value)) return;
    const minimum = Number(profile.min_steps || 1);
    const maximum = Number(profile.max_steps || Math.max(profile.default_steps || 1, 100));
    refs.stepsRange.value = String(Math.max(minimum, Math.min(maximum, Math.round(value))));
    refs.qualityPresets.querySelectorAll("button[data-steps]").forEach((button) => {
      button.classList.toggle("active", Number(button.dataset.steps) === value);
    });
    const outside = value < minimum || value > maximum;
    refs.stepsNote.textContent = outside
      ? `可选范围为 ${minimum} 到 ${maximum} 步，离开输入框后会自动校正。`
      : `当前 ${Math.round(value)} 步；可在 ${minimum} 到 ${maximum} 之间选择任意整数。`;
  }

  function renderQualityControls() {
    const profile = activeProfile();
    if (!profile) return;
    const fixed = profile.fixed_steps != null;
    const minimum = fixed ? Number(profile.fixed_steps) : Number(profile.min_steps || 1);
    const maximum = fixed ? Number(profile.fixed_steps) : Number(profile.max_steps || Math.max(profile.default_steps || 1, 100));
    refs.steps.min = String(minimum);
    refs.steps.max = String(maximum);
    refs.stepsRange.min = String(minimum);
    refs.stepsRange.max = String(maximum);
    refs.stepsRange.disabled = fixed;
    refs.steps.readOnly = fixed;
    refs.steps.closest("label")?.classList.toggle("field-fixed", fixed);
    refs.qualityPresets.innerHTML = qualityStepPresets(profile)
      .map(
        (item) => `<button type="button" data-steps="${item.value}"${fixed ? " disabled" : ""}>
          <strong>${escapeHtml(item.label)}</strong><small>${item.value} 步</small>
        </button>`,
      )
      .join("");
    syncQualityControls();
  }

  function formatGb(value, digits = 2) {
    return `${Number(value || 0).toFixed(digits)} GB`;
  }

  function formatEta(seconds) {
    const value = Number(seconds);
    if (!Number.isFinite(value) || value < 0) return "计算中";
    if (value < 60) return `${Math.max(1, Math.round(value))} 秒`;
    if (value < 3600) return `${Math.ceil(value / 60)} 分钟`;
    const hours = Math.floor(value / 3600);
    const minutes = Math.ceil((value % 3600) / 60);
    return `${hours} 小时 ${minutes} 分钟`;
  }

  function groupedProfileOptions(profiles, currentProfile) {
    const editMode = isEditMode();
    const groups = new Map();
    for (const item of profiles || []) {
      if (!groups.has(item.family)) groups.set(item.family, []);
      groups.get(item.family).push(item);
    }
    return [...groups.entries()]
      .map(
        ([family, items]) => `<optgroup label="${escapeHtml(family)}">${items
          .map(
            (item) => {
              const edit = item.image_edit || {};
              const supported = editMode ? Boolean(edit.supported) : item.generation_supported !== false;
              const ready = editMode ? edit.ready : item.ready;
              const state = !supported
                ? editMode
                  ? "不支持微调"
                  : "仅图片微调"
                : ready
                  ? editMode
                    ? "微调就绪"
                    : "就绪"
                  : "待准备";
              return `<option value="${escapeHtml(item.id)}"${item.id === currentProfile ? " selected" : ""}${supported ? "" : " disabled"}>${escapeHtml(item.short_label || item.label)} · ${escapeHtml(state)}</option>`;
            },
          )
          .join("")}</optgroup>`,
      )
      .join("");
  }

  function refreshProfileOptions() {
    if (!bootstrap?.profiles?.length) return;
    const current = refs.profile.value;
    refs.profile.innerHTML = groupedProfileOptions(bootstrap.profiles, current);
    if ([...refs.profile.options].some((option) => option.value === current && !option.disabled)) {
      refs.profile.value = current;
      return;
    }
    const first = [...refs.profile.options].find((option) => !option.disabled);
    if (first) refs.profile.value = first.value;
  }

  function renderProfileDetails() {
    const profile = activeProfile();
    if (!profile) return;
    if (refs.topModel && refs.viewTab?.classList.contains("active")) {
      refs.topModel.textContent = profile.label;
      refs.topModel.title = profile.label;
    }
    refs.profileName.textContent = profile.label;
    refs.profileDescription.textContent = profile.description || "";
    refs.profileTags.innerHTML = [
      profile.recommended ? "推荐" : "可选",
      profile.quantization,
      profile.released,
      isEditMode() ? activeEditCapability().label : "文字生成",
    ]
      .filter(Boolean)
      .map((item) => `<span>${escapeHtml(item)}</span>`)
      .join("");
    const facts = [
      ["系列", profile.family],
      ["量化", profile.quantization],
      ["发布时间", profile.released],
      ["显存建议", profile.vram_hint],
      ["当前工作流", isEditMode() ? activeEditCapability().label : "文字生成"],
    ];
    refs.profileFacts.innerHTML = facts
      .map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value || "未标注")}</dd></div>`)
      .join("");
    const editCapability = activeEditCapability();
    const capabilities = (profile.capabilities || []).join(" · ");
    const graphError = (isEditMode() ? editCapability.graph_errors : profile.graph_errors || [])[0];
    refs.compatibilityNote.textContent = graphError
      || (isEditMode() ? `${editCapability.label} · ${editCapability.description}` : capabilities)
      || "平台原生图片生成工作流";
    if (profile.official_workflow) {
      refs.workflowLink.href = isEditMode() && profile.official_edit_workflow ? profile.official_edit_workflow : profile.official_workflow;
      refs.workflowLink.classList.remove("hidden");
    } else {
      refs.workflowLink.classList.add("hidden");
    }
  }

  function renderStorageLocations(data) {
    const current = isFaceSwap()
      ? imageModelDownloadPath || localStorage.getItem(STORAGE.downloadPath) || data.base_dir || data.active_base_dir || ""
      : refs.downloadPath.value || localStorage.getItem(STORAGE.downloadPath) || data.base_dir || data.active_base_dir || "";
    const locations = data.storage_locations || [];
    refs.storagePreset.innerHTML = locations
      .map((item) => `<option value="${escapeHtml(item.path)}">${escapeHtml(item.label)}${item.free_gb == null ? "" : ` · ${Number(item.free_gb).toFixed(1)} GB 可用`}</option>`)
      .join("");
    if (current && !locations.some((item) => item.path === current)) {
      refs.storagePreset.insertAdjacentHTML("beforeend", `<option value="${escapeHtml(current)}">自定义路径</option>`);
    }
    if (isFaceSwap()) imageModelDownloadPath = current;
    else refs.downloadPath.value = current;
    refs.storagePreset.value = current;
    localStorage.setItem(STORAGE.downloadPath, current);
    const selected = locations.find((item) => item.path === current);
    const mode = data.custom_target ? "自定义模型目录，下载完成后需重启 ComfyUI 8188" : "ComfyUI 当前目录";
    refs.storageNote.textContent = `${mode}${selected?.free_gb == null ? "" : `；可用 ${Number(selected.free_gb).toFixed(2)} GB`}`;
  }

  function renderOutputLocation(output = {}) {
    const path = String(output.dir || "").trim();
    const subdir = String(output.subdir || "image_studio").trim() || "image_studio";
    if (document.activeElement !== refs.outputSubdir) refs.outputSubdir.value = subdir;
    refs.outputPath.textContent = path || "输出目录尚未就绪";
    const canOpen = Boolean(path) && output.open_supported !== false;
    refs.outputPathButton.disabled = !canOpen;
    refs.openOutput.disabled = !canOpen;
    refs.outputPathButton.title = canOpen ? `在系统文件管理器中打开 ${path}` : "当前系统无法打开此目录";
  }

  async function saveOutputLocation(event) {
    event?.preventDefault();
    refs.outputSave.disabled = true;
    try {
      const data = await jsonRequest("/api/image-studio/output", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ subdir: refs.outputSubdir.value.trim() }),
      });
      bootstrap = { ...(bootstrap || {}), output: data };
      renderOutputLocation(data);
      setLog(`图片输出位置已保存：${data.dir}`);
    } catch (error) {
      setLog(`保存图片输出位置失败：${error.message}`);
    } finally {
      refs.outputSave.disabled = false;
    }
  }

  async function openOutputLocation() {
    refs.outputPathButton.disabled = true;
    refs.openOutput.disabled = true;
    try {
      const data = await jsonRequest("/api/image-studio/output/open", { method: "POST" });
      bootstrap = { ...(bootstrap || {}), output: data };
      renderOutputLocation(data);
      setLog(`已在系统文件管理器中打开：${data.dir}`);
    } catch (error) {
      setLog(`打开图片输出目录失败：${error.message}`);
      renderOutputLocation(bootstrap?.output || {});
    }
  }


  function playbook() {
    return bootstrap?.nsfw_playbook || {};
  }

  function linkage() {
    return playbook().linkage || {};
  }

  function selectedCharacterId() {
    return localStorage.getItem("local-ai-workbench.image.characterId") || localStorage.getItem("wan22.image.characterId") || "";
  }

  function setSelectedCharacterId(id) {
    if (id) {
      localStorage.setItem("local-ai-workbench.image.characterId", id);
      if (linkage().character_box_shared !== false) localStorage.setItem("local-ai-workbench.video.characterId", id);
    } else {
      localStorage.removeItem("local-ai-workbench.image.characterId");
      if (linkage().character_box_shared !== false) localStorage.removeItem("local-ai-workbench.video.characterId");
    }
  }

  function effectiveTrigger(profile = activeProfile()) {
    const custom = String(refs.customTrigger?.value || "").trim();
    if (custom) return custom;
    return String(profile?.nsfw?.trigger || "").trim();
  }

  function rememberedAdultWizardId() {
    return localStorage.getItem(STORAGE.adultWizard) || "";
  }

  function rememberAdultWizardId(id) {
    const value = String(id || "").trim();
    if (value) localStorage.setItem(STORAGE.adultWizard, value);
    else localStorage.removeItem(STORAGE.adultWizard);
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
            const title = item.note || item.prompt || item.prompt_en || "";
            const active = item.id === activeId ? " active" : "";
            return `<button type="button" class="chip${active}" data-${dataAttr}="${escapeHtml(item.id)}" title="${escapeHtml(title)}">${escapeHtml(item.label)}</button>`;
          })
          .join("");
        return `<div class="chip-group"><span class="chip-group-label">${escapeHtml(group)}</span><div class="chip-row">${chips}</div></div>`;
      })
      .join("");
  }

  let lastAppliedImageSceneId = "";

  function markGroupedChipActive(container, dataAttr, activeId) {
    container?.querySelectorAll(`button[${dataAttr}]`).forEach((button) => {
      button.classList.toggle("active", button.getAttribute(dataAttr) === activeId);
    });
  }

  function pickAvailableProfile(ids) {
    const profiles = bootstrap?.profiles || [];
    const options = [...(refs.profile?.options || [])];
    const usable = ids
      .map((id) => {
        const option = options.find((item) => item.value === id && !item.disabled);
        if (!option) return null;
        const profile = profiles.find((item) => item.id === id);
        return { id, ready: Boolean(profile?.ready) };
      })
      .filter(Boolean);
    return usable.find((item) => item.ready)?.id || usable[0]?.id || "";
  }

  let pendingStillToVideo = null;

  function syncAdultGenerateButton(wizard) {
    const canGenerate = Boolean(
      wizard &&
        wizard.one_click !== false &&
        wizard.pipeline !== "t2v" &&
        wizard.pipeline !== "keyframe" &&
        wizard.pipeline !== "manual" &&
        !wizard.skip_image_prompt,
    );
    refs.adultApplyGenerate?.classList.toggle("hidden", !canGenerate);
    refs.adultApplyVideo?.classList.toggle("hidden", !canGenerate);
    const busy = Boolean(pendingStillToVideo);
    if (refs.adultApplyGenerate) refs.adultApplyGenerate.disabled = Boolean(busy || submitting);
    if (refs.adultApplyVideo) refs.adultApplyVideo.disabled = Boolean(busy || submitting);
  }

  function renderAdultRecipeChips() {
    const wizards = playbook().wizard_modes || [];
    const active = rememberedAdultWizardId() || refs.nsfwWizard?.value || "manual";
    if (refs.adultRecipeChips) {
      refs.adultRecipeChips.innerHTML = groupedPresetHtml(wizards, "adult-wizard", active);
    }
    const current = wizards.find((item) => item.id === active);
    if (refs.adultRecipeHint) {
      refs.adultRecipeHint.textContent = current?.note || "点选后自动开无限制、切模型、填场景。「套用并出视频」会在静帧成功后自动排队图生视频。";
    }
    syncAdultGenerateButton(current);
  }

  function renderPlaybookControls() {
    const book = playbook();
    const wizards = book.wizard_modes || [];
    if (refs.nsfwWizard) {
      const current = rememberedAdultWizardId() || refs.nsfwWizard.value || "manual";
      refs.nsfwWizard.innerHTML = wizards.length
        ? wizards.map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.label)}</option>`).join("")
        : `<option value="manual">全手动</option>`;
      refs.nsfwWizard.value = wizards.some((item) => item.id === current) ? current : "manual";
    }
    const intensities = book.intensity_presets || [];
    if (refs.nsfwIntensitySwitch) {
      const current = refs.nsfwIntensity?.value || "medium";
      refs.nsfwIntensitySwitch.innerHTML = intensities.length
        ? intensities
            .map(
              (item) =>
                `<button type="button" data-intensity="${escapeHtml(item.id)}" class="${item.id === current ? "active" : ""}" title="${escapeHtml(item.note || "")}">${escapeHtml(item.label)}</button>`,
            )
            .join("")
        : `<span class="muted">无强度档位</span>`;
    }
    const scenes = book.image_scenes || [];
    if (refs.nsfwScenes) {
      refs.nsfwScenes.innerHTML = groupedPresetHtml(scenes, "scene", lastAppliedImageSceneId);
    }
    renderAdultRecipeChips();
    renderCharacterBox(bootstrap?.character_box || {});
    renderFaceStrengthPresets();
    renderAdvancedModules();
    updateTriggerPreview();
  }

  function renderFaceStrengthPresets() {
    if (!refs.faceStrengthPresets) return;
    if (linkage().face_strength_presets_enabled === false) {
      refs.faceStrengthPresets.innerHTML = `<span class="muted">强度预设已在玩法配置中关闭。</span>`;
      return;
    }
    const presets = playbook().face_strength_presets || [];
    refs.faceStrengthPresets.innerHTML = presets.length
      ? presets
          .map(
            (item) =>
              `<button type="button" class="chip" data-face-strength="${escapeHtml(item.id)}" title="${escapeHtml(item.note || "")}">${escapeHtml(item.label)} · ${escapeHtml(String(item.strength))}</button>`,
          )
          .join("")
      : `<span class="muted">玩法配置未提供换脸强度预设。</span>`;
  }

  function applyFaceStrengthPreset(presetId) {
    const preset = (playbook().face_strength_presets || []).find((item) => item.id === presetId);
    if (!preset || refs.faceSwapStrength == null) return;
    syncFaceSwapStrength(preset.strength);
  }

  function advancedModuleState() {
    try {
      return JSON.parse(localStorage.getItem(STORAGE.advancedModules) || "{}") || {};
    } catch (_error) {
      return {};
    }
  }

  function ensureAdvancedModuleDefaults() {
    const state = advancedModuleState();
    let changed = false;
    for (const item of playbook().advanced_modules || []) {
      if (state[item.id] === undefined && item.enabled_default) {
        state[item.id] = true;
        changed = true;
      }
    }
    if (changed) localStorage.setItem(STORAGE.advancedModules, JSON.stringify(state));
  }

  function isAdvancedModuleEnabled(id) {
    const state = advancedModuleState();
    if (state[id] !== undefined) return Boolean(state[id]);
    const item = (playbook().advanced_modules || []).find((entry) => entry.id === id);
    return Boolean(item?.enabled_default);
  }

  function enabledAdvancedModuleIds() {
    return (playbook().advanced_modules || [])
      .filter((item) => isAdvancedModuleEnabled(item.id))
      .map((item) => item.id);
  }

  function setAdvancedModuleEnabled(id, enabled) {
    const state = advancedModuleState();
    state[id] = Boolean(enabled);
    localStorage.setItem(STORAGE.advancedModules, JSON.stringify(state));
    renderAdvancedModules();
  }

  function nsfwCapabilities() {
    return bootstrap?.nsfw_capabilities || {};
  }

  function storeFaceAuthToken(token) {
    const value = String(token || "").trim();
    if (value) localStorage.setItem(STORAGE.faceAuthToken, value);
  }

  function faceAuthTokenValue() {
    return localStorage.getItem(STORAGE.faceAuthToken) || "";
  }

  async function loadNsfwCapabilities() {
    try {
      const data = await jsonRequest("/api/nsfw-extensions/capabilities");
      bootstrap = { ...(bootstrap || {}), nsfw_capabilities: data.capabilities || {} };
      renderExtensionCapabilities();
    } catch (error) {
      bootstrap = { ...(bootstrap || {}), nsfw_capabilities: bootstrap?.nsfw_capabilities || {} };
      if (refs.poseMapStatus) refs.poseMapStatus.textContent = `能力检查失败：${error.message}`;
    }
  }

  function renderExtensionCapabilities() {
    const caps = nsfwCapabilities();
    const regionalReady = Boolean(caps.regional?.ready);
    const controlnetReady = Boolean(caps.controlnet?.ready);
    const secondaryReady = Boolean(caps.secondary_lora?.ready !== false);
    refs.regionalPanel?.classList.toggle("is-disabled", !regionalReady);
    refs.poseControlPanel?.classList.toggle("is-disabled", !controlnetReady);
    if (refs.regionalStatus) {
      refs.regionalStatus.textContent = regionalReady
        ? caps.regional?.note || "分区提示词可用。"
        : caps.regional?.note || "当前 ComfyUI 未安装 ConditioningSetArea 节点。";
    }
    if (refs.regionalFacePrompt) refs.regionalFacePrompt.disabled = !regionalReady;
    if (refs.regionalBodyPrompt) refs.regionalBodyPrompt.disabled = !regionalReady;
    if (refs.secondaryLoraName) refs.secondaryLoraName.disabled = !secondaryReady;
    if (refs.secondaryLoraStrength) refs.secondaryLoraStrength.disabled = !secondaryReady;
    if (refs.poseMapFile) refs.poseMapFile.disabled = !controlnetReady;
    if (refs.controlnetName) {
      const models = caps.controlnet?.models || [];
      const current = refs.controlnetName.value;
      refs.controlnetName.innerHTML = [`<option value="">不启用</option>`]
        .concat(models.map((item) => `<option value="${escapeHtml(item)}">${escapeHtml(item)}</option>`))
        .join("");
      refs.controlnetName.value = models.includes(current) ? current : "";
      refs.controlnetName.disabled = !controlnetReady || !models.length;
    }
    if (refs.controlnetStrength) refs.controlnetStrength.disabled = !controlnetReady;
    if (refs.poseMapStatus) {
      refs.poseMapStatus.textContent = controlnetReady
        ? caps.controlnet?.note || "选择 OpenPose 图并指定 ControlNet 模型。"
        : caps.controlnet?.note || "ControlNet 节点或模型尚未就绪。";
    }
  }

  async function uploadPoseMapFile(file) {
    if (!file || poseMapUploadBusy) return;
    const comfyUrl = String(bootstrap?.comfy?.url || "http://127.0.0.1:8188").replace(/\/$/, "");
    poseMapUploadBusy = true;
    if (refs.poseMapStatus) refs.poseMapStatus.textContent = "正在上传姿态图…";
    try {
      const payload = new FormData();
      payload.append("image", file, file.name);
      payload.append("type", "input");
      payload.append("subfolder", "beginner_frontend");
      const response = await fetch(`${comfyUrl}/upload/image`, { method: "POST", body: payload });
      const data = await response.json();
      if (!response.ok) throw new Error(formatError(data.detail || data.error || data));
      const subfolder = String(data.subfolder || "beginner_frontend");
      const name = String(data.name || "");
      const stored = subfolder ? `${subfolder}/${name}` : name;
      refs.poseMapFilename.value = stored;
      if (refs.poseMapStatus) refs.poseMapStatus.textContent = `已上传：${stored}`;
      scheduleWorkflowCheck();
    } catch (error) {
      if (refs.poseMapStatus) refs.poseMapStatus.textContent = `姿态图上传失败：${error.message}`;
    } finally {
      poseMapUploadBusy = false;
    }
  }

  function renderEditStrengthPresetSwitches() {
    const presets = playbook().edit_strength_presets || [];
    const current = refs.editStrengthPreset?.value || "";
    const markup = presets.length
      ? presets
          .map(
            (item) =>
              `<button type="button" data-edit-strength-preset="${escapeHtml(item.id)}" class="${item.id === current ? "active" : ""}" title="${escapeHtml(item.note || "")}">${escapeHtml(item.label)}</button>`,
          )
          .join("")
      : `<span class="muted">玩法配置未提供编辑强度预设。</span>`;
    for (const container of [refs.editStrengthSwitch, refs.editStrengthInlineSwitch].filter(Boolean)) {
      container.innerHTML = markup;
    }
    refs.editStrengthPresetField?.classList.toggle("hidden", !isEditMode() || isFaceSwap() || !presets.length);
  }

  function applyEditStrengthPreset(presetId, { schedule = true } = {}) {
    const preset = (playbook().edit_strength_presets || []).find((item) => item.id === presetId);
    if (!preset || !refs.editStrengthPreset) return;
    refs.editStrengthPreset.value = preset.id;
    if (preset.strength != null) syncEditStrength(preset.strength, { schedule: false });
    renderEditStrengthPresetSwitches();
    if (schedule) scheduleWorkflowCheck();
  }

  function clearEditStrengthPreset() {
    if (refs.editStrengthPreset) refs.editStrengthPreset.value = "";
    renderEditStrengthPresetSwitches();
  }

  function updateCompareWallButton() {
    if (!refs.compareWallButton) return;
    refs.compareWallButton.classList.toggle("active", compareWallEnabled);
    refs.compareWallButton.setAttribute("aria-pressed", compareWallEnabled ? "true" : "false");
  }

  function historyMatchesFilter(job = {}) {
    if (historyFilter === "nsfw") return Boolean(job.nsfw);
    if (historyFilter === "face_swap") return job.edit_operation === "face_swap";
    return true;
  }

  function restoreJobParams(job = {}) {
    if (job.model_profile && refs.profile.querySelector(`option[value="${job.model_profile}"]`)) {
      refs.profile.value = job.model_profile;
      applyProfileDefaults(false);
    }
    if (job.source_prompt != null) refs.prompt.value = job.source_prompt;
    if (job.negative != null) refs.negative.value = job.negative;
    if (job.style_preset && refs.style.querySelector(`option[value="${job.style_preset}"]`)) refs.style.value = job.style_preset;
    if (job.seed != null && job.seed !== "") refs.seed.value = String(job.seed);
    if (job.nsfw != null) refs.nsfw.checked = Boolean(job.nsfw);
    if (job.nsfw_lora_strength != null && refs.nsfwStrength) syncNsfwStrength(job.nsfw_lora_strength, { schedule: false });
    if (job.nsfw_intensity && refs.nsfwIntensity) applyIntensity(job.nsfw_intensity);
    if (job.triple_compare != null && refs.tripleCompare) refs.tripleCompare.checked = Boolean(job.triple_compare);
    if (job.prompt_expand != null && refs.promptExpand) refs.promptExpand.checked = Boolean(job.prompt_expand);
    if (job.secondary_lora?.name != null && refs.secondaryLoraName) refs.secondaryLoraName.value = job.secondary_lora.name || "";
    if (job.secondary_lora?.strength != null && refs.secondaryLoraStrength) refs.secondaryLoraStrength.value = String(job.secondary_lora.strength);
    if (job.regional_prompts?.face != null && refs.regionalFacePrompt) refs.regionalFacePrompt.value = job.regional_prompts.face || "";
    if (job.regional_prompts?.body != null && refs.regionalBodyPrompt) refs.regionalBodyPrompt.value = job.regional_prompts.body || "";
    if (job.controlnet?.name && refs.controlnetName) refs.controlnetName.value = job.controlnet.name;
    if (job.controlnet?.strength != null && refs.controlnetStrength) refs.controlnetStrength.value = String(job.controlnet.strength);
    if (job.edit_strength_preset) applyEditStrengthPreset(job.edit_strength_preset, { schedule: false });
    else if (job.source_adherence != null) syncEditStrength(job.source_adherence, { schedule: false });
    if (Array.isArray(job.advanced_modules)) {
      const state = advancedModuleState();
      for (const item of playbook().advanced_modules || []) state[item.id] = job.advanced_modules.includes(item.id);
      localStorage.setItem(STORAGE.advancedModules, JSON.stringify(state));
      renderAdvancedModules();
    }
    if (job.character_id) setSelectedCharacterId(String(job.character_id));
    renderNsfwSupport();
    updatePromptCount();
    if (!isFaceSwap()) {
      schedulePromptPreview();
      scheduleWorkflowCheck();
    }
    setLog("已还原该任务参数。");
  }

  function renderAdvancedModules() {
    if (!refs.advancedModuleList) return;
    ensureAdvancedModuleDefaults();
    const modules = (playbook().advanced_modules || []).filter((item) => {
      const status = String(item.status || "");
      return ["workflow_native", "profile_native"].includes(status) || Boolean(item.install_profile);
    });
    if (refs.advancedModulesSummary) {
      const enabledCount = enabledAdvancedModuleIds().length;
      refs.advancedModulesSummary.textContent = `${enabledCount}/${modules.length} 项已启用`;
    }
    refs.advancedModuleList.innerHTML = modules.length
      ? modules
          .map((item) => {
            const status = String(item.status || "");
            const actionable = Boolean(item.install_profile);
            const toggleable = ["workflow_native", "profile_native"].includes(status);
            const active = toggleable ? isAdvancedModuleEnabled(item.id) : false;
            const suffix = actionable ? " · 可安装" : toggleable ? " · 可开关" : "";
            return `<button type="button" class="chip ${active ? "active" : ""}" data-advanced-module="${escapeHtml(item.id)}" data-module-status="${escapeHtml(status)}" data-install-profile="${escapeHtml(item.install_profile || "")}" title="${escapeHtml(item.note || "")}">${escapeHtml(item.label)}${suffix}</button>`;
          })
          .join("")
      : `<span class="muted">当前没有可安装或已接入的进阶模块。</span>`;
  }

  function currentIdentityFaceAsset() {
    const index = Number(refs.identityFaceIndex?.value);
    const faces = identityFaceExtraction?.faces || [];
    const selected = faces.find((item) => Number(item.index) === index) || faces[0];
    if (selected?.filename) {
      return {
        filename: selected.filename,
        subfolder: selected.subfolder || "",
        type: selected.type || "input",
        url: selected.url || "",
        label: selected.label || identityFaceSource?.label || selected.filename,
      };
    }
    if (identityFaceExtraction?.original?.filename) {
      const original = identityFaceExtraction.original;
      return {
        filename: original.filename,
        subfolder: original.subfolder || "",
        type: original.type || "input",
        url: original.url || identityFaceSource?.url || "",
        label: identityFaceSource?.label || original.filename,
      };
    }
    if (identityFaceSource?.filename) {
      return {
        filename: identityFaceSource.filename,
        subfolder: identityFaceSource.subfolder || "",
        type: identityFaceSource.type || "input",
        url: identityFaceSource.url || "",
        label: identityFaceSource.label || identityFaceSource.filename,
      };
    }
    return null;
  }

  function renderCharacterIdentityPreview() {
    if (!refs.characterIdentityPreview) return;
    const asset = currentIdentityFaceAsset();
    const previewUrl = asset?.url || identityFaceSource?.url || "";
    if (!previewUrl && !identityFaceSource?.file) {
      refs.characterIdentityPreview.innerHTML = "<p>尚未选择身份参考图。</p>";
      return;
    }
    const label = asset?.label || identityFaceSource?.label || "身份参考";
    const src = previewUrl || identityFaceSource?.url || "";
    refs.characterIdentityPreview.innerHTML = src
      ? `<img src="${escapeHtml(src)}" alt="角色盒身份预览" /><figcaption>${escapeHtml(label)}</figcaption>`
      : `<p>${escapeHtml(label)}（待提取后可预览）</p>`;
  }

  async function extractCharacterIdentityAuthorized() {
    if (!hasIdentityFaceSource()) {
      if (refs.characterStatus) refs.characterStatus.textContent = "请先导入身份参考图。";
      return false;
    }
    if (refs.characterStatus) refs.characterStatus.textContent = "正在提取身份脸…";
    try {
      const data = await requestFaceExtraction(identityFaceSource);
      identityFaceExtraction = data;
      refs.identityFaceExtractId.value = data.id;
      if (data.authorization?.token) storeFaceAuthToken(data.authorization.token);
      refs.identityFaceIndex.value = String(data.selected_index ?? data.faces?.[0]?.index ?? -1);
      if (data.original?.filename) {
        identityFaceSource = {
          ...(identityFaceSource || {}),
          filename: data.original.filename,
          subfolder: data.original.subfolder || "",
          type: data.original.type || "input",
          url: data.original.url || identityFaceSource?.url || "",
          label: identityFaceSource?.label || data.original.filename,
          file: undefined,
        };
      }
      renderIdentityFaceSource();
      renderCharacterIdentityPreview();
      renderFaceCandidates("identity");
      if (refs.characterStatus) refs.characterStatus.textContent = data.message || "身份脸已提取，可存入角色盒。";
      return true;
    } catch (error) {
      if (refs.characterStatus) refs.characterStatus.textContent = error.message;
      return false;
    }
  }

  async function extractCharacterIdentity() {
    if (!hasIdentityFaceSource()) {
      if (refs.characterStatus) refs.characterStatus.textContent = "请先导入身份参考图。";
      refs.characterIdentityFile?.click();
      return;
    }
    if (!faceAuthorizationConfirmed) {
      pendingCharacterExtract = true;
      requestFaceAuthorization(refs.characterExtract);
      return;
    }
    await extractCharacterIdentityAuthorized();
  }

  async function saveCharacterFromIdentity() {
    let asset = currentIdentityFaceAsset();
    if (!asset && hasIdentityFaceSource()) {
      if (!faceAuthorizationConfirmed) {
        pendingCharacterExtract = true;
        pendingCharacterSave = true;
        requestFaceAuthorization(refs.characterSave);
        return;
      }
      const ok = await extractCharacterIdentityAuthorized();
      if (!ok) return;
      asset = currentIdentityFaceAsset();
    }
    if (!asset?.filename) {
      if (refs.characterStatus) refs.characterStatus.textContent = "请先导入并提取身份脸。";
      return;
    }
    try {
      const data = await jsonRequest("/api/character-box", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "upsert",
          item: {
            label: asset.label || asset.filename,
            identity_filename: asset.filename,
            identity_subfolder: asset.subfolder || "",
            identity_type: asset.type || "input",
            preview_url: asset.url || "",
          },
        }),
      });
      bootstrap = { ...(bootstrap || {}), character_box: data };
      renderCharacterBox(data);
      if (data.items?.length) {
        const last = data.items[data.items.length - 1];
        setSelectedCharacterId(last.id);
        renderCharacterBox(data);
      }
      if (refs.characterStatus) refs.characterStatus.textContent = data.message || "已保存到角色盒";
    } catch (error) {
      if (refs.characterStatus) refs.characterStatus.textContent = error.message;
    }
  }

  function applyCharacterToIdentity(characterId) {
    const items = bootstrap?.character_box?.items || [];
    const item = items.find((entry) => entry.id === characterId);
    if (!item?.identity_filename) {
      if (refs.characterStatus) refs.characterStatus.textContent = "该角色没有可用身份图。";
      return;
    }
    setSelectedCharacterId(characterId);
    setIdentityFaceSource({
      filename: item.identity_filename,
      subfolder: item.identity_subfolder || "",
      type: item.identity_type || "input",
      url: item.preview_url || "",
      label: item.label || item.identity_filename,
    });
    identityFaceExtraction = null;
    refs.identityFaceExtractId.value = "";
    refs.identityFaceIndex.value = "-1";
    renderCharacterBox(bootstrap?.character_box || {});
    renderCharacterIdentityPreview();
    if (refs.characterStatus) refs.characterStatus.textContent = `已选中角色：${item.label || item.id}`;
  }

  function gotoFaceSwapWithCharacter() {
    selectTaskMode("edit", { schedule: false });
    selectEditOperation("face_swap", { schedule: true });
    if (selectedCharacterId()) applyCharacterToIdentity(selectedCharacterId());
    refs.faceOptions?.scrollIntoView({ behavior: "smooth", block: "start" });
    if (refs.characterStatus) refs.characterStatus.textContent = "已切换到换脸；可继续检测双方并提交。";
  }

  function renderCharacterBox(data = {}) {
    const items = Array.isArray(data.items) ? data.items : [];
    if (refs.characterBoxSummary) refs.characterBoxSummary.textContent = `${items.length} 个`;
    if (!refs.characterBoxList) return;
    const selected = selectedCharacterId();
    refs.characterBoxList.innerHTML = items.length
      ? items
          .map(
            (item) =>
              `<button type="button" class="chip ${item.id === selected ? "active" : ""}" data-character="${escapeHtml(item.id)}" title="${escapeHtml(item.identity_filename || "")}">${escapeHtml(item.label || item.id)}</button>`,
          )
          .join("")
      : `<span class="muted">还没有角色。导入身份图并提取后可存入。</span>`;
    renderCharacterIdentityPreview();
  }

  async function clearCharacterBox() {
    const data = await jsonRequest("/api/character-box", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "clear" }),
    });
    bootstrap = { ...(bootstrap || {}), character_box: data };
    setSelectedCharacterId("");
    renderCharacterBox(data);
    if (refs.characterStatus) refs.characterStatus.textContent = "角色盒已清空";
  }

  function updateTriggerPreview() {
    const trigger = effectiveTrigger();
    if (refs.triggerPreview) refs.triggerPreview.textContent = trigger ? `将使用：${trigger}` : "模型无默认触发词";
  }

  function applyIntensity(intensityId, { syncStrength = true } = {}) {
    if (refs.nsfwIntensity) refs.nsfwIntensity.value = intensityId;
    refs.nsfwIntensity.dataset.manualStrength = "";
    refs.nsfwIntensitySwitch?.querySelectorAll("button[data-intensity]").forEach((button) => {
      button.classList.toggle("active", button.dataset.intensity === intensityId);
    });
    if (!syncStrength || linkage().intensity_updates_strength === false) return;
    const profile = activeProfile();
    const preset = (playbook().intensity_presets || []).find((item) => item.id === intensityId);
    if (!profile?.nsfw || !preset || profile.nsfw.strength_default == null) return;
    const minimum = Number(profile.nsfw.strength_min ?? 0);
    const maximum = Number(profile.nsfw.strength_max ?? 1.5);
    const value = Math.max(minimum, Math.min(maximum, Number(profile.nsfw.strength_default) * Number(preset.multiplier || 1)));
    syncNsfwStrength(value, { schedule: true, fromIntensity: true });
  }

  function applyScene(sceneId, { replace = false, applyHints = true } = {}) {
    const scene = (playbook().image_scenes || []).find((item) => item.id === sceneId);
    if (!scene) return;
    const language = /[\u4e00-\u9fff]/.test(refs.prompt.value || scene.prompt || "") ? "zh" : "en";
    const fill = language === "en" ? scene.prompt_en || scene.prompt : scene.prompt || scene.prompt_en;
    if (replace || scene.fill_mode === "replace" || !String(refs.prompt.value || "").trim()) {
      refs.prompt.value = fill || "";
    } else if (fill) {
      refs.prompt.value = `${String(refs.prompt.value).trim()}。${fill}`;
    }
    updatePromptCount();
    if (applyHints && linkage().scene_applies_style !== false && scene.style_hint && refs.style.querySelector(`option[value="${scene.style_hint}"]`)) {
      refs.style.value = scene.style_hint;
    }
    if (applyHints && linkage().scene_applies_intensity !== false && scene.intensity_hint) {
      applyIntensity(scene.intensity_hint);
    }
    lastAppliedImageSceneId = sceneId;
    markGroupedChipActive(refs.nsfwScenes, "data-scene", sceneId);
    schedulePromptPreview();
  }

  function applyWizard(wizardId, { generate = false, queueVideo = false, source = "image" } = {}) {
    const wizard = (playbook().wizard_modes || []).find((item) => item.id === wizardId);
    if (!wizard) return;
    rememberAdultWizardId(wizard.id);
    if (refs.nsfwWizard) refs.nsfwWizard.value = wizard.id;
    const notes = [];
    if (pendingStillToVideo && !queueVideo) {
      pendingStillToVideo = null;
      notes.push("已取消自动出视频");
    }
    if (source === "video") {
      let videoNotes = [];
      if (typeof window.applyAdultPlaybookVideo === "function") {
        videoNotes = window.applyAdultPlaybookVideo(wizard, { imagePrompt: "", replacePrompt: false })?.notes || [];
      }
      renderAdultRecipeChips();
      setLog(`已套用玩法「${wizard.label}」的视频设置，未改静帧提示词。${[...notes, ...videoNotes, wizard.note || ""].filter(Boolean).join("；")}`);
      return;
    }
    const skipImage = Boolean(
      wizard.skip_image_prompt ||
        wizard.pipeline === "t2v" ||
        wizard.pipeline === "keyframe" ||
        wizard.pipeline === "manual",
    );
    const videoOnly = Boolean(
      wizard.skip_image_prompt || wizard.pipeline === "t2v" || wizard.pipeline === "keyframe",
    );
    if (!skipImage && (isEditMode() || isFaceSwap())) {
      selectTaskMode("t2i", { schedule: false });
      notes.push("已切回文生图再套玩法");
    }
    if (!skipImage) {
      const profileIds = preferredIdList(wizard, "preferred_image_profile", "preferred_image_profiles");
      const profileId = pickAvailableProfile(profileIds);
      if (profileId && refs.profile.value !== profileId) {
        refs.profile.value = profileId;
        applyProfileDefaults(true);
        renderProfileDetails();
        renderModelReadiness();
      }
      if (profileIds[0] && profileId && profileId !== profileIds[0]) {
        notes.push(`图片模型已回退到 ${activeProfile()?.short_label || activeProfile()?.label || profileId}`);
      } else if (profileIds[0] && !profileId) {
        notes.push(`未找到可用的 ${profileIds[0]}`);
      }
      const profile = activeProfile();
      const config = profile?.nsfw || {};
      const available = Boolean(config.toggle_enabled && (!config.addon_profile || config.addon_ready));
      refs.nsfw.disabled = !available;
      if (wizard.auto_unrestricted && available) refs.nsfw.checked = true;
      else if (!available) refs.nsfw.checked = false;
      if (wizard.auto_unrestricted && !available) notes.push("当前图片模型无法打开无限制");
      if (refs.autoInjectTrigger) refs.autoInjectTrigger.checked = Boolean(wizard.auto_inject_trigger);
      if (refs.autoStripNegative) refs.autoStripNegative.checked = Boolean(wizard.auto_strip_negative);
      renderNsfwSupport();
      if (!wizard.skip_image_prompt && wizard.image_scene) applyScene(wizard.image_scene, { replace: true, applyHints: false });
      if (wizard.image_style && refs.style.querySelector(`option[value="${wizard.image_style}"]`)) {
        refs.style.value = wizard.image_style;
      }
      if (wizard.intensity) applyIntensity(wizard.intensity);
    }
    let videoNotes = [];
    if (videoOnly && wizard.pipeline !== "manual" && typeof window.applyAdultPlaybookVideo === "function") {
      videoNotes = window.applyAdultPlaybookVideo(wizard, { imagePrompt: "", replacePrompt: false })?.notes || [];
    } else if (wizard.pipeline !== "manual" && typeof window.setPreferredVideoModel === "function") {
      const fallbacks = playbook().video_model_fallbacks || {};
      const listed = preferredIdList(wizard, "preferred_video_model", "preferred_video_models");
      const modelTargets = listed.length ? listed : wizard.pipeline === "t2v" ? fallbacks.t2v || [] : fallbacks.i2v || [];
      if (modelTargets.length) {
        const videoResult = window.setPreferredVideoModel(modelTargets, { applyDefaults: false });
        if (videoResult?.usedFallback && videoResult.selected) {
          videoNotes.push(`视频模型已记为 ${videoResult.selected.label}`);
        } else if (!videoResult?.selected) {
          videoNotes.push("没有可用的目标视频模型");
        }
      }
    }
    renderAdultRecipeChips();
    schedulePromptPreview();
    scheduleWorkflowCheck();
    const extra = [...notes, ...videoNotes, wizard.note || ""].filter(Boolean).join("；");
    const willGenerate = Boolean(generate || queueVideo);
    if (willGenerate && !skipImage && !activeProfileReady()) {
      setLog(`已套用玩法「${wizard.label}」，但 ${activeProfile()?.label || "当前模型"} 还没就绪，请先下载模型。${extra}`);
      return;
    }
    if (queueVideo && skipImage) {
      setLog(`已套用玩法「${wizard.label}」的视频设置。当前玩法不生成静帧，请直接在视频页提交。${extra}`);
      return;
    }
    let compareNote = "";
    if (queueVideo && (compareWallEnabled || refs.tripleCompare?.checked)) {
      compareNote = "对比墙或三联对比开启时不会自动出视频，已改为只生成静帧。";
      queueVideo = false;
      generate = true;
    }
    if (queueVideo) pendingStillToVideo = { wizardId: wizard.id, jobId: null, queued: false };
    const suffix = [compareNote, extra].filter(Boolean).join(" ");
    setLog(
      queueVideo
        ? `已套用玩法「${wizard.label}」，正在生成静帧；完成后会自动排队图生视频。${suffix}`
        : willGenerate
          ? `已套用玩法「${wizard.label}」，正在生成静帧。${suffix}`
          : skipImage
            ? `已套用玩法「${wizard.label}」的视频设置，未改静帧提示词。${suffix}`
            : `已套用玩法「${wizard.label}」。${suffix} 可再改提示词；静帧玩法可点「套用并生成静帧」或「套用并出视频」。`,
    );
    syncAdultGenerateButton(wizard);
    if (willGenerate && !skipImage) {
      form.requestSubmit();
    }
  }

  window.applyAdultPlaybook = (wizardId, options = {}) => applyWizard(wizardId, options);

  function renderNsfwSupport() {
    const profile = activeProfile();
    const config = profile?.nsfw || {};
    const addonReady = Boolean(config.addon_ready);
    const addonInstalled = Boolean(config.addon_installed ?? addonReady);
    const requiresAddon = Boolean(config.addon_profile);
    const available = Boolean(config.toggle_enabled && (!requiresAddon || addonReady));
    refs.nsfw.disabled = !available;
    if (!available) refs.nsfw.checked = false;
    refs.nsfwStrengthField.classList.toggle("hidden", !available || !config.lora_name);
    if (config.lora_name) {
      const minimum = Number(config.strength_min ?? 0);
      const maximum = Number(config.strength_max ?? 2);
      const step = Number(config.strength_step ?? 0.05);
      const defaultValue = Number(config.strength_default ?? 1);
      for (const input of [refs.nsfwStrength, refs.nsfwStrengthRange]) {
        input.min = String(minimum);
        input.max = String(maximum);
        input.step = String(step);
      }
      if (refs.nsfwStrength.dataset.profile !== profile.id) {
        refs.nsfwStrength.dataset.profile = profile.id;
        refs.nsfwStrength.value = String(defaultValue);
        refs.nsfwStrengthRange.value = String(defaultValue);
      }
      refs.nsfwStrengthHelp.textContent = config.strength_help || `推荐 ${config.strength_recommended || `${minimum}-${maximum}`}。`;
    }
    refs.installNsfw.classList.toggle("hidden", !config.addon_profile || addonInstalled);
    refs.installNsfw.dataset.profile = config.addon_profile || "";
    refs.nsfwSource.classList.toggle("hidden", !config.source);
    if (config.source) refs.nsfwSource.href = config.source;
    if (config.readiness_note && addonInstalled && !addonReady) {
      refs.nsfwStatus.textContent = `${config.label}；${config.readiness_note}`;
    } else if (available && requiresAddon) {
      refs.nsfwStatus.textContent = `${config.label || "社区无限制方案已安装"}；${config.note || "社区附加包已就绪。"}`;
    } else if (available) {
      refs.nsfwStatus.textContent = `${config.label || "当前模型原生支持"}；${config.note || "无需额外附加包。"}`;
    } else if (config.toggle_enabled) {
      refs.nsfwStatus.textContent = `${config.label || "有社区无限制方案"}，需要先单独安装；${config.note || ""}`;
    } else {
      refs.nsfwStatus.textContent = `${config.label || "暂无无限制方案"}；${config.note || "当前模型没有可验证的社区无限制方案。"}`;
    }
    if (available && config.model_label) {
      const activeModel = refs.nsfw.checked ? config.model_label : (config.standard_model_label || profile.label);
      refs.nsfwStatus.textContent = `当前模型：${activeModel}。${config.note || ""}`;
    }
    const showExtras = Boolean(refs.nsfw.checked && available);
    refs.nsfwExtras?.classList.toggle("hidden", !showExtras);
    // Always hydrate playbook widgets so opening panels is never blank.
    renderPlaybookControls();
    renderEditStrengthPresetSwitches();
    renderStyleOptions(bootstrap);
    updateTriggerPreview();
  }


  function selectedPromptMode() {
    return refs.promptModes.querySelector('input[name="prompt_mode"]:checked')?.value || "structured";
  }

  function visibleStylePresets(data = bootstrap) {
    const styles = Array.isArray(data?.style_presets) ? data.style_presets : [];
    const nsfwOn = Boolean(refs.nsfw?.checked);
    return styles.filter((item) => !item.nsfw_only || nsfwOn);
  }

  function renderStyleOptions(data = bootstrap) {
    if (!refs.style) return;
    const styles = visibleStylePresets(data);
    const fallback = data?.defaults?.style_preset || "photo";
    const currentStyle = refs.style.value || fallback;
    refs.style.innerHTML = styles
      .map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.label)}</option>`)
      .join("");
    refs.style.value = styles.some((item) => item.id === currentStyle) ? currentStyle : fallback;
  }

  function syncBooleanFormFields(payload) {
    payload.set("nsfw", refs.nsfw?.checked ? "true" : "false");
    payload.set("auto_inject_trigger", refs.autoInjectTrigger?.checked ? "true" : "false");
    payload.set("auto_strip_negative", refs.autoStripNegative?.checked ? "true" : "false");
    payload.set("edit_mode", isEditMode() ? "true" : "false");
    payload.set("triple_compare", refs.tripleCompare?.checked ? "true" : "false");
    payload.set("prompt_expand", refs.promptExpand?.checked ? "true" : "false");
    payload.set("advanced_modules", JSON.stringify(enabledAdvancedModuleIds()));
    const authToken = faceAuthTokenValue();
    if (authToken) payload.set("face_authorization_token", authToken);
    if (faceAuthorizationConfirmed) payload.set("face_authorization_confirmed", "true");
    if (refs.nsfwIntensity?.dataset.manualStrength === "1") {
      payload.set("nsfw_intensity", "");
    } else if (refs.nsfwIntensity) {
      payload.set("nsfw_intensity", refs.nsfwIntensity.value || "medium");
    }
    const characterId = selectedCharacterId();
    if (characterId) payload.set("character_id", characterId);
    else payload.delete("character_id");
    payload.delete("reference_images");
    if (supportsAdditionalReferences()) {
      for (const file of editReferenceFiles.slice(0, maximumAdditionalReferences())) {
        payload.append("reference_images", file, file.name);
      }
    }
    return payload;
  }

  function visibleAspectPresets(data = bootstrap) {
    const profileId = refs.profile?.value || data?.defaults?.profile || "";
    return (data?.aspect_presets || []).filter((item) => {
      const profiles = Array.isArray(item.profiles) ? item.profiles : [];
      return !profiles.length || profiles.includes(profileId);
    });
  }

  function renderAspectOptions(data = bootstrap) {
    if (!refs.aspectGrid || !refs.aspect) return;
    const presets = visibleAspectPresets(data);
    const requestedAspect = refs.aspect.value || data?.defaults?.aspect || "landscape";
    const selectedAspect = presets.find((item) => item.id === requestedAspect)
      || presets.find((item) => item.id === "landscape")
      || presets[0];
    const currentAspect = selectedAspect?.id || "custom";
    if (requestedAspect !== "custom" && selectedAspect && selectedAspect.id !== requestedAspect) {
      refs.aspect.value = selectedAspect.id;
      refs.width.value = String(selectedAspect.width);
      refs.height.value = String(selectedAspect.height);
    }

    const aspectGroups = new Map();
    for (const item of presets) {
      const group = item.group || "常用画幅";
      if (!aspectGroups.has(group)) aspectGroups.set(group, []);
      aspectGroups.get(group).push(item);
    }
    refs.aspectGrid.innerHTML = [
      ...[...aspectGroups.entries()].map(
        ([group, items]) => `<section class="image-aspect-group">
          <span class="image-aspect-group-label">${escapeHtml(group)}</span>
          <div class="image-aspect-options">${items
            .map(
              (item) => `<button type="button" data-aspect="${escapeHtml(item.id)}" data-width="${item.width}" data-height="${item.height}" class="${item.id === currentAspect ? "active" : ""}">
                <strong>${escapeHtml(item.name || item.label)}</strong><small>${escapeHtml(item.label)} · ${item.width} × ${item.height}</small>
              </button>`,
            )
            .join("")}</div>
        </section>`,
      ),
      `<section class="image-aspect-group image-aspect-custom-group">
        <span class="image-aspect-group-label">自定义</span>
        <div class="image-aspect-options"><button type="button" data-aspect="custom" class="${requestedAspect === "custom" ? "active" : ""}">
          <strong>自定义尺寸</strong><small>直接输入宽度和高度</small>
        </button></div>
      </section>`,
    ].join("");
  }

  function renderStaticControls(data) {
    const currentProfile = refs.profile.value || data.defaults?.profile;
    const currentPromptMode = selectedPromptMode() || data.defaults?.prompt_mode || "structured";
    const currentAspect = refs.aspect.value || data.defaults?.aspect || "landscape";
    const currentSampler = refs.sampler.value || "euler";
    const currentScheduler = refs.scheduler.value || "simple";
    refs.profile.innerHTML = groupedProfileOptions(data.profiles || [], currentProfile);
    renderStyleOptions(data);

    refs.promptModes.innerHTML = (data.prompt_modes || [])
      .map(
        (item) => `<label title="${escapeHtml(item.description)}">
          <input type="radio" name="prompt_mode" value="${escapeHtml(item.id)}"${item.id === currentPromptMode ? " checked" : ""} />
          <span>${escapeHtml(item.label)}</span>
        </label>`,
      )
      .join("");

    renderAspectOptions(data);

    refs.sampler.innerHTML = (data.samplers || []).map((name) => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`).join("");
    refs.scheduler.innerHTML = (data.schedulers || []).map((name) => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`).join("");
    refs.sampler.value = data.samplers?.includes(currentSampler)
      ? currentSampler
      : data.samplers?.includes("euler")
        ? "euler"
        : data.samplers?.[0] || "euler";
    refs.scheduler.value = data.schedulers?.includes(currentScheduler)
      ? currentScheduler
      : data.schedulers?.includes("simple")
        ? "simple"
        : data.schedulers?.[0] || "simple";

    if (!initialized) {
      refs.prompt.value = data.defaults?.prompt || "";
      refs.negative.value = data.defaults?.negative || "";
      selectBatch(data.defaults?.batch_size || 1, { schedule: false });
      selectGenerationMode(data.defaults?.generation_mode || "batch", { schedule: false });
      refs.seed.value = String(data.defaults?.seed ?? -1);
      refs.editMode.value = data.defaults?.edit_mode ? "true" : "false";
      refs.editResizeMode.value = data.defaults?.edit_resize_mode || "crop";
      refs.editStrength.value = String(data.defaults?.source_adherence ?? 0.65);
      refs.editStrengthRange.value = refs.editStrength.value;
      refs.aspect.value = data.defaults?.aspect || "landscape";
      const selectedAspect = (data.aspect_presets || []).find((item) => item.id === refs.aspect.value);
      if (selectedAspect) {
        refs.width.value = String(selectedAspect.width);
        refs.height.value = String(selectedAspect.height);
      }
      initialized = true;
    }
    applyProfileDefaults(false);
    renderProfileDetails();
    renderStorageLocations(data);
    renderOutputLocation(data.output || {});
    renderNsfwSupport();
    selectTaskMode(isEditMode() ? "edit" : "t2i", { schedule: false, refreshOptions: true });
    renderFaceSwapPanel();
    updatePromptCount();
  }

  function updateGenerateState() {
    const ready = activeProfileReady();
    const sourceReady = !isEditMode() || (hasEditSource() && faceSourceReady());
    refs.generate.disabled = submitting || faceExtractionBusy || !ready || !sourceReady;
    if (submitting) {
      refs.generate.textContent = "提交中";
    } else if (activeJobIds.size) {
      refs.generate.textContent = `${isFaceSwap() ? "继续添加换脸" : isEditMode() ? "继续添加微调" : "继续添加任务"} (${activeJobIds.size} 个进行中)`;
    } else {
      refs.generate.textContent = isFaceSwap() ? "开始换脸" : isEditMode() ? "开始微调" : "生成图片";
    }
    const wizardId = refs.nsfwWizard?.value || rememberedAdultWizardId();
    syncAdultGenerateButton((playbook().wizard_modes || []).find((item) => item.id === wizardId));
  }

  function renderModelReadiness() {
    if (isFaceSwap()) {
      const capability = faceSwapCapability();
      refs.badge.textContent = capability.ready ? "换脸已就绪" : "换脸待准备";
      refs.badge.classList.toggle("ok", Boolean(capability.ready));
      if (refs.topModel && refs.viewTab?.classList.contains("active")) {
        refs.topModel.textContent = "ReActor 本地换脸";
        refs.topModel.title = "ReActor 本地换脸";
      }
      renderFaceSwapPanel();
      updateGenerateState();
      return;
    }
    const profile = activeProfile();
    const plan = profile?.install_plan || bootstrap?.install_plan || {};
    if (!profile) return;
    const workflowReady = activeProfileReady();
    const editCapability = activeEditCapability();
    refs.badge.textContent = workflowReady ? (isEditMode() ? "微调已就绪" : "模型已就绪") : "模型待准备";
    if (workflowReady) {
      refs.badge.classList.add("ok");
      refs.installButton.textContent = "模型已下载";
      refs.installButton.disabled = true;
      refs.installState.textContent = "模型文件：已下载并加载";
      setModelStatus("ok", `${profile.label} 的${isEditMode() ? editCapability.label : "文字生成"}工作流已通过模型文件、节点和 workflow 预检。`);
      updateGenerateState();
      return;
    }
    refs.badge.classList.remove("ok");
    refs.installButton.textContent = "下载缺失模型";
    refs.installButton.disabled = false;
    updateGenerateState();
    const missing = profile.missing || [];
    const remaining = missing.reduce((sum, item) => sum + Number(item.remaining_gb || 0), 0);
    const graphError = (isEditMode() ? editCapability.graph_errors : profile.graph_errors || [])[0];
    if (!bootstrap?.comfy?.connected) {
      setModelStatus("bad", `ComfyUI 未连接：${bootstrap?.comfy?.error || "请先启动 8188 服务"}`);
    } else if (missing.length) {
      refs.installState.textContent = "模型下载：待开始";
      setModelStatus("pending", `缺少 ${missing.length} 项模型资产，待下载约 ${remaining.toFixed(2)} GB；可用磁盘 ${Number(plan.disk?.free_gb || 0).toFixed(1)} GB。`);
    } else {
      refs.installButton.disabled = true;
      refs.installButton.textContent = "等待 ComfyUI 重载";
      refs.installState.textContent = "模型文件：已下载，待重载";
      setModelStatus("bad", graphError || "模型文件已存在，但 ComfyUI 尚未加载。请重启 ComfyUI 后重新检查。");
    }
  }

  function applyProfileDefaults(force = true) {
    const profile = activeProfile();
    if (!profile) return;
    if (force || !refs.steps.value) refs.steps.value = String(profile.default_steps);
    if (force || !refs.cfg.value) refs.cfg.value = String(profile.default_cfg);
    if (force || !refs.sampler.value) refs.sampler.value = profile.default_sampler || "euler";
    if (force || !refs.scheduler.value) refs.scheduler.value = profile.default_scheduler || "simple";
    for (const [control, fixedValue] of [[refs.sampler, profile.fixed_sampler], [refs.scheduler, profile.fixed_scheduler]]) {
      control.disabled = Boolean(fixedValue);
      if (fixedValue) control.value = fixedValue;
      control.title = fixedValue ? "此档位使用已配置的采样方式；更换模型档位可解锁。" : "";
    }
    refs.width.max = String(profile.max_dimension || 2048);
    refs.height.max = String(profile.max_dimension || 2048);
    refs.width.step = String(profile.dimension_multiple || 16);
    refs.height.step = String(profile.dimension_multiple || 16);
    updateResolutionAvailability(true);
    renderQualityControls();
    const cfgFixed = profile.fixed_cfg != null;
    refs.cfg.readOnly = cfgFixed;
    refs.cfg.closest("label")?.classList.toggle("field-fixed", cfgFixed);
    renderEditControls({ resetStrength: force });
    if (editSource?.width && editSource?.height) applyEditSourceDimensions(editSource.width, editSource.height);
    if (!isFaceSwap()) scheduleWorkflowCheck();
  }

  function updatePromptCount() {
    refs.promptCount.textContent = String(refs.prompt.value.length);
  }

  function promptPayload() {
    return {
      prompt: refs.prompt.value,
      prompt_mode: selectedPromptMode(),
      style_preset: refs.style.value,
      exact_text: refs.exactText.value,
      profile: refs.profile.value,
      nsfw: refs.nsfw.checked,
      edit_mode: isEditMode(),
      source_adherence: refs.editStrength.value,
      auto_inject_trigger: Boolean(refs.autoInjectTrigger?.checked),
      auto_strip_negative: Boolean(refs.autoStripNegative?.checked),
      custom_trigger: refs.customTrigger?.value || "",
      nsfw_intensity: refs.nsfwIntensity?.dataset.manualStrength === "1" ? "" : refs.nsfwIntensity?.value || "medium",
    };
  }

  function schedulePromptPreview() {
    if (isFaceSwap()) return;
    updatePromptCount();
    window.clearTimeout(promptTimer);
    promptTimer = window.setTimeout(refreshPromptPreview, 220);
  }

  async function refreshPromptPreview() {
    if (isFaceSwap()) return;
    try {
      const data = await jsonRequest("/api/image-studio/prompt-preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(promptPayload()),
      });
      refs.effectivePrompt.textContent = data.effective || refs.prompt.value;
    } catch (error) {
      refs.effectivePrompt.textContent = `提示词整理失败：${error.message}`;
    }
  }

  function workflowQuery() {
    const params = new URLSearchParams({
      profile: refs.profile.value,
      aspect: refs.aspect.value,
      width: refs.width.value,
      height: refs.height.value,
      steps: refs.steps.value,
      cfg: refs.cfg.value,
      sampler: refs.sampler.value,
      scheduler: refs.scheduler.value,
      batch_size: refs.generationMode.value === "sequential" ? "1" : refs.batchSize.value,
      edit_mode: isEditMode() ? "true" : "false",
      source_adherence: refs.editStrength.value,
      edit_resize_mode: refs.editResizeMode.value,
      reference_count: supportsAdditionalReferences() ? String(editReferenceFiles.length) : "0",
      nsfw: refs.nsfw.checked ? "true" : "false",
      nsfw_lora_strength: refs.nsfwStrength.value,
    });
    return params.toString();
  }

  function scheduleWorkflowCheck() {
    if (isFaceSwap()) return;
    window.clearTimeout(workflowTimer);
    workflowTimer = window.setTimeout(() => checkWorkflow(true), 300);
  }

  let workflowCheckId = 0;
  async function checkWorkflow(quiet = false, query = workflowQuery().toString()) {
    const requestId = ++workflowCheckId;
    const current = () => requestId === workflowCheckId && query === workflowQuery().toString();
    if (isFaceSwap()) {
      const capability = faceSwapCapability();
      if (!capability.ready && !quiet) setFaceStatus("bad", (capability.errors || [])[0] || "换脸组件尚未就绪。");
      return Boolean(capability.ready);
    }
    const profile = activeProfile();
    if (!profile || !activeProfileReady()) return false;
    if (!quiet) setModelStatus("pending", `正在检查${isEditMode() ? "图片微调" : "文生图"} workflow。`);
    try {
      const data = await jsonRequest(`/api/image-studio/workflow?${query}`);
      if (!data.ok) throw new Error(formatError({ message: data.message, errors: data.errors }));
      if (!quiet && current()) setModelStatus("ok", `${data.label} 已通过预检，${data.node_count} 个节点。`);
      return true;
    } catch (error) {
      if (current()) setModelStatus("bad", error.message);
      return false;
    }
  }

  function historyMediaKey(jobId, item) {
    return [jobId, item.type || "output", item.subfolder || "", item.filename || ""].join("\u001f");
  }

  function resetHistoryDeleteArm() {
    historyDeleteArmed = false;
    window.clearTimeout(historyDeleteArmTimer);
    historyDeleteArmTimer = null;
    refs.historyDelete.classList.remove("armed");
  }

  function syncHistorySelectionControls() {
    const boxes = [...refs.historyGrid.querySelectorAll("input[data-history-select]")];
    const selectedOnPage = boxes.filter((box) => box.checked).length;
    const selectedCount = selectedHistoryItems.size;
    refs.historySelectAll.disabled = !boxes.length;
    refs.historySelectAll.checked = Boolean(boxes.length && selectedOnPage === boxes.length);
    refs.historySelectAll.indeterminate = selectedOnPage > 0 && selectedOnPage < boxes.length;
    refs.historyDelete.disabled = selectedCount === 0;
    if (!historyDeleteArmed) refs.historyDelete.textContent = selectedCount ? `删除所选 (${selectedCount})` : "删除所选";
  }

  function imageJobMethodLabel(job = {}) {
    if (job.edit_operation === "face_swap") {
      const strength = job.face_swap?.strength;
      return `换脸${strength ? ` · 身份 ${strength}` : ""}`;
    }
    if (job.edit_mode) return job.source_processing === "face" ? "面部参考微调" : (job.edit_label || "图片微调");
    return "文字生成";
  }

  function imageHistoryMeta(job = {}) {
    const parts = [`${job.width || "?"} × ${job.height || "?"}`, imageJobMethodLabel(job)];
    if (job.seed !== null && job.seed !== undefined && job.seed !== "") parts.push(`Seed ${job.seed}`);
    return parts.join(" · ");
  }

  function renderHistory(history = []) {
    const filtered = (history || []).filter(historyMatchesFilter);
    const cards = [];
    for (const job of filtered) {
      const entryId = String(job.history_entry_id || job.id || "");
      const media = (job.media || []).filter((item) => item.kind === "image");
      if (!media.length) {
        cards.push(`<article class="image-history-job image-history-pending">
          <strong>${escapeHtml(job.title || "图片任务")}</strong>
          <span>${escapeHtml(statusLabel(job.status))}</span>
        </article>`);
        continue;
      }
      const canDelete = Boolean(job.completed || TERMINAL.has(String(job.status || "").toLowerCase()));
      media.forEach((item, index) => {
        const key = historyMediaKey(job.id, item);
        if (canDelete) {
          historySelectionPayload.set(key, {
            job_id: job.id,
            filename: item.filename,
            subfolder: item.subfolder || "",
            type: item.type || "output",
          });
        }
        const selected = canDelete && selectedHistoryItems.has(key);
        cards.push(`<article class="image-history-job${selected ? " is-selected" : ""}" data-history-card="${escapeHtml(key)}">
          ${canDelete ? `<label class="image-history-select"><input type="checkbox" data-history-select="${escapeHtml(key)}"${selected ? " checked" : ""} /><span>选择</span></label>` : ""}
          <img src="${escapeHtml(item.url)}" alt="${escapeHtml(job.source_prompt || "图片结果")}" loading="lazy" />
          <div>
            <strong>${escapeHtml(job.style_label || job.title || "图片生成")}</strong>
            <small>${escapeHtml(imageHistoryMeta(job))}</small>
          </div>
          <div class="image-history-actions">
            <a class="secondary" href="${escapeHtml(item.url)}" download="${escapeHtml(item.filename || `image-${index + 1}.png`)}">下载图片</a>
            <button class="secondary" type="button" data-history-restore="${escapeHtml(entryId)}">还原此任务参数</button>
            <button class="secondary" type="button" data-history-edit="${escapeHtml(entryId)}" data-media-index="${index}">微调</button>
            <button class="secondary" type="button" data-history-face-swap="${escapeHtml(entryId)}" data-media-index="${index}">换脸</button>
            <button class="secondary" type="button" data-history-keyframe="${escapeHtml(entryId)}" data-media-index="${index}">送入视频</button>
          </div>
        </article>`);
      });
    }
    refs.historyGrid.innerHTML = cards.length ? cards.join("") : '<p class="empty-state">暂无图片生成记录。</p>';
    resetHistoryDeleteArm();
    syncHistorySelectionControls();
  }

  function historyPageTokens(page, totalPages) {
    if (totalPages <= 7) return Array.from({ length: totalPages }, (_item, index) => index + 1);
    const visible = new Set([1, totalPages, page - 1, page, page + 1]);
    if (page <= 3) [2, 3, 4].forEach((item) => visible.add(item));
    if (page >= totalPages - 2) [totalPages - 3, totalPages - 2, totalPages - 1].forEach((item) => visible.add(item));
    const pages = [...visible].filter((item) => item >= 1 && item <= totalPages).sort((left, right) => left - right);
    const tokens = [];
    pages.forEach((item, index) => {
      if (index && item - pages[index - 1] > 1) tokens.push(`gap-${pages[index - 1]}-${item}`);
      tokens.push(item);
    });
    return tokens;
  }

  function renderHistoryPagination(pagination = historyPagination) {
    const total = Math.max(0, Number(pagination.total || 0));
    const totalPages = Math.max(1, Number(pagination.total_pages || 1));
    const page = Math.max(1, Math.min(totalPages, Number(pagination.page || 1)));
    historyPagination = {
      page,
      page_size: Number(pagination.page_size || HISTORY_PAGE_SIZE),
      total,
      total_pages: totalPages,
    };
    refs.historyPageSummary.textContent = total
      ? `第 ${page} / ${totalPages} 页 · 每页 ${HISTORY_PAGE_SIZE} 张 · 共 ${total} 条生成记录`
      : "共 0 条生成记录";
    refs.historyPrev.disabled = historyLoading || page <= 1;
    refs.historyNext.disabled = historyLoading || page >= totalPages || total === 0;
    refs.historyPageNumbers.innerHTML = total
      ? historyPageTokens(page, totalPages)
          .map((token) => {
            if (typeof token === "string") return '<span class="image-history-page-gap" aria-hidden="true">…</span>';
            const active = token === page;
            return `<button class="image-history-page-button${active ? " is-active" : ""}" type="button" data-history-page="${token}" aria-label="第 ${token} 页"${active ? ' aria-current="page"' : ""}${historyLoading ? " disabled" : ""}>${token}</button>`;
          })
          .join("")
      : "";
  }

  function statusLabel(status) {
    const labels = {
      queued: "排队中",
      running: "生成中",
      reconnecting: "重新连接",
      success: "已完成",
      failed: "失败",
      lost: "任务丢失",
      interrupted: "已中断",
      paused: "已暂停",
      pausing: "暂停中",
      canceled: "已取消",
      cancelled: "已取消",
      canceling: "取消中",
    };
    return labels[status] || status || "等待中";
  }

  function historyEntryById(entryId) {
    return (bootstrap?.history || []).find((item) => String(item.history_entry_id || item.id || "") === String(entryId || ""));
  }

  function mediaMarkup(media, prompt) {
    return `<div class="image-output-grid">${media
      .map(
        (item, index) => `<figure class="image-output-item">
          <img src="${escapeHtml(item.url)}" alt="${escapeHtml(prompt || `生成结果 ${index + 1}`)}" />
          <figcaption>
            <span>图片 ${index + 1}</span>
            <a href="${escapeHtml(item.url)}" download="${escapeHtml(item.filename || `image-${index + 1}.png`)}">下载图片 ${index + 1}</a>
          </figcaption>
        </figure>`,
      )
      .join("")}</div>`;
  }

  function imageJobIsTerminal(job) {
    return Boolean(job?.completed || TERMINAL.has(String(job?.status || "").toLowerCase()));
  }

  function upsertHistoryJob(job) {
    if (!job?.id) return;
    const history = [...(bootstrap?.history || [])];
    const index = history.findIndex((item) => item.id === job.id);
    if (index >= 0) history[index] = job;
    else if (historyPage === 1) history.unshift(job);
    else return;
    history.sort((left, right) => Number(right.created_at || 0) - Number(left.created_at || 0));
    bootstrap = { ...(bootstrap || {}), history: history.slice(0, HISTORY_PAGE_SIZE) };
  }

  function formatJobTime(value) {
    const timestamp = Number(value || 0);
    if (!timestamp) return "刚刚";
    return new Date(timestamp).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false });
  }

  function renderTaskQueue() {
    const jobs = [...activeJobIds]
      .map((jobId) => jobCache.get(jobId) || (bootstrap?.history || []).find((item) => item.id === jobId) || { id: jobId, status: "queued" })
      .sort((left, right) => Number(right.created_at || 0) - Number(left.created_at || 0));
    refs.taskQueueCount.textContent = `${jobs.length} 个进行中`;
    if (!jobs.length) {
      refs.taskQueueList.innerHTML = '<p class="empty-state">没有正在生成的任务。</p>';
      updateGenerateState();
      return;
    }
    refs.taskQueueList.innerHTML = jobs
      .map((job) => {
        const percent = Math.max(0, Math.min(100, Number(job.progress?.percent || 0)));
        const mediaCount = (job.media || []).filter((item) => item.kind === "image").length;
        const total = Number(job.batch_size || 1);
        return `<article class="image-task-row${job.id === activeJobId ? " is-focused" : ""}" data-task-id="${escapeHtml(job.id)}">
          <div class="image-task-copy">
            <strong class="image-task-title">${escapeHtml(job.title || "图片任务")}</strong>
            <small>${escapeHtml(formatJobTime(job.created_at))} · ${mediaCount}/${total} 张 · ${escapeHtml(statusLabel(job.status))}</small>
          </div>
          <div class="image-task-progress">
            <div class="image-task-progress-line"><span style="width:${percent}%"></span></div>
            <span>${escapeHtml(job.progress?.label || `${percent.toFixed(0)}%`)}</span>
          </div>
          <div class="image-task-actions">
            <button class="secondary" type="button" data-task-view="${escapeHtml(job.id)}">查看</button>
            <button class="secondary danger" type="button" data-task-cancel="${escapeHtml(job.id)}">中断</button>
          </div>
        </article>`;
      })
      .join("");
    updateGenerateState();
  }

  function renderJob(job) {
    const status = job.status || "queued";
    const faceSwap = job.edit_operation === "face_swap";
    const total = Number(job.batch_size || refs.batchSize.value || 1);
    const modeLabel = job.generation_mode === "sequential" ? "逐张出图" : "整批生成";
    const media = (job.media || []).filter((item) => item.kind === "image");
    if (media.length) latestJob = job;
    const terminal = imageJobIsTerminal(job);
    refs.cancelJob.classList.toggle("hidden", terminal);
    refs.cancelJob.disabled = status === "canceling";
    refs.cancelJob.dataset.jobId = terminal ? "" : job.id || "";
    refs.jobStatus.textContent = statusLabel(status);
    const jobMeta = faceSwap
      ? [
        `${job.width || "?"} × ${job.height || "?"}`,
        "单张换脸",
        `身份替换 ${job.face_swap?.strength || "100%"}`,
        job.face_swap?.restore_model && job.face_swap.restore_model !== "none"
          ? `面部修复 ${job.face_swap.restore_model}`
          : "不额外修复",
        "目标图其余区域不扩散重绘",
      ]
      : [
        `${job.width || refs.width.value} × ${job.height || refs.height.value}`,
        `${total} 张 · ${modeLabel}`,
        `${job.steps || refs.steps.value} 步`,
        `Seed ${job.seed ?? refs.seed.value}`,
        job.edit_mode
          ? `${imageJobMethodLabel(job)}${job.source_adherence == null ? "" : ` · 原图遵循 ${Math.round(Number(job.source_adherence) * 100)}%`}`
          : "文字生成",
      ];
    refs.jobMeta.innerHTML = jobMeta
      .map((item) => `<span>${escapeHtml(item)}</span>`)
      .join("");
    if (job.output_dir) {
      const output = {
        ...(bootstrap?.output || {}),
        dir: job.output_dir,
        subdir: job.output_subdir || bootstrap?.output?.subdir || "image_studio",
      };
      bootstrap = { ...(bootstrap || {}), output };
      renderOutputLocation(output);
    }
    setProgress(job);
    if (media.length) {
      latestMedia = media;
      refs.resultStage.innerHTML = mediaMarkup(media, job.source_prompt);
      refs.resultActions.classList.remove("hidden");
    }

    if (status === "success") {
      latestMedia = media;
      refs.resultHint.textContent = `${media.length} 张${faceSwap ? "换脸" : job.edit_mode ? "微调" : "生成"}图片已保存`;
      if (faceSwap && isAdvancedModuleEnabled("detailer")) {
        setLog("换脸完成。已启用 Detailer 模块时，后续可在结果上继续微调或送入视频工作流保留身份。");
      }
      refs.resultStage.innerHTML = media.length
        ? mediaMarkup(media, job.source_prompt)
        : "<p>任务已完成，但没有读取到输出图片。</p>";
      refs.resultActions.classList.toggle("hidden", !media.length);
      updateGenerateState();
      return;
    }

    if (TERMINAL.has(status)) {
      refs.resultHint.textContent = media.length ? `${media.length}/${total} 张已保存，后续任务未完成` : "生成未完成";
      if (!media.length) refs.resultStage.innerHTML = `<p>${escapeHtml(job.error || "任务执行失败，请查看日志。")}</p>`;
      refs.resultActions.classList.toggle("hidden", !media.length);
      setLog([job.error, ...(job.friendly_messages || [])].filter(Boolean).join("\n"));
      updateGenerateState();
      return;
    }

    refs.resultHint.textContent = status === "reconnecting"
      ? "正在恢复 ComfyUI 连接"
      : media.length
        ? `${media.length}/${total} 张已保存，下一张继续生成`
        : "模型正在生成";
    if (!media.length) {
      refs.resultStage.innerHTML = `<div class="image-generating-state"><strong>${escapeHtml(statusLabel(status))}</strong><span>${escapeHtml(job.progress?.label || `任务 ${job.prompt_id || job.id || "已提交"}`)}</span></div>`;
      refs.resultActions.classList.add("hidden");
    }
    updateGenerateState();
    if (job.connection_error) setLog(job.connection_error);
  }

  function persistActiveJobs() {
    localStorage.setItem(STORAGE.activeJobs, JSON.stringify([...activeJobIds]));
    if (activeJobId && activeJobIds.has(activeJobId)) localStorage.setItem(STORAGE.activeJob, activeJobId);
    else localStorage.removeItem(STORAGE.activeJob);
  }

  function rememberActiveJob(jobId, job = null) {
    if (!jobId) return;
    activeJobIds.add(jobId);
    activeJobId = jobId;
    if (job) {
      jobCache.set(jobId, job);
      upsertHistoryJob(job);
    }
    persistActiveJobs();
    renderTaskQueue();
    startActivePolling();
  }

  function stopFocusedWatching() {
    if (activeEvents) activeEvents.close();
    activeEvents = null;
  }

  function stopWatching() {
    stopFocusedWatching();
    if (pollTimer) window.clearInterval(pollTimer);
    pollTimer = null;
  }

  function removeActiveJob(jobId) {
    activeJobIds.delete(jobId);
    persistActiveJobs();
    if (!activeJobIds.size && pollTimer) {
      window.clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  async function pollJob(jobId) {
    try {
      const job = await jsonRequest(`/api/jobs/${encodeURIComponent(jobId)}`);
      handleJobUpdate(job);
    } catch (error) {
      if (/任务不存在|404/.test(error.message)) removeActiveJob(jobId);
      setLog(`任务状态读取失败：${error.message}`);
    }
  }

  async function pollActiveJobs() {
    if (pollInFlight || !activeJobIds.size) return;
    pollInFlight = true;
    try {
      await Promise.all([...activeJobIds].map((jobId) => pollJob(jobId)));
    } finally {
      pollInFlight = false;
    }
  }

  function startActivePolling() {
    if (!activeJobIds.size || pollTimer) return;
    void pollActiveJobs();
    pollTimer = window.setInterval(pollActiveJobs, 1800);
  }

  function handleJobUpdate(job) {
    if (!job?.id) return;
    const previous = jobCache.get(job.id);
    const previousMediaCount = (previous?.media || []).length;
    jobCache.set(job.id, job);
    upsertHistoryJob(job);
    const terminal = imageJobIsTerminal(job);
    if (terminal) removeActiveJob(job.id);
    else activeJobIds.add(job.id);
    if (!activeJobId) activeJobId = job.id;
    if (job.id === activeJobId) renderJob(job);
    renderTaskQueue();
    if (terminal || previousMediaCount !== (job.media || []).length) {
      if (historyPage === 1) renderHistory(bootstrap?.history || []);
      void loadHistoryPage(historyPage, { syncJobs: false });
    }
    if (terminal && job.id === activeJobId) stopFocusedWatching();
    void maybeQueueVideoAfterStill(job);
  }

  function watchJob(jobId) {
    if (!jobId) return;
    stopFocusedWatching();
    activeJobId = jobId;
    const cached = jobCache.get(jobId) || (bootstrap?.history || []).find((item) => item.id === jobId);
    if (cached) {
      handleJobUpdate(cached);
      if (imageJobIsTerminal(cached)) {
        renderTaskQueue();
        return;
      }
    }
    startActivePolling();
    if (window.EventSource) {
      activeEvents = new EventSource(`/api/jobs/${encodeURIComponent(jobId)}/events`);
      activeEvents.onmessage = (event) => {
        const job = JSON.parse(event.data);
        handleJobUpdate(job);
      };
      activeEvents.onerror = () => {
        activeEvents?.close();
        activeEvents = null;
      };
    }
    void pollJob(jobId);
    persistActiveJobs();
    renderTaskQueue();
  }

  function saveCurrentParams() {
    const params = {};
    for (const [name, value] of new FormData(form).entries()) {
      if (value instanceof File || name.startsWith("source_image") || name.startsWith("face_") || name === "source_processing") continue;
      params[name] = value;
    }
    localStorage.setItem(STORAGE.lastParams, JSON.stringify(params));
  }

  function applySavedParams() {
    let params;
    try {
      params = JSON.parse(localStorage.getItem(STORAGE.lastParams) || "null");
    } catch (_error) {
      params = null;
    }
    if (!params) {
      setLog("还没有可沿用的图片参数。");
      return;
    }
    for (const [name, value] of Object.entries(params)) {
      const input = form.elements.namedItem(name);
      if (!input) continue;
      if (input instanceof RadioNodeList) {
        input.value = value;
      } else {
        input.value = value;
      }
    }
    selectAspect(params.aspect || "custom", Number(params.width), Number(params.height));
    selectTaskMode(params.edit_mode === "true" ? "edit" : "t2i", { schedule: false });
    if (isEditMode()) selectEditOperation(params.edit_operation || "instruction", { schedule: false });
    refs.sourceProcessing.value = "full";
    clearFaceExtractionState();
    selectGenerationMode(params.generation_mode || "batch", { schedule: false });
    selectBatch(Number(params.batch_size || 1));
    applyProfileDefaults(false);
    if (!isFaceSwap()) {
      schedulePromptPreview();
      scheduleWorkflowCheck();
    }
    setLog(isEditMode() && !hasEditSource() ? "已恢复微调参数，请重新选择源图片。" : "已恢复上次图片参数。");
  }

  async function submitFaceSwap() {
    if (!hasEditSource()) {
      refs.editFile.focus();
      setLog("请先选择目标图，或在最近生成中点击“微调”。");
      return;
    }
    if (!hasIdentityFaceSource()) {
      refs.identityFaceFile.focus();
      setLog("请选择一张身份参考图。 ");
      return;
    }
    if (!faceSourceReady()) {
      setLog(faceExtractionBusy ? "正在检测双方人脸，请稍候。" : "请先确认授权、检测双方并分别选择一张脸。 ");
      if (!faceAuthorizationConfirmed) requestFaceAuthorization(refs.faceAnalyze);
      return;
    }
    if (!faceSwapCapability().ready) {
      setFaceStatus("bad", (faceSwapCapability().errors || [])[0] || "换脸组件尚未就绪。 ");
      return;
    }
    submitting = true;
    updateGenerateState();
    refs.jobStatus.textContent = "提交中";
    refs.resultHint.textContent = "正在提交到 ComfyUI";
    refs.resultStage.innerHTML = '<div class="image-generating-state"><strong>提交中</strong><span>正在创建换脸微调任务</span></div>';
    refs.resultActions.classList.add("hidden");
    setProgress("queued");
    setLog("");
    saveCurrentParams();
    const payload = new FormData();
    payload.append("authorization_confirmed", "true");
    const authToken = faceAuthTokenValue();
    if (authToken) payload.append("face_authorization_token", authToken);
    payload.append("target_face_extract_id", refs.faceExtractId.value);
    payload.append("target_face_index", refs.faceIndex.value);
    payload.append("identity_face_extract_id", refs.identityFaceExtractId.value);
    payload.append("identity_face_index", refs.identityFaceIndex.value);
    payload.append("face_swap_strength", refs.faceSwapStrength.value);
    payload.append("face_restore_model", refs.faceRestoreModel.value || "none");
    payload.append("face_restore_visibility", refs.faceRestoreVisibility.value || "0.8");
    try {
      const job = await jsonRequest("/api/image-studio/face-swap", { method: "POST", body: payload });
      rememberActiveJob(job.id, job);
      renderJob(job);
      watchJob(job.id);
    } catch (error) {
      refs.jobStatus.textContent = "失败";
      refs.resultHint.textContent = "提交失败";
      refs.resultStage.innerHTML = `<p>${escapeHtml(error.message)}</p>`;
      setProgress("failed");
      setLog(error.message);
    } finally {
      submitting = false;
      updateGenerateState();
    }
  }

  async function submitCompareWallJobs() {
    if (!(await checkWorkflow(false))) return;
    submitting = true;
    updateGenerateState();
    refs.jobStatus.textContent = "提交中";
    refs.resultHint.textContent = "对比墙：正在提交两条任务";
    refs.resultStage.innerHTML = '<div class="image-generating-state"><strong>对比墙</strong><span>同种子分别提交无限制开/关</span></div>';
    refs.resultActions.classList.add("hidden");
    setProgress("queued");
    setLog("");
    saveCurrentParams();
    const lockedSeed = refs.seed.value && refs.seed.value !== "-1" ? refs.seed.value : String(Math.floor(Math.random() * 1_000_000_000));
    refs.seed.value = lockedSeed;
    const intensityValue = refs.nsfwIntensity?.value || "";
    if (refs.nsfwIntensity && refs.nsfwIntensity.dataset.manualStrength === "1") refs.nsfwIntensity.value = "";
    try {
      for (const nsfwOn of [true, false]) {
        const wasChecked = refs.nsfw.checked;
        refs.nsfw.checked = nsfwOn;
        const payload = syncBooleanFormFields(new FormData(form));
        payload.set("seed", lockedSeed);
        payload.set("triple_compare", "false");
        payload.set("batch_size", "1");
        payload.set("generation_mode", "batch");
        const job = await jsonRequest("/api/image-studio/generate", { method: "POST", body: payload });
        rememberActiveJob(job.id, job);
        renderJob(job);
        watchJob(job.id);
        refs.nsfw.checked = wasChecked;
      }
      setLog(`对比墙已提交 2 个任务，Seed ${lockedSeed}。`);
    } catch (error) {
      refs.jobStatus.textContent = "失败";
      refs.resultHint.textContent = "对比墙提交失败";
      refs.resultStage.innerHTML = `<p>${escapeHtml(error.message)}</p>`;
      setProgress("failed");
      setLog(error.message);
    } finally {
      if (refs.nsfwIntensity) refs.nsfwIntensity.value = intensityValue;
      submitting = false;
      updateGenerateState();
    }
  }

  async function submitGeneration(event) {
    event?.preventDefault();
    if (submitting) return;
    if (isFaceSwap()) {
      await submitFaceSwap();
      return;
    }
    if (compareWallEnabled && !isEditMode()) {
      if (pendingStillToVideo) {
        pendingStillToVideo = null;
        setLog("对比墙开启时不会自动出视频。已改为只提交静帧对比。");
      }
      await submitCompareWallJobs();
      return;
    }
    if (!refs.prompt.value.trim()) {
      refs.prompt.focus();
      setLog(isEditMode() ? "请输入编辑要求。" : "请输入画面描述。");
      return;
    }
    if (isEditMode() && !hasEditSource()) {
      refs.editFile.focus();
      setLog("请先选择一张源图片，或在最近生成中点击“微调”。");
      return;
    }
    submitting = true;
    updateGenerateState();
    const query = workflowQuery().toString();
    const payload = syncBooleanFormFields(new FormData(form));
    if (refs.nsfwIntensity?.dataset.manualStrength === "1") payload.set("nsfw_intensity", "");
    const ready = await checkWorkflow(false, query);
    if (!ready || query !== workflowQuery().toString()) {
      submitting = false;
      updateGenerateState();
      if (ready) setLog("预检期间设置已变化，请确认后重新提交。");
      return;
    }
    refs.jobStatus.textContent = "提交中";
    refs.resultHint.textContent = "正在提交到 ComfyUI";
    refs.resultStage.innerHTML = `<div class="image-generating-state"><strong>提交中</strong><span>正在创建${isEditMode() ? "图片微调" : "文生图"}任务</span></div>`;
    refs.resultActions.classList.add("hidden");
    setProgress("queued");
    setLog("");
    saveCurrentParams();
    try {
      const job = await jsonRequest("/api/image-studio/generate", { method: "POST", body: payload });
      rememberActiveJob(job.id, job);
      if (pendingStillToVideo && !pendingStillToVideo.jobId && !isEditMode() && !isFaceSwap()) {
        pendingStillToVideo.jobId = job.id;
      }
      handleJobUpdate(job);
      watchJob(job.id);
    } catch (error) {
      if (pendingStillToVideo && !pendingStillToVideo.jobId) pendingStillToVideo = null;
      refs.jobStatus.textContent = "失败";
      refs.resultHint.textContent = "提交失败";
      refs.resultStage.innerHTML = `<p>${escapeHtml(error.message)}</p>`;
      setProgress("failed");
      setLog(error.message);
    } finally {
      submitting = false;
      updateGenerateState();
    }
  }

  function selectAspect(id, width, height) {
    refs.aspect.value = id || "custom";
    if (width) refs.width.value = String(width);
    if (height) refs.height.value = String(height);
    refs.aspectGrid.querySelectorAll("button").forEach((button) => button.classList.toggle("active", button.dataset.aspect === id));
    updateResolutionNote();
    scheduleWorkflowCheck();
  }

  function commitCustomDimensions() {
    const fitted = fitImageDimensions(refs.width.value, refs.height.value);
    selectAspect("custom", fitted.width, fitted.height);
  }

  function updateBatchModeNote() {
    const count = Math.max(1, Math.min(20, Number(refs.batchSize.value) || 1));
    const maximum = Math.max(1, Number(activeProfile()?.max_batch || 1));
    if (refs.generationMode.value === "sequential") {
      refs.batchModeNote.textContent = count > maximum
        ? `${count} 张超过当前模型单批上限 ${maximum} 张，已使用逐张出图。`
        : "每张独立排队，完成一张就立即显示；Seed 会依次递增。";
    } else {
      refs.batchModeNote.textContent = `一次工作流生成 ${count} 张；当前模型单批上限 ${maximum} 张。`;
    }
  }

  function selectGenerationMode(value, { schedule = true } = {}) {
    const count = Math.max(1, Math.min(20, Number(refs.batchSize.value) || 1));
    const maximum = Math.max(1, Number(activeProfile()?.max_batch || 1));
    const requested = value === "sequential" ? "sequential" : "batch";
    const normalized = requested === "batch" && count > maximum ? "sequential" : requested;
    refs.generationMode.value = normalized;
    refs.generationModeSwitch.querySelectorAll("button[data-generation-mode]").forEach((button) => {
      button.classList.toggle("active", button.dataset.generationMode === normalized);
    });
    updateBatchModeNote();
    if (schedule) scheduleWorkflowCheck();
  }

  function selectBatch(value, { schedule = true } = {}) {
    const normalized = Math.max(1, Math.min(20, Math.round(Number(value) || 1)));
    refs.batchSize.value = String(normalized);
    refs.batchSwitch.querySelectorAll("button").forEach((button) => button.classList.toggle("active", Number(button.dataset.batch) === normalized));
    selectGenerationMode(refs.generationMode.value, { schedule: false });
    if (schedule) scheduleWorkflowCheck();
  }

  function useMediaForEdit(media, job = null, operation = "instruction") {
    if (!media?.filename || !media?.url) return;
    const profileId = job?.model_profile;
    if (operation !== "face_swap" && profileId && (bootstrap?.profiles || []).some((item) => item.id === profileId && item.image_edit?.supported)) {
      refs.profile.value = profileId;
      applyProfileDefaults(true);
    }
    selectTaskMode("edit", { schedule: false });
    selectEditOperation(operation, { schedule: false });
    setEditSource({
      filename: media.filename,
      subfolder: media.subfolder || "",
      type: media.type || "output",
      url: media.url,
      label: `${job?.title || "最近生成"} · ${media.filename}`,
    });
    if (operation === "face_swap") {
      refs.identityFaceFile.focus({ preventScroll: true });
    } else {
      refs.prompt.focus({ preventScroll: true });
      refs.prompt.select();
    }
    refs.editPanel.scrollIntoView({ behavior: "smooth", block: "start" });
    setLog(operation === "face_swap"
      ? "已把图片设为完整目标图。请导入身份参考图，确认双方授权后分别选脸。"
      : "已把图片载入微调模式，请填写编辑要求；原图会在提交时复制到 ComfyUI input。 ");
  }

  async function sendMediaToVideo(media, job = null, { queueVideo = false } = {}) {
    if (!media?.filename) return;
    refs.toVideo.disabled = true;
    if (refs.stillToVideo) refs.stillToVideo.disabled = true;
    setLog(queueVideo ? "正在把图片送入视频并排队图生视频。" : "正在把图片复制到 ComfyUI input，并同步视频关键帧状态。");
    try {
      const context = job || latestJob || {};
      const handoff = await jsonRequest("/api/image-studio/handoff", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          filename: media.filename,
          subfolder: media.subfolder || "",
          type: media.type || "output",
          model_profile: context.model_profile || refs.profile.value,
          model_label: context.title || activeProfile()?.label || "",
          source_prompt: context.source_prompt || refs.prompt.value,
          nsfw: Boolean(context.nsfw ?? refs.nsfw.checked),
          nsfw_lora_strength: refs.nsfwStrength?.value || context.nsfw_lora_strength || null,
          nsfw_intensity: refs.nsfwIntensity?.value || "",
          character_id: selectedCharacterId(),
          identity_filename: identityFaceSource?.filename || "",
          face_authorization_confirmed: Boolean(faceAuthorizationConfirmed),
          wizard_id: pendingStillToVideo?.wizardId || rememberedAdultWizardId() || refs.nsfwWizard?.value || "",
        }),
      });
      if (typeof window.acceptImageStudioKeyframe !== "function" || !window.acceptImageStudioKeyframe(handoff, { focus: !queueVideo, queueVideo })) {
        throw new Error("视频工作流没有加载关键帧交接接口，请刷新页面后重试。");
      }
      if (queueVideo) {
        if (typeof window.queueVideoFromKeyframe !== "function") {
          throw new Error("视频提交接口未加载，请刷新页面后重试。");
        }
        await window.queueVideoFromKeyframe();
        setLog("静帧已送入视频，图生视频任务已排队。可在视频工作流查看进度。");
      } else {
        setLog(`${handoff.message} 已按当前玩法套到图生视频；可在关键帧步骤继续调整。`);
      }
    } catch (error) {
      setLog(`${queueVideo ? "自动出视频失败" : "送入视频关键帧失败"}：${error.message}`);
      if (queueVideo) throw error;
    } finally {
      refs.toVideo.disabled = false;
      if (refs.stillToVideo) refs.stillToVideo.disabled = false;
    }
  }

  async function maybeQueueVideoAfterStill(job) {
    const pending = pendingStillToVideo;
    if (!pending || pending.queued || !job?.id) return;
    if (!pending.jobId || pending.jobId !== job.id) return;
    const status = String(job.status || "").toLowerCase();
    if (!imageJobIsTerminal(job)) return;
    if (status !== "success") {
      pendingStillToVideo = null;
      syncAdultGenerateButton((playbook().wizard_modes || []).find((item) => item.id === pending.wizardId));
      setLog("静帧未完成，已取消自动出视频。");
      return;
    }
    if (job.edit_mode || job.edit_operation === "face_swap" || job.triple_compare) {
      pendingStillToVideo = null;
      setLog("当前结果不是单张文生图，已取消自动出视频。可点「送入并生成视频」。");
      return;
    }
    const media = (job.media || []).filter((item) => item.kind === "image");
    if (!media.length) {
      pendingStillToVideo = null;
      setLog("静帧完成但没有图片，已取消自动出视频。");
      return;
    }
    if (media.length > 1 || Number(job.batch_size || 1) > 1) {
      pendingStillToVideo = null;
      syncAdultGenerateButton((playbook().wizard_modes || []).find((item) => item.id === pending.wizardId));
      setLog("批量静帧完成。请选一张点「送入并生成视频」。");
      return;
    }
    pending.queued = true;
    pendingStillToVideo = pending;
    try {
      await sendMediaToVideo(media[0], job, { queueVideo: true });
    } catch (_error) {
      /* sendMediaToVideo already logged */
    } finally {
      pendingStillToVideo = null;
      syncAdultGenerateButton((playbook().wizard_modes || []).find((item) => item.id === pending.wizardId));
    }
  }

  function downloadAll() {
    latestMedia.forEach((media, index) => {
      const link = document.createElement("a");
      link.href = media.url;
      link.download = media.filename || `qwen-image-${index + 1}.png`;
      document.body.appendChild(link);
      link.click();
      link.remove();
    });
  }

  function currentTargetPath() {
    if (isFaceSwap()) {
      return (imageModelDownloadPath || localStorage.getItem(STORAGE.downloadPath) || "").trim();
    }
    return (refs.downloadPath.value || localStorage.getItem(STORAGE.downloadPath) || "").trim();
  }

  function bootstrapQuery({ refresh = false, limit = HISTORY_PAGE_SIZE } = {}) {
    const params = new URLSearchParams({ limit: String(limit) });
    if (refresh) params.set("refresh", "true");
    if (refs.profile.value) params.set("profile", refs.profile.value);
    const target = currentTargetPath();
    if (target) params.set("target_dir", target);
    return params.toString();
  }

  function syncActiveJobsFromHistory(history = []) {
    for (const job of history) {
      if (!job?.id || (job.kind !== "image_generation" && !String(job.mode || "").startsWith("image_t2i"))) continue;
      jobCache.set(job.id, job);
      if (imageJobIsTerminal(job)) activeJobIds.delete(job.id);
      else activeJobIds.add(job.id);
    }
    persistActiveJobs();
    renderTaskQueue();
  }

  async function cancelImageJob(jobId) {
    if (!jobId) return;
    const current = jobCache.get(jobId) || (bootstrap?.history || []).find((item) => item.id === jobId);
    if (imageJobIsTerminal(current)) return;
    const pending = { ...(current || { id: jobId }), status: "canceling", completed: false };
    pending.progress = { ...(pending.progress || {}), label: "正在中断该任务" };
    handleJobUpdate(pending);
    setLog("正在从 ComfyUI 队列中移除该任务；已经完成的图片会保留。");
    try {
      const job = await jsonRequest(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, { method: "POST" });
      handleJobUpdate(job);
      await refreshHistory();
      setLog(job.status_note || "任务已中断，已生成图片仍然保留。");
    } catch (error) {
      setLog(`中断任务失败：${error.message}`);
      void pollJob(jobId);
    }
  }

  function selectedHistoryPayload() {
    return [...selectedHistoryItems]
      .map((key) => historySelectionPayload.get(key))
      .filter(Boolean);
  }

  async function deleteSelectedHistory() {
    const items = selectedHistoryPayload();
    if (!items.length) return;
    if (!historyDeleteArmed) {
      historyDeleteArmed = true;
      refs.historyDelete.classList.add("armed");
      refs.historyDelete.textContent = `确认删除 ${items.length} 张`;
      historyDeleteArmTimer = window.setTimeout(() => {
        resetHistoryDeleteArm();
        syncHistorySelectionControls();
      }, 6000);
      return;
    }
    refs.historyDelete.disabled = true;
    refs.historyDelete.textContent = "删除中";
    try {
      const data = await jsonRequest("/api/image-studio/history/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items }),
      });
      selectedHistoryItems.clear();
      historySelectionPayload.clear();
      await loadHistoryPage(historyPage);
      setLog(data.errors?.length ? `已删除 ${data.removed} 张；${data.errors.join("\n")}` : `已删除 ${data.removed} 张图片和对应记录。`);
    } catch (error) {
      resetHistoryDeleteArm();
      syncHistorySelectionControls();
      setLog(`删除最近生成失败：${error.message}`);
    }
  }

  async function loadHistoryPage(page = historyPage, { scroll = false, syncJobs = true } = {}) {
    if (historyLoading) return null;
    historyLoading = true;
    renderHistoryPagination(historyPagination);
    try {
      const params = new URLSearchParams({ page: String(page), page_size: String(HISTORY_PAGE_SIZE) });
      const data = await jsonRequest(`/api/image-studio/history?${params}`);
      historyPage = Number(data.page || 1);
      const pagination = {
        page: historyPage,
        page_size: Number(data.page_size || HISTORY_PAGE_SIZE),
        total: Number(data.total || 0),
        total_pages: Number(data.total_pages || 1),
      };
      bootstrap = { ...(bootstrap || {}), history: data.items || [], history_pagination: pagination };
      renderHistory(bootstrap.history);
      historyPagination = pagination;
      if (syncJobs) syncActiveJobsFromHistory(bootstrap.history);
      if (scroll) refs.historySection.scrollIntoView({ behavior: "smooth", block: "start" });
      return data;
    } finally {
      historyLoading = false;
      renderHistoryPagination(historyPagination);
    }
  }

  async function refreshHistory() {
    try {
      await loadHistoryPage(historyPage);
      resumeActiveJob();
    } catch (error) {
      refs.historyGrid.innerHTML = `<p class="empty-state">历史记录读取失败：${escapeHtml(error.message)}</p>`;
    }
  }

  async function loadBootstrap(refresh = false) {
    refs.refreshButton.disabled = true;
    setModelStatus("pending", "正在检查模型、节点和 workflow。");
    try {
      const data = await jsonRequest(`/api/image-studio?${bootstrapQuery({ refresh })}`);
      bootstrap = data;
      renderStaticControls(data);
      renderPlaybookControls();
      renderEditStrengthPresetSwitches();
      renderModelReadiness();
      await loadNsfwCapabilities();
      renderExtensionCapabilities();
      historyPage = Number(data.history_pagination?.page || 1);
      historyPagination = {
        page: historyPage,
        page_size: Number(data.history_pagination?.page_size || HISTORY_PAGE_SIZE),
        total: Number(data.history_pagination?.total || (data.history || []).length),
        total_pages: Number(data.history_pagination?.total_pages || 1),
      };
      renderHistory(data.history || []);
      renderHistoryPagination(historyPagination);
      syncActiveJobsFromHistory(data.history || []);
      await refreshPromptPreview();
      if (activeProfileReady()) await checkWorkflow(true);
      resumeInstallJob();
      resumeActiveJob();
    } catch (error) {
      refs.badge.textContent = "不可用";
      setModelStatus("bad", error.message);
      refs.generate.disabled = true;
    } finally {
      refs.refreshButton.disabled = false;
    }
  }

  async function installPlanFor(profileId) {
    const active = activeProfile();
    if (active?.install_profile === profileId && active.install_plan) return active.install_plan;
    const params = new URLSearchParams({ profile: profileId });
    const target = currentTargetPath();
    if (target) params.set("target_dir", target);
    const data = await jsonRequest(`/api/install-plan?${params}`);
    return data.install_plan || {};
  }

  async function startInstall(profileOverride = "", actionLabel = "模型文件", targetOverride = "") {
    const profileId = profileOverride || activeProfile()?.install_profile;
    if (!profileId) return;
    if (refs.installPanel && "open" in refs.installPanel) refs.installPanel.open = true;
    const faceInstall = profileId === faceSwapCapability().install_profile;
    const actionButton = faceInstall ? refs.faceInstall : profileOverride ? refs.installNsfw : refs.installButton;
    let plan;
    try {
      plan = targetOverride
        ? (await jsonRequest(`/api/install-plan?${new URLSearchParams({ profile: profileId, target_dir: targetOverride })}`)).install_plan || {}
        : await installPlanFor(profileId);
    } catch (error) {
      setModelStatus("bad", `安装计划读取失败：${error.message}`);
      return;
    }
    const missing = Number(plan.missing_expected_gb || 0);
    if (!installArmed || installArmedProfile !== profileId) {
      installArmed = true;
      installArmedProfile = profileId;
      actionButton.textContent = `确认下载${actionLabel}`;
      setModelStatus("pending", `${actionLabel}将下载约 ${missing.toFixed(2)} GB 到 ${targetOverride || currentTargetPath()}；再次点击确认。`);
      if (isFaceSwap()) setFaceStatus("pending", `${actionLabel}将下载约 ${missing.toFixed(2)} GB 到当前 ComfyUI 目录；再次点击确认。`);
      window.clearTimeout(installArmTimer);
      installArmTimer = window.setTimeout(() => {
        installArmed = false;
        installArmedProfile = "";
        if (faceInstall) faceStatusOverride = null;
        refs.installNsfw.textContent = "下载社区方案";
        if (faceInstall) refs.faceInstall.textContent = "准备换脸组件";
        renderModelReadiness();
      }, 8000);
      return;
    }
    installArmed = false;
    installArmedProfile = "";
    if (faceInstall) faceStatusOverride = null;
    window.clearTimeout(installArmTimer);
    refs.installButton.disabled = true;
    refs.installNsfw.disabled = true;
    refs.faceInstall.disabled = true;
    actionButton.textContent = "启动下载中";
    setModelStatus("pending", `正在启动${actionLabel}下载任务。`);
    const params = new URLSearchParams({ profile: profileId, confirm_requirement: "true", include_post: "false" });
    const target = targetOverride || currentTargetPath();
    if (target) params.set("target_dir", target);
    try {
      const job = await jsonRequest(`/api/install?${params}`, { method: "POST" });
      localStorage.setItem(STORAGE.installJob, job.id);
      renderInstallJob(job);
      watchInstallJob(job.id);
    } catch (error) {
      refs.installButton.disabled = false;
      refs.installNsfw.disabled = false;
      refs.faceInstall.disabled = false;
      refs.installButton.textContent = "下载缺失模型";
      refs.installNsfw.textContent = "下载社区方案";
      if (faceInstall) refs.faceInstall.textContent = "准备换脸组件";
      setModelStatus("bad", error.message);
    }
  }

  function renderInstallProgress(progress = {}) {
    if (refs.installPanel && "open" in refs.installPanel) refs.installPanel.open = true;
    refs.installProgress.classList.remove("hidden");
    const state = String(progress.state || "queued").toLowerCase();
    const percent = Math.max(0, Math.min(100, Number(progress.percent || 0)));
    refs.installProgressBar.className = "progress-bar";
    refs.installProgressBar.style.width = `${percent}%`;
    if (["running", "queued", "pausing", "canceling"].includes(state)) refs.installProgressBar.classList.add("running");
    if (state === "success") refs.installProgressBar.classList.add("success");
    if (["paused", "interrupted"].includes(state)) refs.installProgressBar.classList.add("paused");
    if (["failed", "canceled", "cancelled"].includes(state)) refs.installProgressBar.classList.add("failed");
    const summaryPrefix = {
      queued: "等待下载",
      running: "正在下载",
      pausing: "正在暂停",
      paused: "已暂停",
      interrupted: "已中断",
      canceling: "正在取消",
      canceled: "已取消",
      cancelled: "已取消",
      failed: "下载失败",
      success: "下载完成",
    }[state] || "下载任务";
    refs.installSummary.textContent = progress.current_file ? `${summaryPrefix}：${progress.current_file}` : summaryPrefix;
    const speed = Number(progress.speed_mb_s || 0);
    const activeTransfer = ["running", "pausing", "canceling"].includes(state);
    const transferDetail = activeTransfer && speed > 0
      ? ` · ${speed.toFixed(1)} MB/s · 剩余 ${formatEta(progress.eta_seconds)}`
      : ["paused", "interrupted"].includes(state)
        ? " · .part 已保留，可继续"
        : "";
    refs.installMetrics.textContent = `已下载 ${formatGb(progress.downloaded_gb, 2)} / 预计 ${formatGb(progress.total_gb, 2)} · ${percent.toFixed(1)}%${transferDetail}`;
    refs.installFiles.innerHTML = (progress.files || [])
      .map(
        (item) => `<div class="install-file-row">
          <strong>${escapeHtml(item.label || item.name)}</strong>
          <span>${item.percent == null ? escapeHtml(item.status || "等待") : `${Number(item.percent).toFixed(1)}%`}</span>
          <small>${item.expected_gb == null ? escapeHtml(item.status || "节点安装") : `${formatGb(item.downloaded_gb, 3)} / ${formatGb(item.expected_gb, 3)} · ${escapeHtml(item.status || "等待")}`}</small>
        </div>`,
      )
      .join("");
  }

  function renderInstallJob(job) {
    activeInstallJob = job;
    const status = String(job.status || "queued").toLowerCase();
    const jobProfile = String(job.install_profile || job.profile || "");
    const faceInstall = Boolean(jobProfile && jobProfile === String(faceSwapCapability().install_profile || ""));
    const modelInstall = Boolean(jobProfile && jobProfile === String(activeProfile()?.install_profile || ""));
    const addonInstall = Boolean(jobProfile && jobProfile === String(refs.installNsfw.dataset.profile || ""));
    const profileLabel = String(job.install_plan?.profile_label || job.profile_label || jobProfile || "模型");
    const lastLog = (job.log || []).slice(-1)[0] || "模型下载任务运行中。";
    const resumable = ["paused", "interrupted"].includes(status) && Array.isArray(job.command_args);
    const activelyRunning = ["queued", "running", "pausing", "canceling"].includes(status);
    const retryable = ["failed", "canceled", "cancelled"].includes(status);
    refs.installState.dataset.state = status;
    refs.installState.textContent = `下载任务 · ${profileLabel}：${statusLabel(status)}`;
    renderInstallProgress(job.progress || { state: status });
    refs.pauseInstall.classList.toggle("hidden", !["queued", "running"].includes(status));
    refs.resumeInstall.classList.toggle("hidden", !resumable);
    refs.cancelInstall.classList.toggle("hidden", job.completed && !resumable);
    if (activelyRunning) {
      refs.installButton.disabled = true;
      refs.installNsfw.disabled = true;
      refs.faceInstall.disabled = true;
    } else {
      if (modelInstall) refs.installButton.disabled = !retryable;
      if (addonInstall) refs.installNsfw.disabled = !retryable;
      if (faceInstall) refs.faceInstall.disabled = !retryable;
    }

    if (resumable) {
      const interruptedMessage = status === "paused"
        ? `${profileLabel} 下载已暂停，.part 文件已保留。`
        : `${profileLabel} 下载被前端重启中断，可从现有 .part 继续。`;
      if (modelInstall) {
        refs.installButton.textContent = "当前模型下载已暂停";
        setModelStatus("pending", interruptedMessage);
      }
      if (addonInstall) refs.installNsfw.textContent = "社区方案下载已暂停";
      if (faceInstall) {
        refs.faceInstall.textContent = "换脸组件下载已暂停";
        setFaceStatus("pending", interruptedMessage, "install");
        renderFaceSwapPanel();
      }
      return;
    }
    if (job.completed || TERMINAL.has(status)) {
      if (status === "success") {
        if (modelInstall) {
          refs.installButton.disabled = true;
          refs.installButton.textContent = "模型文件已下载";
          setModelStatus("ok", "模型文件已准备完成；新目录或新模型需要重启 ComfyUI 8188 后加载。");
        }
        if (addonInstall) {
          refs.installNsfw.disabled = true;
          refs.installNsfw.textContent = "社区方案已下载";
        }
        if (faceInstall) {
          refs.faceInstall.disabled = true;
          refs.faceInstall.textContent = "换脸组件已下载";
          setFaceStatus("pending", "换脸组件文件与依赖已准备完成；重启 ComfyUI 8188 后再重新检查。", "install");
        }
        localStorage.removeItem(STORAGE.installJob);
        if (installTimer) window.clearInterval(installTimer);
        installTimer = null;
        window.setTimeout(() => loadBootstrap(true), 700);
      } else {
        const hint = job.failure_hint?.message || job.failure_hint?.title || "";
        const failureMessage = [lastLog, hint].filter(Boolean).join(" ");
        if (modelInstall) {
          setModelStatus("bad", failureMessage);
          refs.installButton.disabled = false;
          refs.installButton.textContent = "重试模型下载";
        }
        if (addonInstall) {
          refs.installNsfw.disabled = false;
          refs.installNsfw.textContent = "重试社区下载";
        }
        if (faceInstall) {
          refs.faceInstall.disabled = false;
          refs.faceInstall.textContent = "重试换脸组件";
          setFaceStatus("bad", failureMessage, "install");
        }
        localStorage.removeItem(STORAGE.installJob);
        if (installTimer) window.clearInterval(installTimer);
        installTimer = null;
      }
      return;
    }
    if (modelInstall) {
      refs.installButton.textContent = "当前模型下载中";
      setModelStatus("pending", lastLog);
    }
    if (addonInstall) refs.installNsfw.textContent = "社区方案下载中";
    if (faceInstall) {
      refs.faceInstall.textContent = "换脸组件下载中";
      setFaceStatus("pending", lastLog, "install");
      renderFaceSwapPanel();
    }
  }

  async function pollInstallJob(jobId) {
    try {
      const job = await jsonRequest(`/api/install/${encodeURIComponent(jobId)}`);
      renderInstallJob(job);
    } catch (error) {
      setModelStatus("bad", `下载状态读取失败：${error.message}`);
    }
  }

  function watchInstallJob(jobId) {
    if (installTimer) window.clearInterval(installTimer);
    void pollInstallJob(jobId);
    installTimer = window.setInterval(() => pollInstallJob(jobId), 1200);
  }

  async function controlInstall(action) {
    const jobId = localStorage.getItem(STORAGE.installJob);
    if (!jobId) return;
    try {
      const job = await jsonRequest(`/api/install/${encodeURIComponent(jobId)}/${action}`, { method: "POST" });
      renderInstallJob(job);
      if (action === "resume") watchInstallJob(jobId);
    } catch (error) {
      setModelStatus("bad", `${action === "pause" ? "暂停" : action === "resume" ? "继续" : "取消"}失败：${error.message}`);
    }
  }

  function resumeInstallJob() {
    const jobId = localStorage.getItem(STORAGE.installJob);
    if (!jobId || installTimer) return;
    watchInstallJob(jobId);
  }

  function resumeActiveJob() {
    if (!activeJobIds.size) {
      try {
        const stored = JSON.parse(localStorage.getItem(STORAGE.activeJobs) || "[]");
        if (Array.isArray(stored)) stored.filter(Boolean).forEach((jobId) => activeJobIds.add(String(jobId)));
      } catch (_error) {
        localStorage.removeItem(STORAGE.activeJobs);
      }
      const legacyJobId = localStorage.getItem(STORAGE.activeJob);
      if (legacyJobId) activeJobIds.add(legacyJobId);
    }
    if (!activeJobIds.size) {
      renderTaskQueue();
      return;
    }
    const preferred = localStorage.getItem(STORAGE.activeJob);
    if (!activeJobId || !activeJobIds.has(activeJobId)) {
      activeJobId = preferred && activeJobIds.has(preferred) ? preferred : [...activeJobIds][0];
    }
    persistActiveJobs();
    renderTaskQueue();
    startActivePolling();
    watchJob(activeJobId);
  }

  function syncNsfwStrength(value, { schedule = true, fromIntensity = false } = {}) {
    const minimum = Number(refs.nsfwStrength.min || 0);
    const maximum = Number(refs.nsfwStrength.max || 2);
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return;
    const normalized = Math.max(minimum, Math.min(maximum, numeric));
    refs.nsfwStrength.value = String(normalized);
    refs.nsfwStrengthRange.value = String(normalized);
    if (refs.nsfwIntensity) {
      refs.nsfwIntensity.dataset.manualStrength = fromIntensity ? "" : "1";
    }
    if (schedule) scheduleWorkflowCheck();
  }

  function syncFaceSwapStrength(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return;
    const options = (faceSwapCapability().strength_options || ["0%", "12.5%", "25%", "37.5%", "50%", "62.5%", "75%", "87.5%", "100%"])
      .map((item) => Number.parseFloat(String(item)))
      .filter((item) => Number.isFinite(item));
    const selected = options.length
      ? options.reduce((best, item) => (Math.abs(item - numeric) < Math.abs(best - numeric) ? item : best), options[0])
      : Math.max(0, Math.min(100, Math.round(numeric / 12.5) * 12.5));
    refs.faceSwapStrength.value = String(selected);
    refs.faceSwapStrengthRange.value = String(selected);
  }

  refs.profile.addEventListener("change", () => {
    refs.nsfw.checked = false;
    renderAspectOptions();
    applyProfileDefaults(true);
    selectGenerationMode(refs.generationMode.value, { schedule: false });
    renderProfileDetails();
    renderNsfwSupport();
    renderReferenceImages();
    renderModelReadiness();
    schedulePromptPreview();
  });
  refs.taskModeSwitch.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-image-task-mode]");
    if (button) selectTaskMode(button.dataset.imageTaskMode);
  });
  refs.editOperationSwitch.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-image-edit-operation]");
    if (button) selectEditOperation(button.dataset.imageEditOperation);
  });
  refs.faceAuthCheckbox.addEventListener("change", () => {
    refs.faceAuthConfirm.disabled = !refs.faceAuthCheckbox.checked;
  });
  [refs.faceAuthBackdrop, refs.faceAuthClose, refs.faceAuthCancel].forEach((button) => {
    button.addEventListener("click", () => closeFaceAuthorizationModal());
  });
  refs.faceAuthConfirm.addEventListener("click", () => {
    if (!refs.faceAuthCheckbox.checked) return;
    faceAuthorizationConfirmed = true;
    refs.faceAuthorization.value = "true";
    refs.sourceProcessing.value = "full";
    closeFaceAuthorizationModal({ returnFocus: false });
    renderFaceSwapPanel();
    if (pendingBatchFaceSwap) {
      void submitBatchFaceSwaps();
      return;
    }
    if (pendingCharacterExtract) {
      const alsoSave = pendingCharacterSave;
      pendingCharacterExtract = false;
      pendingCharacterSave = false;
      void (async () => {
        const ok = await extractCharacterIdentityAuthorized();
        if (ok && alsoSave) await saveCharacterFromIdentity();
      })();
      return;
    }
    void extractFaces("both");
  });
  refs.faceAnalyze.addEventListener("click", () => requestFaceAuthorization(refs.faceAnalyze));
  refs.faceBatchSubmit?.addEventListener("click", requestBatchFaceAuthorization);
  refs.faceBatchTargets?.addEventListener("change", () => {
    batchFaceTargets = Array.from(refs.faceBatchTargets.files || []).slice(0, 50).map((file) => ({ file, label: file.name }));
    faceAuthorizationConfirmed = false;
    refs.faceAuthorization.value = "false";
    pendingBatchFaceSwap = false;
    if (refs.faceBatchSummary) {
      refs.faceBatchSummary.textContent = batchFaceTargets.length
        ? `已选择 ${batchFaceTargets.length} 张；每张自动选择检测到的最大人脸。`
        : "尚未选择批量目标图。";
    }
    refs.faceBatchStatus?.classList.add("hidden");
    renderFaceSwapPanel();
  });
  refs.faceRetry.addEventListener("click", () => void extractFaces("target"));
  refs.identityFaceRetry.addEventListener("click", () => void extractFaces("identity"));
  [refs.faceCandidates, refs.identityFaceCandidates].forEach((container) => container.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-face-index]");
    if (button) selectFaceCandidate(button.dataset.faceRole, Number(button.dataset.faceIndex));
  }));
  refs.editFile.addEventListener("change", () => {
    const file = refs.editFile.files?.[0];
    if (!file) return;
    setEditSource({ file, label: file.name });
    setLog(`已选择${isFaceSwap() ? "目标图" : "源图片"}：${file.name}`);
  });
  refs.editClear.addEventListener("click", () => {
    setEditSource(null);
    setLog(`已移除${isFaceSwap() ? "目标图" : "源图片"}。`);
  });
  refs.referenceFiles?.addEventListener("change", () => {
    const maximum = maximumAdditionalReferences();
    const selected = Array.from(refs.referenceFiles.files || []).filter((file) => file.type.startsWith("image/") || /\.(png|jpe?g|webp|bmp)$/i.test(file.name));
    editReferenceFiles = selected.slice(0, maximum);
    renderReferenceImages();
    scheduleWorkflowCheck();
    if (selected.length > maximum) {
      setLog(`当前模型最多可再添加 ${maximum} 张参考图，已保留前 ${maximum} 张。`);
    } else if (editReferenceFiles.length) {
      setLog(`已添加 ${editReferenceFiles.length} 张参考图；提示词中可用 <image2> 起依次引用。`);
    }
  });
  refs.referenceClear?.addEventListener("click", () => {
    editReferenceFiles = [];
    refs.referenceFiles.value = "";
    renderReferenceImages();
    scheduleWorkflowCheck();
    setLog("已清空附加参考图。");
  });
  refs.identityFaceFile.addEventListener("change", () => {
    const file = refs.identityFaceFile.files?.[0];
    if (!file) return;
    setIdentityFaceSource({ file, label: file.name });
    setLog(`已选择身份参考图：${file.name}`);
  });
  refs.identityFaceClear.addEventListener("click", () => {
    setIdentityFaceSource(null);
    setLog("已移除身份参考图。 ");
  });
  refs.faceSwapStrengthRange.addEventListener("input", () => syncFaceSwapStrength(refs.faceSwapStrengthRange.value));
  refs.faceSwapStrength.addEventListener("input", () => syncFaceSwapStrength(refs.faceSwapStrength.value));
  refs.faceSwapStrength.addEventListener("change", () => syncFaceSwapStrength(refs.faceSwapStrength.value));
  refs.faceRestoreModel.addEventListener("change", renderFaceSwapPanel);
  refs.editFollowSize.addEventListener("change", () => {
    if (refs.editFollowSize.checked && editSource?.width && editSource?.height) {
      applyEditSourceDimensions(editSource.width, editSource.height);
    }
  });
  refs.editResizeMode.addEventListener("change", scheduleWorkflowCheck);
  refs.compareWallButton?.addEventListener("click", () => {
    compareWallEnabled = !compareWallEnabled;
    updateCompareWallButton();
    setLog(compareWallEnabled ? "对比墙已开启：下次生成将同种子提交无限制开/关两条任务。" : "对比墙已关闭。");
  });
  refs.historyFilters?.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-history-filter]");
    if (!button) return;
    historyFilter = button.dataset.historyFilter || "all";
    refs.historyFilters.querySelectorAll("button[data-history-filter]").forEach((item) => {
      item.classList.toggle("active", item.dataset.historyFilter === historyFilter);
    });
    renderHistory(bootstrap?.history || []);
  });
  refs.poseMapFile?.addEventListener("change", () => {
    const file = refs.poseMapFile.files?.[0];
    if (!file) {
      refs.poseMapFilename.value = "";
      return;
    }
    void uploadPoseMapFile(file);
  });
  for (const container of [refs.editStrengthSwitch, refs.editStrengthInlineSwitch].filter(Boolean)) {
    container.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-edit-strength-preset]");
      if (!button) return;
      applyEditStrengthPreset(button.dataset.editStrengthPreset);
    });
  }
  refs.editStrengthRange.addEventListener("input", () => {
    clearEditStrengthPreset();
    syncEditStrength(refs.editStrengthRange.value);
  });
  refs.editStrength.addEventListener("input", () => {
    clearEditStrengthPreset();
    syncEditStrength(refs.editStrength.value);
  });
  refs.editStrength.addEventListener("change", () => {
    clearEditStrengthPreset();
    syncEditStrength(refs.editStrength.value);
  });
  refs.prompt.addEventListener("input", schedulePromptPreview);
  refs.exactText.addEventListener("input", schedulePromptPreview);
  refs.style.addEventListener("change", schedulePromptPreview);
  refs.promptModes.addEventListener("change", schedulePromptPreview);
  refs.nsfw.addEventListener("change", () => {
    renderNsfwSupport();
    schedulePromptPreview();
    scheduleWorkflowCheck();
  });
  refs.nsfwStrengthRange.addEventListener("input", () => syncNsfwStrength(refs.nsfwStrengthRange.value));
  refs.nsfwStrength.addEventListener("input", () => syncNsfwStrength(refs.nsfwStrength.value));
  refs.nsfwStrength.addEventListener("change", () => syncNsfwStrength(refs.nsfwStrength.value));
  refs.aspectGrid.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-aspect]");
    if (!button || button.disabled) return;
    selectAspect(button.dataset.aspect, Number(button.dataset.width), Number(button.dataset.height));
    if (button.dataset.aspect === "custom") refs.width.focus();
  });
  refs.batchSwitch.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-batch]");
    if (button) selectBatch(Number(button.dataset.batch));
  });
  refs.batchSize.addEventListener("input", () => {
    if (refs.batchSize.value) selectBatch(refs.batchSize.value);
  });
  refs.batchSize.addEventListener("change", () => selectBatch(refs.batchSize.value));
  refs.generationModeSwitch.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-generation-mode]");
    if (button) selectGenerationMode(button.dataset.generationMode);
  });
  refs.width.addEventListener("input", () => selectAspect("custom"));
  refs.height.addEventListener("input", () => selectAspect("custom"));
  refs.width.addEventListener("change", commitCustomDimensions);
  refs.height.addEventListener("change", commitCustomDimensions);
  refs.swapSize.addEventListener("click", () => {
    const width = Number(refs.width.value);
    const height = Number(refs.height.value);
    selectAspect("custom", height, width);
  });
  refs.qualityPresets.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-steps]");
    if (!button || button.disabled) return;
    refs.steps.value = button.dataset.steps;
    syncQualityControls();
    scheduleWorkflowCheck();
  });
  refs.stepsRange.addEventListener("input", () => {
    refs.steps.value = refs.stepsRange.value;
    syncQualityControls();
    scheduleWorkflowCheck();
  });
  refs.steps.addEventListener("input", () => {
    if (!refs.steps.value) return;
    previewQualityInput();
    scheduleWorkflowCheck();
  });
  refs.steps.addEventListener("change", () => {
    syncQualityControls();
    scheduleWorkflowCheck();
  });
  [refs.cfg, refs.sampler, refs.scheduler].forEach((input) => input.addEventListener("change", scheduleWorkflowCheck));
  refs.randomSeed.addEventListener("click", () => {
    refs.seed.value = "-1";
  });
  refs.outputForm.addEventListener("submit", saveOutputLocation);
  refs.outputPathButton.addEventListener("click", openOutputLocation);
  refs.openOutput.addEventListener("click", openOutputLocation);
  refs.cancelJob.addEventListener("click", () => cancelImageJob(refs.cancelJob.dataset.jobId || activeJobId));
  refs.taskQueueList.addEventListener("click", (event) => {
    const cancelButton = event.target.closest("button[data-task-cancel]");
    if (cancelButton) {
      void cancelImageJob(cancelButton.dataset.taskCancel);
      return;
    }
    const viewButton = event.target.closest("button[data-task-view]");
    if (viewButton) watchJob(viewButton.dataset.taskView);
  });
  form.addEventListener("submit", submitGeneration);
  refs.repeat.addEventListener("click", submitGeneration);
  refs.reuse.addEventListener("click", applySavedParams);
  refs.refreshButton.addEventListener("click", () => loadBootstrap(true));
  refs.historyRefresh.addEventListener("click", refreshHistory);
  refs.historyPrev.addEventListener("click", () => {
    if (historyPage > 1) void loadHistoryPage(historyPage - 1, { scroll: true });
  });
  refs.historyNext.addEventListener("click", () => {
    if (historyPage < historyPagination.total_pages) void loadHistoryPage(historyPage + 1, { scroll: true });
  });
  refs.historyPageNumbers.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-history-page]");
    if (!button) return;
    const page = Number(button.dataset.historyPage || 1);
    if (page !== historyPage) void loadHistoryPage(page, { scroll: true });
  });
  refs.historySelectAll.addEventListener("change", () => {
    resetHistoryDeleteArm();
    refs.historyGrid.querySelectorAll("input[data-history-select]").forEach((box) => {
      box.checked = refs.historySelectAll.checked;
      const key = box.dataset.historySelect;
      if (box.checked) selectedHistoryItems.add(key);
      else selectedHistoryItems.delete(key);
      box.closest(".image-history-job")?.classList.toggle("is-selected", box.checked);
    });
    syncHistorySelectionControls();
  });
  refs.historyDelete.addEventListener("click", deleteSelectedHistory);
  refs.installButton.addEventListener("click", () => startInstall());

  refs.nsfwWizard?.addEventListener("change", () => applyWizard(refs.nsfwWizard.value));
  refs.adultRecipeChips?.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-adult-wizard]");
    if (!button) return;
    applyWizard(button.dataset.adultWizard);
  });
  refs.adultApplyGenerate?.addEventListener("click", () => {
    const wizardId = refs.nsfwWizard?.value || rememberedAdultWizardId() || "tasteful";
    applyWizard(wizardId, { generate: true });
  });
  refs.adultApplyVideo?.addEventListener("click", () => {
    const wizardId = refs.nsfwWizard?.value || rememberedAdultWizardId() || "tasteful";
    applyWizard(wizardId, { queueVideo: true });
  });
  refs.nsfwIntensitySwitch?.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-intensity]");
    if (!button) return;
    applyIntensity(button.dataset.intensity);
    schedulePromptPreview();
  });
  refs.nsfwScenes?.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-scene]");
    if (!button) return;
    applyScene(button.dataset.scene, { replace: true });
  });
  refs.autoInjectTrigger?.addEventListener("change", () => {
    updateTriggerPreview();
    schedulePromptPreview();
  });
  refs.customTrigger?.addEventListener("input", () => {
    updateTriggerPreview();
    schedulePromptPreview();
  });
  refs.characterBoxList?.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-character]");
    if (!button) return;
    applyCharacterToIdentity(button.dataset.character);
  });
  refs.characterIdentityFile?.addEventListener("change", () => {
    const file = refs.characterIdentityFile.files?.[0];
    if (!file) return;
    setIdentityFaceSource({ file, label: file.name });
    renderCharacterIdentityPreview();
    if (refs.characterStatus) refs.characterStatus.textContent = `已导入 ${file.name}，请点击「提取身份脸」。`;
  });
  refs.characterExtract?.addEventListener("click", () => void extractCharacterIdentity());
  refs.characterGotoFaceSwap?.addEventListener("click", () => gotoFaceSwapWithCharacter());
  refs.characterSave?.addEventListener("click", () => void saveCharacterFromIdentity());
  refs.characterClear?.addEventListener("click", () => void clearCharacterBox());
  refs.faceStrengthPresets?.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-face-strength]");
    if (!button) return;
    applyFaceStrengthPreset(button.dataset.faceStrength);
  });
  refs.advancedModuleList?.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-advanced-module]");
    if (!button) return;
    const moduleId = button.dataset.advancedModule;
    const status = button.dataset.moduleStatus || "";
    const profile = button.dataset.installProfile || "";
    if (profile && !["workflow_native", "profile_native"].includes(status)) {
      void startInstall(profile, button.textContent || "进阶模块");
      return;
    }
    if (["workflow_native", "profile_native"].includes(status)) {
      setAdvancedModuleEnabled(moduleId, !isAdvancedModuleEnabled(moduleId));
    }
  });
  refs.installNsfw.addEventListener("click", () => startInstall(refs.installNsfw.dataset.profile || "", "社区方案"));
  refs.faceInstall.addEventListener("click", () => {
    const capability = faceSwapCapability();
    void startInstall(capability.install_profile || "face-swap-reactor", "换脸组件", capability.install_base_dir || bootstrap?.active_base_dir || "");
  });
  refs.pauseInstall.addEventListener("click", () => controlInstall("pause"));
  refs.resumeInstall.addEventListener("click", () => controlInstall("resume"));
  refs.cancelInstall.addEventListener("click", () => controlInstall("cancel"));
  refs.storagePreset.addEventListener("change", () => {
    refs.downloadPath.value = refs.storagePreset.value;
    localStorage.setItem(STORAGE.downloadPath, refs.downloadPath.value);
    void loadBootstrap(false);
  });
  refs.downloadPath.addEventListener("input", () => {
    window.clearTimeout(storageTimer);
    storageTimer = window.setTimeout(() => {
      localStorage.setItem(STORAGE.downloadPath, refs.downloadPath.value.trim());
      void loadBootstrap(false);
    }, 650);
  });
  refs.sourceButton.addEventListener("click", () => {
    refs.environmentTab?.click();
    window.setTimeout(() => document.querySelector("#openSourceConfigButton")?.click(), 120);
  });
  refs.toVideo.addEventListener("click", () => {
    void sendMediaToVideo(latestMedia[0], latestJob);
  });
  refs.stillToVideo?.addEventListener("click", () => {
    void sendMediaToVideo(latestMedia[0], latestJob, { queueVideo: true }).catch(() => {});
  });
  refs.editResult.addEventListener("click", () => useMediaForEdit(latestMedia[0], latestJob));
  refs.faceSwapResult.addEventListener("click", () => useMediaForEdit(latestMedia[0], latestJob, "face_swap"));
  refs.downloadAll.addEventListener("click", downloadAll);
  refs.historyGrid.addEventListener("click", (event) => {
    const restoreButton = event.target.closest("button[data-history-restore]");
    if (restoreButton) {
      restoreJobParams(historyEntryById(restoreButton.dataset.historyRestore));
      return;
    }
    const editButton = event.target.closest("button[data-history-edit]");
    if (editButton) {
      const job = historyEntryById(editButton.dataset.historyEdit);
      const media = (job?.media || []).filter((item) => item.kind === "image")[Number(editButton.dataset.mediaIndex || 0)];
      useMediaForEdit(media, job);
      return;
    }
    const faceSwapButton = event.target.closest("button[data-history-face-swap]");
    if (faceSwapButton) {
      const job = historyEntryById(faceSwapButton.dataset.historyFaceSwap);
      const media = (job?.media || []).filter((item) => item.kind === "image")[Number(faceSwapButton.dataset.mediaIndex || 0)];
      useMediaForEdit(media, job, "face_swap");
      return;
    }
    const button = event.target.closest("button[data-history-keyframe]");
    if (!button) return;
    const job = historyEntryById(button.dataset.historyKeyframe);
    const media = (job?.media || []).filter((item) => item.kind === "image")[Number(button.dataset.mediaIndex || 0)];
    void sendMediaToVideo(media, job);
  });
  refs.historyGrid.addEventListener("change", (event) => {
    const checkbox = event.target.closest("input[data-history-select]");
    if (!checkbox) return;
    resetHistoryDeleteArm();
    if (checkbox.checked) selectedHistoryItems.add(checkbox.dataset.historySelect);
    else selectedHistoryItems.delete(checkbox.dataset.historySelect);
    checkbox.closest(".image-history-job")?.classList.toggle("is-selected", checkbox.checked);
    syncHistorySelectionControls();
  });

  window.acceptExtractedFrameToImageStudio = (frame = {}) => {
    const inputName = String(frame.input_name || "").trim();
    if (!inputName) return false;
    selectTaskMode("edit", { schedule: false });
    selectEditOperation("instruction", { schedule: false });
    setEditSource({
      filename: PathBasename(inputName),
      subfolder: inputName.includes("/") ? inputName.split("/").slice(0, -1).join("/") : "beginner_frontend",
      type: "input",
      url: frame.preview_url || "",
      label: frame.label || "视频抽帧",
    });
    setLog(frame.message || "已将视频抽帧载入图片工作室微调源图。");
    return true;
  };

  function PathBasename(value) {
    return String(value || "").replace(/\\/g, "/").split("/").pop() || value;
  }

  updateCompareWallButton();

  function catalogWantsImageEdit(detail) {
    const target = (bootstrap?.profiles || []).find((item) => item.id === detail?.profile || item.id === detail?.catalogId);
    if (target?.generation_supported === false && target.image_edit?.supported) return true;
    return Boolean(detail?.editMode) || /edit|微调/i.test(`${detail?.profile || ""} ${detail?.catalogId || ""} ${detail?.installProfile || ""}`);
  }

  function resolveCatalogImageProfile(detail) {
    const profiles = bootstrap?.profiles || [];
    const enabled = (id) => Boolean(id) && [...(refs.profile?.options || [])].some((option) => option.value === id && !option.disabled);
    const catalogId = String(detail?.catalogId || "");
    const requested = String(detail?.profile || "");
    const installProfile = String(detail?.installProfile || "");
    if (enabled(catalogId)) return catalogId;
    if (enabled(requested)) return requested;
    const matches = profiles.filter((item) => installProfile && item.install_profile === installProfile && enabled(item.id));
    return (matches.find((item) => item.recommended) || matches[0])?.id || "";
  }

  function applyCatalogImageSelection(detail) {
    if (!refs.profile || !bootstrap?.profiles?.length) return false;
    selectTaskMode(catalogWantsImageEdit(detail) ? "edit" : "t2i", { schedule: false });
    const profileId = resolveCatalogImageProfile(detail);
    if (!profileId) return false;
    if (refs.profile.value !== profileId) {
      refs.nsfw.checked = false;
      refs.profile.value = profileId;
      applyProfileDefaults(true);
    }
    renderProfileDetails();
    renderModelReadiness();
    return true;
  }

  window.addEventListener("workspace:select-image-profile", (event) => {
    const detail = event.detail || {};
    if (applyCatalogImageSelection(detail)) return;
    void loadBootstrap().then(() => applyCatalogImageSelection(detail));
  });

  window.addEventListener("workspace:viewchange", (event) => {
    const view = event.detail?.view;
    if (view !== "image-studio" && !refs.faceAuthModal.classList.contains("hidden")) {
      closeFaceAuthorizationModal({ returnFocus: false });
    }
    if (view === "image-studio") {
      if (refs.topModel) {
        savedTopModel = refs.topModel.textContent;
        savedTopModelTitle = refs.topModel.title;
        refs.topModel.textContent = activeProfile()?.label || "Qwen-Image-2512 FP8";
        refs.topModel.title = refs.topModel.textContent;
      }
      if (!bootstrap) void loadBootstrap();
      resumeActiveJob();
    } else {
      if (activeJobIds.size) startActivePolling();
      else stopWatching();
      if (refs.topModel && savedTopModel) {
        refs.topModel.textContent = savedTopModel;
        refs.topModel.title = savedTopModelTitle;
        savedTopModel = "";
        savedTopModelTitle = "";
      }
    }
  });

  // A fast tab click can happen before this deferred module finishes loading.
  // Recover the missed view-change event from the DOM's current active state.
  if (refs.viewTab?.classList.contains("active")) {
    if (refs.topModel) {
      savedTopModel = refs.topModel.textContent;
      savedTopModelTitle = refs.topModel.title;
      refs.topModel.textContent = activeProfile()?.label || "Qwen-Image-2512 FP8";
      refs.topModel.title = refs.topModel.textContent;
    }
    void loadBootstrap();
  }

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !refs.faceAuthModal.classList.contains("hidden")) {
      event.preventDefault();
      closeFaceAuthorizationModal();
    }
  });

  window.addEventListener("beforeunload", () => {
    stopWatching();
    clearEditObjectUrl();
    clearIdentityFaceObjectUrl();
    if (installTimer) window.clearInterval(installTimer);
  });
})();
