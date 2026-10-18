import {test} from 'node:test';
import assert from 'node:assert/strict';
import {filterRows, paginate, validateConfig, formatBytes, createPage, createConfig} from '../../../plugins.v3/cleaninvalidseed/dist/assets/view.js';

function fakeVue() {
  const mounts = [], unmounts = [];
  return {mounts, unmounts, defineComponent: value => value, ref: value => ({value}), reactive: value => value,
    computed: get => ({get value() {return get();}}), watch: () => {}, onMounted: fn => mounts.push(fn), onBeforeUnmount: fn => unmounts.push(fn),
    h(type, props, children) {if (typeof props !== 'object' || Array.isArray(props) || props === null) return {type, props: {}, children: props}; return {type, props, children};}};
}
function all(node, predicate) {
  if (!node || typeof node !== 'object') return [];
  if (Array.isArray(node)) return node.flatMap(child => all(child, predicate));
  return [...(predicate(node) ? [node] : []), ...all(node.children, predicate)];
}
const button = (tree, text) => all(tree, n => n.type === 'button' && n.props['aria-label'] === text)[0];

test('search, type and status filters combine without dropping final-page entries', () => {
  const rows = Array.from({length: 53}, (_, i) => ({id: String(i), name: `影片${i}`, service: 'TR', reason: '持续观察', kind: i % 2 ? 'file' : 'torrent', status: 'candidate', ready: i % 3 === 0}));
  assert.equal(filterRows(rows, '影片52 TR', '', 'torrent').length, 1);
  assert.equal(filterRows(rows, '', 'ready', '').length, 18);
  const ids = [1, 2, 3].flatMap(page => paginate(rows, page).rows.map(r => r.id));
  assert.equal(new Set(ids).size, 53);
  assert.equal(paginate(rows, 99).page, 3);
  assert.equal(paginate([], 99).pages, 1);
});

test('space estimate is explicitly bytes and never claims released disk space', () => {
  assert.equal(formatBytes(0), '0 B');
  assert.equal(formatBytes(1024 ** 3), '1.0 GB');
});

test('settings migrate to preview and preserve paths, filters and selected downloaders', () => {
  const Vue = fakeVue(), events = [];
  const render = createConfig(Vue).setup({initialConfig: {enabled: true, cron: '0 21 * * *', downloaders: ['TR'], download_dirs: '/mp/movie:/tr/movie', exclude_keywords: 'keep', delete_invalid_files: true}}, {emit: (...args) => events.push(args)});
  button(render(), '保存设置').props.onClick();
  const saved = events.find(event => event[0] === 'save')[1];
  assert.equal(saved.action, 'preview');
  assert.equal(saved.cron, '0 21 * * *');
  assert.equal(saved.download_dirs, '/mp/movie:/tr/movie');
  assert.equal(saved.exclude_keywords, 'keep');
  assert.deepEqual(saved.downloaders, ['TR']);
  assert.equal(saved.delete_invalid_files, undefined);
});

test('legacy file age follows the previous configured days and null values use safe defaults', () => {
  const Vue = fakeVue(), events = [];
  const render = createConfig(Vue).setup({initialConfig: {downloaders: ['TR'], min_seeding_days: 5, label: null}}, {emit: (...args) => events.push(args)});
  button(render(), '保存设置').props.onClick();
  const saved = events.find(event => event[0] === 'save')[1];
  assert.equal(saved.file_min_age_days, 5);
  assert.equal(saved.label, '无效做种');
});

test('host-normalized empty legacy labels show the real backend default', () => {
  const Vue = fakeVue(), events = [];
  const render = createConfig(Vue).setup({initialConfig: {downloaders: ['TR'], label: ''}}, {emit: (...args) => events.push(args)});
  button(render(), '保存设置').props.onClick();
  assert.equal(events.find(event => event[0] === 'save')[1].label, '无效做种');
});

test('invalid settings are rejected before emitting any save', () => {
  for (const changes of [{confirmations: 1}, {grace_hours: .5}, {file_min_age_days: 0}, {max_actions: 101}, {min_seeding_days: -1}, {downloaders: []}, {detect_invalid_files: true, download_dirs: ''}]) {
    const Vue = fakeVue(), events = [];
    const render = createConfig(Vue).setup({initialConfig: {downloaders: ['TR'], ...changes}}, {emit: (...args) => events.push(args)});
    button(render(), '保存设置').props.onClick();
    assert.equal(events.filter(event => event[0] === 'save').length, 0);
    assert.ok(all(render(), n => n.props.role === 'alert').length);
  }
});

