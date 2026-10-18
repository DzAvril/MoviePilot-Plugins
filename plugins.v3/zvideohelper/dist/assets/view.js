function unwrap(response) {
  return response?.data?.success !== undefined ? response.data : response;
}

export function createPage(Vue) {
  const {defineComponent, h, ref, computed, onMounted, onUnmounted} = Vue;
  return defineComponent({
    name: 'ZvideoSubtitlePage', props: {api: Object, pluginId: String}, emits: ['layout', 'switch', 'close'],
    setup(props, {emit}) {
      const scanKeyword = ref('');
      const keyword = ref(''), mediaType = ref('all'), choices = ref(null), selectedMedia = ref(null), choicePage = ref(1), filter = ref(''), page = ref(1);
      const series = ref(null), seasonNo = ref(''), episodeNo = ref(''), busyMessage = ref('');
      const status = ref(null), result = ref(null), busy = ref(false), error = ref(''), message = ref('');
      const library = ref(null), auth = ref(null), code = ref(''), files = ref(null), selectedFile = ref(''), destination = ref('');
      const toolFile = ref(null);
      const working = ref(false), listFilter = ref('missing');
      let timer = null, polling = false, disposed = false;
      const endpoint = name => `plugin/${props.pluginId}/${name}`;
      const get = async (name, options) => unwrap(await props.api.get(endpoint(name), options));
      const post = async (name, payload = {}) => {
        const response = unwrap(await props.api.post(endpoint(name), payload, {timeout:180000}));
        if (!response?.success) throw new Error(response?.message || '操作失败，请稍后重试');
        return response;
      };
      const rows = computed(() => (result.value?.candidates || []).filter(item => item.title.toLowerCase().includes(filter.value.trim().toLowerCase())));
      const pages = computed(() => Math.max(1, Math.ceil(rows.value.length / 10)));
      const visible = computed(() => rows.value.slice((Math.min(page.value,pages.value)-1)*10, Math.min(page.value,pages.value)*10));
      const choicePages = computed(() => Math.max(1,Math.ceil((choices.value?.items.length || 0)/8)));
      const visibleChoices = computed(() => (choices.value?.items || []).slice((choicePage.value-1)*8,choicePage.value*8));
      const media = computed(() => (library.value?.items || []).filter(i => listFilter.value === 'all' || i.state === listFilter.value));
      const loadStatus = async () => {
        try {status.value = await get('subtitle_status');library.value = await get('subtitle_library');}
        catch {error.value = '无法读取插件状态，请稍后刷新';}
      };
      const act = async fn => {
        if (working.value) return;
        working.value = true;error.value = '';message.value = '';
        try {await fn();} catch (caught) {error.value = caught.message || '操作失败，请稍后重试';}
        finally {working.value = false;}
      };
      const resetManual = () => {
        choices.value = null;selectedMedia.value = null;result.value = null;files.value = null;
        series.value = null;seasonNo.value = '';episodeNo.value = '';
        destination.value = '';page.value = 1;choicePage.value = 1;filter.value = '';error.value = '';message.value = '';
      };
      const findMedia = async () => {
        if (busy.value || working.value) return;
        resetManual();
        if (!keyword.value.trim()) {error.value = '请输入影视名称';return;}
        busy.value = true;
        try {
          const response = await get('subtitle_media_search',{params:{keyword:keyword.value.trim(),media_type:mediaType.value},timeout:90000});
          if (!response?.success) throw new Error(response?.message || '影视查询失败');choices.value = response;
        } catch (caught) {error.value = caught.message || '影视查询失败';}
        finally {busy.value = false;}
      };
      const clearEpisodeResults = () => {result.value = null;files.value = null;destination.value = '';page.value = 1;filter.value = '';error.value = '';message.value = '';};
      const loadSeason = async (number, preferredEpisode = '') => {
        const response = await get('subtitle_series',{params:{tmdb_id:selectedMedia.value.id,season:Number(number)},timeout:90000});
        if (!response?.success) throw new Error(response?.message || '无法读取本季集列表');
        series.value = response;seasonNo.value = String(number);
        episodeNo.value = response.episodes.some(ep=>String(ep.number)===String(preferredEpisode)) ? String(preferredEpisode) : '';
      };
      const fetchSelectedSubtitle = async () => {
        const payload = {tmdb_id:selectedMedia.value.id,media_type:selectedMedia.value.media_type};
        if (payload.media_type==='tv') {payload.season = Number(seasonNo.value);payload.episode = Number(episodeNo.value);}
        busyMessage.value = payload.media_type==='tv' ? '正在核对本集字幕及字幕包，请稍候…' : '正在查找字幕…';
        const response = await post('subtitle_selected',payload);
        selectedMedia.value = response.selected_media || selectedMedia.value;result.value = response;
      };
      const chooseMedia = async (item, targetId = '', scope = null) => {
        if (busy.value || working.value) return;
        clearEpisodeResults();series.value = null;seasonNo.value = '';episodeNo.value = '';
        selectedMedia.value = item;busy.value = true;busyMessage.value = item.media_type==='tv' ? '正在读取季集信息…' : '正在查找字幕…';
        try {
          if (item.media_type==='tv') {
            const catalog = await get('subtitle_series',{params:{tmdb_id:item.id},timeout:90000});
            if (!catalog?.success) throw new Error(catalog?.message || '无法读取季集信息');
            selectedMedia.value = catalog.selected_media || item;
            const first = catalog.seasons.find(s=>s.number===scope?.season) || catalog.seasons.find(s=>s.number>0 && s.episode_count>0) || catalog.seasons.find(s=>s.number>0) || catalog.seasons[0];
            await loadSeason(first.number,scope?.episode);
            if (scope && episodeNo.value) {await fetchSelectedSubtitle();destination.value = targetId;}
          } else {await fetchSelectedSubtitle();destination.value = targetId;}
        } catch (caught) {error.value = caught.message || '字幕搜索失败';}
        finally {busy.value = false;busyMessage.value = '';}
      };
      const changeSeason = async value => {
        if (busy.value || working.value) return;
        clearEpisodeResults();seasonNo.value = value;episodeNo.value = '';busy.value = true;busyMessage.value = '正在读取本季集列表…';
        try {await loadSeason(value);} catch (caught) {series.value = {...series.value,episodes:[]};error.value = caught.message || '季集查询失败';}
        finally {busy.value = false;busyMessage.value = '';}
      };
      const searchEpisode = async () => {
        if (busy.value || working.value) return;
        if (!episodeNo.value) {error.value = '请先选择一集';return;}
        clearEpisodeResults();busy.value = true;
        try {await fetchSelectedSubtitle();} catch (caught) {error.value = caught.message || '本集字幕搜索失败';}
        finally {busy.value = false;busyMessage.value = '';}
      };
      const backToChoices = () => {const previous = choices.value;resetManual();if (previous) choices.value = previous;else findMedia();};
      const searchFromLibrary = item => {
        keyword.value = item.title;mediaType.value = item.season != null ? 'tv' : 'movie';
        if (item.tmdb_id) {
          choices.value = null;
          chooseMedia({id:String(item.tmdb_id),title:item.title,year:item.year,media_type:mediaType.value},item.id,
            item.season != null && item.episode != null ? {season:item.season,episode:item.episode} : null);
        } else findMedia();
      };
      const uploadTool = () => act(async () => {
        if (!toolFile.value) return;
        const form = new FormData();form.append('file',toolFile.value);
        const response = unwrap(await props.api.post(endpoint('subtitle_tool_install'),form));
        if (!response?.success) throw new Error(response?.message || '导入失败');
        message.value = response.message;await loadStatus();
      });
      const startAuth = () => act(async () => {auth.value = await post('subtitle_auth_start');});
      const submitAuth = () => act(async () => {
        const value = code.value;code.value = '';
        const response = await post('subtitle_auth_submit', {session:auth.value.session,code:value});
        auth.value = {...auth.value,...response};
      });
      const scan = download => act(async () => {message.value = (await post('subtitle_scan',{download,keyword:scanKeyword.value.trim()})).message;library.value = await get('subtitle_library');});
      const preview = item => act(async () => {
        files.value = await post('subtitle_preview',{id:item.id});files.value.title = item.title;
        selectedFile.value = files.value.files[0]?.id || '';
      });
      const download = () => act(async () => {
        const response = await post('subtitle_download',{file_id:selectedFile.value,media_id:destination.value});
        if (response.ticket) {
          const raw = await props.api.get(endpoint('subtitle_file'),{params:{ticket:response.ticket},responseType:'blob'});
          const blob = raw instanceof Blob ? raw : raw.data;
          if (!(blob instanceof Blob)) throw new Error('无法读取下载文件，请刷新页面后重试');
          const url = URL.createObjectURL(blob), link = document.createElement('a');link.href = url;link.download = response.name;
          link.click();setTimeout(() => URL.revokeObjectURL(url),30000);message.value = '字幕已交给浏览器，保存到当前设备';
        } else {message.value = response.message;library.value = await get('subtitle_library');}
      });
      const poll = async () => {
        if (polling || disposed) return;polling = true;
        try {
          if (auth.value && ['starting','waiting','verifying'].includes(auth.value.state)) {
            const next = await get('subtitle_auth_state');auth.value = next;
            if (next.state === 'complete') {code.value = '';await loadStatus();}
          }
          if (library.value?.running) library.value = await get('subtitle_library');
        } catch { /* A later poll recovers a transient connection failure. */ }
        finally {polling = false;}
      };
      onMounted(() => {emit('layout',{maxWidth:'1120px'});loadStatus();timer = setInterval(poll,2000);});
      onUnmounted(() => {disposed = true;clearInterval(timer);code.value = '';});
      const button = (text, action, disabled=false, primary=false) => h('button',{type:'button',class:['zvh-button',primary && 'zvh-primary'],onClick:action,disabled},text);
      const stateText = value => ({present:'已有中文',missing:'未发现中文',unknown:'待确认',excluded:'中文原声，已跳过'}[value] || value);
      return () => h('div',{class:'zvh-root'},[
        h('header',{class:'zvh-header'},[h('div',[h('p',{class:'zvh-kicker'},'极影视助手'),h('h2','中文字幕补全'),h('p',{class:'zvh-muted'},'定时检查入库媒体，保留手动搜索和下载。')]),button('插件设置',()=>emit('switch'))]),
        h('div',{class:'zvh-status',role:'status'},[h('span',{class:['zvh-dot',status.value?.authorized && 'zvh-ready']}),h('span',status.value?.message || '读取授权状态…'),
          button('刷新状态',loadStatus,working.value),button(status.value?.authorized?'重新授权':'网页授权',startAuth,working.value || busy.value || library.value?.running)]),
        status.value && !status.value.installed && h('section',{class:'zvh-panel zvh-settings'},[
          h('h3','首次初始化'),h('p','从自己的 zspace-nas-agent-toolkit v0.1.4 工具包中选择 Linux 授权程序（x64 / arm64 对应 NAS 架构），导入后即可网页授权，无需终端。'),
          h('input',{type:'file','aria-label':'Linux 授权程序',onChange:e=>{toolFile.value=e.target.files?.[0] || null;}}),
          button('导入授权工具',uploadTool,working.value || !toolFile.value)]),
        auth.value && h('section',{class:'zvh-panel zvh-settings'},[h('h3','极空间网页授权'),h('p',{role:'status'},auth.value.message),
          auth.value.state === 'waiting' && [h('a',{href:auth.value.url,target:'_blank',rel:'noopener noreferrer',class:'zvh-button zvh-primary'},'打开极空间授权网页'),
            h('label',{class:'zvh-field'},[h('span','一次性授权码'),h('input',{'aria-label':'一次性授权码',type:'password',autocomplete:'one-time-code',value:code.value,onInput:e=>{code.value=e.target.value;}})]),
            button('完成授权',submitAuth,working.value || !code.value.trim())],
          ['failed','expired'].includes(auth.value.state) && button('重新开始',startAuth,working.value)]),
        error.value && h('div',{class:'zvh-notice zvh-error',role:'alert'},error.value),message.value && h('div',{class:'zvh-notice',role:'status'},message.value),
        h('section',{class:'zvh-panel zvh-settings'},[h('div',{class:'zvh-results-heading'},[h('h3','本地影视库检查'),h('div',{class:'zvh-actions'},[
          button('立即检查',()=>scan(false),working.value || library.value?.running || !status.value?.enabled),
          button('立即补全',()=>scan(true),working.value || busy.value || library.value?.running || !status.value?.authorized || !status.value?.enabled,true)])]),
          h('label',{class:'zvh-field'},[h('span','本次检查的媒体名称（可选，定时任务仍检查全部）'),h('input',{'aria-label':'本次检查的媒体名称',value:scanKeyword.value,maxlength:200,placeholder:'留空检查全部；也可填写一个片名',onInput:e=>{scanKeyword.value=e.target.value;}})]),
          h('p',{class:'zvh-muted'},`定时补全${library.value?.auto_enabled?'已开启':'未开启'} · ${library.value?.cron || '*/30 * * * *'} · 每轮分批检查，最多尝试 5 个媒体`),
          h('p',`已有中文 ${library.value?.counts?.present || 0} · 未发现中文 ${library.value?.counts?.missing || 0} · 待确认 ${library.value?.counts?.unknown || 0} · 中文原声跳过 ${library.value?.counts?.excluded || 0}`),
          h('p',{role:'status'},library.value?.running ? `正在${library.value.mode || '检查'}：已检查 ${library.value.checked}，已下载 ${library.value.downloaded}` : library.value?.last_message || '点击“立即检查”建立媒体列表，或在设置中开启定时补全。'),
          h('p',{class:'zvh-muted'},'根据 TMDB 原始语言跳过中文原声作品。仅检查 MoviePilot 本地影视入库目录；语言不明、STRM 和原盘跳过；不识别画面烧录字幕，不覆盖已有字幕。'),
          h('label',{class:'zvh-field'},[h('span','检查结果'),h('select',{'aria-label':'检查结果',value:listFilter.value,onChange:e=>{listFilter.value=e.target.value;}},[
            ...['missing','unknown','present','excluded','all'].map(v=>h('option',{value:v},v==='all'?'全部':stateText(v)))])]),
          media.value.length ? h('div',{class:'zvh-library-list'},media.value.slice(0,60).map(item=>h('div',{class:'zvh-library-item',key:item.id},[
            h('strong',`${item.title} · ${stateText(item.state)}`),h('small',item.path),h('span',item.reason),button('为此媒体搜索',()=>searchFromLibrary(item),busy.value || working.value)]))) : h('p',{class:'zvh-muted'},'当前列表没有此类媒体。')]),
        h('form',{class:'zvh-panel zvh-settings',onSubmit:e=>{e.preventDefault();findMedia();}},[
          h('h3','手动查找字幕'),h('p',{class:'zvh-muted'},'先按名称查找电影或剧集，核对年份并选择作品，再搜索它的字幕。'),
          h('div',{class:'zvh-search'},[
            h('label',{class:'zvh-field zvh-keyword'},[h('span','影视名称'),h('input',{'aria-label':'影视名称',value:keyword.value,maxlength:200,disabled:busy.value || working.value,placeholder:'如：异形 / 肖申克的救赎',onInput:e=>{keyword.value=e.target.value;resetManual();}})]),
            h('label',{class:'zvh-field'},[h('span','影视类型'),h('select',{'aria-label':'影视类型',value:mediaType.value,disabled:busy.value || working.value,onChange:e=>{mediaType.value=e.target.value;resetManual();}},[
              h('option',{value:'all'},'电影和剧集'),h('option',{value:'movie'},'电影'),h('option',{value:'tv'},'剧集')])]),
            h('button',{type:'submit',class:'zvh-button zvh-primary',disabled:busy.value || working.value || !status.value?.enabled},busy.value && !selectedMedia.value?'正在查找…':'查找影视')])]),
        choices.value && !selectedMedia.value && h('section',{class:'zvh-panel zvh-settings'},[
          h('h3',`找到 ${choices.value.count} 部候选作品`),h('p',{class:'zvh-muted'},'请选择你要找字幕的那一部；同名作品可根据年份、类型和简介区分。'),
          h('div',{class:'zvh-media-choices'},visibleChoices.value.map(item=>h('article',{key:item.media_type+item.id,class:['zvh-media-choice',selectedMedia.value?.id===item.id && selectedMedia.value?.media_type===item.media_type && 'zvh-selected']},[
            h('h4',item.title),h('p',{class:'zvh-muted'},`${item.media_type==='movie'?'电影':'剧集'} · ${item.year || '年份未知'}`),
            item.original_title && item.original_title!==item.title && h('small',item.original_title),
            item.overview && h('p',{class:'zvh-overview'},item.overview),
            h('button',{type:'button',class:'zvh-button zvh-primary','aria-label':`为《${item.title}》（${item.year || '年份未知'}·${item.media_type==='movie'?'电影':'剧集'}）${item.media_type==='tv'?'选择季集':'查找字幕'}`,onClick:()=>chooseMedia(item),disabled:busy.value || working.value || !status.value?.authorized},item.media_type==='tv'?'选择季集':'查找字幕')]))),
          !choices.value.count && h('p',choices.value.message),
          choicePages.value>1 && h('footer',{class:'zvh-pagination'},[h('span',`${choices.value.count} 部作品`),h('div',[
            button('上一页作品',()=>{choicePage.value--;},choicePage.value<=1),h('span',`${choicePage.value} / ${choicePages.value}`),button('下一页作品',()=>{choicePage.value++;},choicePage.value>=choicePages.value)])])]),
        selectedMedia.value && h('div',{class:'zvh-notice zvh-selected-work',role:'status'},[
          h('span',`已选择：${selectedMedia.value.title}（${selectedMedia.value.year || '年份未知'} · ${selectedMedia.value.media_type==='movie'?'电影':'剧集'}）`),
          button('重新选片',backToChoices,busy.value || working.value),
          h('p',busy.value ? busyMessage.value : selectedMedia.value.media_type==='tv' ? (result.value ? `仅显示第 ${seasonNo.value} 季第 ${episodeNo.value} 集的字幕` : '请选择季和集，再查找本集字幕') : '仅显示这部作品的字幕')]),
        selectedMedia.value?.media_type==='tv' && series.value && h('section',{class:'zvh-panel zvh-search'},[
          h('label',{class:'zvh-field'},[h('span','季'),h('select',{'aria-label':'季',value:seasonNo.value,disabled:busy.value || working.value,onChange:e=>changeSeason(e.target.value)},
            series.value.seasons.map(s=>h('option',{value:String(s.number)},`${s.number===0?'特别篇':`第 ${s.number} 季`} · ${s.name}`)))]),
          h('label',{class:'zvh-field zvh-keyword'},[h('span','集'),h('select',{'aria-label':'集',value:episodeNo.value,disabled:busy.value || working.value,onChange:e=>{episodeNo.value=e.target.value;clearEpisodeResults();}},[
            h('option',{value:''},'请选择一集'),...series.value.episodes.map(ep=>h('option',{value:String(ep.number)},`第 ${ep.number} 集 · ${ep.name}`))])]),
          button(busy.value?'正在查询…':'查找本集字幕',searchEpisode,busy.value || working.value || !episodeNo.value || !status.value?.authorized,true)]),
        result.value && h('section',{class:'zvh-panel'},[
          h('div',{class:'zvh-results-heading'},[h('h3',`找到 ${result.value.count} 个字幕版本`),h('input',{'aria-label':'筛选搜索结果',placeholder:'筛选名称、语言、版本',value:filter.value,onInput:e=>{filter.value=e.target.value;page.value=1;}})]),
          h('div',{class:'zvh-table-wrap'},[h('table',{class:'zvh-table'},[h('thead',[h('tr',[h('th','字幕版本'),h('th','格式'),h('th','操作')])]),h('tbody',visible.value.map(item=>h('tr',{key:item.id},[
            h('td',[h('strong',item.title),h('small',item.archive_title || item.movie)]),h('td',item.format),h('td',button('选择 / 下载',()=>preview(item),working.value || busy.value || !item.download_available))])) )])]),
          result.value.archive_warning && h('p',{class:'zvh-muted'},result.value.archive_warning),
          !rows.value.length && h('p',result.value.message || '没有符合筛选条件的字幕'),
          h('footer',{class:'zvh-pagination'},[h('span',`${rows.value.length} 个结果`),h('div',[button('上一页',()=>{page.value--;},page.value<=1),h('span',`${Math.min(page.value,pages.value)} / ${pages.value}`),button('下一页',()=>{page.value++;},page.value>=pages.value)])])]),
        files.value && h('section',{class:'zvh-panel zvh-settings'},[h('h3','选择字幕文件'),h('p',files.value.title),
          h('label',{class:'zvh-field'},[h('span','字幕文件'),h('select',{'aria-label':'字幕文件',value:selectedFile.value,onChange:e=>{selectedFile.value=e.target.value;}},files.value.files.map(f=>h('option',{value:f.id},f.title)))]),
          h('label',{class:'zvh-field'},[h('span','保存位置'),h('select',{'aria-label':'保存位置',value:destination.value,onChange:e=>{destination.value=e.target.value;}},[
            h('option',{value:''},'下载到当前设备（手机 / 电脑）'),...(library.value?.items || []).map(i=>h('option',{value:i.id},'保存到 NAS：'+i.path))])]),
          files.value.message && h('p',files.value.message),button(working.value?'处理中…':destination.value?'保存到 NAS 媒体目录':'下载到当前设备',download,working.value || busy.value || !selectedFile.value,true)]),
        h('p',{class:'zvh-footnote'},'字幕时间轴可能因发行版本不同而有偏差；自动匹配会校验影片身份与剧集季集。豆瓣同步和评分在插件设置中使用。'),
      ]);
    },
  });
}

