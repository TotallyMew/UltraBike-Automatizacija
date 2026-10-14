
const assert = require('node:assert/strict');
const scripts = JSON.parse(process.argv[2]);
let input = {type: 'checkbox', owned: true, checked: true, getClientRects: () => [{}]};
let directInput = input, labels = [], canvases = [];
let template = {id: 277, hash: 'custom-template', type: 'essential', views: [
    {type: 'front', order: 2, status: 'published'}, {type: 'side', order: 1, status: 'published'}]};
const standard = {id: 433, hash: 'standard-template', type: 'standard'};
const root = {contains: node => node.owned,
    querySelector: () => directInput,
    querySelectorAll: selector => selector === 'label' ? labels :
        canvases.filter(canvas => canvas.id.startsWith(selector.match(/id\^="(.+)"/)[1]))};
const state = {templates: [template, standard], template: 277, currentTemplate: template, customization: {}, initialize: true,
    isStandardTemplate: false, canvasesReady: true,
    imagesCanvas: {'277': {side: {60: 'frame.png', 85: 'wheels.png', base: 'base.png'},
        front: {60: 'frame-front.png', base: 'base-front.png'}}}};
const document = {querySelector: () => root, getElementById: id => canvases.find(canvas => canvas.id === id),
    createElement: () => {const draws = []; return {getContext: () => ({
        drawImage(canvas) { draws.push(canvas.id); }, clearRect() {} }), toDataURL: () => draws.join(',')};}};
const window = {Alpine: {$data: () => state}};
const getComputedStyle = node => ({visibility: node.invisible ? 'hidden' : 'visible'});
const execute = (script, ...args) => new Function('document', 'window', 'getComputedStyle', 'args',
    'return (function() {' + script + '}).apply(null, args);')(document, window, getComputedStyle, args);
const label = (text, choice=input, extra={}) => ({innerText: text, control: choice,
    getClientRects: () => extra.hidden ? [] : [{}], querySelector: () => extra.caption ? {textContent: extra.caption} : null, ...extra});
labels = [label(scripts.captions.join(' '), input, {caption: scripts.captions[1]})];
assert.equal(execute(scripts.control).input, input);
assert.equal(execute(scripts.control).control, input);
directInput = null; assert.equal(execute(scripts.control).input, input); // combined label fallback
labels.push(label('Your Design', {...input}));
assert.throws(() => execute(scripts.control), /More than one/);
labels = [label('Gloss'), label('Paint'), label('Your Design', {type: 'button', owned: true})];
assert.equal(execute(scripts.control), null);
labels = [label('Your Design', input, {hidden: true})]; assert.equal(execute(scripts.control), null);
labels = [label('Your Design', {...input, disabled: true})]; assert.equal(execute(scripts.control), null);
directInput = input;
state.initialize = false; assert.equal(execute(scripts.control), null); state.initialize = true;
state.customization = null; assert.equal(execute(scripts.control), null); state.customization = {};
state.canvasesReady = false; assert.equal(execute(scripts.control), null); state.canvasesReady = true;
state.loadingTemplate = 277; assert.equal(execute(scripts.control), null); state.loadingTemplate = null;
const canvas = (id, extra={}) => ({id, owned: true, dataset: {drawn: '1'}, width: 4100, height: 2310, ...extra});
canvases = [canvas('canvas-433_side_base'), canvas('canvas-277_side_60'), canvas('canvas-277_side_85'),
    canvas('canvas-277_side_alt60'), canvas('canvas-277_side_base'),
    canvas('canvas-277_side_name1', {dataset: {drawn: '1', textZone: 'name1'}}),
    canvas('canvas-277_front_60', {hidden: true}), canvas('canvas-277_front_base', {hidden: true}),
    canvas('canvas-277_side_unpublished', {dataset: {}})];
let result = execute(scripts.gallery, input);
assert.deepEqual(result.images.map(image => image.view), ['side', 'front']);
assert.equal(result.images[0].data_url, 'canvas-277_side_60,canvas-277_side_85,canvas-277_side_base,canvas-277_side_name1');
assert.equal(result.images[1].data_url, 'canvas-277_front_60,canvas-277_front_base');
assert.equal(result.images[0].width, 4100);
input.checked = false; assert.equal(execute(scripts.gallery, input), null); input.checked = true;
state.template = 433; assert.equal(execute(scripts.gallery, input), null); state.template = 277;
state.isStandardTemplate = true; assert.equal(execute(scripts.gallery, input), null); state.isStandardTemplate = false;
for (const flag of ['loadingTemplate', 'loadingInspiration', 'loadingVarnish', 'componentUpdating']) {
    state[flag] = true; assert.equal(execute(scripts.metadata, input), null); state[flag] = null;
}
state.canvasesReady = false; assert.equal(execute(scripts.metadata, input), null); state.canvasesReady = true;
canvases[2].dataset.drawn = ''; assert.equal(execute(scripts.metadata, input), null); canvases[2].dataset.drawn = '1';
canvases[2].width = 300; assert.equal(execute(scripts.metadata, input), null); canvases[2].width = 4100;
canvases[4].dataset.drawn = ''; assert.equal(execute(scripts.metadata, input), null); canvases[4].dataset.drawn = '1';
canvases[2].owned = false; assert.equal(execute(scripts.metadata, input), null); canvases[2].owned = true;
state.templates = [template]; labels = []; directInput = null;
assert.equal(execute(scripts.control).default_only, true);
assert.equal(execute(scripts.gallery, null).images.length, 2);
state.templates = [template, standard]; assert.equal(execute(scripts.gallery, null), null);
template.views.push({type: 'detail', order: 3, status: 'published'});
assert.deepEqual(execute(scripts.gallery, input).unavailable, ['detail']);
console.log('Real toggle, complete layer export and readiness checks passed');