test('disabled, removed and renamed downloaders can be deselected before choosing a replacement', async () => {
  const Vue = fakeVue(), events = [];
  const render = createConfig(Vue).setup({initialConfig: {downloaders: ['Retired', 'Gone']}, pluginId: 'CleanInvalidSeed',
    api: {get: async () => ({downloaders: [{name: 'Retired', type: 'qbittorrent', enabled: false}, {name: 'Replacement', type: 'qbittorrent', enabled: true}]})}}, {emit: (...args) => events.push(args)});
  for (const mount of Vue.mounts) await mount();
  const checkbox = name => {
    const label = all(render(), n => n.type === 'label' && all(n, child => child.type === 'strong' && child.children === name).length)[0];
    return all(label, n => n.type === 'input' && n.props.type === 'checkbox')[0];
  };
  assert.equal(checkbox('Retired').props.disabled, false);
  checkbox('Retired').props.onChange({target: {checked: false}});
  assert.equal(checkbox('Retired').props.disabled, true);
  assert.ok(checkbox('Gone'));
  checkbox('Gone').props.onChange({target: {checked: false}});
  checkbox('Replacement').props.onChange({target: {checked: true}});
  button(render(), '保存设置').props.onClick();
  assert.deepEqual(events.find(event => event[0] === 'save')[1].downloaders, ['Replacement']);
});

test('config ranges support only whole numbers', () => {
  for (const value of ['nan', 'inf', '1.5', '-1', '721']) {
    assert.ok(validateConfig({downloaders: ['TR'], confirmations: 2, grace_hours: value, min_seeding_days: 0, file_min_age_days: 10, max_actions: 10}));
  }
});

async function pageFixture(overrides = {}) {
  const Vue = fakeVue(), calls = [];
  const state = {success: true, busy: false, config: {action: 'preview'}, counts: {candidate: 1}, history: [], trash: [],
    report: {scan_id: 'scan1', at: Date.now() / 1000, rows: [{id: 'one', name: '候选', kind: 'torrent', status: 'candidate', ready: true, size: 1, reason: '明确删种', service: 'TR', trackers: []}]}, ...overrides};
  const api = {get: async () => state, post: async (path, payload) => {calls.push({path, payload}); return {success: true, results: [{status: 'success'}]};}};
  const render = createPage(Vue).setup({api, pluginId: 'CleanInvalidSeed'}, {emit: () => {}});
  for (const fn of Vue.mounts) await fn();
  await new Promise(resolve => setImmediate(resolve));
  return {render, calls, state, close: () => Vue.unmounts.forEach(fn => fn())};
}

test('destructive action needs selected ready rows and exact confirmation text', async () => {
  const fixture = await pageFixture();
  try {
    all(fixture.render(), n => n.type === 'input' && n.props.type === 'checkbox')[0].props.onChange();
    button(fixture.render(), '移除任务 · 保留文件').props.onClick();
    let tree = fixture.render();
    assert.equal(button(tree, '确认执行').props.disabled, true);
    all(tree, n => n.type === 'form')[0].props.onSubmit({preventDefault() {}});
    assert.equal(fixture.calls.length, 0);
    all(tree, n => n.type === 'input' && n.props['aria-label'] === '确认文字')[0].props.onInput({target: {value: '移除任务并保留文件'}});
    tree = fixture.render();
    assert.equal(button(tree, '确认执行').props.disabled, false);
    await button(tree, '确认执行').props.onClick();
    assert.equal(fixture.calls[0].path, 'plugin/CleanInvalidSeed/page_execute');
    assert.equal(fixture.calls[0].payload.confirmation, '移除任务并保留文件');
    assert.deepEqual(fixture.calls[0].payload.ids, ['one']);
  } finally {fixture.close();}
});

