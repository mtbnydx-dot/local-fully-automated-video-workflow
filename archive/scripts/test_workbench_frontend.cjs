const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const {chromium} = require('playwright');
// Every request is mocked. This test never starts ComfyUI or invokes inference.
const root = path.resolve(__dirname, '..');
const output = process.env.WORKBENCH_QA_DIR || path.join(require('node:os').tmpdir(), 'workbench-ui-qa');
fs.mkdirSync(output, {recursive:true});
const fixture = spawnSync(process.env.TEST_PYTHON || path.join(root,'.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python'), ['-B','-c', `
import json
from beginner_frontend import app, video_params
from beginner_frontend.image_studio import image_studio_static_payload
from beginner_frontend.model_catalog import MODEL_ASSETS
from beginner_frontend.social_presets import social_presets_payload
hw = {'accelerator':'cuda','max_vram_gb':96,'platform_strategy':'cuda_multi_model'}
options = app.workflow_model_options(os_info={'name':'Windows'}, hardware=hw,
 assets=[{'id':a['id'],'ok':True} for a in MODEL_ASSETS], custom_nodes=[], tool_checks=[], node_checks=[],
 selected_model_id='minimax_h3_fl2va_int8')
for entries in options['options'].values():
 for item in entries:
  if item.get('mode') not in ('unsupported','external_workflow'):
   item.update(status='ok',supported=True)
images = image_studio_static_payload()
for p in images['profiles']:
 p.update(ready=p.get('generation_supported') is not False, missing=[], graph_errors=[],install_plan={})
 p['image_edit'].update(ready=True,graph_errors=[])
 p['nsfw'].update(addon_ready=True,addon_installed=True)
print(json.dumps({'environment':{'ok':True,'hardware':hw,'os':{'name':'Windows'},'model_options':options,
 'comfy':{'connected':True,'comfyui_version':'CPU fixture'}},'images':images,
 'params':{'modes':{m:video_params.param_schema(m) for m in video_params.MODE_PARAMS},
 'capabilities':{m:video_params.mode_capabilities(m) for m in video_params.MODE_PARAMS}},
 'social':social_presets_payload()}))
`],{cwd:root,encoding:'utf8',env:{...process.env, PYTHONIOENCODING:'utf-8',
 BEGINNER_FRONTEND_DISABLE_GPU_PROBES:'1',BEGINNER_FRONTEND_DISABLE_JOB_PERSISTENCE:'1',CUDA_VISIBLE_DEVICES:'-1'}});
assert.equal(fixture.status,0,fixture.stderr);
const data = JSON.parse(fixture.stdout);

