import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createConfig, DEFAULTS} from '../plugins/removelink/dist/assets/view.js';
const Vue = await import(process.env.REMOVELINK_VUE_RUNTIME || 'vue');

function fixture(initial = {}) {
  const node = (type, text = '') => ({type, text, props: {}, children: [], parent: null});
  const remove = item => {if (item.parent) {const siblings = item.parent.children; siblings.splice(siblings.indexOf(item), 1); item.parent = null;}};
  const renderer = Vue.createRenderer({
    createElement: type => node(type), createText: text => node('#text', text), createComment: text => node('#comment', text),
    insert(item, parent, anchor = null) {remove(item); const index = anchor ? parent.children.indexOf(anchor) : -1; parent.children.splice(index < 0 ? parent.children.length : index, 0, item); item.parent = parent;},
    remove, parentNode: item => item.parent, nextSibling: item => item.parent?.children[item.parent.children.indexOf(item) + 1] || null,
    setElementText(item, text) {item.text = text; item.children = [];}, setText(item, text) {item.text = text;},
    patchProp(item, key, previous, value) {item.props[key] = value;},
  });
  const root = node('root'), events = [], calls = [];
  const api = {get: (...args) => calls.push(args), post: (...args) => calls.push(args)};
  const app = renderer.createApp(createConfig(Vue), {initialConfig: initial, api, pluginId: 'RemoveLink',
    onSave: value => events.push(['save', JSON.parse(JSON.stringify(value))]), onClose: () => events.push(['close']), onLayout: value => events.push(['layout', value])});
  app.mount(root);
  const all = (predicate, item = root) => [...(predicate(item) ? [item] : []), ...item.children.flatMap(child => all(predicate, child))];
  const text = item => (item.type === '#comment' ? '' : item.text) + item.children.map(text).join('');
  const button = label => all(item => item.type === 'button' && text(item) === label)[0];
  const field = label => all(item => item.props['aria-label'] === label && ['input', 'textarea'].includes(item.type))[0];
  const click = async label => {assert.ok(button(label), label); button(label).props.onClick(); await Vue.nextTick();};
  const input = async (label, value) => {field(label).props.onInput({target: {value}}); await Vue.nextTick();};
  const toggle = async (label, checked) => {field(label).props.onChange({target: {checked}}); await Vue.nextTick();};
  return {root, events, calls, all, text, field, click, input, toggle, close: () => app.unmount()};
}

test('real Vue accepts reactive host props and preserves defaults and unknown saved keys', async () => {
  const original = {...DEFAULTS, enabled: true, monitor_dirs: '/downloads\n/media/影片', extra: {value: 'keep'}};
  const f = fixture(Vue.reactive(original));
  try {
    assert.equal(f.field('目录列表').props.value, original.monitor_dirs);
    await f.click('保存设置');
    assert.deepEqual(f.events.find(event => event[0] === 'save')[1], original);
    assert.equal(f.calls.length, 0);
  } finally {f.close();}
});

test('draft paths, switches and mappings survive navigation without mutating host configuration', async () => {
  const initial = {...DEFAULTS, monitor_strm_deletion: true, strm_path_mappings: '/strm: u115:/media'};
  const snapshot = structuredClone(initial), f = fixture(initial);
  try {
    await f.input('目录列表', ' /下载目录\n/media/path with spaces ');
    await f.click('STRM 联动');
    await f.toggle('启用 STRM 文件监控', false);
    await f.input('STRM 路径映射', '/strm: u115:/资料/目录:with:colon');
    await f.click('运行设置');
    await f.toggle('发送结果通知', true);
    await f.click('硬链接');
    assert.equal(f.field('目录列表').props.value, ' /下载目录\n/media/path with spaces ');
    await f.click('保存设置');
    const saved = f.events.find(event => event[0] === 'save')[1];
    assert.equal(saved.monitor_dirs, ' /下载目录\n/media/path with spaces ');
    assert.equal(saved.strm_path_mappings, '/strm: u115:/资料/目录:with:colon');
    assert.equal(saved.monitor_strm_deletion, false);
    assert.equal(saved.notify, true);
    assert.deepEqual(initial, snapshot);
    assert.equal(f.calls.length, 0);
  } finally {f.close();}
});

test('invalid delays stay in the draft and cannot emit a save', async () => {
  const f = fixture();
  try {
    for (const value of ['9', '30.5', '', '86401']) {
      await f.input('等待时间（秒）', value);
      await f.click('保存设置');
      assert.equal(f.events.filter(event => event[0] === 'save').length, 0);
      assert.match(f.text(f.all(item => item.props.role === 'alert')[0]), /10 至 86400/);
    }
    await f.input('等待时间（秒）', '86400');
    await f.click('保存设置');
    assert.equal(f.events.find(event => event[0] === 'save')[1].delay_seconds, 86400);
  } finally {f.close();}
});

test('turning scrape cleanup off retains the configured custom suffixes', async () => {
  const f = fixture({delete_scrap_infos: true, custom_scrap_extensions: '.txt\n-mediainfo.json'});
  try {
    await f.click('清理选项');
    await f.toggle('清理刮削文件', false);
    assert.equal(f.field('自定义后缀').props.disabled, true);
    await f.click('硬链接');
    await f.click('保存设置');
    const saved = f.events.find(event => event[0] === 'save')[1];
    assert.equal(saved.custom_scrap_extensions, '.txt\n-mediainfo.json');
    assert.equal(saved.delete_scrap_infos, false);
  } finally {f.close();}
});

test('navigation and cancel make no API calls and never save the draft', async () => {
  const initial = {...DEFAULTS, notify: true}, f = fixture(initial);
  try {
    for (const label of ['运行设置', 'STRM 联动', '清理选项', '硬链接']) await f.click(label);
    await f.click('运行设置');
    await f.toggle('发送结果通知', false);
    await f.click('取消');
    assert.equal(f.events.filter(event => event[0] === 'close').length, 1);
    assert.equal(f.events.filter(event => event[0] === 'save').length, 0);
    assert.equal(f.events.filter(event => event[0] === 'layout').length, 1);
    assert.equal(f.calls.length, 0);
    assert.equal(initial.notify, true);
  } finally {f.close();}
});
