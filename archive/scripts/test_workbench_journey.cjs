const assert = require('node:assert/strict');
const journey = require('../beginner_frontend/static/workbench-journey.js');

assert.deepEqual(journey.restore(null), {view:'workflow', step:'draft', task:'video'});
assert.deepEqual(journey.route('workflow', 'upscale'), {view:'workflow', step:'draft', task:'video'});
assert.deepEqual(journey.route('process', 'upscale'), {view:'workflow', step:'upscale', task:'process'});
assert.equal(journey.restore({view:'process',operation:'rife'}).step, 'rife');
assert.equal(journey.restore({view:'process',operation:'missing'}).step, 'deflicker');
assert.equal(journey.restore({view:'missing'}).view, 'workflow');
assert.equal(journey.route('image-studio').task, 'image');
assert.equal(journey.route('tasks').view, 'tasks');
assert.equal(journey.tools.includes('keyframe'), false);
console.log('PASS task routing, persisted operations, legacy and invalid routes');
