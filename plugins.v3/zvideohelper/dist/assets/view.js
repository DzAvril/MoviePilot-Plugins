function unwrap(response) {
  return response?.data?.success !== undefined ? response.data : response;
}

const STATES = {all:'全部记录',pending:'待检查',missing:'未发现中文',present:'已有中文',unknown:'待确认',excluded:'中文原声'};
const PATHS = {
  film:'M4 3h16v18H4zM4 8h16M4 16h16M8 3v18M16 3v18',
  search:'m21 21-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z',
  library:'M4 4h6v16H4zM14 4l6-1 3 16-6 1z',
  check:'m5 12 4 4L19 6',arrow:'m9 5 7 7-7 7',
  download:'M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5',
};

export function createPoster(Vue) {
  const {defineComponent,h,ref} = Vue;
  return defineComponent({props:{media:Object},setup(props) {
    const failed = ref('');
    return () => h('div',{class:'zvh-poster'},[
      h('span',{'aria-hidden':'true'},props.media.media_type==='tv'?'剧集':'电影'),
      props.media.poster_url && failed.value!==props.media.poster_url && h('img',{
        key:props.media.poster_url,src:`/api/v1/system/img/0?imgurl=${encodeURIComponent(props.media.poster_url)}&cache=true`,
        alt:`《${props.media.title}》海报`,loading:'lazy',decoding:'async',referrerpolicy:'no-referrer',
        onError:()=>{failed.value=props.media.poster_url;},
      }),
    ]);
  }});
}