(async()=>{
 const browser=await chromium.launch({headless:true,args:['--disable-gpu']});
 try {
  for(const width of [1440,390]) {
   const context=await browser.newContext({viewport:{width,height:1000}});
   const page=await context.newPage();
   const errors=[], posts=[], queries=[];
   const jobs=new Map();
   let imagePosts=0, tunePosts=[];
   const field=(body,name)=>body.match(new RegExp('name="'+name+'"\\r\\n\\r\\n([^\\r]*)'))?.[1]||'';
   page.on('pageerror',e=>errors.push(e.message));
   page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
   await context.route('**/*',async route=>{
    const req=route.request(), url=new URL(req.url());
    assert.equal(url.origin,'http://127.0.0.1:18762','No live network');
    if(url.pathname.startsWith('/api/')) {
     queries.push(url);
     let body={ok:true};
     if(url.pathname==='/api/client-config') body={mode:'both',mode_configured:true};
     if(url.pathname==='/api/environment') body=data.environment;
     if(url.pathname==='/api/video-params') body=data.params;
     if(url.pathname==='/api/social-presets') body=data.social;
     if(url.pathname==='/api/status') body={connected:false};
     if(url.pathname==='/api/image-studio') body={...data.images,comfy:{connected:true},history:[],output:{}};
     if(url.pathname.endsWith('/workflow')) {await new Promise(r=>setTimeout(r,120));body={ok:true,node_count:9,message:'CPU preflight'};}
     if(url.pathname==='/api/image-studio/prompt-preview') body={prompt:'A cup',negative:''};
     if(url.pathname==='/api/generate') {
      const raw=req.postData(); posts.push(raw);
      body={id:`job-${posts.length}`,mode:field(raw,'mode'),title:'CPU 模拟任务',status:'queued',completed:false,
       created_at:Date.now(),width:Number(field(raw,'width')),height:Number(field(raw,'height')),fps:Number(field(raw,'fps'))||24,
       upscale_scale:Number(field(raw,'upscale_scale'))||2,rife_multiplier:Number(field(raw,'rife_multiplier'))||2,media:[]};
      jobs.set(body.id,body);
     }
     if(url.pathname==='/api/image-studio/generate') {
      imagePosts++;body={id:`image-${imagePosts}`,kind:'image_generation',status:'queued',media:[]};jobs.set(body.id,body);
     }
     if(url.pathname==='/api/video/tune') {
      tunePosts.push(req.postData());body={id:'tune-1',mode:'video_tune',status:'queued',media:[]};jobs.set(body.id,body);
     }
     if(url.pathname==='/api/jobs') body={items:[...jobs.values()],count:jobs.size,active_count:jobs.size,projects:[]};
     if(url.pathname.startsWith('/api/jobs/')) {
      if(url.pathname.endsWith('/events')) return route.fulfill({contentType:'text/event-stream',body:': connected\n\n'});
      body=jobs.get(url.pathname.split('/')[3])||{id:'old',title:'历史失败任务',status:'failed',completed:true,error:'缺少模型文件',media:[]};
     }
     if(url.pathname==='/api/outputs') body={items:[{filename:'测试镜头.mp4',media_subfolder:'local_ai_workbench/project',subfolder:'project',
       kind:'video',rel:'project/测试镜头.mp4',size:1000,url:'/api/view?filename=test.mp4'}],count:1};
     if(url.pathname==='/api/media/metadata') body={ok:true,metadata:{width:1920,height:1080,fps:30}};
     if(url.pathname==='/api/view') return route.fulfill({status:204});
     assert.ok(!/\/(start-comfyui|install-comfyui|free|video-smoke-test)$/.test(url.pathname));
     return route.fulfill({contentType:'application/json',body:JSON.stringify(body)});
    }
    const base=path.resolve(root,'beginner_frontend/static');
    const file=path.resolve(base,url.pathname==='/'?'index.html':url.pathname.replace(/^\/static\//,''));
    assert.ok(file.startsWith(base+path.sep));
    if(!fs.existsSync(file))return route.fulfill({status:204});
    return route.fulfill({path:file,contentType:file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html'});
   });
   await page.goto('http://127.0.0.1:18762/');
   await page.waitForFunction(()=>typeof appInitialized!=='undefined'&&appInitialized);
   assert.match(await page.title(),/创作工作台/);
   assert.equal(await page.locator('.view:not(.hidden)').count(),1);
   assert.equal(await page.locator('.view-tab.active').getAttribute('data-view'),'workflow','new users start in the creation form');
   assert.equal(await page.locator('#modelSelector').inputValue(),'minimax_h3_fl2va_int8_t2v','pending placeholder must yield to local hardware recommendation, never first cloud option');
   await page.locator('.view-tab[data-view="workflow"]').click();
   assert.equal(await page.locator('.stepper').isVisible(),false,'generation is not a six-step wizard');
   assert.equal(await page.locator('#steps').isVisible(),false,'basic controls by default');
   await page.waitForTimeout(400);
   await page.screenshot({path:path.join(output,`entry-${width}.png`)});
   await page.locator('[data-level="full"]').click();
   await page.locator('#modelSelector').selectOption('minimax_h3_fl2va_int8_t2v');
   await page.locator('#prompt').fill('A quiet shoreline in soft daylight');
   await page.locator('#projectTag').fill('课程作业');
   await page.locator('#steps').fill('31');
   await page.locator('#cfg').fill('1.3');
   await page.locator('.view-tab[data-view="process"]').click();
   await page.locator('[data-step="upscale"]').click();
   assert.equal(await page.locator('.view-tab.active').getAttribute('data-view'),'process');
   await page.locator('.view-tab[data-view="workflow"]').click();
   assert.equal(await page.locator('#steps').inputValue(),'31');
   assert.equal(await page.locator('#cfg').inputValue(),'1.3');
   await page.evaluate(()=>renderEnvironment(environmentData));
   assert.equal(await page.locator('#steps').inputValue(),'31','refresh preserves parameters');
   await page.evaluate(()=>{
    pipelineTuneToggle.checked=false;pipelineRifeToggle.checked=true;pipelineUpscaleToggle.checked=true;
    selectedModels.rife='rife49_2x';selectedModels.upscale='realesrgan_x2plus';
    void submitJob();void submitJob();
   });
   await page.waitForFunction(()=>!videoSubmitting&&submissionContexts.size===1);
   assert.equal(posts.length,1,'double click generates once');
   await page.locator('.view-tab[data-view="library"]').click();
   assert.equal(await page.evaluate(()=>Boolean(POLL_TIMERS.poll)),true,'tracking survives navigation');
   await page.screenshot({path:path.join(output,`library-${width}.png`)});
   await page.evaluate(()=>{
    pipelineRifeToggle.checked=false;pipelineUpscaleToggle.checked=false;
    rifeMultiplierInput.value='4';
    const job={id:'job-1',mode:'minimax_h3_t2v',title:'首镜头',status:'success',completed:true,width:1280,height:720,fps:24,
     media:[{kind:'video',filename:'first.mp4',type:'output',subfolder:'clips',metadata:{width:1280,height:720,fps:24}}]};
    handleJobUpdate(job,'draft');handleJobUpdate(job,'draft');
   });
   await page.waitForFunction(()=>submissionContexts.size===2);
   assert.equal(posts.length,2,'one captured pipeline continuation');
   assert.equal(field(posts[1],'rife_multiplier'),'2','captured multiplier survives UI edits');
   await page.evaluate(()=>{
    const job={id:'job-2',mode:'rife_2x',status:'success',completed:true,fps:24,rife_multiplier:2,
     media:[{kind:'video',filename:'smooth.mp4',subfolder:'clips',type:'output',metadata:{width:1280,height:720,fps:48}}]};
    handleJobUpdate(job,'rife');handleJobUpdate(job,'rife');
   });
   await page.waitForFunction(()=>submissionContexts.size===3);
   assert.equal(field(posts[2],'fps'),'48');
   assert.equal(field(posts[2],'source_video_filename'),'smooth.mp4');
   await page.evaluate(()=>{
    setStep('upscale'); setView('workflow');
    handleJobUpdate({id:'job-3',mode:'upscale_2x',status:'success',completed:true,
     media:[{kind:'video',filename:'enhanced.mp4',url:'/api/view?filename=enhanced.mp4',type:'output',subfolder:'clips',
      metadata:{width:2560,height:1440,fps:48}}]},'upscale');
   });
   await page.locator('[data-result-step="deflicker"]').click();
   assert.equal(await page.locator('#sourceVideoFilename').inputValue(),'enhanced.mp4','reverse processing uses chosen result, not the original');
   assert.equal(await page.locator('.view-tab.active').getAttribute('data-view'),'process');
   await page.locator('[data-step="upscale"]').click();
   await page.locator('#chooseWorkflowSource').click();
   await page.locator('.output-use').click();
   await page.waitForFunction(()=>workflowState.outputs.draft?.filename==='测试镜头.mp4');
   assert.equal(await page.locator('#sourceVideoSubfolder').inputValue(),'local_ai_workbench/project');
   assert.equal(await page.locator('.step-button.active').getAttribute('data-step'),'upscale','asset picker returns to chosen tool');
   await page.locator('[data-step="deflicker"]').click();
   await page.evaluate(()=>{pipelineRifeToggle.checked=true;pipelineUpscaleToggle.checked=true;});
   await page.locator('#videoTuneBrightness').fill('0.1');
   await page.locator('#primaryButton').click();
   await page.waitForFunction(()=>!videoSubmitting);
   assert.equal(tunePosts.length,1);
   assert.deepEqual(await page.evaluate(()=>submissionContexts.get('tune-1').pipeline),[],'manual processing never inherits automatic generation stages');
   assert.equal(field(tunePosts[0],'brightness'),'0.1','primary respects visible tune controls');
   await page.locator('[data-step="upscale"]').click();
   assert.match(await page.locator('#targetResolutionText').textContent(),/3840 x 2160/);
   assert.equal(await page.locator('.step-button.active').getAttribute('data-step'),'upscale');
   await page.waitForTimeout(250);
   await page.screenshot({path:path.join(output,`workflow-${width}.png`)});
   await page.locator('.view-tab[data-view="tasks"]').click();
   await page.locator('#recentJobsFilter [data-filter="failed"]').click();
   await page.waitForTimeout(150);
   assert.ok(queries.some(u=>u.pathname==='/api/jobs'&&u.searchParams.get('status')==='failed'));
   await page.evaluate(()=>previewJobFromList('old'));
   assert.match(await page.locator('#taskPreviewDetail').textContent(),/缺少模型文件/);
   assert.ok(queries.some(u=>u.pathname==='/api/jobs/old'&&u.searchParams.get('refresh')==='false'));
   await page.screenshot({path:path.join(output,`tasks-${width}.png`)});
   await page.locator('.view-tab[data-view="image-studio"]').click();
   await page.locator('#imageProfile').selectOption('qwen21_turbo_int8');
   await page.locator('#imagePrompt').fill('A ceramic cup on a desk');
   await page.evaluate(()=>{
    const form=document.querySelector('#imageStudioForm');
    form.dispatchEvent(new Event('submit',{cancelable:true}));form.dispatchEvent(new Event('submit',{cancelable:true}));
   });
   await page.waitForTimeout(500);
   assert.equal(imagePosts,1,'image preflight has same submission lock');
   await page.locator('.view-tab[data-view="tasks"]').click();
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
   await page.reload();
   try { await page.waitForFunction(()=>appInitialized); }
   catch(error) {console.error('reload errors',errors,queries.slice(-15).map(u=>u.pathname));throw error;}
   assert.equal(await page.evaluate(()=>workflowState.outputs.draft?.filename),'测试镜头.mp4','selected source survives refresh');
   await page.locator('.view-tab[data-view="workflow"]').click();
   assert.equal(await page.locator('#prompt').inputValue(),'A quiet shoreline in soft daylight','prompt survives refresh');
   assert.equal(await page.locator('#projectTag').inputValue(),'课程作业','project survives refresh');
   assert.equal(await page.locator('#steps').inputValue(),'31','per-model generation parameters survive refresh');
   await page.locator('[data-level="basic"]').click();
   assert.equal(await page.locator('#steps').isVisible(),false);
   await page.waitForTimeout(250);
   await page.screenshot({path:path.join(output,`generation-${width}.png`)});
   await page.locator('#modelSelector').selectOption('ltx25_distilled_int8_t2v');
   assert.equal(await page.locator('#h3Tools').isVisible(),false,'LTX does not show H3-only tools');
   await page.locator('#modelSelector').selectOption('ltx25_distilled_int8_i2v');
   assert.equal(await page.locator('[data-section="image"]').isVisible(),true);
   assert.equal(await page.locator('#mode').inputValue(),'ltx25_i2v');
   await page.evaluate(()=>window.acceptImageStudioKeyframe({input_name:'keyframe.png',source_label:'图片结果'}, {focus:false}));
   assert.equal(await page.evaluate(()=>currentStep().id),'draft','image handoff opens generation directly');
   assert.equal(await page.locator('#sourceImageFilename').inputValue(),'keyframe.png');
   assert.equal(await page.locator('#modelSelector').inputValue(),'ltx25_distilled_int8_i2v','handoff retains compatible engine');
   await page.locator('.view-tab[data-view="process"]').click();
   await page.locator('#clearProcessingSource').click();
   assert.equal(await page.locator('#sourceVideoFilename').inputValue(),'','remove source does not leave hidden input');
   assert.equal(await page.locator('#resultActions').isVisible(),false);
   await page.locator('#videoInput').setInputFiles({name:'local-clip.mp4',mimeType:'video/mp4',buffer:Buffer.from('CPU fixture')});
   assert.equal(await page.locator('#sourceVideoFilename').inputValue(),'');
   assert.match(await page.locator('#workflowSourceLabel').textContent(),/local-clip.mp4/);
   assert.equal(await page.locator('#resultActions').isVisible(),false,'upload never retains old result actions');
   await page.locator('[data-step="edit"]').click();
   assert.equal(await page.evaluate(()=>stitchFiles.length),1,'local input carries into stitching');
   assert.equal(await page.locator('#videoInput').inputValue(),'');
   await page.locator('#clipsInput').setInputFiles({name:'second.mp4',mimeType:'video/mp4',buffer:Buffer.from('CPU fixture')});
   assert.equal(await page.evaluate(()=>stitchFiles.length),2,'adding clips does not replace the carried source');
   await page.locator('#clearProcessingSource').click();
   assert.equal(await page.evaluate(()=>stitchFiles.length),0,'clear source also clears the current clip list');
   await page.locator('[data-step="upscale"]').click();
   await page.reload();
   await page.waitForFunction(()=>appInitialized);
   assert.equal(await page.locator('.view-tab.active').getAttribute('data-view'),'process','resume the selected task, not setup');
   assert.equal(await page.locator('.step-button.active').getAttribute('data-step'),'upscale','resume the selected operation');
   assert.equal(await page.locator('#sourceVideoFilename').inputValue(),'','removed source stays removed');
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
   assert.deepEqual(errors,[]);
   await context.close();
   console.log(`PASS ${width}: navigation, parameter isolation, double submit, captured pipeline, source metadata, task filtering, image submission`);
  }
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