test('expired evidence and a busy operation disable every selection', async () => {
  for (const changes of [{busy: true}, {plan_current:false}, {last_error: {at: Date.now() / 1000 + 1, message: 'offline'}}]) {
    const fixture = await pageFixture(changes);
    try {assert.equal(all(fixture.render(), n => n.type === 'input' && n.props.type === 'checkbox')[0].props.disabled, true);}
    finally {fixture.close();}
  }
});

test('waiting candidates explain the observation window and disable empty bulk selection', async () => {
  const fixture = await pageFixture({config: {action: 'preview', confirmations: 2}, report: {scan_id: 'waiting', at: Date.now() / 1000,
    rows: [{id: 'wait', name: '观察中', kind: 'torrent', status: 'candidate', ready: false, observations: 2, ready_at: Date.now() / 1000 + 3600}]}});
  try {
    const tree = fixture.render(), checkbox = all(tree, n => n.props.type === 'checkbox')[0];
    assert.equal(checkbox.props.disabled, true);
    assert.match(checkbox.props.title, /已观察 2\/2 次；观察期未结束/);
    assert.equal(checkbox.props['aria-describedby'], 'cis-row-block-wait');
    assert.ok(all(tree, n => n.props.id === 'cis-row-block-wait' && n.children.includes('后重新检测')).length);
    assert.equal(button(tree, '选择本页可处理项').props.disabled, true);
    assert.equal(fixture.calls.length, 0);
  } finally {fixture.close();}
});

test('stale plans show the recovery action while refresh only loads stored results', async () => {
  const fixture = await pageFixture();
  try {
    fixture.state.report.at -= 601;
    await button(fixture.render(), '刷新结果').props.onClick();
    const tree = fixture.render(), checkbox = all(tree, n => n.props.type === 'checkbox')[0];
    assert.equal(checkbox.props.disabled, true);
    assert.match(checkbox.props.title, /超过 10 分钟/);
    assert.match(all(tree, n => n.props.id === 'cis-plan-block')[0].children, /只读检测.*刷新结果/);
    assert.equal(fixture.calls.length, 0);
    await button(tree, '只读检测').props.onClick();
    assert.equal(fixture.calls[0].path, 'plugin/CleanInvalidSeed/page_scan');
  } finally {fixture.close();}
});

test('a confirmation left open across plan expiry cannot submit an action', async () => {
  const fixture = await pageFixture(), originalNow = Date.now, start = originalNow();
  try {
    all(fixture.render(), n => n.props.type === 'checkbox')[0].props.onChange();
    button(fixture.render(), '移除任务 · 保留文件').props.onClick();
    all(fixture.render(), n => n.props['aria-label'] === '确认文字')[0].props.onInput({target: {value: '移除任务并保留文件'}});
    assert.equal(button(fixture.render(), '确认执行').props.disabled, false);
    Date.now = () => start + 601000;
    await button(fixture.render(), '确认执行').props.onClick();
    assert.equal(fixture.calls.length, 0);
    assert.equal(all(fixture.render(), n => n.props.role === 'dialog').length, 0);
    assert.equal(button(fixture.render(), '移除任务 · 保留文件').props.disabled, true);
  } finally {Date.now = originalNow; fixture.close();}
});

test('fresh eligible rows can be selected and new scans clear old selections', async () => {
  const fixture = await pageFixture();
  try {
    const checkbox = all(fixture.render(), n => n.props.type === 'checkbox')[0];
    assert.equal(checkbox.props.disabled, false);
    assert.equal(checkbox.props.title, '');
    checkbox.props.onChange();
    assert.equal(all(fixture.render(), n => n.props.type === 'checkbox')[0].props.checked, true);
    assert.equal(button(fixture.render(), '标记任务').props.disabled, false);
    await button(fixture.render(), '只读检测').props.onClick();
    assert.equal(all(fixture.render(), n => n.props.type === 'checkbox')[0].props.checked, false);
    assert.deepEqual(fixture.calls.map(c => c.path), ['plugin/CleanInvalidSeed/page_scan']);
  } finally {fixture.close();}
});

test('read only button invokes only the scan route even with automatic removal configured', async () => {
  const fixture = await pageFixture({config: {action: 'remove'}});
  try {await button(fixture.render(), '只读检测').props.onClick(); assert.equal(fixture.calls.length, 1); assert.equal(fixture.calls[0].path, 'plugin/CleanInvalidSeed/page_scan');}
  finally {fixture.close();}
});
