const STATUSES = {searching: '待搜索', downloading: '下载中', downloaded: '待入库', library: '已入库',
  pending: '待订阅', failed: '等待重试', transfer_failed: '整理失败', unknown: '状态待确认'};
const PATHS = {
  music: 'M9 18V5l12-2v13M9 8l12-2M9 18c0 1.7-1.8 3-4 3s-4-1.3-4-3 1.8-3 4-3 4 1.3 4 3Zm12-2c0 1.7-1.8 3-4 3s-4-1.3-4-3 1.8-3 4-3 4 1.3 4 3Z',
  refresh: 'M20 7v5h-5M4 17v-5h5M6.1 7a7 7 0 0 1 11.5-2L20 8M4 16l2.4 3A7 7 0 0 0 18 17',
  settings: 'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8ZM9 3h6l1 3 3 1 2 5-2 5-3 1-1 3H9l-1-3-3-1-2-5 2-5 3-1 1-3Z',
  search: 'M21 21l-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z',
  arrow: 'm9 5 7 7-7 7', check: 'm5 12 4 4L19 6', download: 'M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5',
  folder: 'M3 7V4h7l3 3h8v13H3V7Z', close: 'm6 6 12 12M6 18 18 6', play: 'm8 4 12 8-12 8V4Z',
};

export function filterSongs(songs, query = '', playlist = '', status = '') {
  const terms = query.normalize('NFKC').trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  return songs.filter(song => (!playlist || song.playlist_ids.includes(playlist)) &&
    (!status || (status === 'unresolved' ? song.status !== 'library' : song.status === status)) &&
    terms.every(term => [song.title, ...song.artists, song.album].join(' ').normalize('NFKC').toLocaleLowerCase().includes(term)));
}

export function paginate(songs, page, size = 10) {
  const pages = Math.max(1, Math.ceil(songs.length / size));
  const current = Math.max(1, Math.min(page, pages));
  return {rows: songs.slice((current - 1) * size, current * size), page: current, pages,
    start: songs.length ? (current - 1) * size + 1 : 0, end: Math.min(current * size, songs.length)};
}

export function applySongStates(data, response) {
  const songs = data.songs.map(song => ({...song, ...(response.song_states || {})[song.id]}));
  const counts = songs.reduce((result, song) => {result[song.status] = (result[song.status] || 0) + 1; return result;}, {});
  return {...data, songs, status_counts: counts, downloads: response.downloads ?? data.downloads,
    status_updated_at: response.status_updated_at, status_warning: response.status_warning || ''};
}

export function downloadStatus(item) {
  if (item.error) return {text: '需要检查', tone: 'warn'};
  if (item.live_error) return {text: '进度暂不可用', tone: 'muted'};
  const state = item.state || '';
  if (state === 'missing') return {text: '下载器中未找到', tone: 'muted'};
  if (['error', 'missingFiles', 'unknown'].includes(state)) return {text: '下载异常', tone: 'warn'};
  if (/checking/i.test(state)) return {text: '校验中', tone: 'purple'};
  if (item.progress >= 1 && item.progress !== null) return {text: '下载完成', tone: 'green'};
  if (/paused|stopped/i.test(state)) return {text: '已暂停', tone: 'muted'};
  if (/queued/i.test(state)) return {text: '等待下载', tone: 'muted'};
  if (/DL$|downloading|metaDL/i.test(state)) return {text: '下载中', tone: 'purple'};
  return {text: '已核对选曲', tone: 'muted'};
}

function unwrap(response) {
  if (response?.data?.success !== undefined) return response.data;
  return response;
}

