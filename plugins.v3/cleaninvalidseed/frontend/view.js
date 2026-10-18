const PLUGIN_ICON = `/api/v1/system/img/1?imgurl=${encodeURIComponent('https://raw.githubusercontent.com/DzAvril/MoviePilot-Plugins/a06b2f2a7916a9e492fdf5b0a25e30a38ca28127/icons/CleanInvalidSeed-3.0.2.png')}&cache=true`;
const STATUS = {healthy: '正常', candidate: '待复核', protected: '已保护', warning: '需检查', unknown: '信息不足', processed: '已处理'};
const ACTION = {tag: '标记选中任务', remove: '移除任务并保留文件', quarantine: '移入回收区', restore: '恢复原位'};
const RESULT = {success: '已确认', skipped: '已跳过', uncertain: '需核对', intent: '待核对'};
const DEFAULTS = {enabled: false, cron: '0 3 * * *', action: 'preview', downloaders: [], notify: false,
  notify_all: false, label: '无效做种', confirmations: 2, grace_hours: 24, min_seeding_days: 10, max_actions: 10,
  detect_invalid_files: false, download_dirs: '', file_min_age_days: 10, exclude_keywords: '', exclude_categories: '',
  exclude_labels: '', custom_error_msg: '', onlyonce: false};
const unwrap = result => result?.data?.success !== undefined ? result.data : result;
export function formatBytes(size) {
  if (!size) return '0 B';
  const index = Math.min(4, Math.floor(Math.log(Math.max(1, size)) / Math.log(1024)));
  return `${(size / 1024 ** index).toFixed(index ? 1 : 0)} ${['B', 'KB', 'MB', 'GB', 'TB'][index]}`;
}
export function filterRows(rows, query, status, kind) {
  const terms = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  return rows.filter(row => (!kind || row.kind === kind) && (!status || (status === 'ready' ? row.ready : row.status === status)) &&
    terms.every(term => [row.name, row.service, row.reason, row.path, ...(row.trackers || []).map(t => t.host)].join(' ').toLocaleLowerCase().includes(term)));
}
export function paginate(rows, page, size = 20) {
  const pages = Math.max(1, Math.ceil(rows.length / size)), current = Math.min(pages, Math.max(1, page));
  return {rows: rows.slice((current - 1) * size, current * size), page: current, pages};
}
export function validateConfig(config) {
  for (const [key, min, max] of [['confirmations', 2, 20], ['grace_hours', 1, 720], ['min_seeding_days', 0, 3650], ['file_min_age_days', 1, 3650], ['max_actions', 1, 100]]) {
    if (!Number.isInteger(Number(config[key])) || Number(config[key]) < min || Number(config[key]) > max) return '请检查观察次数、时间及每批上限的范围。';
  }
  if (!config.downloaders.length) return '请选择至少一个需要检测的下载器。';
  if (config.detect_invalid_files && !config.download_dirs.trim()) return '启用源文件检测前请填写目录映射。';
  return '';
}
function elements(Vue) {
  const {h} = Vue;
  const icon = (name, size = 20) => h('svg', {viewBox: '0 0 24 24', width: size, height: size, fill: 'none', stroke: 'currentColor', 'stroke-width': 1.7, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': true},
    [h('path', {d: {shield: 'M12 3 3 7v5c0 5 9 10 9 10s9-5 9-10V7L12 3Zm-4 9 3 3 5-6', refresh: 'M20 7v5h-5M4 17v-5h5M6 7a7 7 0 0 1 12-2l2 3M4 16l2 3a7 7 0 0 0 12-2',
      settings: 'M9 3h6l1 3 3 1 2 5-2 5-3 1-1 3H9l-1-3-3-1-2-5 2-5 3-1 1-3ZM8 12a4 4 0 1 0 8 0 4 4 0 0 0-8 0Z', close: 'm6 6 12 12M6 18 18 6',
      folder: 'M3 7V4h7l3 3h8v13H3V7Z', check: 'm5 12 4 4L19 6', search: 'm21 21-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z'}[name] || 'M12 4v16M4 12h16'})]);
  const button = (label, onClick, options = {}) => h('button', {type: 'button', class: `cis-btn ${options.primary ? 'cis-primary' : ''} ${options.danger ? 'cis-danger' : ''}`, onClick, disabled: options.disabled, 'aria-label': label}, [options.icon && icon(options.icon, 17), label]);
  const badge = (text, status = '') => h('span', {class: `cis-badge cis-${status}`}, text);
  const date = time => time ? new Date(time * 1000).toLocaleString('zh-CN', {month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false}) : '尚未检测';
  const header = (title, detail, actions) => h('header', {class: 'cis-header'}, [h('div', {class: 'cis-brand'}, [h('img', {class: 'cis-logo', src: PLUGIN_ICON, alt: '清理无效做种图标', width: 64, height: 64}), h('div', [h('div', {class: 'cis-eyebrow'}, 'SEEDING · CARE'), h('h2', title), h('p', detail)])]), h('div', {class: 'cis-actions'}, actions)]);
  const section = (title, detail, content) => h('section', {class: 'cis-panel'}, [h('div', {class: 'cis-section-title'}, [h('h3', title), detail && h('p', detail)]), ...content]);
  const select = (label, value, options, change) => h('select', {'aria-label': label, value, onChange: e => change(e.target.value)}, options.map(([key, text]) => h('option', {value: key}, text)));
  return {icon, button, badge, date, header, section, select};
}

export function createPage(Vue) {
  const {defineComponent, h, ref, computed, onMounted, onBeforeUnmount, watch} = Vue;
  const {icon, button, badge, date, header, section, select} = elements(Vue);
  return defineComponent({name: 'CleanInvalidSeedPage', props: {api: Object, pluginId: String}, emits: ['layout', 'switch', 'close'],
    setup(props, {emit}) {
      const data = ref(null), error = ref(''), notice = ref(''), loading = ref(false), acting = ref(false);
      const query = ref(''), status = ref('candidate'), kind = ref(''), page = ref(1), tab = ref('review');
      const selected = ref([]), dialog = ref(''), confirmation = ref('');
      let timer, disposed = false, fetching = false;
      const endpoint = name => `plugin/${props.pluginId}/page_${name}`;
      const rows = computed(() => filterRows(data.value?.report?.rows || [], query.value, status.value, kind.value));
      const paged = computed(() => paginate(rows.value, page.value));
      const chosen = computed(() => (data.value?.report?.rows || []).filter(row => selected.value.includes(row.id)));
      const expired = computed(() => data.value?.plan_current === false || !data.value?.report?.at || Date.now() / 1000 - data.value.report.at > 600 || (data.value.last_error?.at || 0) > data.value.report.at);
      watch([query, status, kind], () => {page.value = 1; selected.value = [];});
      const load = async (quiet = false) => {
        if (fetching || disposed) return;
        fetching = true; if (!quiet) loading.value = true;
        try {
          const revision = quiet && data.value?.revision ? `?revision=${encodeURIComponent(data.value.revision)}` : '';
          const result = unwrap(await props.api.get(endpoint('status') + revision));
          if (!result?.success) throw new Error();
          if (!disposed) {
            if (result.unchanged && data.value) data.value.busy = result.busy;
            else {if (result.report?.scan_id !== data.value?.report?.scan_id) selected.value = []; data.value = result;}
            error.value = '';
          }
        } catch {if (!disposed) error.value = '暂时无法读取检测结果，请刷新重试。';}
        finally {fetching = false; loading.value = false;}
      };
      const scan = async () => {
        selected.value = []; notice.value = ''; acting.value = true;
        try {
          const result = unwrap(await props.api.post(endpoint('scan')));
          notice.value = result?.message || (result.success ? '检测已开始' : '检测未能开始');
          await load(true);
        } catch {error.value = '检测请求未完成，请刷新查看状态。';}
        finally {acting.value = false;}
      };
      const execute = async () => {
        acting.value = true;
        try {
          const result = unwrap(await props.api.post(endpoint('execute'), {scan_id: data.value.report.scan_id, ids: selected.value, action: dialog.value, confirmation: confirmation.value}));
          if (!result?.success) {notice.value = result?.message || '操作未完成，请重新检测。';}
          else {const successes = result.results.filter(item => item.status === 'success').length; notice.value = `已确认 ${successes} 项，其他 ${result.results.length - successes} 项请查看操作记录。`; selected.value = [];}
          dialog.value = ''; await load(true);
        } catch {error.value = '结果暂时无法确认，请先查看操作记录，避免重复提交。'; dialog.value = '';}
        finally {acting.value = false;}
      };
      const restore = async entry => {
        acting.value = true;
        try {const result = unwrap(await props.api.post(endpoint('restore'), {id: entry.id})); notice.value = result?.message || '恢复未完成'; await load(true);}
        catch {error.value = '暂时无法确认恢复结果，请刷新后查看。';}
        finally {acting.value = false;}
      };
      const toggle = id => {selected.value = selected.value.includes(id) ? selected.value.filter(x => x !== id) : [...selected.value, id];};
      const open = action => {dialog.value = action; confirmation.value = '';};
      onMounted(() => {emit('layout', {maxWidth: '1180px'}); load(); timer = setInterval(() => {if (!document.hidden && !acting.value) load(true);}, 3000);});
      onBeforeUnmount(() => {disposed = true; clearInterval(timer);});
      const rowView = row => h('article', {key: row.id, class: `cis-row ${selected.value.includes(row.id) ? 'cis-selected' : ''}`}, [
        h('input', {type: 'checkbox', 'aria-label': `选择 ${row.name}`, checked: selected.value.includes(row.id), disabled: !row.ready || expired.value || data.value.busy || acting.value, onChange: () => toggle(row.id)}),
        h('div', {class: 'cis-row-icon'}, icon(row.kind === 'file' ? 'folder' : 'shield', 20)),
        h('div', {class: 'cis-row-body'}, [h('div', {class: 'cis-row-title'}, [h('strong', row.name), badge(STATUS[row.status], row.status), row.ready && badge('可处理', 'ready')]),
          h('p', {class: 'cis-reason'}, row.reason), h('div', {class: 'cis-meta'}, [row.service || '源文件', ' · ', formatBytes(row.size),
            row.kind === 'torrent' && ` · ${row.client === 'transmission' ? 'Transmission' : 'qBittorrent'}${row.category ? ` · ${row.category}` : ''}`,
            row.observations && ` · 已观察 ${row.observations} 次`, !row.ready && row.ready_at && ` · 最早 ${date(row.ready_at)}`]),
          row.path && h('code', {class: 'cis-path'}, row.path),
          row.trackers?.length > 0 && h('details', [h('summary', 'Tracker 证据'), ...row.trackers.map(t => h('p', {class: 'cis-evidence'}, [h('strong', t.host), ` · ${t.healthy ? '成功' : t.detail || '暂无成功记录'}`]))])])]);
      const review = () => [
        h('div', {class: 'cis-toolbar'}, [h('label', {class: 'cis-search'}, [icon('search', 17), h('input', {'aria-label': '搜索任务、目录或原因', placeholder: '搜索任务、目录或原因', value: query.value, onInput: e => {query.value = e.target.value;}})]),
          select('检测状态', status.value, [['candidate', '待复核'], ['ready', '可处理'], ['warning', '需检查'], ['protected', '已保护'], ['unknown', '信息不足'], ['healthy', '正常'], ['', '全部状态']], v => {status.value = v;}),
          select('项目类型', kind.value, [['', '全部项目'], ['torrent', '种子任务'], ['file', '源文件']], v => {kind.value = v;})]),
        h('div', {class: 'cis-results-heading'}, [h('span', `共 ${rows.value.length} 项`), button('选择本页可处理项', () => {selected.value = [...new Set([...selected.value, ...paged.value.rows.filter(r => r.ready).map(r => r.id)])];}, {disabled: expired.value || data.value.busy || acting.value})]),
        h('div', {class: 'cis-list'}, paged.value.rows.length ? paged.value.rows.map(rowView) : [h('div', {class: 'cis-empty'}, [icon('check', 36), h('strong', data.value.report.at ? '当前筛选下没有项目' : '从一次只读检测开始'), h('p', data.value.report.at ? '可以切换状态，查看正常任务与受保护项目。' : '读取下载器和目录，只展示证据，不修改任务和文件。')])]),
        h('div', {class: 'cis-pagination'}, [h('span', `第 ${paged.value.page} / ${paged.value.pages} 页`), button('上一页', () => {page.value = paged.value.page - 1;}, {disabled: paged.value.page <= 1}), button('下一页', () => {page.value = paged.value.page + 1;}, {disabled: paged.value.page >= paged.value.pages})]),
        selected.value.length > 0 && h('div', {class: 'cis-selection'}, [h('strong', `已选 ${selected.value.length} 项`),
          button('取消选择', () => {selected.value = [];}),
          chosen.value.every(row => row.kind === 'torrent') && button('标记任务', () => open('tag'), {disabled: expired.value || acting.value || data.value.busy}),
          chosen.value.every(row => row.kind === 'torrent') && button('移除任务 · 保留文件', () => open('remove'), {danger: true, disabled: expired.value || acting.value || data.value.busy}),
          chosen.value.every(row => row.kind === 'file') && button('移入回收区', () => open('quarantine'), {disabled: expired.value || acting.value || data.value.busy}),
          new Set(chosen.value.map(r => r.kind)).size > 1 && h('span', '请分别选择种子任务或源文件')]),
      ];
      return () => h('div', {class: 'cis-root'}, [header('做种复核', '每一项清理，都有可检查的依据', [
        button('刷新', () => load(), {disabled: loading.value, icon: 'refresh'}), button(data.value?.busy ? '检测中…' : '只读检测', scan, {primary: true, disabled: acting.value || data.value?.busy, icon: 'search'}),
        button('设置', () => emit('switch'), {icon: 'settings'}), button('关闭', () => emit('close'), {icon: 'close'})]),
        error.value && h('div', {class: 'cis-alert cis-alert-error', role: 'alert'}, error.value),
        notice.value && h('div', {class: 'cis-alert', role: 'status'}, notice.value),
        data.value ? [
          h('div', {class: 'cis-overview'}, [['candidate', '待复核', '持续复核后才可处理'], ['warning', '需检查', '网络或账号问题，保留任务'], ['protected', '已保护', '命中保护条件，保留任务'], ['ready', '可处理', '已满足复核与观察条件']].map(([key, title, detail]) => h('button', {type: 'button', class: `cis-stat ${status.value === key ? 'cis-stat-active' : ''}`, onClick: () => {tab.value = 'review'; status.value = key;}}, [h('span', title), h('strong', key === 'ready' ? (data.value.report.rows || []).filter(r => r.ready).length : data.value.counts[key] || 0), h('small', detail)]))),
          h('div', {class: 'cis-context'}, [badge({preview: '定时仅预览', tag: '定时标记任务', remove: '定时移除任务 · 保留文件'}[data.value.config.action] || '仅预览'), h('span', `上次检测 ${date(data.value.report.at)}`), data.value.report.services?.map(s => h('span', `${s.name} ${s.count} 项`)), data.value.busy && badge('正在读取最新状态', 'warning')]),
          data.value.config_error && h('div', {class: 'cis-alert cis-alert-error', role: 'alert'}, data.value.config_error),
          (data.value.last_error?.at || 0) > (data.value.report.at || 0) && h('div', {class: 'cis-alert cis-alert-error', role: 'alert'}, data.value.last_error.message),
          data.value.report.warnings?.map(text => h('div', {class: 'cis-alert cis-alert-warning'}, text)),
          h('div', {class: 'cis-tabs', role: 'tablist', 'aria-label': '复核工作台'}, [['review', '检测结果'], ['history', '操作记录'], ['trash', `回收区 ${data.value.trash.length}`]].map(([key, label]) => h('button', {type: 'button', role: 'tab', 'aria-selected': tab.value === key, class: tab.value === key ? 'cis-tab-active' : '', onClick: () => {tab.value = key;}}, label))),
          tab.value === 'review' && section('检测结果', '未满足观察期的项目无法操作；结果超过 10 分钟后需重新检测。', review()),
          tab.value === 'history' && section('操作记录', '只有回读验证通过才标记成功；保留最近 200 条。', data.value.history.length ? data.value.history.map(item => h('article', {class: 'cis-history', key: `${item.id}-${item.status}`}, [h('div', [h('strong', item.name), h('p', `${ACTION[item.action] || item.action} · ${item.service} · ${date(item.at)}`), item.message && h('p', item.message)]), badge(RESULT[item.status], item.status === 'success' ? 'ready' : 'warning')])) : [h('div', {class: 'cis-empty'}, '尚无操作记录')]),
          tab.value === 'trash' && section('可恢复的源文件', '文件仍占用磁盘空间。恢复时保留原位置已有的同名内容。', data.value.trash.length ? data.value.trash.map(item => h('article', {class: 'cis-history', key: item.id}, [h('div', [h('strong', item.name), h('p', `${formatBytes(item.size)} · ${date(item.at)}`), h('code', {class: 'cis-path'}, item.path), item.status === 'intent' && h('p', '移动结果待核对，可尝试恢复；原文件和回收区内容均保留。')]), button('恢复原位', () => restore(item), {disabled: acting.value || data.value.busy})])) : [h('div', {class: 'cis-empty'}, '回收区为空')]),
        ] : h('div', {class: 'cis-empty'}, loading.value ? '正在读取…' : '点击刷新读取工作台'),
        dialog.value && h('div', {class: 'cis-modal-backdrop', onClick: e => {if (e.target === e.currentTarget && !acting.value) dialog.value = '';}}, [h('form', {class: 'cis-modal', role: 'dialog', 'aria-modal': true, 'aria-labelledby': 'cis-confirm-title', onSubmit: e => {e.preventDefault(); if (confirmation.value === ACTION[dialog.value] && !acting.value) execute();}}, [
          h('h3', {id: 'cis-confirm-title'}, ACTION[dialog.value]), h('p', `即将处理 ${selected.value.length} 项。执行前会重新读取下载器状态；状态改变的项目会跳过。`),
          h('p', dialog.value === 'remove' ? '仅移除下载器任务，保留下载文件。恢复做种需要重新添加种子。' : dialog.value === 'quarantine' ? '源文件移动到各源目录内的隐藏回收区，可从本页恢复；不会释放磁盘空间。' : '追加标记标签，保留原有标签与任务。'),
          h('ul', {class: 'cis-confirm-items'}, chosen.value.map(row => h('li', row.name))),
          h('label', {class: 'cis-field'}, [h('span', `请输入「${ACTION[dialog.value]}」确认`), h('input', {autofocus: true, value: confirmation.value, onInput: e => {confirmation.value = e.target.value;}, 'aria-label': '确认文字'})]),
          h('div', {class: 'cis-actions'}, [button('取消', () => {dialog.value = '';}, {disabled: acting.value}), button(acting.value ? '正在复核…' : '确认执行', execute, {danger: true, disabled: acting.value || confirmation.value !== ACTION[dialog.value]})])])]),
      ]);
    },
  });
}

export function createConfig(Vue) {
  const {defineComponent, h, reactive, ref, onMounted} = Vue;
  const {button, header, section, select} = elements(Vue);
  return defineComponent({name: 'CleanInvalidSeedConfig', props: {api: Object, pluginId: String, initialConfig: Object}, emits: ['layout', 'save', 'close'],
    setup(props, {emit}) {
      const initial = Object.fromEntries(Object.entries(props.initialConfig || {}).filter(([key, value]) => key in DEFAULTS && value !== null));
      const config = reactive({...DEFAULTS, ...initial, downloaders: [...(initial.downloaders || [])],
        label: String(initial.label || DEFAULTS.label),
        file_min_age_days: initial.file_min_age_days ?? Math.max(1, Number(initial.min_seeding_days ?? DEFAULTS.min_seeding_days))});
      const choices = ref([]), error = ref(''), advanced = ref(false), loading = ref(false);
      onMounted(async () => {emit('layout', {maxWidth: '860px'}); loading.value = true; try {const result = unwrap(await props.api.get(`plugin/${props.pluginId}/page_status`)); choices.value = result.downloaders || [];} catch {error.value = '下载器列表暂时无法读取，请关闭后重试。';} finally {loading.value = false;}});
      const toggle = (key, title, detail) => h('label', {class: 'cis-toggle'}, [h('div', [h('strong', title), h('p', detail)]), h('input', {type: 'checkbox', role: 'switch', 'aria-label': title, checked: config[key], onChange: e => {config[key] = e.target.checked;}})]);
      const field = (key, label, attrs = {}, hint = '') => h('label', {class: 'cis-field'}, [h('span', label), h('input', {...attrs, value: config[key], onInput: e => {config[key] = e.target.value;}}), hint && h('small', hint)]);
      const area = (key, label, hint = '', rows = 3) => h('label', {class: 'cis-field'}, [h('span', label), h('textarea', {rows, value: config[key], onInput: e => {config[key] = e.target.value;}}), hint && h('small', hint)]);
      const save = () => {error.value = validateConfig(config); if (error.value) return; const payload = {...config}; for (const key of ['confirmations', 'grace_hours', 'min_seeding_days', 'file_min_age_days', 'max_actions']) payload[key] = Number(payload[key]); emit('save', payload);};
      return () => h('form', {class: 'cis-root cis-config', onSubmit: e => {e.preventDefault(); save();}}, [
        header('做种复核设置', '先积累证据，再决定如何处理', [button('取消', () => emit('close'))]),
        section('运行方式', '页面上的「只读检测」始终只预览；以下模式仅用于定时任务。', [
          toggle('enabled', '启用定时复核', '按设定周期读取下载器，积累持续观察记录'),
          h('div', {class: 'cis-form-grid'}, [h('label', {class: 'cis-field'}, [h('span', '定时处理方式'), select('定时处理方式', config.action, [['preview', '只预览 · 推荐'], ['tag', '标记已确认的失效任务'], ['remove', '移除已确认的任务 · 保留文件']], value => {config.action = value;})]), field('cron', '运行周期', {placeholder: '0 3 * * *'}, '五段 Cron，使用 MP 时区；默认每天 03:00')]),
          config.action === 'remove' && h('div', {class: 'cis-alert cis-alert-warning'}, '定时任务将自动移除满足全部保护条件的失效任务，保留文件；恢复做种需要重新添加种子。'),
          toggle('notify', '发送结果通知', '发现候选或异常时通知，正常轮次保持安静'),
          config.notify && toggle('notify_all', '正常轮次也通知', '每次完成检测后发送一条摘要')]),
        section('检测范围', '种子任务只检测选中的下载器；源文件检测会额外核对所有已配置下载器。', [
          loading.value && h('p', '正在读取下载器…'), ...choices.value.map(choice => h('label', {class: 'cis-client'}, [h('input', {type: 'checkbox', checked: config.downloaders.includes(choice.name), disabled: !choice.enabled || !['qbittorrent', 'transmission'].includes(choice.type), onChange: e => {config.downloaders = e.target.checked ? [...config.downloaders, choice.name] : config.downloaders.filter(x => x !== choice.name);}}), h('strong', choice.name), h('span', `${choice.type}${choice.enabled ? '' : ' · 已停用'}`)])),
          ...config.downloaders.filter(name => !choices.value.some(c => c.name === name)).map(name => h('p', {class: 'cis-alert cis-alert-warning'}, `原下载器 ${name} 暂不可读取，请检查 MP 下载器设置。`))]),
        section('复核与保护', '所有 Tracker 都明确返回删种错误，且同站点存在成功做种，才进入持续观察。', [
          h('div', {class: 'cis-form-grid'}, [field('confirmations', '至少观察次数', {type: 'number', min: 2, max: 20}, '每次有效观察至少间隔 1 小时'), field('grace_hours', '持续观察时长（小时）', {type: 'number', min: 1, max: 720}), field('min_seeding_days', '最少累计做种（天）', {type: 'number', min: 0, max: 3650}, '使用下载器真实累计时长；未知时保留任务'), field('max_actions', '每批处理上限', {type: 'number', min: 1, max: 100})]),
          field('label', '失效标记标签'),
          h('div', {class: 'cis-form-grid'}, [area('exclude_categories', '排除分类', '每行一个；qBittorrent 分类'), area('exclude_labels', '排除标签', '每行一个；支持 qBittorrent 和 Transmission')]),
          area('exclude_keywords', '排除名称关键词', '每行一个，同时保护种子任务与源文件'),
          h('p', {class: 'cis-note'}, '暂停、下载未完成、排队、校验和本地数据异常的任务会自动保护。网络故障、账号禁用、认证失败不会判定为站点删种。')]),
        section('源文件复核', '定时任务仅检查源文件；移动操作始终由工作台手动确认。', [toggle('detect_invalid_files', '检测没有任务引用的源文件', '任一下载器不可核对、路径信息缺失或映射无法验证时，停止源文件检测'),
          config.detect_invalid_files && h('div', [area('download_dirs', '目录映射', '每行：MP目录:下载器目录1,下载器目录2。保留现有映射，不会自动创建下载目录。', 5),
            field('file_min_age_days', '源文件至少静置（天）', {type: 'number', min: 1, max: 3650}, '目录内有文件近期变化、软链接、挂载点或未完成下载时均跳过'),
            h('p', {class: 'cis-note'}, '确认后移入源目录内 .cleaninvalidseed-trash 回收区，可恢复。文件继续占用空间，插件不会永久删除。')])]),
        h('details', {open: advanced.value, class: 'cis-panel', onToggle: e => {advanced.value = e.target.open;}}, [h('summary', '高级匹配规则'), area('custom_error_msg', '自定义站点删种错误', '每行一条完整错误，忽略大小写与结尾标点；不接受网络、账号或权限类错误。')]),
        error.value && h('div', {class: 'cis-alert cis-alert-error', role: 'alert'}, error.value),
        h('div', {class: 'cis-config-footer'}, [h('span', '设置保存后，已有检测计划需要重新复核。'), button('保存设置', save, {primary: true, icon: 'check'})]),
      ]);
    },
  });
}