export function createPage(Vue) {
  const {defineComponent,h,ref,computed,onMounted,onUnmounted,nextTick} = Vue;
  const Poster = createPoster(Vue);
  return defineComponent({
    name:'ZvideoSubtitlePage',props:{api:Object,pluginId:String},emits:['layout','switch','close'],
    setup(props,{emit}) {
      const tab = ref('library'),scanKeyword = ref(''),libraryQuery = ref(''),listFilter = ref('all'),libraryPage = ref(1),libraryBusy = ref(false);
      const keyword = ref(''),mediaType = ref('all'),choices = ref(null),selectedMedia = ref(null),choicePage = ref(1),filter = ref(''),page = ref(1),chineseOnly = ref(false);
      const series = ref(null),seasonNo = ref(''),episodeNo = ref(''),busyMessage = ref('');
      const status = ref(null),result = ref(null),busy = ref(false),error = ref(''),message = ref('');
      const library = ref(null),auth = ref(null),code = ref(''),files = ref(null),selectedFile = ref(''),destination = ref(''),saveMode = ref('device'),targets = ref([]),targetMessage = ref('');
      const toolFile = ref(null),working = ref(false);
      const previewState = ref(null),downloadState = ref(null),downloadPanel = ref(null);
      const manualDraft = ref({}),markFeedback = ref(null);
      let timer = null,polling = false,disposed = false,libraryRequest = 0;
      const endpoint = name => `plugin/${props.pluginId}/${name}`;
      const get = async (name,options) => unwrap(await props.api.get(endpoint(name),options));
      const post = async (name,payload={}) => {
        const response = unwrap(await props.api.post(endpoint(name),payload,{timeout:180000}));
        if (!response?.success) throw new Error(response?.message || '操作失败，请稍后重试');
        return response;
      };
      const rows = computed(()=>(result.value?.candidates || []).filter(item=>item.title.toLowerCase().includes(filter.value.trim().toLowerCase()) && (!chineseOnly.value || item.chinese_label)));
      const pages = computed(()=>Math.max(1,Math.ceil(rows.value.length/10)));
      const visible = computed(()=>rows.value.slice((Math.min(page.value,pages.value)-1)*10,Math.min(page.value,pages.value)*10));
      const choicePages = computed(()=>Math.max(1,Math.ceil((choices.value?.items.length || 0)/8)));
      const visibleChoices = computed(()=>(choices.value?.items || []).slice((choicePage.value-1)*8,choicePage.value*8));
      const scope = computed(()=>libraryQuery.value ? `“${libraryQuery.value}”` : '全部本地影视');
      const date = timestamp => timestamp ? new Date(timestamp*1000).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}) : '尚未检查';
      const episodeLabel = item => item.season!=null ? `第 ${item.season} 季 · 第 ${item.episode} 集` : `电影${item.year?' · '+item.year:''}`;
      const loadLibrary = async () => {
        const request = ++libraryRequest;libraryBusy.value = true;
        try {
          const response = await get('subtitle_library',{params:{keyword:libraryQuery.value,state:listFilter.value,page:libraryPage.value,page_size:12}});
          if (!response?.success) throw new Error(response?.message || '无法读取检查记录');
          if (request===libraryRequest && !disposed) {library.value=response;libraryPage.value=response.page;}
        } finally {if (request===libraryRequest) libraryBusy.value=false;}
      };
      const loadStatus = async () => {
        try {status.value=await get('subtitle_status');await loadLibrary();}
        catch {error.value='无法读取插件状态，请稍后刷新';}
      };
      const act = async fn => {
        if (working.value) return;
        working.value=true;error.value='';message.value='';
        try {await fn();} catch(caught) {error.value=caught.message || '操作失败，请稍后重试';}
        finally {working.value=false;}
      };
      const applyLibraryFilter = (clear=false) => act(async()=>{
        if (clear) {scanKeyword.value='';listFilter.value='all';}
        libraryQuery.value=scanKeyword.value.trim();libraryPage.value=1;await loadLibrary();
      });
      const changeLibraryState = value => act(async()=>{libraryQuery.value=scanKeyword.value.trim();listFilter.value=value;libraryPage.value=1;await loadLibrary();});
      const turnLibraryPage = value => act(async()=>{libraryPage.value=value;await loadLibrary();});
      const markItem = item => act(async()=>{
        markFeedback.value={id:item.id,state:'loading',message:'正在保存人工确认…'};
        try {
          const response=await post('subtitle_mark',{media_id:item.id,state:manualDraft.value[item.id]});
          delete manualDraft.value[item.id];markFeedback.value={id:item.id,state:'ready',message:response.message};await loadLibrary();
        } catch(caught) {markFeedback.value={id:item.id,state:'failed',message:caught.message || '人工确认保存失败，请重试'};}
      });
      const scan = (download,force=false) => act(async()=>{
        libraryQuery.value=scanKeyword.value.trim();libraryPage.value=1;listFilter.value='all';
        message.value=(await post('subtitle_scan',{download,keyword:libraryQuery.value,force})).message;await loadLibrary();
      });
      const resetManual = () => {
        choices.value=null;selectedMedia.value=null;result.value=null;files.value=null;series.value=null;seasonNo.value='';episodeNo.value='';
        previewState.value=null;downloadState.value=null;
        destination.value='';targets.value=[];page.value=1;choicePage.value=1;filter.value='';chineseOnly.value=false;error.value='';message.value='';
      };
      const findMedia = async () => {
        if (busy.value || working.value) return;
        resetManual();if (!keyword.value.trim()) {error.value='请输入影视名称';return;}
        busy.value=true;busyMessage.value='正在查找影视…';
        try {
          const response=await get('subtitle_media_search',{params:{keyword:keyword.value.trim(),media_type:mediaType.value},timeout:90000});
          if (!response?.success) throw new Error(response?.message || '影视查询失败');choices.value=response;
        } catch(caught) {error.value=caught.message || '影视查询失败';}
        finally {busy.value=false;busyMessage.value='';}
      };
      const clearEpisodeResults = () => {result.value=null;files.value=null;previewState.value=null;downloadState.value=null;destination.value='';targets.value=[];page.value=1;filter.value='';error.value='';message.value='';};
      const loadSeason = async (number,preferredEpisode='') => {
        const response=await get('subtitle_series',{params:{tmdb_id:selectedMedia.value.id,season:Number(number)},timeout:90000});
        if (!response?.success) throw new Error(response?.message || '无法读取本季集列表');
        series.value=response;seasonNo.value=String(number);
        episodeNo.value=response.episodes.some(ep=>String(ep.number)===String(preferredEpisode)) ? String(preferredEpisode) : '';
      };
      const fetchSelectedSubtitle = async () => {
        const payload={tmdb_id:selectedMedia.value.id,media_type:selectedMedia.value.media_type};
        if (payload.media_type==='tv') {payload.season=Number(seasonNo.value);payload.episode=Number(episodeNo.value);}
        busyMessage.value=payload.media_type==='tv'?'正在核对本集字幕与包内文件，首次查询可能需要 1–2 分钟…':'正在查找字幕…';
        const response=await post('subtitle_selected',payload);selectedMedia.value=response.selected_media || selectedMedia.value;result.value=response;
      };
      const chooseMedia = async (item,targetId='',selectedScope=null) => {
        if (busy.value || working.value) return;
        clearEpisodeResults();series.value=null;seasonNo.value='';episodeNo.value='';
        selectedMedia.value=item;busy.value=true;busyMessage.value=item.media_type==='tv'?'正在读取季集信息…':'正在查找字幕…';
        try {
          if (item.media_type==='tv') {
            const catalog=await get('subtitle_series',{params:{tmdb_id:item.id},timeout:90000});
            if (!catalog?.success) throw new Error(catalog?.message || '无法读取季集信息');
            selectedMedia.value=catalog.selected_media || item;
            const first=catalog.seasons.find(s=>s.number===selectedScope?.season) || catalog.seasons.find(s=>s.number>0 && s.episode_count>0) || catalog.seasons.find(s=>s.number>0) || catalog.seasons[0];
            await loadSeason(first.number,selectedScope?.episode);
            if (selectedScope && episodeNo.value) {await fetchSelectedSubtitle();destination.value=targetId;}
          } else {await fetchSelectedSubtitle();destination.value=targetId;}
        } catch(caught) {error.value=caught.message || '字幕搜索失败';}
        finally {busy.value=false;busyMessage.value='';}
      };
      const changeSeason = async value => {
        if (busy.value || working.value) return;
        clearEpisodeResults();seasonNo.value=value;episodeNo.value='';busy.value=true;busyMessage.value='正在读取本季集列表…';
        try {await loadSeason(value);} catch(caught) {series.value={...series.value,episodes:[]};error.value=caught.message || '季集查询失败';}
        finally {busy.value=false;busyMessage.value='';}
      };
      const searchEpisode = async () => {
        if (busy.value || working.value) return;
        if (!episodeNo.value) {error.value='请先选择一集';return;}
        clearEpisodeResults();busy.value=true;
        try {await fetchSelectedSubtitle();} catch(caught) {error.value=caught.message || '本集字幕搜索失败';}
        finally {busy.value=false;busyMessage.value='';}
      };
      const backToChoices = () => {const previous=choices.value;resetManual();if (previous) choices.value=previous;else findMedia();};
      const searchFromLibrary = item => {
        tab.value='manual';keyword.value=item.title;mediaType.value=item.season!=null?'tv':'movie';
        if (item.tmdb_id) {choices.value=null;chooseMedia({id:String(item.tmdb_id),title:item.title,year:item.year,media_type:mediaType.value},item.id,
          item.season!=null && item.episode!=null ? {season:item.season,episode:item.episode} : null);} else findMedia();
      };
      const uploadTool = () => act(async()=>{
        if (!toolFile.value) return;
        const form=new FormData();form.append('file',toolFile.value);
        const response=unwrap(await props.api.post(endpoint('subtitle_tool_install'),form));
        if (!response?.success) throw new Error(response?.message || '导入失败');message.value=response.message;await loadStatus();
      });
      const startAuth = () => act(async()=>{auth.value=await post('subtitle_auth_start');});
      const submitAuth = () => act(async()=>{
        const value=code.value;code.value='';const response=await post('subtitle_auth_submit',{session:auth.value.session,code:value});auth.value={...auth.value,...response};
      });
      const preview = item => act(async()=>{
        files.value=null;selectedFile.value='';downloadState.value=null;
        previewState.value={id:item.id,state:'loading',message:'正在读取字幕文件…'};
        try {
          const response=await post('subtitle_preview',{id:item.id});
          if (!response.files?.length) {
            previewState.value={id:item.id,state:'unavailable',message:response.message || '此资源没有可下载的文本字幕，请选择其他版本',unsupported:response.unsupported_files || []};
            return;
          }
          files.value={...response,title:item.title};selectedFile.value=response.files[0].id;
          previewState.value={id:item.id,state:'ready',message:`已展开 ${response.files.length} 个字幕文件，请在下载区选择保存位置`};
        } catch(caught) {
          previewState.value={id:item.id,state:'failed',message:caught.message || '字幕文件读取失败，请重试或选择其他版本'};
          return;
        }
        targets.value=[];targetMessage.value='';saveMode.value=destination.value?'nas':'device';
        await nextTick();downloadPanel.value?.scrollIntoView({block:'start',behavior:'instant'});downloadPanel.value?.focus({preventScroll:true});
        try {
          const selected=selectedMedia.value;
          const response=await get('subtitle_destinations',{params:{tmdb_id:selected.id,media_type:selected.media_type,
            season:selected.media_type==='tv'?Number(seasonNo.value):-1,episode:selected.media_type==='tv'?Number(episodeNo.value):-1}});
          if (!response?.success) throw new Error();targets.value=response.items;
          if (!targets.value.some(i=>i.id===destination.value && i.state!=='present')) destination.value='';
          saveMode.value=destination.value?'nas':'device';
          if (!targets.value.length) targetMessage.value='本地检查记录中还没有这部作品的对应文件。可先到影视库补全按片名检查，或下载到当前设备。';
          else if (targets.value.every(i=>i.state==='present')) targetMessage.value='对应媒体已存在中文字幕，将保留已有文件；仍可下载到当前设备比较版本。';
        } catch {targetMessage.value='暂时无法读取 NAS 目标，仍可下载到当前设备。';}
      });
      const download = () => act(async()=>{
        downloadState.value={state:'loading',message:saveMode.value==='nas'?'正在下载并保存到 NAS…':'正在准备下载文件…'};
        try {
          const response=await post('subtitle_download',{file_id:selectedFile.value,media_id:saveMode.value==='nas'?destination.value:''});
          if (response.ticket) {
            const raw=await props.api.get(endpoint('subtitle_file'),{params:{ticket:response.ticket},responseType:'blob',timeout:90000});const blob=raw instanceof Blob?raw:raw.data;
            if (!(blob instanceof Blob) || /json/i.test(blob.type)) throw new Error('下载文件已失效，请重新选择字幕后重试');
            const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=response.name;link.click();setTimeout(()=>URL.revokeObjectURL(url),30000);
            downloadState.value={state:'ready',message:'字幕已交给浏览器，保存到当前设备：'+response.name};
          } else {downloadState.value={state:'ready',message:response.message};await loadLibrary();}
        } catch(caught) {downloadState.value={state:'failed',message:caught.message || '字幕下载失败，请重试或选择其他版本'};}
      });
      const poll = async () => {
        if (polling || disposed) return;polling=true;
        try {
          if (auth.value && ['starting','waiting','verifying'].includes(auth.value.state)) {
            const next=await get('subtitle_auth_state');auth.value=next;if (next.state==='complete') {code.value='';await loadStatus();}
          }
          if (library.value?.running) await loadLibrary();
        } catch { /* A later poll recovers a transient connection failure. */ }
        finally {polling=false;}
      };
      onMounted(()=>{emit('layout',{maxWidth:'1160px'});loadStatus();timer=setInterval(poll,2000);});
      onUnmounted(()=>{disposed=true;clearInterval(timer);code.value='';});
      const icon = name => h('svg',{viewBox:'0 0 24 24',fill:'none',stroke:'currentColor','stroke-width':1.6,'stroke-linecap':'round','stroke-linejoin':'round','aria-hidden':'true'},[h('path',{d:PATHS[name]})]);
      const button = (text,action,disabled=false,primary=false) => h('button',{type:'button',class:['zvh-button',primary && 'zvh-primary'],onClick:action,disabled},text);
      const empty = (title,description,action=null) => h('div',{class:'zvh-empty'},[icon('search'),h('strong',title),h('p',description),action]);
      const pagination = (current,total,previous,next,description) => h('footer',{class:'zvh-pagination'},[
        h('span',description),h('div',[button('上一页',previous,current<=1 || working.value),h('span',`${current} / ${total}`),button('下一页',next,current>=total || working.value)])]);
      const libraryView = () => h('div',{class:'zvh-tab-content',role:'tabpanel','aria-label':'影视库补全'},[
        h('section',{class:'zvh-panel zvh-settings'},[
          h('div',{class:'zvh-section-heading'},[h('div',[h('h3','检查本地影视的中文字幕'),h('p',{class:'zvh-muted'},'首次完整检查，之后只检查新增或变化的文件。')]),
            h('span',{class:'zvh-badge'},library.value?.auto_enabled?'定时补全已开启':'定时补全未开启')]),
          h('div',{class:'zvh-directories'},[h('div',[h('strong','扫描目录'),h('span',{class:'zvh-muted'},library.value?.root_source==='custom'?'来自插件自定义配置':'来自 MoviePilot 媒体目录'),button('配置目录',()=>emit('switch'))]),...(library.value?.roots || []).map(root=>h('code',root)),...(library.value?.root_errors || []).map(text=>h('p',{class:'zvh-error'},text))]),
          h('div',{class:'zvh-coverage'},[h('strong',library.value?.coverage?.baseline_complete?'首次检查已完成':'首次检查尚未完成'),h('span',`已发现 ${library.value?.coverage?.discovered || 0} 个 · 已检查 ${library.value?.coverage?.checked || 0} 个 · 待检查 ${library.value?.coverage?.pending || 0} 个`)]),
          h('form',{class:'zvh-library-search',onSubmit:e=>{e.preventDefault();applyLibraryFilter();}},[
            h('label',{class:'zvh-field zvh-keyword'},[h('span','本地影视名称'),h('input',{'aria-label':'本地影视名称',value:scanKeyword.value,maxlength:200,placeholder:'搜索影视名称，留空查看全部',onInput:e=>{scanKeyword.value=e.target.value;}})]),
            h('button',{type:'submit',class:'zvh-button',disabled:working.value || libraryBusy.value},'筛选记录'),
            (scanKeyword.value || libraryQuery.value) && button('清除筛选',()=>applyLibraryFilter(true),working.value)]),
          h('div',{class:'zvh-scan-actions'},[
            h('p',{class:'zvh-muted'},'检查未变化的文件会复用结果。强制重检会重新检查当前片名范围。'),
            h('div',{class:'zvh-actions'},[button(scanKeyword.value.trim()?'增量检查此作品':library.value?.coverage?.baseline_complete?'增量检查':'首次全量检查',()=>scan(false),working.value || busy.value || library.value?.running || !status.value?.enabled || !!library.value?.root_errors?.length),
              button('强制重检',()=>scan(false,true),working.value || busy.value || library.value?.running || !status.value?.enabled || !!library.value?.root_errors?.length),
              button(scanKeyword.value.trim()?'补全此作品':'补全全部影视',()=>scan(true),working.value || busy.value || library.value?.running || !status.value?.authorized || !status.value?.enabled || !!library.value?.root_errors?.length,true)])])]),
        h('div',{class:'zvh-scope-line'},[h('strong',`当前范围：${scope.value}`),h('span',`共 ${library.value?.scoped_total || 0} 个已索引文件`),
          button('刷新记录',()=>act(loadLibrary),working.value || libraryBusy.value)]),
        h('div',{class:'zvh-stats'},['missing','present','unknown','excluded'].map(state=>h('button',{
          type:'button',class:['zvh-stat',`zvh-${state}`,listFilter.value===state && 'zvh-active'],'aria-pressed':listFilter.value===state,
          'aria-label':`${STATES[state]} ${library.value?.counts?.[state] || 0}`,onClick:()=>changeLibraryState(state),disabled:working.value || libraryBusy.value,
        },[h('span',STATES[state]),h('strong',library.value?.counts?.[state] || 0),h('small',state==='missing'?'可尝试补全':state==='present'?'无需自动补全':state==='unknown'?'信息不足，需人工确认':'自动搜索已跳过')]))),
        library.value?.task?.started_at && h('section',{class:'zvh-task',role:'status'},[
          h('div',[h('strong',`${library.value.running?'正在执行':'最近任务'} · ${library.value.task.scan_type || library.value.task.mode}`),h('span',{class:'zvh-muted'},`任务范围：${library.value.task.keyword || '全部本地影视'}`)]),
          h('p',library.value.task.error || `${library.value.task.phase || ''} · 检查 ${library.value.task.checked || 0}/${library.value.task.planned || 0} · 复用 ${library.value.task.skipped || 0} · 下载 ${library.value.task.downloaded || 0}`),
          library.value.running && h('progress',{max:Math.max(1,library.value.task.planned || 1),value:library.value.task.checked || 0,'aria-label':'本轮检查进度'}),
          h('small',{class:'zvh-muted'},library.value.running ? library.value.task.current_title || '正在读取本地影视文件…' : `${date(library.value.task.finished_at)} · 视频轨道探测 ${library.value.task.probed || 0} 次`),
          library.value.running && button('停止本次任务',()=>act(async()=>{message.value=(await post('subtitle_scan_cancel')).message;await loadLibrary();}),working.value)]),
        h('section',{class:'zvh-panel'},[
          h('div',{class:'zvh-results-heading'},[h('div',[h('h3','检查记录'),h('p',{class:'zvh-muted'},`${scope.value} · ${STATES[listFilter.value]} · ${library.value?.total || 0} 个文件`)]),
            h('div',{class:'zvh-actions'},[button(`待检查 ${library.value?.counts?.pending || 0}`,()=>changeLibraryState('pending'),working.value || libraryBusy.value),button('全部状态',()=>changeLibraryState('all'),listFilter.value==='all' || working.value || libraryBusy.value)])]),
          markFeedback.value && !(library.value?.items || []).some(i=>i.id===markFeedback.value.id) && h('p',{class:['zvh-notice',markFeedback.value.state==='failed'?'zvh-error':'zvh-success'],role:markFeedback.value.state==='failed'?'alert':'status'},markFeedback.value.message),
          libraryBusy.value ? h('div',{class:'zvh-empty',role:'status'},'正在读取当前范围…') : library.value?.items?.length ? h('div',{class:'zvh-library-list'},library.value.items.map(item=>h('article',{class:'zvh-library-item',key:item.id},[
            h('div',{class:'zvh-library-info'},[h('div',{class:'zvh-row-heading'},[h('h4',item.title),h('span',{class:['zvh-badge',`zvh-${item.state}`]},STATES[item.state]),item.manual_state && h('span',{class:'zvh-badge'},'人工确认')]),
              h('p',{class:'zvh-muted'},`${episodeLabel(item)} · ${date(item.checked_at)}`),h('p',{class:'zvh-reason'},item.reason),
              item.manual_state && h('p',{class:'zvh-muted'},`人工确认于 ${date(item.manual_at)} · 自动检测：${STATES[item.detected_state]}，${item.detected_reason}`),
              !!item.external_subtitles?.length && h('details',{class:'zvh-subtitle-evidence'},[h('summary',`已发现 ${item.external_subtitles.length} 个外挂字幕 · 查看依据`),h('ul',item.external_subtitles.map(file=>h('li',[h('strong',file.name),h('span',`${file.language} · ${file.basis}`)])))]),
              item.evidence && !item.external_subtitles?.length && h('p',{class:'zvh-muted'},`检测依据：${item.evidence}`),
              h('details',{class:'zvh-manual-confirm'},[h('summary',item.manual_state?'修改人工确认':'人工确认字幕状态'),
                h('p',{class:'zvh-muted'},'硬字幕或检测不确定时，可由你确认。已有中文会跳过自动补全；后续扫描保留标记，替换视频后重新检测。'),
                h('div',{class:'zvh-manual-actions'},[
                  h('select',{'aria-label':`《${item.title}》人工确认结果`,value:manualDraft.value[item.id] || '',disabled:working.value || item.state==='pending',onChange:e=>{manualDraft.value[item.id]=e.target.value;}},[
                    h('option',{value:''},'请选择确认结果'),h('option',{value:'present'},'已有中文（含硬字幕）'),h('option',{value:'missing'},'确认缺少中文'),h('option',{value:'auto',disabled:!item.manual_state},'恢复自动判断')]),
                  button(markFeedback.value?.id===item.id && markFeedback.value.state==='loading'?'保存中…':'保存确认',()=>markItem(item),working.value || item.state==='pending' || !manualDraft.value[item.id])]),
                h('small',{class:'zvh-muted'},'标记仅影响当前文件。中文原声、STRM 和原盘仍跳过自动下载；确认缺少中文后可点“补全此作品”。')]),
              markFeedback.value?.id===item.id && h('p',{class:['zvh-selection-feedback',markFeedback.value.state==='failed'?'zvh-error':'zvh-success'],role:markFeedback.value.state==='failed'?'alert':'status'},markFeedback.value.message),
              h('details',{class:'zvh-file-details'},[h('summary','查看文件位置'),h('code',item.path)])]),
            button('为此文件找字幕',()=>searchFromLibrary(item),busy.value || working.value || item.state==='pending')]))) : empty(
              libraryQuery.value?'当前范围没有符合条件的记录':'还没有符合条件的检查记录',
              library.value?.scoped_total ? '可切换“全部状态”查看此作品的其他记录。':'点击上方检查按钮建立记录；发现的新文件会先标为待检查。',
              listFilter.value!=='all' && button('查看全部状态',()=>changeLibraryState('all'),working.value)),
          library.value?.total>0 && pagination(library.value.page,library.value.pages,()=>turnLibraryPage(library.value.page-1),()=>turnLibraryPage(library.value.page+1),`共 ${library.value.total} 个文件 · 每页 ${library.value.page_size} 个`)]),
        h('details',{class:'zvh-rules'},[h('summary','检查规则与目录'),h('p','按 TMDB 原始语言跳过中文原声作品。只检查 MoviePilot 本地影视入库目录；语言不明、STRM 和原盘需人工确认，不识别画面烧录字幕，不覆盖已有字幕。'),
          h('p',`检查会覆盖全部目录并缓存结果；后续只探测新增、变化或需重试的文件。每轮最多尝试 ${library.value?.download_limit || 5} 个自动下载。`),
          ...(library.value?.roots || []).map(root=>h('code',root))]),
      ]);
      const manualView = () => h('div',{class:'zvh-tab-content',role:'tabpanel','aria-label':'手动找字幕'},[
        h('form',{class:'zvh-panel zvh-settings',onSubmit:e=>{e.preventDefault();findMedia();}},[
          h('div',{class:'zvh-section-heading'},[h('div',[h('h3','先找到你要的作品'),h('p',{class:'zvh-muted'},'按名称查找，核对海报和年份；电视剧还可选择季和集。')]),h('span',{class:'zvh-badge'},'1 选作品 → 2 选字幕 → 3 下载')]),
          h('div',{class:'zvh-search'},[
            h('label',{class:'zvh-field zvh-keyword'},[h('span','影视名称'),h('input',{'aria-label':'影视名称',value:keyword.value,maxlength:200,disabled:busy.value || working.value,placeholder:'例如：异形 / 现在不是出轨的问题',onInput:e=>{keyword.value=e.target.value;resetManual();}})]),
            h('label',{class:'zvh-field'},[h('span','影视类型'),h('select',{'aria-label':'影视类型',value:mediaType.value,disabled:busy.value || working.value,onChange:e=>{mediaType.value=e.target.value;resetManual();}},[
              h('option',{value:'all'},'电影和剧集'),h('option',{value:'movie'},'电影'),h('option',{value:'tv'},'剧集')])]),
            h('button',{type:'submit',class:'zvh-button zvh-primary',disabled:busy.value || working.value || !status.value?.enabled},'查找影视')])]),
        busy.value && h('div',{class:'zvh-loading',role:'status'},[h('span',{class:'zvh-spinner'}),h('span',busyMessage.value)]),
        !choices.value && !selectedMedia.value && !busy.value && empty('从片名开始','无需填写 TMDB 或 IMDb 编号。选择具体作品后，只查它的字幕。'),
        choices.value && !selectedMedia.value && h('section',{class:'zvh-panel zvh-settings'},[
          h('div',{class:'zvh-section-heading'},[h('h3',`找到 ${choices.value.count} 部候选作品`),h('span',{class:'zvh-muted'},'根据海报、年份和简介选择')]),
          h('div',{class:'zvh-media-choices'},visibleChoices.value.map(item=>h('article',{key:item.media_type+item.id,class:'zvh-media-choice'},[
            h(Poster,{media:item}),h('div',{class:'zvh-choice-info'},[h('div',{class:'zvh-row-heading'},[h('span',{class:'zvh-badge'},item.media_type==='tv'?'剧集':'电影'),h('span',{class:'zvh-muted'},item.year || '年份未知')]),
              h('h4',item.title),item.original_title && item.original_title!==item.title && h('small',{class:'zvh-muted'},item.original_title),
              h('p',{class:'zvh-overview'},item.overview || '暂无简介'),
              h('button',{type:'button',class:'zvh-button zvh-primary','aria-label':`为《${item.title}》（${item.year || '年份未知'}·${item.media_type==='movie'?'电影':'剧集'}）${item.media_type==='tv'?'选择季集':'查找字幕'}`,onClick:()=>chooseMedia(item),disabled:busy.value || working.value || !status.value?.authorized},item.media_type==='tv'?'选择季集':'查找字幕')])]))),
          !choices.value.count && empty('没有找到作品',choices.value.message),
          choicePages.value>1 && pagination(choicePage.value,choicePages.value,()=>{choicePage.value--;},()=>{choicePage.value++;},`${choices.value.count} 部作品`)]),
        selectedMedia.value && h('section',{class:'zvh-panel zvh-selected-work'},[
          h('div',{class:'zvh-selected-header'},[h(Poster,{media:selectedMedia.value}),h('div',{class:'zvh-selected-info'},[
            h('p',{class:'zvh-kicker'},'已选择作品'),h('h3',selectedMedia.value.title),h('p',{class:'zvh-muted'},`${selectedMedia.value.year || '年份未知'} · ${selectedMedia.value.media_type==='tv'?'剧集':'电影'}`),
            h('p',selectedMedia.value.media_type==='tv'?(result.value?`仅显示第 ${seasonNo.value} 季第 ${episodeNo.value} 集的字幕`:'选择具体一集，再查找本集字幕'):'只显示这部电影的字幕')]),button('重新选片',backToChoices,busy.value || working.value)]),
          selectedMedia.value.media_type==='tv' && series.value && h('div',{class:'zvh-season-picker'},[
            h('label',{class:'zvh-field'},[h('span','季'),h('select',{'aria-label':'季',value:seasonNo.value,disabled:busy.value || working.value,onChange:e=>changeSeason(e.target.value)},series.value.seasons.map(s=>h('option',{value:String(s.number)},s.number===0?'特别篇':s.name || `第 ${s.number} 季`)))]),
            h('label',{class:'zvh-field zvh-keyword'},[h('span','集'),h('select',{'aria-label':'集',value:episodeNo.value,disabled:busy.value || working.value,onChange:e=>{episodeNo.value=e.target.value;clearEpisodeResults();}},[h('option',{value:''},'请选择一集'),...series.value.episodes.map(ep=>h('option',{value:String(ep.number)},`第 ${ep.number} 集 · ${ep.name}`))])]),
            button('查找本集字幕',searchEpisode,busy.value || working.value || !episodeNo.value || !status.value?.authorized,true)])]),
        result.value && h('section',{class:'zvh-panel'},[
          h('div',{class:'zvh-results-heading'},[h('div',[h('h3',`找到 ${result.value.count} 个字幕版本`),h('p',{class:'zvh-muted'},'整季包已按集展开，可比较语言和发行版本。')]),
            h('div',{class:'zvh-result-filters'},[h('input',{'aria-label':'筛选搜索结果',placeholder:'筛选语言、格式或发行版本',value:filter.value,onInput:e=>{filter.value=e.target.value;page.value=1;}}),
              h('label',{class:'zvh-checkbox'},[h('input',{type:'checkbox',checked:chineseOnly.value,onChange:e=>{chineseOnly.value=e.target.checked;page.value=1;}}),'仅看已标注中文'])])]),
          h('div',{class:'zvh-sub-list'},visible.value.map(item=>h('article',{class:['zvh-sub-row',previewState.value?.id===item.id && 'zvh-selected-sub'],key:item.id},[
            h('div',[h('div',{class:'zvh-row-heading'},[h('span',{class:'zvh-format'},item.format),item.chinese_label && h('span',{class:'zvh-badge'},'中文标记')]),h('strong',item.title),
              h('small',{class:'zvh-muted'},item.archive_title?'来源：'+item.archive_title:item.movie),
              previewState.value?.id===item.id && h('div',{class:['zvh-selection-feedback',['failed','unavailable'].includes(previewState.value.state)?'zvh-error':'zvh-success'],role:['failed','unavailable'].includes(previewState.value.state)?'alert':'status'},[
                h('p',previewState.value.message),...(previewState.value.unsupported || []).map(name=>h('small',`包内文件：${name}`))])]),
            button(previewState.value?.id===item.id && previewState.value.state==='loading'?'正在读取…':previewState.value?.id===item.id && previewState.value.state==='ready'?'已选择':'选择字幕',()=>preview(item),working.value || busy.value || !item.download_available)]))),
          result.value.archive_warning && h('p',{class:'zvh-inline-notice'},result.value.archive_warning),
          !rows.value.length && empty('没有符合条件的字幕',result.value.message || '可清空筛选词，或取消“仅看已标注中文”。'),
          pagination(Math.min(page.value,pages.value),pages.value,()=>{page.value--;},()=>{page.value++;},`${rows.value.length} 个结果`)]),
        files.value?.files?.length && h('section',{class:'zvh-panel zvh-settings zvh-download-panel',ref:downloadPanel,tabindex:-1,'aria-label':'下载选中的字幕'},[
          h('div',{class:'zvh-section-heading'},[h('div',[h('h3','下载选中的字幕'),h('p',{class:'zvh-muted'},files.value.title)]),h('span',{class:'zvh-badge'},'最后一步')]),
          h('label',{class:'zvh-field'},[h('span','字幕文件'),h('select',{'aria-label':'字幕文件',value:selectedFile.value,disabled:working.value,onChange:e=>{selectedFile.value=e.target.value;downloadState.value=null;}},files.value.files.map(f=>h('option',{value:f.id},f.title)))]),
          h('div',{class:'zvh-save-options'},['device','nas'].map(value=>h('label',{class:['zvh-save-option',saveMode.value===value && 'zvh-active']},[
            h('input',{type:'radio',name:'zvh-save-mode',value,checked:saveMode.value===value,disabled:working.value,onChange:()=>{saveMode.value=value;downloadState.value=null;}}),
            h('div',[h('strong',value==='device'?'下载到当前设备':'保存到 NAS'),h('p',value==='device'?'交给手机或电脑的浏览器保存':'写入对应影视文件的同级目录')])]))),
          saveMode.value==='nas' && [h('label',{class:'zvh-field'},[h('span','NAS 对应媒体'),h('select',{'aria-label':'NAS 对应媒体',value:destination.value,disabled:working.value,onChange:e=>{destination.value=e.target.value;downloadState.value=null;}},[
            h('option',{value:''},'请选择对应文件'),...targets.value.map(i=>h('option',{value:i.id,disabled:i.state==='present'},(i.state==='present'?'已有中文 · ':'')+i.path))])]),h('p',{class:'zvh-muted'},'保存名使用视频名 + .zh + 字幕扩展名，区分语言；已有字幕保留，不覆盖。')],
          targetMessage.value && h('p',{class:'zvh-muted'},targetMessage.value),
          files.value.message && h('p',files.value.message),
          downloadState.value && h('div',{class:['zvh-notice',downloadState.value.state==='failed'?'zvh-error':'zvh-success'],role:downloadState.value.state==='failed'?'alert':'status'},downloadState.value.message),
          h('div',{class:'zvh-download-actions'},[h('p',{class:'zvh-muted'},'字幕时间轴可能因发行版本不同而有偏差。'),button(working.value?'处理中…':saveMode.value==='nas'?'保存到 NAS 媒体目录':'下载到当前设备',download,working.value || busy.value || !selectedFile.value || (saveMode.value==='nas' && !destination.value),true)])]),
      ]);
      return () => h('div',{class:'zvh-root'},[
        h('header',{class:'zvh-header'},[h('div',{class:'zvh-brand'},[h('div',{class:'zvh-brand-icon'},icon('film')),h('div',[h('p',{class:'zvh-kicker'},'极影视助手 · 1.12.0'),h('h2','中文字幕补全'),h('p',{class:'zvh-muted'},'自动补全与手动选择，都在这里。')])]),button('插件设置',()=>emit('switch'))]),
        h('div',{class:'zvh-status'},[h('div',[h('span',{class:['zvh-dot',status.value?.authorized && 'zvh-ready']}),h('span',status.value?.message || '读取授权状态…')]),
          h('div',[button('刷新状态',loadStatus,working.value || libraryBusy.value),button(status.value?.authorized?'重新授权':'网页授权',startAuth,working.value || busy.value || library.value?.running)])]),
        status.value && !status.value.installed && h('section',{class:'zvh-panel zvh-settings'},[
          h('h3','首次初始化'),h('p','从自己的 zspace-nas-agent-toolkit v0.1.4 工具包中选择 NAS 架构对应的 Linux 授权程序，导入后即可网页授权，无需终端。'),
          h('input',{type:'file','aria-label':'Linux 授权程序',onChange:e=>{toolFile.value=e.target.files?.[0] || null;}}),button('导入授权工具',uploadTool,working.value || !toolFile.value)]),
        auth.value && h('section',{class:'zvh-panel zvh-settings'},[h('h3','极空间网页授权'),h('p',{role:'status'},auth.value.message),
          auth.value.state==='waiting' && [h('a',{href:auth.value.url,target:'_blank',rel:'noopener noreferrer',class:'zvh-button zvh-primary'},'打开极空间授权网页'),
            h('label',{class:'zvh-field'},[h('span','一次性授权码'),h('input',{'aria-label':'一次性授权码',type:'password',autocomplete:'one-time-code',value:code.value,onInput:e=>{code.value=e.target.value;}})]),button('完成授权',submitAuth,working.value || !code.value.trim())],
          ['failed','expired'].includes(auth.value.state) && button('重新开始',startAuth,working.value)]),
        h('nav',{class:'zvh-tabs',role:'tablist','aria-label':'字幕功能'},['library','manual'].map(value=>h('button',{type:'button',role:'tab','aria-selected':tab.value===value,onClick:()=>{tab.value=value;error.value='';message.value='';},class:tab.value===value?'zvh-active':''},[icon(value==='library'?'library':'search'),value==='library'?'影视库补全':'手动找字幕']))),
        error.value && h('div',{class:'zvh-notice zvh-error',role:'alert'},error.value),message.value && h('div',{class:'zvh-notice zvh-success',role:'status'},message.value),
        tab.value==='library'?libraryView():manualView(),
      ]);
    },
  });
}

