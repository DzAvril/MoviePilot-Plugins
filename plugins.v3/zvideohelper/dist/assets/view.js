function unwrap(response) {
  return response?.data?.success !== undefined ? response.data : response;
}

export function createPage(Vue) {
  const {defineComponent, h, ref, computed, onMounted} = Vue;
  return defineComponent({
    name: 'ZvideoSubtitlePage', props: {api: Object, pluginId: String}, emits: ['layout', 'switch', 'close'],
    setup(props, {emit}) {
      const keyword = ref(''), imdb = ref(''), filter = ref(''), page = ref(1);
      const status = ref(null), result = ref(null), busy = ref(false), refreshing = ref(false), error = ref('');
      const endpoint = name => `plugin/${props.pluginId}/${name}`;
      const rows = computed(() => (result.value?.candidates || []).filter(item =>
        item.title.toLocaleLowerCase().includes(filter.value.trim().toLocaleLowerCase())));
      const pages = computed(() => Math.max(1, Math.ceil(rows.value.length / 12)));
      const visible = computed(() => rows.value.slice((Math.min(page.value, pages.value) - 1) * 12, Math.min(page.value, pages.value) * 12));
      const loadStatus = async () => {
        refreshing.value = true;
        try { status.value = unwrap(await props.api.get(endpoint('subtitle_status'))); }
        catch { error.value = '暂时无法读取授权状态，请稍后刷新'; }
        finally { refreshing.value = false; }
      };
      const search = async () => {
        if (busy.value) return;
        error.value = ''; result.value = null; page.value = 1; filter.value = '';
        if (!keyword.value.trim() && !imdb.value.trim()) { error.value = '请输入片名或 IMDb ID'; return; }
        busy.value = true;
        try {
          const response = unwrap(await props.api.get(endpoint('subtitle_search'), {
            params: {keyword: keyword.value.trim(), imdb_id: imdb.value.trim()}, timeout: 180000,
          }));
          if (!response?.success) throw new Error(response?.message || '字幕搜索失败，请稍后重试');
          result.value = response;
        } catch (caught) { error.value = caught.message || '字幕搜索失败，请稍后重试'; }
        finally { busy.value = false; }
      };
      onMounted(() => { emit('layout', {maxWidth: '1040px'}); loadStatus(); });
      const button = (text, action, disabled = false, primary = false) => h('button', {
        type: 'button', class: ['zvh-button', primary && 'zvh-primary'], onClick: action, disabled,
      }, text);
      return () => h('div', {class: 'zvh-root'}, [
        h('header', {class: 'zvh-header'}, [h('div', [h('p', {class: 'zvh-kicker'}, '极影视助手'),
          h('h2', '寻找合适的字幕'), h('p', {class: 'zvh-muted'}, '按影片搜索，查看字幕版本和格式。')]),
          button('插件设置', () => emit('switch'))]),
        h('div', {class: 'zvh-status', role: 'status'}, [
          h('span', {class: ['zvh-dot', status.value?.authorized && 'zvh-ready']}),
          h('span', status.value?.message || '正在读取 NAS 授权状态…'),
          status.value && !status.value.enabled && h('span', ' · 字幕搜索已关闭'),
          button(refreshing.value ? '刷新中…' : '刷新状态', loadStatus, refreshing.value || busy.value),
        ]),
        h('form', {class: 'zvh-panel zvh-search', onSubmit: event => {event.preventDefault(); search();}}, [
          h('label', {class: 'zvh-field zvh-keyword'}, [h('span', '片名或 IMDb ID'), h('input', {
            'aria-label': '片名或 IMDb ID', value: keyword.value, maxlength: 200, disabled: busy.value,
            placeholder: '如：肖申克的救赎 / tt0111161', onInput: event => {keyword.value = event.target.value;},
          })]),
          h('label', {class: 'zvh-field'}, [h('span', 'IMDb ID（可选）'), h('input', {
            'aria-label': 'IMDb ID（可选）', value: imdb.value, maxlength: 14, disabled: busy.value,
            placeholder: '优先使用 ID，空结果时回退片名', onInput: event => {imdb.value = event.target.value;},
          })]),
          h('button', {type: 'submit', class: 'zvh-button zvh-primary', disabled: busy.value || !status.value?.authorized || !status.value?.enabled}, busy.value ? '正在搜索…' : '搜索字幕'),
        ]),
        error.value && h('div', {class: 'zvh-notice zvh-error', role: 'alert'}, error.value),
        busy.value && h('div', {class: 'zvh-empty', role: 'status'}, '正在向 NAS 查询字幕，请稍候…'),
        result.value && h('section', {class: 'zvh-panel'}, [
          h('div', {class: 'zvh-results-heading'}, [h('h3', `找到 ${result.value.count} 个字幕版本`),
            h('input', {'aria-label': '筛选搜索结果', placeholder: '筛选字幕名称、语言或版本', value: filter.value,
              onInput: event => {filter.value = event.target.value; page.value = 1;}})]),
          rows.value.length ? h('div', {class: 'zvh-table-wrap'}, [h('table', {class: 'zvh-table'}, [
            h('thead', [h('tr', [h('th', '字幕版本'), h('th', '格式'), h('th', '大小')])]),
            h('tbody', visible.value.map(item => h('tr', {key: item.id}, [
              h('td', [h('strong', item.title), h('small', `${item.movie || '未标注影片'} · 字幕 ID ${item.subtitle_id}`)]),
              h('td', [h('span', {class: 'zvh-format'}, item.format)]), h('td', item.size || '未标注'),
            ]))),
          ])]) : h('div', {class: 'zvh-empty'}, result.value.count ? '没有符合筛选条件的字幕' : result.value.message),
          rows.value.length > 0 && h('footer', {class: 'zvh-pagination'}, [h('span', `${rows.value.length} 个结果${result.value.cached ? ' · 使用最近的搜索结果' : ''}`),
            h('div', [button('上一页', () => {page.value--;}, page.value <= 1),
              h('span', `${Math.min(page.value, pages.value)} / ${pages.value}`), button('下一页', () => {page.value++;}, page.value >= pages.value)])]),
        ]),
        h('p', {class: 'zvh-footnote'}, '当前提供字幕搜索和版本查看，下载及挂载功能尚未开放。豆瓣同步和评分管理继续在插件设置中使用。'),
      ]);
    },
  });
}