function primitives(Vue) {
  const {h} = Vue;
  const icon = (name, extra = {}) => h('svg', {viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor',
    'stroke-width': 1.7, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true', ...extra},
    [h('path', {d: PATHS[name] || PATHS.music})]);
  const button = (label, onClick, options = {}) => h('button', {type: 'button', class: `qqm-btn ${options.primary ? 'qqm-btn-primary' : ''} ${options.iconOnly ? 'qqm-btn-icon' : ''}`,
    onClick, disabled: options.disabled, title: options.title || label, 'aria-label': options.title || label},
    [options.icon && icon(options.icon), !options.iconOnly && label]);
  const badge = (text, tone = 'muted') => h('span', {class: `qqm-badge qqm-${tone}`}, text);
  const time = value => value ? new Date(value * 1000).toLocaleString('zh-CN', {month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hour12: false}) : '等待首次同步';
  const title = (label, detail, action) => h('div', {class: 'qqm-section-heading'}, [h('div', [h('h3', label),
    detail && h('p', detail)]), action]);
  return {icon, button, badge, time, title};
}

export function createPage(Vue) {
  const {defineComponent, h, ref, computed, watch, onMounted, onBeforeUnmount} = Vue;
  const {icon, button, badge, time, title} = primitives(Vue);
  return defineComponent({
    name: 'QQMusicPage',
    props: {api: Object, pluginId: String},
    emits: ['layout', 'switch', 'close'],
    setup(props, {emit}) {
      const data = ref(null), loading = ref(false), refreshingDownloads = ref(false), syncing = ref(false);
      const error = ref(''), notice = ref(''), query = ref(''), playlist = ref(''), status = ref(''), page = ref(1);
      const allDownloads = ref(false);
      const library = ref(null);
      let refreshTimer, disposed = false, loadInFlight = false, lastMetadataAt = 0;
      const endpoint = path => `plugin/${props.pluginId}/${path}`;
      const songs = computed(() => filterSongs(data.value?.songs || [], query.value, playlist.value, status.value));
      const result = computed(() => paginate(songs.value, page.value));
      watch([query, playlist, status], () => {page.value = 1;});
      const refreshDownloads = async () => {
        refreshingDownloads.value = true;
        try {
          const response = unwrap(await props.api.get(endpoint('page_downloads')));
          if (response?.success && data.value && !disposed) data.value = applySongStates(data.value, response);
          else throw new Error('download unavailable');
        } catch {
          if (data.value && !disposed) data.value.status_warning = '状态自动更新暂时失败，正在显示上次确认结果';
        } finally {refreshingDownloads.value = false;}
      };
      const load = async (options = {}) => {
        if (loadInFlight || refreshingDownloads.value || disposed) return;
        loadInFlight = true;
        if (!options.background) loading.value = true;
        error.value = '';
        try {
          const response = unwrap(await props.api.get(endpoint('page_data')));
          if (!response?.success) throw new Error('page unavailable');
          if (disposed) return;
          data.value = response;
          lastMetadataAt = Date.now();
          await refreshDownloads();
        } catch {error.value = '暂时无法读取歌单数据，请重试。';}
        finally {loading.value = false; loadInFlight = false;}
      };
      const sync = async () => {
        if (syncing.value) return;
        syncing.value = true;
        notice.value = '';
        try {
          const response = unwrap(await props.api.post(endpoint('page_sync')));
          notice.value = response?.success ? `同步完成，新增 ${response.created || 0} 个订阅。` :
            response?.message || response?.last_error || '本轮同步未完成，请查看同步状态。';
          await load();
        } catch {notice.value = '同步请求未完成，请稍后刷新查看结果。';}
        finally {syncing.value = false;}
      };
      const selectStatus = value => {
        status.value = value; page.value = 1;
        library.value?.scrollIntoView({behavior: 'smooth', block: 'start'});
      };
      const clear = () => {query.value = ''; playlist.value = ''; status.value = ''; page.value = 1;};
      onMounted(() => {
        emit('layout', {maxWidth: '1140px'}); load();
        refreshTimer = setInterval(() => {
          if (document.hidden || loadInFlight || refreshingDownloads.value || syncing.value) return;
          if (Date.now() - lastMetadataAt >= 60000) load({background: true});
          else refreshDownloads();
        }, 15000);
      });
      onBeforeUnmount(() => {disposed = true; clearInterval(refreshTimer);});
      const header = () => h('header', {class: 'qqm-header'}, [
        h('div', {class: 'qqm-brand'}, [h('img', {class: 'qqm-logo qqm-logo-image', src: '/api/v1/plugin/file/QQMusicPlaylistSync/dist/assets/MusicPlaylistSync-1.7.1.png', alt: '音乐歌单同步图标', width: 54, height: 54}),
          h('div', [h('div', {class: 'qqm-eyebrow'}, 'MUSIC · PLAYLIST SYNC'), h('h2', '歌单同步'),
            h('p', '从喜欢的歌单，到自己的音乐库')])]),
        h('div', {class: 'qqm-actions'}, [button(loading.value ? '刷新中' : '刷新', load,
          {icon: 'refresh', disabled: loading.value || refreshingDownloads.value || syncing.value}),
          button(syncing.value ? '同步中…' : '立即同步', sync, {primary: true, icon: 'play', disabled: syncing.value || loading.value || refreshingDownloads.value}),
          button('插件设置', () => emit('switch'), {icon: 'settings', iconOnly: true}),
          button('关闭数据页面', () => emit('close'), {icon: 'close', iconOnly: true})]),
      ]);
      const downloadCard = item => {
        const state = downloadStatus(item);
        const progress = item.progress === null ? null : Math.round(item.progress * 1000) / 10;
        return h('article', {class: 'qqm-download-card', key: item.id}, [
          h('div', {class: 'qqm-task-top'}, [h('div', {class: 'qqm-task-icon'}, icon('download')),
            h('div', {class: 'qqm-task-name'}, [h('h4', item.title), h('p', item.artists.join(' / ') || '歌单歌曲')]), badge(state.text, state.tone)]),
          h('div', {class: 'qqm-progress-heading'}, [h('span', [h('strong', `${item.selected}`), ` / ${item.total || '?'} 首已选`]),
            h('span', progress === null ? (refreshingDownloads.value ? '正在读取进度…' : '暂无进度') : `${progress}%`)]),
          h('div', {class: 'qqm-progress', role: 'progressbar', 'aria-label': `${item.title}下载进度`,
            'aria-valuemin': 0, 'aria-valuemax': 100, 'aria-valuenow': progress ?? undefined},
            h('div', {style: {width: `${progress ?? 0}%`}})),
          item.error && h('p', {class: 'qqm-error-text'}, item.error),
          item.live_error && h('p', {class: 'qqm-muted qqm-small'}, item.live_error),
          h('details', {class: 'qqm-track-details'}, [h('summary', [`查看 ${item.selected} 首选曲`, icon('arrow')]),
            h('p', {class: 'qqm-resource'}, item.resource), h('ol', item.files.map(file => h('li', file)))])]);
      };
      const songTable = () => h('section', {class: 'qqm-panel qqm-library', ref: library}, [
        title('歌曲库', '按音轨进度和入库结果显示，每 15 秒自动更新。', badge(`${data.value.songs.length} 首去重歌曲`)),
        h('div', {class: 'qqm-filters'}, [
          h('label', {class: 'qqm-search'}, [icon('search'), h('input', {type: 'search', value: query.value,
            'aria-label': '搜索歌曲、歌手或专辑', placeholder: '搜索歌曲、歌手或专辑', onInput: e => {query.value = e.target.value;}})]),
          h('select', {'aria-label': '筛选歌单', value: playlist.value, onChange: e => {playlist.value = e.target.value;}},
            [h('option', {value: ''}, '全部歌单'), ...data.value.playlists.map(p => h('option', {value: p.id}, p.title))]),
          h('select', {'aria-label': '筛选状态', value: status.value, onChange: e => {status.value = e.target.value;}},
            [h('option', {value: ''}, '全部状态'), ...Object.entries(STATUSES).map(([value, label]) => h('option', {value}, label)),
              h('option', {value: 'unresolved'}, '全部未入库')]),
        ]),
        h('div', {class: 'qqm-table-wrap'}, h('table', {class: 'qqm-table'}, [
          h('thead', h('tr', [h('th', {class: 'qqm-number'}, '#'), h('th', '歌曲'), h('th', '歌手'), h('th', {class: 'qqm-album'}, '专辑'), h('th', '状态')])),
          h('tbody', result.value.rows.length ? result.value.rows.map((song, i) => h('tr', {key: song.id}, [
            h('td', {class: 'qqm-number'}, String(result.value.start + i).padStart(2, '0')),
            h('td', {class: 'qqm-song-title', title: song.title}, song.title), h('td', {title: song.artists.join(' / ')}, song.artists.join(' / ')),
            h('td', {class: 'qqm-album', title: song.album}, song.album || '—'),
            h('td', {class: 'qqm-song-state', title: song.status_message}, [
              badge(song.status_label || STATUSES[song.status] || song.status, song.status_tone || (song.status === 'library' ? 'green' : 'muted')),
              song.status === 'downloading' && typeof song.progress === 'number' && h('div', {class: 'qqm-song-progress'}, [
                h('span', {class: 'qqm-mini-progress', role: 'progressbar', 'aria-label': `${song.title}音轨下载进度`,
                  'aria-valuemin': 0, 'aria-valuemax': 100, 'aria-valuenow': Math.round(song.progress * 1000) / 10},
                  h('span', {style: {width: `${song.progress * 100}%`}})),
                h('span', `${Math.round(song.progress * 1000) / 10}%`)]),
            ]),
          ])) : h('tr', h('td', {colspan: 5}, h('div', {class: 'qqm-empty'}, [icon('search'), h('strong', '没有匹配的歌曲'),
            h('p', data.value.songs.length ? '试试其他关键词或调整筛选条件' : '添加歌单并完成首次同步后，歌曲会显示在这里'),
            data.value.songs.length > 0 && button('清除筛选', clear)])))),
        ])),
        h('div', {class: 'qqm-pagination'}, [h('span', `显示 ${result.value.start}–${result.value.end}，共 ${songs.value.length} 首`),
          h('div', [button('上一页', () => {page.value = result.value.page - 1;}, {disabled: result.value.page <= 1}),
            h('span', {class: 'qqm-page-count'}, `${result.value.page} / ${result.value.pages}`),
            button('下一页', () => {page.value = result.value.page + 1;}, {disabled: result.value.page >= result.value.pages})])]),
      ]);
      const settings = () => h('details', {class: 'qqm-panel qqm-fold'}, [
        h('summary', [h('span', [icon('folder'), '下载与同步设置']), icon('arrow')]),
        h('div', {class: 'qqm-setting-body'}, [
          ...[['downloader', '下载器'], ['save_path', '下载目录'], ['library_path', '音乐库目录']].map(([key, label]) =>
            h('div', {class: 'qqm-setting-row'}, [h('span', label), h('code', data.value.settings[key] || '未配置'),
              badge(data.value.settings.follow_mp?.[key] ? '跟随 MP' : '插件配置')])),
          data.value.settings.error && h('p', {class: 'qqm-error-text'}, data.value.settings.error),
          h('p', {class: 'qqm-rule'}, '保持单曲订阅 · 分轨专辑只下载歌单歌曲 · CUE 整轨跳过'),
        ])]);
      return () => h('main', {class: 'qqm-root'}, [header(),
        notice.value && h('div', {class: 'qqm-notice', role: 'status'}, [notice.value, button('关闭提示', () => {notice.value = '';}, {icon: 'close', iconOnly: true})]),
        error.value && h('div', {class: 'qqm-notice qqm-error', role: 'alert'}, [error.value, button('重试', load)]),
        !data.value ? h('div', {class: 'qqm-loading', 'aria-busy': loading.value}, [icon('music'), h('p', loading.value ? '正在读取你的歌单…' : '歌单数据暂不可用')]) : [
          h('div', {class: 'qqm-sync-line'}, [h('div', [badge(data.value.dry_run ? '预览模式' : data.value.enabled ? '持续同步中' : '已暂停同步', data.value.enabled ? 'green' : 'muted'),
            h('span', `${data.value.playlists.length} 个歌单 · 每 ${data.value.interval_minutes} 分钟检查`)]), h('span', `最近同步 ${time(data.value.overview.last_sync || data.value.overview.last_fetch)}`)]),
          (data.value.overview.last_error || data.value.adapter_error) && h('div', {class: 'qqm-notice qqm-error', role: 'alert'}, data.value.adapter_error || data.value.overview.last_error),
          data.value.status_warning && h('div', {class: 'qqm-notice qqm-error', role: 'status'}, data.value.status_warning),
          h('div', {class: 'qqm-stats'}, [
            ['歌单歌曲', data.value.overview.tracked, '跨歌单自动去重', '', 'music', 'purple'],
            ['待搜索', data.value.status_counts.searching, '等待匹配可用资源', 'searching', 'search', 'purple'],
            ['下载中', data.value.status_counts.downloading, '跟随歌曲音轨实际进度', 'downloading', 'download', 'purple'],
            ['已入库', data.value.status_counts.library, '已确认音乐库文件', 'library', 'folder', 'green'],
          ].map(([label, value, note, filter, glyph, tone]) => h('button', {type: 'button', class: `qqm-stat qqm-stat-${tone}`, onClick: () => selectStatus(filter)}, [
            h('div', {class: 'qqm-stat-top'}, [h('span', label), icon(glyph)]), h('strong', value || 0), h('p', note)]))),
          h('div', {class: 'qqm-stage-line'}, [h('div', Object.entries(STATUSES).filter(([key]) =>
            !['searching', 'downloading', 'library'].includes(key) && data.value.status_counts[key]).map(([key, label]) =>
            h('button', {type: 'button', onClick: () => selectStatus(key)}, `${label} ${data.value.status_counts[key]}`))),
            h('time', {'aria-label': '歌曲状态更新时间'}, data.value.status_updated_at ?
              `状态更新于 ${new Date(data.value.status_updated_at * 1000).toLocaleTimeString('zh-CN', {hour12: false})}` : '正在核对下载与入库状态…')]),
          h('section', {class: 'qqm-playlists-section'}, [title('订阅歌单', '歌单新增歌曲会自动加入单曲订阅。',
            data.value.unavailable ? badge(`${data.value.unavailable} 项暂不可读`, 'warn') : null),
            h('div', {class: 'qqm-playlists'}, data.value.playlists.length ? data.value.playlists.map((p, i) =>
              h('article', {class: 'qqm-playlist', key: p.id}, [h('div', {class: `qqm-cover qqm-cover-${i % 3}`}, icon('music')),
                h('div', {class: 'qqm-playlist-info'}, [h('h4', p.title), h('p', `${p.source === 'netease' ? '网易云' : 'QQ 音乐'} · ${p.total || 0} 首歌曲`),
                  p.last_error ? h('p', {class: 'qqm-error-text'}, '读取失败，保留上次结果') : h('span', {class: 'qqm-playlist-status'}, [icon('check'), p.last_fetch ? '同步正常' : '等待同步'])]),
                button('查看歌曲', () => {playlist.value = p.id; selectStatus('');}, {icon: 'arrow', iconOnly: true})])) :
              [h('div', {class: 'qqm-empty qqm-panel'}, [h('p', '还没有添加歌单'), button('添加音乐歌单', () => emit('switch'), {primary: true})])])]),
          h('section', [title('最近选曲下载', '只下载歌单需要的音轨，保留原生整理流程。', data.value.downloads.length > 2 ?
            button(allDownloads.value ? '收起任务' : `查看全部 ${data.value.downloads.length} 个任务`, () => {allDownloads.value = !allDownloads.value;}) : null),
            h('div', {class: 'qqm-downloads', 'aria-busy': refreshingDownloads.value}, data.value.downloads.length ?
              (allDownloads.value ? data.value.downloads : data.value.downloads.slice(0, 2)).map(downloadCard) :
              [h('div', {class: 'qqm-panel qqm-quiet-empty'}, [icon('download'), h('div', [h('strong', '等待匹配可用资源'), h('p', '匹配到可选曲的资源后，下载任务会显示在这里。')])])])]),
          songTable(), settings(),
          h('details', {class: 'qqm-panel qqm-fold'}, [h('summary', [h('span', '最近资源检查'), badge(`${data.value.checks.length} 条`), icon('arrow')]),
            h('div', {class: 'qqm-checks'}, data.value.checks.length ? data.value.checks.map(check => h('article', [
              badge(check.allowed ? '可选曲' : '已跳过', check.allowed ? 'green' : 'muted'),
              h('div', [h('strong', check.title), h('p', check.reason)]), h('time', time(check.at)),
            ])) : h('p', {class: 'qqm-muted'}, '暂无检查记录'))]),
          h('footer', {class: 'qqm-footer'}, [h('span', '音乐歌单同步'), h('span', 'v1.7.1')]),
        ],
      ]);
    },
  });
}

export function createConfig(Vue) {
  const {defineComponent, h, reactive, ref, onMounted} = Vue;
  const {icon, button, title} = primitives(Vue);
  return defineComponent({
    name: 'QQMusicConfig', props: {initialConfig: Object}, emits: ['save', 'close', 'switch', 'layout'],
    setup(props, {emit}) {
      const config = reactive({enabled: false, dry_run: true, playlist_urls: '', netease_playlist_urls: '', interval: 1, subscribe_workers: 4,
        immediate_search: true, downloader: '', save_path: '', library_path: '', ...props.initialConfig});
      const error = ref('');
      onMounted(() => emit('layout', {maxWidth: '800px'}));
      const toggle = (key, label, detail) => h('label', {class: 'qqm-toggle-row'}, [h('div', [h('strong', label), h('p', detail)]),
        h('input', {type: 'checkbox', role: 'switch', 'aria-label': label, checked: config[key], onChange: e => {config[key] = e.target.checked;}})]);
      const field = (key, label, attrs = {}) => h('label', {class: 'qqm-field'}, [h('span', label), h('input', {value: config[key],
        ...attrs, onInput: e => {config[key] = e.target.value;}})]);
      const save = () => {
        const interval = Number(config.interval), workers = Number(config.subscribe_workers);
        if (!Number.isInteger(interval) || interval < 1 || interval > 1440 || !Number.isInteger(workers) || workers < 1 || workers > 8) {
          error.value = '同步间隔需为 1–1440 分钟，同时创建订阅数需为 1–8 的整数。'; return;
        }
        emit('save', {...config, interval, subscribe_workers: workers});
      };
      return () => h('form', {class: 'qqm-root qqm-config', onSubmit: e => {e.preventDefault(); save();}}, [
        h('header', {class: 'qqm-header'}, [h('div', {class: 'qqm-brand'}, [h('img', {class: 'qqm-logo qqm-logo-image', src: '/api/v1/plugin/file/QQMusicPlaylistSync/dist/assets/MusicPlaylistSync-1.7.1.png', alt: '音乐歌单同步图标', width: 54, height: 54}),
          h('div', [h('div', {class: 'qqm-eyebrow'}, 'MUSIC · SETTINGS'), h('h2', '歌单同步设置'), h('p', '把 QQ 与网易云歌单持续收进音乐库')])])]),
        h('section', {class: 'qqm-panel qqm-config-section'}, [toggle('enabled', '启用持续同步', '按设定间隔检查所有歌单'),
          toggle('dry_run', '只预览歌单', '开启后读取歌单，不创建新订阅')]),
        h('section', {class: 'qqm-panel qqm-config-section'}, [title('订阅歌单', '每行一个歌单链接或 ID，公开歌单无需登录。'),
          h('label', {class: 'qqm-field'}, [h('span', 'QQ 音乐'),
          h('textarea', {'aria-label': 'QQ音乐歌单链接或ID', rows: 4, value: config.playlist_urls, placeholder: '9060297214\nhttps://c6.y.qq.com/base/fcgi-bin/u?__=…',
            onInput: e => {config.playlist_urls = e.target.value;}})]),
          h('label', {class: 'qqm-field'}, [h('span', '网易云音乐'),
            h('textarea', {'aria-label': '网易云歌单链接或ID', rows: 3, value: config.netease_playlist_urls,
              placeholder: '80068278\nhttps://music.163.com/#/playlist?id=…',
              onInput: e => {config.netease_playlist_urls = e.target.value;}})]),
          h('div', {class: 'qqm-form-grid'}, [field('interval', '同步间隔（分钟）', {type: 'number', min: 1, max: 1440}),
            field('subscribe_workers', '同时创建订阅数', {type: 'number', min: 1, max: 8})]),
          toggle('immediate_search', '建好订阅立即搜索下载', '发现新歌曲后进入 MP 手动搜索队列')]),
        h('section', {class: 'qqm-panel qqm-config-section'}, [title('下载与音乐目录', '以下三项可留空，使用 MP 设置中的默认值。'),
          field('downloader', '下载器', {placeholder: '跟随 MP 默认下载器'}),
          field('save_path', '下载目录', {placeholder: '跟随 MP 音乐下载目录'}),
          field('library_path', '音乐库目录', {placeholder: '跟随 MP 音乐库目录'}),
          h('p', {class: 'qqm-rule'}, '分轨选曲需要 qBittorrent；歌曲整理继续使用 MP 的目录设置。')]),
        error.value && h('p', {class: 'qqm-error-text', role: 'alert'}, error.value),
        h('div', {class: 'qqm-config-actions'}, [button('取消', () => emit('close')), button('保存设置', save, {primary: true, icon: 'check'})]),
      ]);
    },
  });
}