export function createConfig(Vue) {
  const {defineComponent, h, reactive, ref, onMounted} = Vue;
  return defineComponent({
    name: 'ZvideoHelperConfig', props: {initialConfig: Object}, emits: ['save', 'close', 'switch', 'layout'],
    setup(props, {emit}) {
      const config = reactive({enabled: false, subtitle_enabled: true, subtitle_auto: false, subtitle_cron: '*/30 * * * *', subtitle_batch: 25, subtitle_nas_cache: '', notify: false, onlyonce: false,
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
        const batch = Number(config.subtitle_batch);
        if (!Number.isInteger(batch) || batch < 1 || batch > 100) {error.value = '每轮检查媒体数需为 1–100 的整数'; return;}
        if (config.subtitle_auto && config.subtitle_cron.trim().split(/\s+/).length !== 5) {error.value = '执行周期需为 5 段 Cron 表达式'; return;}
        emit('save', {...config, subtitle_batch: batch, douban_score_update_days: days});
      };
      return () => h('form', {class: 'zvh-root', onSubmit: event => {event.preventDefault(); save();}}, [
        h('header', {class: 'zvh-header'}, [h('div', [h('p', {class: 'zvh-kicker'}, '极影视助手'), h('h2', '插件设置')])]),
        h('section', {class: 'zvh-panel zvh-settings'}, [h('h3', '中文字幕补全'), toggle('subtitle_enabled', '开启字幕功能'), toggle('subtitle_auto', '定时检查并自动补全中文字幕'),
          field('subtitle_cron', '字幕检查周期（默认每 30 分钟）'), field('subtitle_batch', '每轮检查媒体数（1–100）', 'number'),
          h('p', {class: 'zvh-muted'}, '自动读取 MoviePilot 本地影视入库目录；每轮最多尝试 5 个媒体。未标注语言、STRM、原盘、匹配不确定的媒体跳过。同名字幕不覆盖。'),
          field('subtitle_nas_cache', 'NAS 缓存路径（通常自动识别，识别失败时填写 staging 对应路径）'),
          h('p', {class: 'zvh-muted'}, '在插件首页完成网页授权，无需终端。日常自动续期；重新授权期间暂停下载。')]),
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