export function createConfig(Vue) {
  const {defineComponent, h, reactive, ref, onMounted} = Vue;
  return defineComponent({
    name: 'ZvideoHelperConfig', props: {initialConfig: Object}, emits: ['save', 'close', 'switch', 'layout'],
    setup(props, {emit}) {
      const config = reactive({enabled: false, subtitle_enabled: true, notify: false, onlyonce: false,
        sync_douban_status: false, use_douban_score: false, clean_cache: false, cron: '0 0 * * *',
        douban_score_update_days: 0, db_path: '', cookie: '', ...props.initialConfig});
      const error = ref('');
      onMounted(() => emit('layout', {maxWidth: '800px'}));
      const toggle = (key, text) => h('label', {class: 'zvh-toggle'}, [h('span', text), h('input', {
        type: 'checkbox', role: 'switch', 'aria-label': text, checked: !!config[key], onChange: event => {config[key] = event.target.checked;},
      })]);
      const field = (key, text, type = 'text') => h('label', {class: 'zvh-field'}, [h('span', text), h('input', {
        type, 'aria-label': text, value: config[key], onInput: event => {config[key] = event.target.value;},
      })]);
      const save = () => {
        const days = Number(config.douban_score_update_days || 0);
        if (!Number.isInteger(days) || days < 0) {error.value = '评分更新周期需为不小于 0 的整数'; return;}
        emit('save', {...config, douban_score_update_days: days});
      };
      return () => h('form', {class: 'zvh-root', onSubmit: event => {event.preventDefault(); save();}}, [
        h('header', {class: 'zvh-header'}, [h('div', [h('p', {class: 'zvh-kicker'}, '极影视助手'), h('h2', '插件设置')])]),
        h('section', {class: 'zvh-panel zvh-settings'}, [h('h3', '字幕搜索'), toggle('subtitle_enabled', '开启字幕搜索'),
          h('p', {class: 'zvh-muted'}, '使用 NAS 的极影视字幕服务，首次使用需完成 NAS 授权。')]),
        h('section', {class: 'zvh-panel zvh-settings'}, [h('h3', '观影状态与评分'),
          toggle('enabled', '启用定时任务'), toggle('notify', '开启通知'), toggle('onlyonce', '保存后立即运行一次'),
          toggle('sync_douban_status', '同步在看 / 已看至豆瓣'), toggle('use_douban_score', '使用豆瓣评分'),
          toggle('clean_cache', '清理豆瓣同步缓存'), field('cron', '执行周期'),
          field('douban_score_update_days', '豆瓣评分更新周期（天，0 表示不更新）', 'number'),
          field('db_path', '极影视数据库路径'), field('cookie', '豆瓣 Cookie（留空使用 CookieCloud）', 'password'),
          h('p', {class: 'zvh-muted'}, '评分功能会修改极影视数据库，沿用原插件设置；使用前请保留数据库备份。')]),
        error.value && h('p', {class: 'zvh-notice zvh-error', role: 'alert'}, error.value),
        h('div', {class: 'zvh-actions'}, [h('button', {type: 'button', class: 'zvh-button', onClick: () => emit('close')}, '取消'),
          h('button', {type: 'submit', class: 'zvh-button zvh-primary'}, '保存设置')]),
      ]);
    },
  });
}