export function createConfig(Vue) {
  const {defineComponent, h, reactive, ref, onMounted} = Vue;
  return defineComponent({
    name: 'ZvideoHelperConfig', props: {initialConfig: Object}, emits: ['save', 'close', 'switch', 'layout'],
    setup(props, {emit}) {
      const config = reactive({enabled: false, subtitle_enabled: true, subtitle_auto: false, subtitle_cron: '*/30 * * * *', subtitle_library_paths: '', subtitle_download_limit: 5, subtitle_nas_cache: '', notify: false, onlyonce: false,
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
        const limit = Number(config.subtitle_download_limit);
        if (!Number.isInteger(limit) || limit < 1 || limit > 20) {error.value = '每轮自动补全尝试数需为 1–20 的整数'; return;}
        if (config.subtitle_library_paths.split('\n').some(path=>path.trim() && (!path.trim().startsWith('/') || path.trim()==='/' || path.trim().split('/').includes('..')))) {error.value='影视目录请填写具体的绝对路径，每行一个';return;}
        if (config.subtitle_auto && config.subtitle_cron.trim().split(/\s+/).length !== 5) {error.value = '执行周期需为 5 段 Cron 表达式'; return;}
        emit('save', {...config, subtitle_download_limit: limit, douban_score_update_days: days});
      };
      return () => h('form', {class: 'zvh-root', onSubmit: event => {event.preventDefault(); save();}}, [
        h('header', {class: 'zvh-header'}, [h('div', [h('p', {class: 'zvh-kicker'}, '极影视助手'), h('h2', '插件设置')])]),
        h('section', {class: 'zvh-panel zvh-settings'}, [h('h3', '中文字幕补全'), toggle('subtitle_enabled', '开启字幕功能'), toggle('subtitle_auto', '定时检查并自动补全中文字幕'),
          h('label',{class:'zvh-field'},[h('span','影视库目录（每行一个，留空沿用 MoviePilot）'),h('textarea',{'aria-label':'影视库目录',rows:4,value:config.subtitle_library_paths,placeholder:'/media/电影\n/media/电视剧',onInput:e=>{config.subtitle_library_paths=e.target.value;}})]),
          h('p',{class:'zvh-muted'},'填写 MoviePilot 容器内已有目录的绝对路径。填写后只扫描这些目录；留空读取 MoviePilot 的本地电影、电视剧入库目录。不会创建目录。'),
          field('subtitle_cron', '增量检查与补全周期（默认每 30 分钟）'), field('subtitle_download_limit', '每轮最多尝试自动补全的文件数（1–20）', 'number'),
          h('p', {class: 'zvh-muted'}, '首次完整建立索引，后续复用未变化文件的检查结果；后台串行、低优先级探测，支持停止与续扫。未标注语言、STRM、原盘、匹配不确定的媒体跳过。同名字幕不覆盖。'),
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
