const state = {
  config: null,
  file: null,
  mode: 'summary',
  filter: '',
  answerRaw: '',
  lastMode: 'summary',
  reportTarget: null,
  language: 'ja',
  analysisTabs: [],
  dismissedAnalysisTabIds: new Set(),
  activeAnalysisTabId: null,
  improvementRunning: false,
  editing: false,
  editDirty: false,
  readOnly: true,
  pinnedProjects: [],
  loopJob: null,
  loopRunning: false,
};

const $ = (selector) => document.querySelector(selector);
const tree = $('#tree');
const ASSISTANT_WIDTH_KEY = 'ollama-assistant-width';
const DEFAULT_ASSISTANT_WIDTH = 370;
const MAX_ANALYSIS_TABS = 8;
const WORKSPACE_DB_NAME = 'ollama-code-browser';
const WORKSPACE_DB_VERSION = 1;
const WORKSPACE_STORE = 'workspace';
const WORKSPACE_STATE_KEY = 'latest';
const PINNED_PROJECTS_KEY = 'code-browser-pinned-projects';
let analysisTabSequence = 0;
let persistenceTimer = null;
let mcpSyncTimer = null;
let loopPollTimer = null;
let restoringWorkspace = false;
const translations = {
  ja: {
    openFolder: 'フォルダを開く', filter: 'ファイルを絞り込み', noFile: 'ファイルを選択',
    chooseFile: 'プロジェクトからファイルを選択してください', emptyTitle: 'コードを選んで、理解する',
    emptyDescription: '左のファイルツリーからソースコードを開くと、要約や詳しい解説を Ollama に依頼できます。',
    fileSearch: 'ファイル検索', summary: '要約', explain: '詳しく解説', review: 'レビュー',
    improve: '改善点',
    selectionFull: 'ファイル全体を解析します', question: 'このコードについて質問…',
    generateSummary: '要約を生成', generateExplain: '詳しい解説を生成', runReview: 'レビューを実行',
    runImprovement: '3モデルで改善点を検証', improvementStarting: n => `${n}モデルで改善点を同時検証中…`,
    improvementAlreadyRunning: '改善点の複数モデル検証はすでに実行中です',
    improvementComplete: (done, tried) => `${tried}モデルを検証し、${done}モデルの結果を取得しました`,
    integratedResult: '統合結果', integratingResults: 'モデル別の改善案を統合中…',
    noIntegratedResult: '成功したモデル結果がないため、統合結果を生成できませんでした。',
    restoredInterrupted: 'リロード時に実行中だったため、この解析は中断されました。',
    folderDescription: '閲覧するローカルディレクトリの絶対パスを入力してください。',
    directory: 'ディレクトリ', cancel: 'キャンセル', open: '開く', files: 'ファイル', code: 'コード',
    loading: '読み込み中…', emptyFolder: '空のフォルダ', operations: '操作', folderSummary: 'このフォルダ構成を要約',
    askOllama: 'Ollama に送信中…', projectSending: '構成と主要設定ファイルを Ollama に送信中…',
    projectAnalyzing: '## プロジェクト構成を解析中…', cachedSummary: 'このセッションで生成済みのプロジェクト構成要約',
    project: 'プロジェクト構成要約', answerQuestion: '質問への回答', codeExplanation: 'コード解説',
    target: '対象ファイル', model: 'Ollamaモデル', host: '接続先', created: '作成日時',
    initialAnswer: 'ファイルを開いて解析を実行すると、ここに回答が表示されます。',
    readyAnswer: '解析方法を選んで実行してください。コードを範囲選択すると、その部分だけを解析できます。',
    selectedLines: n => `選択範囲のみ解析（${n} 行）`, lines: n => `${n} 行`,
    connecting: '接続中…', noModels: 'モデルなし', disconnected: '接続なし', offline: 'Ollama オフライン',
    emptyResponse: '回答が空でした。別のモデルで再実行してください。',
    analysisFailed: '解析に失敗しました', analysisTimedOut: seconds => `${seconds}秒で応答が完了しなかったため、次のモデルへ切り替えました。`,
    projectEmpty: 'プロジェクト要約が空でした。別のモデルで再実行してください。',
    projectFailed: 'プロジェクト構成の要約に失敗しました', fileOpenFailed: 'ファイルを開けません',
    pdfBlocked: 'PDF画面を開けません。ポップアップを許可してください。', pdfPrint: '印刷画面で「PDFとして保存」を選択してください',
    codeReview: 'コードレビュー', parentDirectory: '親ディレクトリへ移動', refresh: '更新',
    fullscreen: '全画面表示', exitFullscreen: '全画面を終了', clearAnswer: '回答をクリア',
    resolvingReference: '参照先を検索中…', referenceOpened: (path, line) => `${path} の ${line} 行目へ移動しました`,
    referenceNotFound: ref => `参照先を見つけられません: ${ref}`,
    copyPath: 'フルパスをコピー', pathCopied: 'フルパスをコピーしました', pathCopyFailed: 'パスをコピーできませんでした',
    projectImprove: 'プロジェクト全体の改善点', projectImproving: n => `${n}モデルでプロジェクト全体を検証中…`,
    editFile: '編集', saveFile: '保存', cancelEdit: '編集をキャンセル', fileSaved: 'ファイルを保存しました',
    saveFailed: '保存に失敗しました', discardChanges: '未保存の変更を破棄しますか？', sourceEditor: 'ソースコード編集',
    commitFile: 'このファイルをコミット', commitMessage: 'コミットメッセージ', commit: 'コミット', committed: 'コミットしました',
    readOnly: '読み取り専用', editingEnabled: '編集可能', readOnlyOn: '読み取り専用です', readOnlyOff: '編集を許可しました',
    unlockEditing: '編集を許可', lockEditing: '編集を禁止', gitClean: '変更なし', gitModified: '変更あり',
    pinProject: 'このプロジェクトを固定', unpinProject: '固定を解除', pinnedProjects: '固定したプロジェクト',
    noPinnedProjects: '固定したプロジェクトはありません', openPinnedProject: 'このプロジェクトを開く', removePin: '一覧から削除',
    copyProjectPath: 'プロジェクトのフルパスをコピー',
    currentProject: '開いている',
    projectOperations: 'プロジェクト操作',
    projectPinned: name => `${name} を固定しました`, projectUnpinned: name => `${name} の固定を解除しました`,
    loop: 'Loop ×3 · Python', stopLoop: '停止', loopReadOnly: 'Loopを開始するにはREAD ONLYを解除してください',
    loopConfirm: target => `${target} のPython（.py）ファイルだけを最大3ラウンド自動解析・修正します。Git未管理の場合はローカルリポジトリを初期化し、専用ブランチとラウンド別コミットを作成します（pushはしません）。開始しますか？`,
    loopStarting: 'Loopを開始しています…', loopFailed: 'Loopの開始に失敗しました', loopProject: 'このプロジェクトでLoop ×3', loopFile: 'このファイルでLoop ×3',
    loopSummary: 'Loop統合結果', loopRound: n => `Round ${n}`,
    loopOutcome: '終了結果',
    loopConcreteChanges: '具体的な変更内容', loopNoConcreteChanges: '適用された変更はありません。',
    loopNoChangeDecisions: '変更なしの判定', loopNotRun: rounds => `未実行：Round ${rounds.join(', ')}`,
    loopIntegrationAttempts: '統合モデルの試行',
    loopNoChangesOutcome: (done, max) => `正常終了：Round ${done}で安全に適用できる追加変更がなくなったため、最大${max}ラウンドのうち${done}ラウンドで終了しました。残り${Math.max(0, max - done)}ラウンドは実行していません。`,
    loopAllRoundsOutcome: count => `正常終了：予定した${count}ラウンドをすべて完了しました。`,
    loopFailedOutcome: message => `失敗終了：${message || 'エラーが発生しました。'}`,
    loopCancelledOutcome: 'キャンセルされました。以降のラウンドは実行していません。',
  },
  en: {
    openFolder: 'Open folder', filter: 'Filter files', noFile: 'Select a file',
    chooseFile: 'Select a file from the project', emptyTitle: 'Select code. Understand it.',
    emptyDescription: 'Open source code from the file tree, then ask Ollama to summarize or explain it.',
    fileSearch: 'File search', summary: 'Summary', explain: 'Explain', review: 'Review',
    improve: 'Improvements',
    selectionFull: 'Analyzing the entire file', question: 'Ask about this code…',
    generateSummary: 'Generate summary', generateExplain: 'Generate explanation', runReview: 'Run review',
    runImprovement: 'Verify with 3 models', improvementStarting: n => `Checking improvements with ${n} models…`,
    improvementAlreadyRunning: 'A multi-model improvement check is already running',
    improvementComplete: (done, tried) => `Checked ${tried} models and received ${done} results`,
    integratedResult: 'Combined result', integratingResults: 'Combining the model findings…',
    noIntegratedResult: 'No successful model results were available to combine.',
    restoredInterrupted: 'This analysis was interrupted because it was running when the page reloaded.',
    folderDescription: 'Enter the absolute path of a local directory to browse.',
    directory: 'Directory', cancel: 'Cancel', open: 'Open', files: 'Files', code: 'Code',
    loading: 'Loading…', emptyFolder: 'Empty folder', operations: 'Actions', folderSummary: 'Summarize this folder structure',
    askOllama: 'Sending to Ollama…', projectSending: 'Sending structure and project metadata to Ollama…',
    projectAnalyzing: '## Analyzing project structure…', cachedSummary: 'Project summary generated earlier in this session',
    project: 'Project structure summary', answerQuestion: 'Answer', codeExplanation: 'Code explanation',
    target: 'Target', model: 'Ollama model', host: 'Host', created: 'Created',
    initialAnswer: 'Open a file and run an analysis to see the response here.',
    readyAnswer: 'Choose an analysis action. Select a code range to analyze only that section.',
    selectedLines: n => `Analyzing selection (${n} lines)`, lines: n => `${n} lines`,
    connecting: 'Connecting…', noModels: 'No models', disconnected: 'Disconnected', offline: 'Ollama offline',
    emptyResponse: 'The response was empty. Try another model.', analysisFailed: 'Analysis failed',
    analysisTimedOut: seconds => `The response did not complete within ${seconds} seconds, so the next model was started.`,
    projectEmpty: 'The project summary was empty. Try another model.', projectFailed: 'Project summary failed',
    fileOpenFailed: 'Could not open file', pdfBlocked: 'Could not open the PDF view. Allow pop-ups and try again.',
    pdfPrint: 'Choose “Save as PDF” in the print dialog', codeReview: 'Code review',
    parentDirectory: 'Go to parent directory', refresh: 'Refresh',
    fullscreen: 'Fullscreen', exitFullscreen: 'Exit fullscreen', clearAnswer: 'Clear response',
    resolvingReference: 'Finding reference…', referenceOpened: (path, line) => `Opened ${path} at line ${line}`,
    referenceNotFound: ref => `Reference not found: ${ref}`,
    copyPath: 'Copy full path', pathCopied: 'Full path copied', pathCopyFailed: 'Could not copy path',
    projectImprove: 'Project-wide improvements', projectImproving: n => `Checking the entire project with ${n} models…`,
    editFile: 'Edit', saveFile: 'Save', cancelEdit: 'Cancel editing', fileSaved: 'File saved',
    saveFailed: 'Save failed', discardChanges: 'Discard unsaved changes?', sourceEditor: 'Source code editor',
    commitFile: 'Commit this file', commitMessage: 'Commit message', commit: 'Commit', committed: 'Committed',
    readOnly: 'READ ONLY', editingEnabled: 'EDITABLE', readOnlyOn: 'Read-only mode is on', readOnlyOff: 'Editing is enabled',
    unlockEditing: 'Enable editing', lockEditing: 'Disable editing', gitClean: 'clean', gitModified: 'modified',
    pinProject: 'Pin this project', unpinProject: 'Unpin project', pinnedProjects: 'Pinned projects',
    noPinnedProjects: 'No pinned projects', openPinnedProject: 'Open this project', removePin: 'Remove from pins',
    copyProjectPath: 'Copy project full path',
    currentProject: 'OPEN',
    projectOperations: 'Project actions',
    projectPinned: name => `Pinned ${name}`, projectUnpinned: name => `Unpinned ${name}`,
    loop: 'Loop ×3 · Python', stopLoop: 'Stop', loopReadOnly: 'Turn off READ ONLY before starting Loop',
    loopConfirm: target => `Automatically analyze and modify only Python (.py) files in ${target} for up to 3 rounds. If needed, a local Git repository will be initialized, then a dedicated branch and one commit per round will be created. Nothing is pushed. Start?`,
    loopStarting: 'Starting Loop…', loopFailed: 'Could not start Loop', loopProject: 'Run Loop ×3 on this project', loopFile: 'Run Loop ×3 on this file',
    loopSummary: 'Loop combined result', loopRound: n => `Round ${n}`,
    loopOutcome: 'Outcome',
    loopConcreteChanges: 'Concrete changes', loopNoConcreteChanges: 'No changes were applied.',
    loopNoChangeDecisions: 'No-change decisions', loopNotRun: rounds => `Not run: Round ${rounds.join(', ')}`,
    loopIntegrationAttempts: 'Integration attempts',
    loopNoChangesOutcome: (done, max) => `Completed normally: no further safe changes were found in Round ${done}, so the Loop stopped after ${done} of up to ${max} rounds. The remaining ${Math.max(0, max - done)} round(s) were not run.`,
    loopAllRoundsOutcome: count => `Completed normally: all ${count} planned rounds finished.`,
    loopFailedOutcome: message => `Failed: ${message || 'An error occurred.'}`,
    loopCancelledOutcome: 'Cancelled. No subsequent rounds were run.',
  },
};

function t(key, ...args) {
  const value = translations[state.language]?.[key] ?? translations.ja[key] ?? key;
  return typeof value === 'function' ? value(...args) : value;
}

function openWorkspaceDatabase() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(WORKSPACE_DB_NAME, WORKSPACE_DB_VERSION);
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(WORKSPACE_STORE)) request.result.createObjectStore(WORKSPACE_STORE);
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function writeWorkspaceState() {
  if (!state.config) return;
  const tabs = state.analysisTabs.map(tab => {
    const {controller, ...saved} = tab;
    return saved;
  });
  const value = {
    version: 1,
    root: state.config.root,
    filePath: state.file?.path || '',
    fileAbsolutePath: state.file?.absolutePath || '',
    activeAnalysisTabId: state.activeAnalysisTabId,
    dismissedAnalysisTabIds: [...state.dismissedAnalysisTabIds].slice(-100),
    tabs,
    savedAt: new Date().toISOString(),
  };
  const database = await openWorkspaceDatabase();
  await new Promise((resolve, reject) => {
    const transaction = database.transaction(WORKSPACE_STORE, 'readwrite');
    transaction.objectStore(WORKSPACE_STORE).put(value, WORKSPACE_STATE_KEY);
    transaction.oncomplete = resolve;
    transaction.onerror = () => reject(transaction.error);
  });
  database.close();
}

function scheduleWorkspaceSave(delay = 500) {
  if (restoringWorkspace) return;
  clearTimeout(persistenceTimer);
  persistenceTimer = setTimeout(() => writeWorkspaceState().catch(() => {}), delay);
  scheduleMcpStateSync(Math.max(delay, 700));
}

function scheduleMcpStateSync(delay = 700) {
  clearTimeout(mcpSyncTimer);
  mcpSyncTimer = setTimeout(() => syncMcpState().catch(() => {}), delay);
}

async function syncMcpState() {
  if (!state.config) return;
  const analyses = state.analysisTabs.map(tab => ({
    id: tab.id,
    title: tab.title,
    mode: tab.mode,
    model: tab.model,
    host: tab.host,
    status: tab.status,
    language: tab.language,
    projectRoot: tab.projectRoot || state.config.root,
    groupId: tab.groupId,
    tabRole: tab.tabRole,
    reportTarget: tab.reportTarget,
    content: tab.content,
  }));
  await api('/api/mcp-state', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      pinnedProjects: state.pinnedProjects,
      current: {
        projectRoot: state.config.root,
        filePath: state.file?.path || '',
        fileAbsolutePath: state.file?.absolutePath || '',
      },
      analyses,
    }),
  });
}

async function readWorkspaceState() {
  const database = await openWorkspaceDatabase();
  const value = await new Promise((resolve, reject) => {
    const transaction = database.transaction(WORKSPACE_STORE, 'readonly');
    const request = transaction.objectStore(WORKSPACE_STORE).get(WORKSPACE_STATE_KEY);
    request.onsuccess = () => resolve(request.result || null);
    request.onerror = () => reject(request.error);
  });
  database.close();
  return value;
}

async function restoreWorkspaceState() {
  let saved;
  try { saved = await readWorkspaceState(); } catch (_) { return; }
  if (!saved || saved.version !== 1) return;
  restoringWorkspace = true;
  state.dismissedAnalysisTabIds = new Set(
    Array.isArray(saved.dismissedAnalysisTabIds) ? saved.dismissedAnalysisTabIds.slice(-100) : [],
  );
  state.analysisTabs = (saved.tabs || []).filter(tab => !state.dismissedAnalysisTabIds.has(tab.id)).slice(-MAX_ANALYSIS_TABS).map(tab => {
    const interrupted = tab.status === 'streaming';
    return {
      ...tab,
      content: interrupted
        ? `${tab.content || ''}\n\n---\n\n_${t('restoredInterrupted')}_`.trim()
        : tab.content || '',
      status: interrupted ? 'failed' : tab.status,
      controller: null,
    };
  });
  state.activeAnalysisTabId = state.analysisTabs.some(tab => tab.id === saved.activeAnalysisTabId)
    ? saved.activeAnalysisTabId : state.analysisTabs.at(-1)?.id || null;
  renderAnalysisTabs();
  if (saved.root === state.config.root && saved.filePath) {
    await openFile(saved.filePath, null, {preserveAnalysis: true});
  }
  if (state.activeAnalysisTabId) activateAnalysisTab(state.activeAnalysisTabId);
  else if (!state.file) clearAnswer();
  restoringWorkspace = false;
  scheduleWorkspaceSave(0);
}

function applyLanguage() {
  document.documentElement.lang = state.language;
  $('#languageSelect').value = state.language;
  $('#openFolderLabel').textContent = t('openFolder');
  $('#filterInput').placeholder = t('filter');
  $('#emptyTitle').textContent = t('emptyTitle');
  $('#emptyDescription').textContent = t('emptyDescription');
  $('#fileSearchLabel').textContent = t('fileSearch');
  $('#summaryActionLabel').textContent = t('summary');
  $('#explainActionLabel').textContent = t('explain');
  $('#reviewActionLabel').textContent = t('review');
  $('#improveActionLabel').textContent = t('improve');
  $('#questionInput').placeholder = t('question');
  $('#folderDialogTitle').textContent = t('openFolder');
  $('#folderDialogDescription').textContent = t('folderDescription');
  $('#directoryLabel').textContent = t('directory');
  $('#cancelFolderButton').textContent = t('cancel');
  $('#confirmFolderButton').textContent = t('open');
  $('#mobileFilesLabel').textContent = t('files');
  $('#mobileCodeLabel').textContent = t('code');
  $('#parentButton').setAttribute('aria-label', t('parentDirectory'));
  $('#projectImproveButton').title = t('projectImprove');
  $('#projectImproveButton').setAttribute('aria-label', t('projectImprove'));
  $('#rootProjectMenuButton').title = t('projectOperations');
  $('#rootProjectMenuButton').setAttribute('aria-label', t('projectOperations'));
  $('#refreshButton').title = t('refresh');
  $('#clearButton').title = t('clearAnswer');
  $('#clearButton').setAttribute('aria-label', t('clearAnswer'));
  $('#copyPathButton').title = t('copyPath');
  $('#copyPathButton').setAttribute('aria-label', t('copyPath'));
  $('#editFileButton').title = t('editFile');
  $('#editFileButton').setAttribute('aria-label', t('editFile'));
  $('#saveFileButton').textContent = t('saveFile');
  $('#saveFileButton').title = t('saveFile');
  $('#cancelEditButton').title = t('cancelEdit');
  $('#cancelEditButton').setAttribute('aria-label', t('cancelEdit'));
  $('#gitCommitButton').title = t('commitFile');
  $('#gitCommitButton').setAttribute('aria-label', t('commitFile'));
  $('#codeEditor').setAttribute('aria-label', t('sourceEditor'));
  $('#commitDialogTitle').textContent = t('commitFile');
  $('#commitMessageLabel').textContent = t('commitMessage');
  $('#cancelCommitButton').textContent = t('cancel');
  $('#confirmCommitButton').textContent = t('commit');
  $('#loopLabel').textContent = t('loop');
  $('#stopLoopLabel').textContent = t('stopLoop');
  $('#pinnedProjectsTitle').textContent = t('pinnedProjects');
  $('#pinnedSidebarTitle').textContent = state.language === 'en' ? 'PINNED PROJECTS' : '固定したプロジェクト';
  renderPinnedProjects();
  updateReadOnlyButton();
  updateFullscreenButton();
  updateParentButton();
  const placeholder = document.querySelector('.answer-placeholder p');
  if (placeholder && !state.answerRaw) placeholder.textContent = state.file ? t('readyAnswer') : t('initialAnswer');
  if (!state.file) {
    $('#tabName').textContent = t('noFile');
    $('#breadcrumbs').textContent = t('chooseFile');
  }
  updateAnalyzeLabel();
  updateSelectionNote();
}

function updateAnalyzeLabel() {
  $('#analyzeLabel').textContent = {summary: t('generateSummary'), explain: t('generateExplain'), review: t('runReview'), improve: t('runImprovement')}[state.mode];
}

function updateSelectionNote() {
  const selected = getSelectedCode();
  $('#selectionNote').textContent = selected ? t('selectedLines', selected.split('\n').length) : t('selectionFull');
}

function updateParentButton() {
  const canMove = Boolean(state.config?.parent && state.config.parent !== state.config.root);
  $('#parentButton').disabled = !canMove;
  $('#parentButton').title = canMove ? `${t('parentDirectory')}: ${state.config.parent}` : t('parentDirectory');
}

function updateFullscreenButton() {
  const active = $('.assistant').classList.contains('fullscreen');
  $('#fullscreenButton').textContent = active ? '↙' : '⛶';
  $('#fullscreenButton').title = t(active ? 'exitFullscreen' : 'fullscreen');
  $('#fullscreenButton').setAttribute('aria-label', t(active ? 'exitFullscreen' : 'fullscreen'));
  $('#fullscreenButton').setAttribute('aria-pressed', String(active));
}

function toggleAssistantFullscreen(force) {
  const assistant = $('.assistant');
  const active = typeof force === 'boolean' ? force : !assistant.classList.contains('fullscreen');
  assistant.classList.toggle('fullscreen', active);
  document.body.classList.toggle('assistant-is-fullscreen', active);
  updateFullscreenButton();
}

function analysisModeLabel(mode) {
  return {project: t('project'), 'project-improve': t('projectImprove'), 'project-consensus': t('integratedResult'), summary: t('summary'), explain: t('explain'), review: t('review'), improve: t('improve'), consensus: t('integratedResult'), ask: t('answerQuestion'), loop: t('loopSummary')}[mode] || t('codeExplanation');
}

function createAnalysisTab(mode, target, requestedModel = $('#modelSelect').value, options = {}) {
  const modelSuffix = mode === 'improve' && requestedModel ? ` · ${requestedModel}` : '';
  const tab = {
    id: `analysis-${Date.now()}-${++analysisTabSequence}`,
    title: options.title || `${target.name} · ${analysisModeLabel(mode)}${modelSuffix}`,
    displayTitle: options.displayTitle || '',
    content: '',
    metaText: '',
    model: requestedModel,
    host: $('#connectionText').textContent,
    mode,
    language: state.language,
    reportTarget: {...target},
    groupId: options.groupId || null,
    tabRole: options.tabRole || 'standalone',
    projectRoot: state.config?.root || '',
    status: 'streaming',
    controller: null,
  };
  while (state.analysisTabs.length >= MAX_ANALYSIS_TABS) {
    const removed = state.analysisTabs.shift();
    removed?.controller?.abort();
  }
  state.analysisTabs.push(tab);
  state.activeAnalysisTabId = tab.id;
  renderAnalysisTabs();
  return tab;
}

function findAnalysisTab(id) {
  return state.analysisTabs.find(tab => tab.id === id);
}

function activateAnalysisTab(id) {
  const tab = findAnalysisTab(id);
  if (!tab) return;
  state.activeAnalysisTabId = id;
  state.answerRaw = tab.content;
  state.reportTarget = {...tab.reportTarget};
  state.lastMode = tab.mode;
  if (tab.content) showAnswer(tab.content);
  else {
    $('#answer').innerHTML = renderMarkdown(tab.status === 'streaming' ? t('projectAnalyzing') : t('emptyResponse'));
    setExportEnabled(false);
  }
  $('#assistantMeta').textContent = tab.metaText;
  $('#answer').classList.toggle('loading', tab.status === 'streaming');
  renderAnalysisTabs();
}

function closeAnalysisTab(id) {
  const index = state.analysisTabs.findIndex(tab => tab.id === id);
  if (index < 0) return;
  const wasActive = state.activeAnalysisTabId === id;
  const removed = state.analysisTabs[index];
  state.analysisTabs.splice(index, 1);
  state.dismissedAnalysisTabIds.add(id);
  while (state.dismissedAnalysisTabIds.size > 100) {
    state.dismissedAnalysisTabIds.delete(state.dismissedAnalysisTabIds.values().next().value);
  }
  if (removed.status === 'streaming') removed.controller?.abort();
  if (wasActive) {
    const next = state.analysisTabs[Math.min(index, state.analysisTabs.length - 1)];
    if (next) activateAnalysisTab(next.id);
    else {
      state.activeAnalysisTabId = null;
      state.reportTarget = state.file ? {name: state.file.name, path: state.file.path} : null;
      clearAnswer();
    }
  }
  renderAnalysisTabs();
  scheduleWorkspaceSave(0);
}

function renderAnalysisTabs() {
  const container = $('#analysisTabs');
  container.classList.toggle('has-tabs', state.analysisTabs.length > 0);
  container.innerHTML = state.analysisTabs.map(tab => `
    <div class="analysis-tab ${tab.id === state.activeAnalysisTabId ? 'active' : ''} ${tab.status === 'streaming' ? 'streaming' : ''} ${tab.status === 'failed' ? 'failed' : ''} ${tab.tabRole === 'summary' ? 'group-summary' : ''} ${tab.tabRole === 'model' ? 'group-model' : ''}" role="tab" tabindex="0" data-analysis-tab="${tab.id}" aria-selected="${tab.id === state.activeAnalysisTabId}">
      <span class="analysis-tab-status"></span>
      ${tab.tabRole === 'model' ? '<span class="analysis-tab-branch">↳</span>' : ''}
      <span class="analysis-tab-label" title="${escapeHtml(tab.title)}">${escapeHtml(tab.displayTitle || tab.title)}</span>
      <button class="analysis-tab-close" data-close-analysis-tab="${tab.id}" aria-label="Close">×</button>
    </div>`).join('');
  container.querySelectorAll('[data-analysis-tab]').forEach(element => {
    element.addEventListener('click', event => {
      if (!event.target.closest('[data-close-analysis-tab]')) activateAnalysisTab(element.dataset.analysisTab);
    });
    element.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') activateAnalysisTab(element.dataset.analysisTab);
    });
  });
  container.querySelectorAll('[data-close-analysis-tab]').forEach(button => {
    button.addEventListener('click', event => { event.stopPropagation(); closeAnalysisTab(button.dataset.closeAnalysisTab); });
  });
  scheduleWorkspaceSave();
}

function assistantWidthLimits() {
  return {min: 280, max: Math.max(280, Math.min(760, window.innerWidth - 570))};
}

function setAssistantWidth(width, persist = true) {
  const limits = assistantWidthLimits();
  const next = Math.round(Math.min(limits.max, Math.max(limits.min, width)));
  document.documentElement.style.setProperty('--assistant-width', `${next}px`);
  $('#assistantResizer').setAttribute('aria-valuenow', String(next));
  $('#assistantResizer').setAttribute('aria-valuemin', String(limits.min));
  $('#assistantResizer').setAttribute('aria-valuemax', String(limits.max));
  if (persist) localStorage.setItem(ASSISTANT_WIDTH_KEY, String(next));
}

function initAssistantResizer() {
  const saved = Number(localStorage.getItem(ASSISTANT_WIDTH_KEY));
  setAssistantWidth(Number.isFinite(saved) && saved > 0 ? saved : DEFAULT_ASSISTANT_WIDTH, false);
  const resizer = $('#assistantResizer');
  resizer.addEventListener('pointerdown', event => {
    if (event.button !== 0) return;
    resizer.setPointerCapture(event.pointerId);
    document.body.classList.add('resizing-assistant');
  });
  resizer.addEventListener('pointermove', event => {
    if (!resizer.hasPointerCapture(event.pointerId)) return;
    setAssistantWidth(window.innerWidth - event.clientX, false);
  });
  const finishResize = event => {
    if (!resizer.hasPointerCapture(event.pointerId)) return;
    resizer.releasePointerCapture(event.pointerId);
    document.body.classList.remove('resizing-assistant');
    const width = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--assistant-width'));
    setAssistantWidth(width, true);
  };
  resizer.addEventListener('pointerup', finishResize);
  resizer.addEventListener('pointercancel', finishResize);
  resizer.addEventListener('dblclick', () => setAssistantWidth(DEFAULT_ASSISTANT_WIDTH));
  resizer.addEventListener('keydown', event => {
    if (!['ArrowLeft', 'ArrowRight', 'Home'].includes(event.key)) return;
    event.preventDefault();
    if (event.key === 'Home') return setAssistantWidth(DEFAULT_ASSISTANT_WIDTH);
    const current = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--assistant-width'));
    setAssistantWidth(current + (event.key === 'ArrowLeft' ? 20 : -20));
  });
  window.addEventListener('resize', () => {
    const current = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--assistant-width'));
    setAssistantWidth(current, false);
  });
}

function switchMobilePanel(panel) {
  document.body.dataset.mobilePanel = panel;
  document.querySelectorAll('.mobile-nav [data-mobile-panel]').forEach(button => {
    button.classList.toggle('active', button.dataset.mobilePanel === panel);
  });
  closeTreeContextMenu();
}

async function api(path, options) {
  const requestOptions = {...(options || {})};
  if ((requestOptions.method || 'GET').toUpperCase() === 'POST') {
    const headers = new Headers(requestOptions.headers || {});
    headers.set('X-Requested-With', 'CodeBrowser');
    requestOptions.headers = headers;
  }
  const response = await fetch(path, requestOptions);
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try { message = (await response.json()).error || message; } catch (_) {}
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return response;
}

async function init() {
  loadPinnedProjects();
  try {
    state.config = await (await api('/api/config')).json();
    state.readOnly = state.config.readOnly !== false;
    updateReadOnlyButton();
    $('#rootPath').textContent = state.config.root;
    updateParentButton();
    renderPinnedProjects();
    await loadDirectory('', tree, 0);
    scheduleWorkspaceSave();
  } catch (error) {
    showTreeError(error.message);
  }
  await loadModels();
  await restoreWorkspaceState();
  await pollLoopStatus();
}

async function changeRoot(path) {
  if (state.editing && state.editDirty && !window.confirm(t('discardChanges'))) return false;
  if (state.editing) finishEditing();
  const button = $('#confirmFolderButton');
  button.disabled = true;
  $('#folderError').textContent = '';
  try {
    const response = await api('/api/root', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({path}),
    });
    state.config = await response.json();
    state.file = null;
    state.filter = '';
    $('#rootPath').textContent = state.config.root;
    updateParentButton();
    renderPinnedProjects();
    $('#filterInput').value = '';
    resetEditor();
    await loadDirectory('', tree, 0);
    $('#folderDialog').close();
    switchMobilePanel('explorer');
    return true;
  } catch (error) {
    $('#folderError').textContent = error.message;
    $('#assistantMeta').textContent = error.message;
    return false;
  } finally {
    button.disabled = false;
  }
}

function loadPinnedProjects() {
  try {
    const stored = JSON.parse(localStorage.getItem(PINNED_PROJECTS_KEY) || '[]');
    state.pinnedProjects = Array.isArray(stored)
      ? [...new Set(stored.filter(path => typeof path === 'string' && path.startsWith('/')))].slice(0, 30)
      : [];
  } catch (_) {
    state.pinnedProjects = [];
  }
  renderPinnedProjects();
}

function savePinnedProjects() {
  localStorage.setItem(PINNED_PROJECTS_KEY, JSON.stringify(state.pinnedProjects));
  renderPinnedProjects();
  scheduleMcpStateSync(0);
}

function projectName(path) {
  return path.replace(/\/$/, '').split('/').pop() || path;
}

function absoluteProjectPath(relativePath = '') {
  if (!relativePath) return state.config?.root || '';
  return `${state.config.root.replace(/\/$/, '')}/${relativePath.replace(/^\//, '')}`;
}

function toggleProjectPin(path) {
  if (!path) return;
  const index = state.pinnedProjects.indexOf(path);
  const removing = index >= 0;
  if (removing) state.pinnedProjects.splice(index, 1);
  else state.pinnedProjects.unshift(path);
  state.pinnedProjects = state.pinnedProjects.slice(0, 30);
  savePinnedProjects();
  $('#assistantMeta').textContent = t(removing ? 'projectUnpinned' : 'projectPinned', projectName(path));
}

function renderPinnedProjects() {
  renderPinnedProjectList($('#pinnedProjectsList'), false);
  renderPinnedProjectList($('#pinnedSidebarList'), true);
}

function renderPinnedProjectList(container, compact) {
  if (!container) return;
  container.innerHTML = '';
  if (!state.pinnedProjects.length) {
    container.innerHTML = `<div class="pinned-projects-empty">${t('noPinnedProjects')}</div>`;
    return;
  }
  for (const path of state.pinnedProjects) {
    const current = path === state.config?.root;
    const row = document.createElement('div');
    row.className = `pinned-project-row${compact ? ' compact' : ''}${current ? ' current' : ''}`;
    row.innerHTML = `
      <button type="button" class="pinned-project-open" title="${t('openPinnedProject')}"${current ? ' aria-current="true"' : ''}>
        <span class="pinned-project-star">${current ? '●' : '★'}</span>
        <span class="pinned-project-text">
          <span class="pinned-project-name">
            <strong>${escapeHtml(projectName(path))}</strong>
            ${current ? `<span class="pinned-current-label">${t('currentProject')}</span>` : ''}
          </span>
          <small>${escapeHtml(path)}</small>
        </span>
      </button>
      <button type="button" class="pinned-project-remove" title="${t('removePin')}" aria-label="${t('removePin')}: ${escapeHtml(projectName(path))}">×</button>`;
    row.querySelector('.pinned-project-open').addEventListener('click', () => changeRoot(path));
    row.addEventListener('contextmenu', event => showPinnedProjectContextMenu(event, path));
    row.querySelector('.pinned-project-remove').addEventListener('click', () => {
      state.pinnedProjects = state.pinnedProjects.filter(item => item !== path);
      savePinnedProjects();
    });
    container.append(row);
  }
}

async function openPinnedProjectForAction(path) {
  if (path === state.config?.root) return true;
  return changeRoot(path);
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    $('#assistantMeta').textContent = t('pathCopied');
  } catch (_) {
    $('#assistantMeta').textContent = t('pathCopyFailed');
  }
}

function showPinnedProjectContextMenu(event, path) {
  event.preventDefault();
  event.stopPropagation();
  const menu = $('#treeContextMenu');
  menu.innerHTML = `
    <div class="menu-label">${escapeHtml(path)}</div>
    <button role="menuitem" data-menu-action="open"><span class="menu-icon">↗</span>${t('openPinnedProject')}</button>
    <button role="menuitem" data-menu-action="loop"><span class="menu-icon">↻</span>${t('loopProject')}</button>
    <div class="menu-separator"></div>
    <button role="menuitem" data-menu-action="summary"><span class="menu-icon">✦</span>${t('folderSummary')}</button>
    <button role="menuitem" data-menu-action="improve"><span class="menu-icon">⇧</span>${t('projectImprove')}</button>
    <div class="menu-separator"></div>
    <button role="menuitem" data-menu-action="copy"><span class="menu-icon">⧉</span>${t('copyProjectPath')}</button>
    <button role="menuitem" data-menu-action="unpin"><span class="menu-icon">★</span>${t('unpinProject')}</button>`;
  menu.classList.add('open');
  const rect = menu.getBoundingClientRect();
  menu.style.left = `${Math.max(6, Math.min(event.clientX, window.innerWidth - rect.width - 6))}px`;
  menu.style.top = `${Math.max(6, Math.min(event.clientY, window.innerHeight - rect.height - 6))}px`;
  menu.querySelectorAll('[data-menu-action]').forEach(button => button.addEventListener('click', async () => {
    const action = button.dataset.menuAction;
    closeTreeContextMenu();
    if (action === 'copy') {
      await copyText(path);
      return;
    }
    if (action === 'unpin') {
      toggleProjectPin(path);
      return;
    }
    if (!await openPinnedProjectForAction(path)) return;
    if (action === 'loop') await startLoop('', 'project');
    if (action === 'summary') {
      switchMobilePanel('assistant');
      await analyzeProject('');
    }
    if (action === 'improve') await analyzeProjectImprovements('');
  }));
  menu.querySelector('button')?.focus();
}

function resetEditor() {
  state.editing = false;
  state.editDirty = false;
  state.reportTarget = null;
  $('#tabName').textContent = t('noFile');
  $('#breadcrumbs').textContent = t('chooseFile');
  $('#codeView').textContent = '';
  $('#lineNumbers').textContent = '';
  $('#languageLabel').textContent = 'Plain Text';
  $('#fileStats').textContent = '—';
  $('#activeTab').removeAttribute('title');
  $('#breadcrumbs').removeAttribute('title');
  $('#copyPathButton').disabled = true;
  $('#editFileButton').disabled = true;
  $('#editFileButton').hidden = false;
  $('#saveFileButton').hidden = true;
  $('#cancelEditButton').hidden = true;
  $('#gitCommitButton').disabled = true;
  $('#gitStatus').textContent = 'Git: —';
  $('#codeEditor').hidden = true;
  $('#codeWrap').classList.remove('editing');
  $('#codeWrap').classList.add('hidden');
  $('#emptyState').classList.remove('hidden');
  $('#analyzeButton').disabled = true;
  clearAnswer();
}

async function loadModels() {
  const select = $('#modelSelect');
  select.innerHTML = `<option value="">${t('connecting')}</option>`;
  try {
    const data = await (await api('/api/models')).json();
    select.innerHTML = '';
    for (const model of data.models) {
      const option = document.createElement('option');
      option.value = model;
      option.textContent = model;
      option.selected = model === data.preferred;
      select.append(option);
    }
    $('#statusDot').classList.add('online');
    $('#connectionText').textContent = new URL(data.host).hostname;
    if (!data.models.length) select.innerHTML = `<option value="">${t('noModels')}</option>`;
  } catch (error) {
    select.innerHTML = `<option value="">${t('disconnected')}</option>`;
    $('#statusDot').classList.remove('online');
    $('#connectionText').textContent = t('offline');
    $('#assistantMeta').textContent = error.message;
  }
}

async function loadDirectory(path, container, depth) {
  container.innerHTML = `<div class="tree-row"><span class="tree-caret">·</span><span class="tree-label">${t('loading')}</span></div>`;
  try {
    const data = await (await api(`/api/tree?path=${encodeURIComponent(path)}`)).json();
    container.innerHTML = '';
    for (const item of data.items) container.append(createTreeItem(item, depth));
    if (!data.items.length) container.innerHTML = `<div class="tree-row"><span class="tree-caret"></span><span class="tree-label">${t('emptyFolder')}</span></div>`;
    applyFilter();
  } catch (error) {
    container.innerHTML = `<div class="tree-row"><span class="tree-caret">!</span><span class="tree-label">${escapeHtml(error.message)}</span></div>`;
  }
}

function createTreeItem(item, depth) {
  const wrapper = document.createElement('div');
  const row = document.createElement('div');
  row.className = 'tree-row';
  row.dataset.path = item.path;
  row.dataset.name = item.name.toLowerCase();
  row.style.paddingLeft = `${7 + depth * 13}px`;
  const isDirectory = item.type === 'directory';
  row.innerHTML = `
    <span class="tree-caret">${isDirectory ? '›' : ''}</span>
    <span class="tree-icon ${isDirectory ? 'folder' : 'code'}">${isDirectory ? '▰' : fileIcon(item.name)}</span>
    <span class="tree-label" title="${escapeHtml(item.path)}">${escapeHtml(item.name)}</span>
    <button class="tree-mobile-action" aria-label="${escapeHtml(item.name)} ${t('operations')}" title="${t('operations')}">•••</button>`;
  wrapper.append(row);
  row.addEventListener('contextmenu', event => showTreeContextMenu(event, item, row));
  row.querySelector('.tree-mobile-action').addEventListener('click', event => {
    event.preventDefault();
    event.stopPropagation();
    const rect = event.currentTarget.getBoundingClientRect();
    showTreeContextMenu({preventDefault() {}, stopPropagation() {}, clientX: rect.right, clientY: rect.bottom}, item, row);
  });
  if (isDirectory) {
    const children = document.createElement('div');
    children.className = 'tree-children collapsed';
    wrapper.append(children);
    row.addEventListener('click', async () => {
      const opening = children.classList.contains('collapsed');
      children.classList.toggle('collapsed');
      row.querySelector('.tree-caret').textContent = opening ? '⌄' : '›';
      if (opening && !children.dataset.loaded) {
        children.dataset.loaded = 'true';
        await loadDirectory(item.path, children, depth + 1);
      }
    });
  } else {
    row.addEventListener('click', () => openFile(item.path, row));
  }
  return wrapper;
}

async function openFile(path, row = null, options = {}) {
  const {line = null, preserveAnalysis = false} = options;
  if (state.editing && state.editDirty && !window.confirm(t('discardChanges'))) return false;
  if (state.editing) finishEditing();
  try {
    const data = await (await api(`/api/file?path=${encodeURIComponent(path)}`)).json();
    state.file = data;
    if (!preserveAnalysis) state.reportTarget = {name: data.name, path: data.path};
    document.querySelectorAll('.tree-row.selected').forEach(el => el.classList.remove('selected'));
    if (row) row.classList.add('selected');
    $('#tabName').textContent = data.name;
    const fullPath = data.absolutePath || `${state.config.root.replace(/\/$/, '')}/${data.path}`;
    state.file.absolutePath = fullPath;
    $('#breadcrumbs').textContent = fullPath;
    $('#breadcrumbs').title = fullPath;
    $('#activeTab').title = fullPath;
    $('#copyPathButton').disabled = false;
    renderCodeContent(data.content);
    $('#languageLabel').textContent = data.language;
    $('#fileStats').textContent = `${t('lines', data.lines)}  ·  ${formatBytes(data.size)}`;
    $('#emptyState').classList.add('hidden');
    $('#codeWrap').classList.remove('hidden');
    $('#analyzeButton').disabled = false;
    $('#editFileButton').disabled = state.readOnly;
    updateGitStatus();
    if (!preserveAnalysis) {
      state.activeAnalysisTabId = null;
      renderAnalysisTabs();
      clearAnswer();
    }
    switchMobilePanel('editor');
    if (line) markCodeLine(line);
    scheduleWorkspaceSave();
    return true;
  } catch (error) {
    showAnswer(`### ${t('fileOpenFailed')}\n\n${error.message}`);
    return false;
  }
}

function renderCodeContent(content) {
  const lines = content.split('\n');
  $('#codeView').innerHTML = lines.map((line, index) =>
    `<span class="code-line" data-code-line="${index + 1}">${line ? escapeHtml(line) : ' '}</span>`
  ).join('');
  $('#lineNumbers').innerHTML = lines.map((_, index) =>
    `<span data-line-number="${index + 1}">${index + 1}</span>`
  ).join('');
}

function updateGitStatus(git = state.file?.git) {
  if (!git) {
    $('#gitStatus').textContent = 'Git: —';
    $('#gitCommitButton').disabled = true;
    return;
  }
  const branch = git.branch || 'detached';
  $('#gitStatus').textContent = `Git: ${branch} · ${git.dirty ? (git.status || t('gitModified')) : t('gitClean')}`;
  $('#gitCommitButton').disabled = state.readOnly || state.editing || !git.dirty;
}

function updateReadOnlyButton() {
  const button = $('#readOnlyButton');
  if (!button) return;
  button.classList.toggle('active', state.readOnly);
  button.setAttribute('aria-pressed', String(state.readOnly));
  button.textContent = state.readOnly ? `🔒 ${t('readOnly')}` : `🔓 ${t('editingEnabled')}`;
  button.title = t(state.readOnly ? 'unlockEditing' : 'lockEditing');
  $('#editFileButton').disabled = state.readOnly || !state.file;
  $('#loopButton').disabled = state.readOnly || state.loopRunning;
  updateGitStatus();
}

function loopIsRunning(status) {
  return ['queued', 'running'].includes(status);
}

function localizedLoopMessage(job) {
  const message = job?.message || '';
  if (state.language !== 'en' || !/[ぁ-んァ-ン一-龯]/.test(message)) return message;
  let match;
  if ((match = message.match(/^Round (\d+): 安全に適用できる変更はありませんでした$/))) return `Round ${match[1]}: no further safe changes were found`;
  if ((match = message.match(/^Round (\d+): 実質的な変更はありませんでした$/))) return `Round ${match[1]}: no effective changes were produced`;
  if ((match = message.match(/^Round (\d+): (\d+)モデルで解析中$/))) return `Round ${match[1]}: analyzing with ${match[2]} models`;
  if ((match = message.match(/^Round (\d+): 改善案を統合中$/))) return `Round ${match[1]}: consolidating improvements`;
  if ((match = message.match(/^Round (\d+): テスト実行中$/))) return `Round ${match[1]}: running tests`;
  if ((match = message.match(/^Round (\d+)を解析中$/))) return `Analyzing Round ${match[1]}`;
  if (message === 'Loopを開始しています') return 'Starting Loop';
  if (message === 'Loopを停止しました') return 'Loop stopped';
  if (message === '停止要求を受け付けました') return 'Stop requested';
  if (message.includes('編集許可されていないファイルです')) return message.replace('編集許可されていないファイルです', 'File is not authorized for editing');
  return `Loop ${job?.status || 'status'} (saved message was generated in Japanese)`;
}

function loopStatusMarkdown(job) {
  const rounds = job.rounds || [];
  const lastRound = rounds.at(-1);
  const requestedRounds = job.requestedRounds || rounds.length;
  const displayMessage = localizedLoopMessage(job);
  let outcome = displayMessage;
  if (job.status === 'completed' && lastRound?.status === 'no_changes') {
    outcome = t('loopNoChangesOutcome', rounds.length, requestedRounds);
  } else if (job.status === 'completed') {
    outcome = t('loopAllRoundsOutcome', rounds.length);
  } else if (job.status === 'failed') {
    outcome = t('loopFailedOutcome', displayMessage);
  } else if (['cancelled', 'interrupted'].includes(job.status)) {
    outcome = t('loopCancelledOutcome');
  }
  const lastCommit = [...rounds].reverse().find(round => round.commit)?.commit || '—';
  const appliedChanges = rounds.flatMap(round => (round.changes || []).map(change => ({...change, round: round.number, commit: round.commit || ''})));
  const noChangeRounds = rounds.filter(round => round.status === 'no_changes');
  const notRunRounds = Array.from({length: Math.max(0, requestedRounds - rounds.length)}, (_, index) => rounds.length + index + 1);
  const lines = [
    `# ${t('loopSummary')}`, '',
    `## ${t('loopOutcome')}`, '',
    outcome,
    '', `- Rounds: **${rounds.length} / ${requestedRounds}**`,
    `- Last commit: \`${lastCommit}\``, '',
    `- Status: **${job.status || 'idle'}**`,
    `- Target: \`${job.targetPath || ''}\``,
    `- Branch: \`${job.branch || '—'}\``,
    `- Models: ${(job.models || []).map(model => `\`${model}\``).join(', ') || '—'}`,
    '', displayMessage, '',
    `## ${t('loopConcreteChanges')}`, '',
  ];
  if (appliedChanges.length) {
    for (const change of appliedChanges) {
      const stats = Number.isInteger(change.additions) && Number.isInteger(change.deletions)
        ? ` (+${change.additions} / -${change.deletions})` : '';
      const commit = change.commit.match(/\b[0-9a-f]{7,40}\b/)?.[0];
      lines.push(`- **Round ${change.round}** · \`${change.path}\`${stats}: ${change.reason || ''}${commit ? ` — commit \`${commit}\`` : ''}`);
    }
  } else {
    lines.push(t('loopNoConcreteChanges'));
  }
  if (noChangeRounds.length) {
    lines.push('', `## ${t('loopNoChangeDecisions')}`, '');
    for (const round of noChangeRounds) lines.push(`- **Round ${round.number}**: ${round.summary || t('loopNoConcreteChanges')}`);
  }
  if (notRunRounds.length) lines.push('', `- ${t('loopNotRun', notRunRounds)}`);
  for (const round of rounds) {
    lines.push('', `## ${t('loopRound', round.number)}`, '', round.summary || '');
    if (round.changes?.length) lines.push('', '### Changes', ...round.changes.map(change => `- \`${change.path}\`: ${change.reason || ''}`));
    if (round.tests) lines.push('', '### Tests', `- Status: **${round.tests.status}**`, `- Command: \`${(round.tests.command || []).join(' ')}\``, '', '```text', (round.tests.output || '').slice(-5000), '```');
    if (round.commit) lines.push('', `- Commit: \`${round.commit}\``);
  }
  return lines.join('\n');
}

function loopRoundMarkdown(round) {
  const lines = [`# ${t('loopRound', round.number)}`, '', round.summary || ''];
  if (round.integrationAttempts?.length) {
    lines.push('', `## ${t('loopIntegrationAttempts')}`);
    for (const attempt of round.integrationAttempts) lines.push(`- \`${attempt.model}\`: **${attempt.status}**${attempt.error ? ` — ${attempt.error}` : ''}`);
  }
  for (const analysis of round.analyses || []) lines.push('', `## ${analysis.model} · ${analysis.status}`, '', analysis.content || '');
  if (round.changes?.length) lines.push('', '## Changes', ...round.changes.map(change => `- \`${change.path}\`: ${change.reason || ''}`));
  if (round.tests) lines.push('', '## Tests', `**${round.tests.status}** — \`${(round.tests.command || []).join(' ')}\``, '', '```text', (round.tests.output || '').slice(-10000), '```');
  if (round.commit) lines.push('', '## Commit', `\`${round.commit}\``);
  return lines.join('\n');
}

function upsertLoopTab(tab) {
  if (state.dismissedAnalysisTabIds.has(tab.id)) return;
  const existing = findAnalysisTab(tab.id);
  if (existing) Object.assign(existing, tab);
  else {
    while (state.analysisTabs.length >= MAX_ANALYSIS_TABS) state.analysisTabs.shift()?.controller?.abort();
    state.analysisTabs.push(tab);
  }
}

function renderLoopJob(job) {
  if (!job?.id) return;
  const streaming = loopIsRunning(job.status);
  const hadJobTabs = state.analysisTabs.some(tab => tab.groupId === job.id);
  const common = {
    model: (job.models || []).join(', '), host: job.host || '', language: state.language,
    projectRoot: job.repository || state.config?.root || '', groupId: job.id, controller: null,
    reportTarget: {name: projectName(job.targetPath || 'Loop'), path: job.targetPath || ''},
  };
  upsertLoopTab({
    ...common, id: `${job.id}-summary`, title: `${projectName(job.targetPath || 'Loop')} · ${t('loopSummary')}`,
    displayTitle: t('loopSummary'), content: loopStatusMarkdown(job), metaText: localizedLoopMessage(job), mode: 'loop',
    tabRole: 'summary', status: streaming ? 'streaming' : (job.status === 'failed' ? 'failed' : 'complete'),
  });
  for (const round of job.rounds || []) {
    const roundStatus = !streaming && round.status === 'analyzing' ? job.status : round.status;
    upsertLoopTab({
      ...common, id: `${job.id}-round-${round.number}`, title: `${t('loopRound', round.number)} · ${projectName(job.targetPath || '')}`,
      displayTitle: t('loopRound', round.number), content: loopRoundMarkdown({...round, status: roundStatus}), metaText: roundStatus || '', mode: 'loop',
      tabRole: 'model', status: roundStatus === 'analyzing' ? 'streaming' : (roundStatus === 'failed' ? 'failed' : 'complete'),
    });
  }
  state.loopJob = job;
  state.loopRunning = streaming;
  $('#loopButton').disabled = state.readOnly || streaming;
  $('#stopLoopButton').hidden = !streaming;
  $('#assistantMeta').textContent = localizedLoopMessage(job);
  renderAnalysisTabs();
  const activeTabStillExists = Boolean(findAnalysisTab(state.activeAnalysisTabId));
  if ((!hadJobTabs || !activeTabStillExists) && findAnalysisTab(`${job.id}-summary`)) {
    activateAnalysisTab(`${job.id}-summary`);
  }
  scheduleWorkspaceSave();
}

async function pollLoopStatus() {
  clearTimeout(loopPollTimer);
  try {
    const job = await (await api('/api/loop/status')).json();
    if (job?.id) renderLoopJob(job);
    else {
      state.loopRunning = false;
      $('#loopButton').disabled = state.readOnly;
      $('#stopLoopButton').hidden = true;
    }
    if (loopIsRunning(job?.status)) loopPollTimer = setTimeout(pollLoopStatus, 1200);
  } catch (_) {
    state.loopRunning = false;
  }
}

async function startLoop(path = '', targetType = 'project') {
  if (state.readOnly) {
    $('#assistantMeta').textContent = t('loopReadOnly');
    return;
  }
  const target = targetType === 'file' ? (state.file?.absolutePath || path) : absoluteProjectPath(path);
  if (!window.confirm(t('loopConfirm', target))) return;
  $('#loopButton').disabled = true;
  $('#assistantMeta').textContent = t('loopStarting');
  switchMobilePanel('assistant');
  try {
    const response = await api('/api/loop/start', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({path, targetType, rounds: 3, models: improvementModels().slice(0, 3), language: state.language}),
    });
    renderLoopJob(await response.json());
    loopPollTimer = setTimeout(pollLoopStatus, 600);
  } catch (error) {
    $('#assistantMeta').textContent = `${t('loopFailed')}: ${error.message}`;
    $('#loopButton').disabled = state.readOnly;
  }
}

async function stopLoop() {
  try {
    const response = await api('/api/loop/cancel', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'});
    renderLoopJob(await response.json());
    loopPollTimer = setTimeout(pollLoopStatus, 500);
  } catch (error) {
    $('#assistantMeta').textContent = error.message;
  }
}

async function setReadOnly(enabled) {
  if (enabled && state.editing && state.editDirty && !window.confirm(t('discardChanges'))) return;
  if (state.editing) finishEditing();
  try {
    const response = await api('/api/read-only', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({readOnly: enabled}),
    });
    const result = await response.json();
    state.readOnly = result.readOnly;
    updateReadOnlyButton();
    $('#assistantMeta').textContent = t(state.readOnly ? 'readOnlyOn' : 'readOnlyOff');
  } catch (error) {
    $('#assistantMeta').textContent = error.message;
  }
}

function startEditing() {
  if (!state.file || state.readOnly) return;
  state.editing = true;
  state.editDirty = false;
  $('#codeEditor').value = state.file.content;
  $('#codeEditor').hidden = false;
  $('#codeWrap').classList.add('editing');
  $('#editFileButton').hidden = true;
  $('#saveFileButton').hidden = false;
  $('#saveFileButton').disabled = true;
  $('#cancelEditButton').hidden = false;
  $('#gitCommitButton').disabled = true;
  $('#analyzeButton').disabled = true;
  $('#codeEditor').focus();
}

function finishEditing() {
  state.editing = false;
  state.editDirty = false;
  $('#codeEditor').hidden = true;
  $('#codeWrap').classList.remove('editing');
  $('#editFileButton').hidden = false;
  $('#saveFileButton').hidden = true;
  $('#cancelEditButton').hidden = true;
  $('#editFileButton').disabled = state.readOnly || !state.file;
  $('#analyzeButton').disabled = !state.file;
  $('.file-dot')?.classList.remove('dirty');
  updateGitStatus();
}

function cancelEditing() {
  if (state.editDirty && !window.confirm(t('discardChanges'))) return;
  finishEditing();
}

async function saveEditedFile() {
  if (!state.file || state.readOnly || !state.editDirty) return;
  const button = $('#saveFileButton');
  button.disabled = true;
  try {
    const response = await api('/api/file/save', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({path: state.file.path, content: $('#codeEditor').value, fingerprint: state.file.fingerprint}),
    });
    const result = await response.json();
    state.file = {...state.file, content: $('#codeEditor').value, ...result};
    renderCodeContent(state.file.content);
    $('#fileStats').textContent = `${t('lines', result.lines)}  ·  ${formatBytes(result.size)}`;
    finishEditing();
    $('#assistantMeta').textContent = t('fileSaved');
    scheduleWorkspaceSave();
  } catch (error) {
    button.disabled = false;
    $('#assistantMeta').textContent = `${t('saveFailed')}: ${error.message}`;
  }
}

function openCommitDialog() {
  if (state.readOnly || !state.file?.git?.dirty) return;
  $('#commitPath').textContent = state.file.absolutePath || state.file.path;
  $('#commitMessage').value = `Update ${state.file.name}`;
  $('#commitError').textContent = '';
  $('#commitDialog').showModal();
  setTimeout(() => { $('#commitMessage').focus(); $('#commitMessage').select(); }, 0);
}

function showTreeContextMenu(event, item, row) {
  event.preventDefault();
  event.stopPropagation();
  const menu = $('#treeContextMenu');
  const isDirectory = item.type === 'directory';
  const isPythonFile = !isDirectory && item.name.toLowerCase().endsWith('.py');
  const projectPath = isDirectory ? absoluteProjectPath(item.path) : '';
  const projectPinned = Boolean(projectPath && state.pinnedProjects.includes(projectPath));
  menu.innerHTML = `
    <div class="menu-label">${escapeHtml(item.path || state.config?.root || item.name)}</div>
    ${isDirectory ? `
      <button role="menuitem" data-menu-action="pin"><span class="menu-icon">${projectPinned ? '★' : '☆'}</span>${t(projectPinned ? 'unpinProject' : 'pinProject')}</button>
      <button role="menuitem" data-menu-action="loop-project"><span class="menu-icon">↻</span>${t('loopProject')}</button>
      <div class="menu-separator"></div>
      <button role="menuitem" data-menu-action="project"><span class="menu-icon">✦</span>${t('folderSummary')}</button>
      <button role="menuitem" data-menu-action="project-improve"><span class="menu-icon">⇧</span>${t('projectImprove')}</button>
    ` : `
      <button role="menuitem" data-menu-action="open"><span class="menu-icon">↗</span>${t('open')}</button>
      ${isPythonFile ? `<button role="menuitem" data-menu-action="loop-file"><span class="menu-icon">↻</span>${t('loopFile')}</button>` : ''}
      <div class="menu-separator"></div>
      <button role="menuitem" data-menu-action="summary"><span class="menu-icon">≡</span>${t('summary')}</button>
      <button role="menuitem" data-menu-action="explain"><span class="menu-icon">◎</span>${t('explain')}</button>
      <button role="menuitem" data-menu-action="review"><span class="menu-icon">◇</span>${t('review')}</button>
      <button role="menuitem" data-menu-action="improve"><span class="menu-icon">⇧</span>${t('improve')}</button>
    `}`;
  menu.classList.add('open');
  const rect = menu.getBoundingClientRect();
  menu.style.left = `${Math.max(6, Math.min(event.clientX, window.innerWidth - rect.width - 6))}px`;
  menu.style.top = `${Math.max(6, Math.min(event.clientY, window.innerHeight - rect.height - 6))}px`;
  menu.querySelectorAll('[data-menu-action]').forEach(button => button.addEventListener('click', async () => {
    const action = button.dataset.menuAction;
    closeTreeContextMenu();
    if (action === 'pin') {
      toggleProjectPin(projectPath);
      return;
    }
    if (action === 'loop-project') {
      await startLoop(item.path, 'project');
      return;
    }
    if (action === 'loop-file') {
      const opened = await openFile(item.path, row);
      if (opened) await startLoop(item.path, 'file');
      return;
    }
    if (action === 'project') {
      switchMobilePanel('assistant');
      await analyzeProject(item.path);
      return;
    }
    if (action === 'project-improve') {
      await analyzeProjectImprovements(item.path);
      return;
    }
    const opened = await openFile(item.path, row);
    if (opened && action !== 'open') await analyze(action);
  }));
  menu.querySelector('button')?.focus();
}

function closeTreeContextMenu() {
  $('#treeContextMenu').classList.remove('open');
}

function improvementModels() {
  const selected = $('#modelSelect').value;
  const paidModels = new Set(['kimi-k3']);
  const available = Array.from($('#modelSelect').options).map(option => option.value)
    .filter(model => model && !paidModels.has(model));
  const automatic = available.filter(model =>
    /(coder|code|gpt-oss|qwen|deepseek|kimi|gemma|glm|minimax)/i.test(model)
  );
  const selectedForRun = paidModels.has(selected) ? '' : selected;
  return [...new Set([selectedForRun, ...automatic, ...available].filter(model => model && !paidModels.has(model)))];
}

function moveSummaryBeforeGroup(summaryTab, groupId) {
  const currentIndex = state.analysisTabs.indexOf(summaryTab);
  if (currentIndex < 0) return;
  state.analysisTabs.splice(currentIndex, 1);
  const firstChild = state.analysisTabs.findIndex(tab => tab.groupId === groupId);
  state.analysisTabs.splice(firstChild < 0 ? state.analysisTabs.length : firstChild, 0, summaryTab);
  renderAnalysisTabs();
}

function consensusPrompt(results) {
  return results.map((result, index) => {
    const tab = findAnalysisTab(result.tabId);
    return `## Model ${index + 1}: ${result.model}\n\n${(tab?.content || result.content || '').slice(0, 30000)}`;
  }).join('\n\n---\n\n');
}

async function analyzeWithModels() {
  if (!state.file) return;
  if (state.improvementRunning) {
    const running = [...state.analysisTabs].reverse().find(tab => tab.mode === 'improve' && tab.status === 'streaming');
    if (running) activateAnalysisTab(running.id);
    $('#assistantMeta').textContent = t('improvementAlreadyRunning');
    switchMobilePanel('assistant');
    return;
  }
  const models = improvementModels();
  if (!models.length) return;
  const fileSnapshot = {...state.file};
  const selection = getSelectedCode();
  const groupId = `improvement-group-${Date.now()}`;
  const successfulResults = [];
  state.improvementRunning = true;
  $('#analyzeButton').disabled = true;
  $('#assistantMeta').textContent = t('improvementStarting', models.length);
  switchMobilePanel('assistant');
  try {
    let nextIndex = 0;
    let completed = 0;
    let tried = 0;
    while (completed < 3 && nextIndex < models.length) {
      const batch = models.slice(nextIndex, nextIndex + (3 - completed));
      nextIndex += batch.length;
      tried += batch.length;
      const results = await Promise.all(batch.map(model => analyze('improve', '', {
        model, selection, file: fileSnapshot, groupId, tabRole: 'model', displayTitle: model, timeoutMs: 45000,
      })));
      const successful = results.filter(result => result?.success);
      successfulResults.push(...successful);
      completed += successful.length;
    }
    const target = {name: fileSnapshot.name, path: fileSnapshot.path};
    if (successfulResults.length) {
      $('#assistantMeta').textContent = t('integratingResults');
      const summaryModelCandidates = [...new Set(successfulResults.map(result => result.model))];
      const summaryTab = createAnalysisTab('consensus', target, summaryModelCandidates[0], {
        groupId,
        tabRole: 'summary',
        title: `${target.name} · ${t('integratedResult')}`,
        displayTitle: `✦ ${t('integratedResult')}`,
      });
      moveSummaryBeforeGroup(summaryTab, groupId);
      let summaryResult = null;
      for (const model of summaryModelCandidates) {
        summaryResult = await analyze('consensus', consensusPrompt(successfulResults), {
          model,
          selection,
          file: fileSnapshot,
          existingTab: summaryTab,
          timeoutMs: 60000,
        });
        if (summaryResult?.success) break;
      }
      activateAnalysisTab(summaryTab.id);
    } else {
      const summaryTab = createAnalysisTab('consensus', target, '', {
        groupId,
        tabRole: 'summary',
        title: `${target.name} · ${t('integratedResult')}`,
        displayTitle: `✦ ${t('integratedResult')}`,
      });
      summaryTab.content = t('noIntegratedResult');
      summaryTab.status = 'complete';
      moveSummaryBeforeGroup(summaryTab, groupId);
      activateAnalysisTab(summaryTab.id);
    }
    $('#assistantMeta').textContent = t('improvementComplete', completed, tried);
  } finally {
    state.improvementRunning = false;
    $('#analyzeButton').disabled = !state.file;
  }
}

async function analyze(mode = state.mode, question = '', options = {}) {
  const sourceFile = options.file || state.file;
  if (!sourceFile) return;
  if (mode === 'improve' && !options.model) return analyzeWithModels();
  const requestedModel = options.model || $('#modelSelect').value;
  const controller = new AbortController();
  let timedOut = false;
  const timeoutId = options.timeoutMs ? setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, options.timeoutMs) : null;
  state.lastMode = mode;
  state.reportTarget = {name: sourceFile.name, path: sourceFile.path};
  const analysisTab = options.existingTab || createAnalysisTab(mode, state.reportTarget, requestedModel, options);
  if (options.existingTab) {
    analysisTab.content = '';
    analysisTab.metaText = '';
    analysisTab.model = requestedModel;
    analysisTab.status = 'streaming';
    analysisTab.controller?.abort();
    state.activeAnalysisTabId = analysisTab.id;
    renderAnalysisTabs();
  }
  let success = false;
  let failed = false;
  analysisTab.controller = controller;
  const button = $('#analyzeButton');
  $('#answer').classList.add('loading');
  state.answerRaw = '';
  showAnswer('');
  $('#assistantMeta').textContent = t('askOllama');
  switchMobilePanel('assistant');
  try {
    const response = await api('/api/analyze', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      signal: controller.signal,
      body: JSON.stringify({
        path: sourceFile.path,
        mode,
        question,
        model: requestedModel,
        language: state.language,
        selection: options.selection ?? getSelectedCode(),
      }),
    });
    await consumeAnalysisResponse(response, analysisTab.id);
    if (!analysisTab.content) {
      analysisTab.content = t('emptyResponse');
      failed = true;
      if (state.activeAnalysisTabId === analysisTab.id) showAnswer(analysisTab.content);
    } else success = true;
  } catch (error) {
    failed = true;
    if (error.name === 'AbortError' && timedOut) {
      analysisTab.content = `### ${t('analysisFailed')}\n\n${t('analysisTimedOut', Math.round(options.timeoutMs / 1000))}`;
      if (state.activeAnalysisTabId === analysisTab.id) showAnswer(analysisTab.content);
    } else if (error.name !== 'AbortError') {
      analysisTab.content = `### ${t('analysisFailed')}\n\n${error.message}`;
      if (state.activeAnalysisTabId === analysisTab.id) showAnswer(analysisTab.content);
    }
  } finally {
    if (timeoutId) clearTimeout(timeoutId);
    analysisTab.status = failed ? 'failed' : 'complete';
    analysisTab.controller = null;
    renderAnalysisTabs();
    if (state.activeAnalysisTabId === analysisTab.id) $('#answer').classList.remove('loading');
    button.disabled = !state.file || state.improvementRunning;
  }
  return {success, model: requestedModel, tabId: analysisTab.id, content: analysisTab.content};
}

async function analyzeProject(relativePath = '') {
  if (!state.config || !$('#modelSelect').value) return;
  const normalizedPath = relativePath.replace(/^\/+|\/+$/g, '');
  const targetName = normalizedPath ? normalizedPath.split('/').pop() : state.config.rootName;
  const targetPath = normalizedPath ? `${state.config.root}/${normalizedPath}` : state.config.root;
  state.lastMode = 'project';
  state.reportTarget = {name: targetName, path: targetPath};
  const cacheKey = `project-summary:${state.language}:${targetPath}`;
  const cached = sessionStorage.getItem(cacheKey);
  if (cached) {
    const cachedTab = createAnalysisTab('project', state.reportTarget);
    cachedTab.content = cached;
    cachedTab.metaText = t('cachedSummary');
    cachedTab.status = 'complete';
    activateAnalysisTab(cachedTab.id);
    return;
  }
  const analysisTab = createAnalysisTab('project', state.reportTarget);
  const controller = new AbortController();
  analysisTab.controller = controller;
  $('#answer').classList.add('loading');
  state.answerRaw = '';
  $('#answer').innerHTML = renderMarkdown(t('projectAnalyzing'));
  setExportEnabled(false);
  $('#assistantMeta').textContent = t('projectSending');
  try {
    const response = await api('/api/project-summary', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      signal: controller.signal,
      body: JSON.stringify({model: $('#modelSelect').value, path: normalizedPath, root: state.config.root, language: state.language}),
    });
    state.answerRaw = '';
    await consumeAnalysisResponse(response, analysisTab.id);
    if (analysisTab.content) sessionStorage.setItem(cacheKey, analysisTab.content);
    else {
      analysisTab.content = t('projectEmpty');
      if (state.activeAnalysisTabId === analysisTab.id) showAnswer(analysisTab.content);
    }
  } catch (error) {
    if (error.name !== 'AbortError') {
      analysisTab.content = `### ${t('projectFailed')}\n\n${error.message}`;
      if (state.activeAnalysisTabId === analysisTab.id) showAnswer(analysisTab.content);
    }
  } finally {
    analysisTab.status = 'complete';
    analysisTab.controller = null;
    renderAnalysisTabs();
    if (state.activeAnalysisTabId === analysisTab.id) $('#answer').classList.remove('loading');
    $('#analyzeButton').disabled = !state.file;
  }
}

function projectTargetInfo(relativePath, config = state.config) {
  const path = relativePath.replace(/^\/+|\/+$/g, '');
  const name = path ? path.split('/').pop() : config.rootName;
  return {relativePath: path, target: {name, path: path ? `${config.root}/${path}` : config.root}};
}

async function analyzeProjectWithModel(mode, project, model, options = {}) {
  const controller = new AbortController();
  let timedOut = false;
  const timeoutId = options.timeoutMs ? setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, options.timeoutMs) : null;
  const tabMode = mode === 'consensus' ? 'project-consensus' : 'project-improve';
  const analysisTab = options.existingTab || createAnalysisTab(tabMode, project.target, model, options);
  if (options.existingTab) {
    analysisTab.content = '';
    analysisTab.metaText = '';
    analysisTab.model = model;
    analysisTab.status = 'streaming';
    analysisTab.controller?.abort();
    state.activeAnalysisTabId = analysisTab.id;
    renderAnalysisTabs();
  }
  analysisTab.controller = controller;
  state.reportTarget = {...project.target};
  state.lastMode = tabMode;
  state.answerRaw = '';
  $('#answer').classList.add('loading');
  showAnswer('');
  switchMobilePanel('assistant');
  let success = false;
  let failed = false;
  try {
    const response = await api('/api/project-summary', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      signal: controller.signal,
      body: JSON.stringify({
        model,
        mode,
        reports: options.reports || '',
        path: project.relativePath,
        root: project.config.root,
        language: state.language,
      }),
    });
    await consumeAnalysisResponse(response, analysisTab.id);
    if (analysisTab.content) success = true;
    else {
      failed = true;
      analysisTab.content = t('emptyResponse');
      if (state.activeAnalysisTabId === analysisTab.id) showAnswer(analysisTab.content);
    }
  } catch (error) {
    failed = true;
    analysisTab.content = error.name === 'AbortError' && timedOut
      ? `### ${t('analysisFailed')}\n\n${t('analysisTimedOut', Math.round(options.timeoutMs / 1000))}`
      : `### ${t('analysisFailed')}\n\n${error.message || String(error)}`;
    if (state.activeAnalysisTabId === analysisTab.id) showAnswer(analysisTab.content);
  } finally {
    if (timeoutId) clearTimeout(timeoutId);
    analysisTab.status = failed ? 'failed' : 'complete';
    analysisTab.controller = null;
    renderAnalysisTabs();
    if (state.activeAnalysisTabId === analysisTab.id) $('#answer').classList.remove('loading');
  }
  return {success, model, tabId: analysisTab.id, content: analysisTab.content};
}

async function analyzeProjectImprovements(relativePath = '') {
  if (!state.config || state.improvementRunning) {
    if (state.improvementRunning) $('#assistantMeta').textContent = t('improvementAlreadyRunning');
    switchMobilePanel('assistant');
    return;
  }
  const models = improvementModels();
  if (!models.length) return;
  const config = {...state.config};
  const info = projectTargetInfo(relativePath, config);
  const project = {...info, config};
  const groupId = `project-improvement-${Date.now()}`;
  const successfulResults = [];
  state.improvementRunning = true;
  $('#analyzeButton').disabled = true;
  $('#projectImproveButton').disabled = true;
  $('#assistantMeta').textContent = t('projectImproving', models.length);
  switchMobilePanel('assistant');
  let completed = 0;
  let tried = 0;
  try {
    let nextIndex = 0;
    while (completed < 3 && nextIndex < models.length) {
      const batch = models.slice(nextIndex, nextIndex + (3 - completed));
      nextIndex += batch.length;
      tried += batch.length;
      const results = await Promise.all(batch.map(model => analyzeProjectWithModel('improve', project, model, {
        groupId,
        tabRole: 'model',
        displayTitle: model,
        timeoutMs: 90000,
      })));
      const successful = results.filter(result => result.success);
      successfulResults.push(...successful);
      completed += successful.length;
    }
    const summaryModels = [...new Set(successfulResults.map(result => result.model))];
    const summaryTab = createAnalysisTab('project-consensus', project.target, summaryModels[0] || '', {
      groupId,
      tabRole: 'summary',
      title: `${project.target.name} · ${t('integratedResult')}`,
      displayTitle: `✦ ${t('integratedResult')}`,
    });
    moveSummaryBeforeGroup(summaryTab, groupId);
    if (successfulResults.length) {
      const reports = consensusPrompt(successfulResults);
      for (const model of summaryModels) {
        const result = await analyzeProjectWithModel('consensus', project, model, {
          existingTab: summaryTab,
          reports,
          timeoutMs: 90000,
        });
        if (result.success) break;
      }
    } else {
      summaryTab.content = t('noIntegratedResult');
      summaryTab.status = 'failed';
    }
    activateAnalysisTab(summaryTab.id);
    $('#assistantMeta').textContent = t('improvementComplete', completed, tried);
  } finally {
    state.improvementRunning = false;
    $('#analyzeButton').disabled = !state.file;
    $('#projectImproveButton').disabled = false;
  }
}

async function consumeAnalysisResponse(response, tabId) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const {value, done} = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), {stream: !done});
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';
    for (const line of lines) {
      if (!line.trim()) continue;
      const chunk = JSON.parse(line);
      const tab = findAnalysisTab(tabId);
      if (!tab) continue;
      if (chunk.meta) {
        tab.host = new URL(chunk.meta.host).hostname;
        tab.model = chunk.meta.model;
        tab.metaText = `${tab.host} · ${tab.model}`;
        if (state.activeAnalysisTabId === tabId) $('#assistantMeta').textContent = tab.metaText;
      }
      if (chunk.content) {
        tab.content += chunk.content;
        if (state.activeAnalysisTabId === tabId) {
          state.answerRaw = tab.content;
          showAnswer(tab.content);
          $('#answer').scrollTop = $('#answer').scrollHeight;
        }
      }
    }
    if (done) break;
  }
}

function getSelectedCode() {
  const selection = window.getSelection();
  if (!selection || selection.isCollapsed || !$('#codeWrap').contains(selection.anchorNode)) return '';
  return selection.toString();
}

function clearAnswer() {
  state.answerRaw = '';
  $('#answer').classList.remove('loading');
  $('#answer').innerHTML = `<div class="answer-placeholder"><div class="orb">✦</div><p>${t('readyAnswer')}</p></div>`;
  $('#assistantMeta').textContent = '';
  setExportEnabled(false);
}

function showAnswer(markdown) {
  $('#answer').innerHTML = renderMarkdown(markdown);
  linkifyAnswerReferences();
  setExportEnabled(Boolean(markdown && state.reportTarget));
  scheduleWorkspaceSave();
}

const FILE_REFERENCE_PATTERN = /(?:[\w@.+-]+\/)*[\w@.+-]+\.(?:py|js|mjs|cjs|jsx|ts|tsx|go|rs|java|kt|c|h|cpp|hpp|cs|rb|php|swift|vue|svelte|sh|json|toml|ya?ml|md)(?:(?::|#L)\d+)?/g;
const SYMBOL_REFERENCE_PATTERN = /\b[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)?\(\)/g;

function referenceMatches(text) {
  const matches = [];
  for (const pattern of [FILE_REFERENCE_PATTERN, SYMBOL_REFERENCE_PATTERN]) {
    pattern.lastIndex = 0;
    for (const match of text.matchAll(pattern)) matches.push({start: match.index, text: match[0]});
  }
  matches.sort((a, b) => a.start - b.start || b.text.length - a.text.length);
  return matches.filter((match, index) => !matches.slice(0, index).some(previous =>
    match.start < previous.start + previous.text.length
  ));
}

function linkifyAnswerReferences() {
  const answer = $('#answer');
  answer.querySelectorAll('code:not(pre code)').forEach(code => {
    const value = code.textContent.trim();
    const matches = referenceMatches(value);
    const bareSymbol = /^[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)?$/.test(value);
    if (bareSymbol || (matches.length === 1 && matches[0].start === 0 && matches[0].text.length === value.length)) {
      code.classList.add('code-reference');
      code.dataset.codeReference = value;
      code.tabIndex = 0;
      code.setAttribute('role', 'link');
    }
  });
  const walker = document.createTreeWalker(answer, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) {
    const parent = walker.currentNode.parentElement;
    if (!parent?.closest('a, pre, [data-code-reference]')) nodes.push(walker.currentNode);
  }
  nodes.forEach(node => {
    const matches = referenceMatches(node.nodeValue || '');
    if (!matches.length) return;
    const fragment = document.createDocumentFragment();
    let offset = 0;
    for (const match of matches) {
      fragment.append((node.nodeValue || '').slice(offset, match.start));
      const link = document.createElement('a');
      link.href = '#';
      link.className = 'code-reference';
      link.dataset.codeReference = match.text;
      link.textContent = match.text;
      fragment.append(link);
      offset = match.start + match.text.length;
    }
    fragment.append((node.nodeValue || '').slice(offset));
    node.replaceWith(fragment);
  });
}

async function navigateToCodeReference(reference) {
  $('#assistantMeta').textContent = t('resolvingReference');
  const current = state.file?.path || '';
  try {
    const response = await api(`/api/resolve-reference?reference=${encodeURIComponent(reference)}&current=${encodeURIComponent(current)}`);
    const result = await response.json();
    const opened = await openFile(result.path, null, {line: result.line || 1, preserveAnalysis: true});
    if (opened) $('#assistantMeta').textContent = t('referenceOpened', result.path, result.line || 1);
  } catch (error) {
    $('#assistantMeta').textContent = `${t('referenceNotFound', reference)}${error.message ? ` — ${error.message}` : ''}`;
  }
}

function markCodeLine(line) {
  document.querySelectorAll('.reference-marker').forEach(element => element.classList.remove('reference-marker'));
  const number = Math.max(1, Number.parseInt(line, 10) || 1);
  const codeLine = $(`[data-code-line="${number}"]`);
  const gutterLine = $(`[data-line-number="${number}"]`);
  codeLine?.classList.add('reference-marker');
  gutterLine?.classList.add('reference-marker');
  codeLine?.scrollIntoView({block: 'center', inline: 'nearest', behavior: 'smooth'});
}

function setExportEnabled(enabled) {
  $('#saveMarkdownButton').disabled = !enabled;
  $('#savePdfButton').disabled = !enabled;
}

function reportTitle() {
  const label = {project: t('project'), 'project-improve': t('projectImprove'), 'project-consensus': t('integratedResult'), summary: t('summary'), explain: t('explain'), review: t('codeReview'), improve: t('improve'), consensus: t('integratedResult'), ask: t('answerQuestion')}[state.lastMode] || t('codeExplanation');
  return `${state.reportTarget?.name || 'code'} - ${label}`;
}

function safeBaseName() {
  const base = (state.reportTarget?.name || 'code').replace(/\.[^.]+$/, '');
  return base.replace(/[^a-zA-Z0-9\u3040-\u30ff\u3400-\u9fff_-]+/g, '_').slice(0, 80) || 'code';
}

function reportMetadata() {
  const tab = findAnalysisTab(state.activeAnalysisTabId);
  return {
    title: reportTitle(),
    path: state.reportTarget?.path || '',
    model: tab?.model || $('#modelSelect').value,
    host: tab?.host || $('#connectionText').textContent,
    created: new Date().toLocaleString(state.language === 'en' ? 'en-US' : 'ja-JP'),
  };
}

function saveMarkdown() {
  if (!state.answerRaw || !state.reportTarget) return;
  const meta = reportMetadata();
  const content = [
    `# ${meta.title}`,
    '',
    `- ${t('target')}: \`${meta.path}\``,
    `- ${t('model')}: \`${meta.model}\``,
    `- ${t('host')}: \`${meta.host}\``,
    `- ${t('created')}: ${meta.created}`,
    '',
    '---',
    '',
    state.answerRaw.trim(),
    '',
  ].join('\n');
  const blob = new Blob([content], {type: 'text/markdown;charset=utf-8'});
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${safeBaseName()}-analysis.md`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function savePdf() {
  if (!state.answerRaw || !state.reportTarget) return;
  const meta = reportMetadata();
  const popup = window.open('', '_blank', 'popup,width=920,height=760');
  if (!popup) {
    $('#assistantMeta').textContent = t('pdfBlocked');
    return;
  }
  const documentHtml = `<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><title>${escapeHtml(safeBaseName())}-analysis</title>
<style>
  @page { size: A4; margin: 18mm 17mm 19mm; }
  * { box-sizing: border-box; }
  body { margin: 0; color: #20242a; font-family: -apple-system, BlinkMacSystemFont, "Hiragino Sans", "Yu Gothic", "Noto Sans JP", sans-serif; font-size: 10.5pt; line-height: 1.72; }
  header { border-bottom: 2px solid #8bb52f; padding-bottom: 10mm; margin-bottom: 8mm; }
  h1 { margin: 0 0 3mm; font-size: 20pt; line-height: 1.3; }
  h2 { margin: 8mm 0 3mm; padding-bottom: 1.5mm; border-bottom: 1px solid #d7dce2; font-size: 15pt; break-after: avoid; }
  h3 { margin: 6mm 0 2mm; font-size: 12pt; break-after: avoid; }
  p { margin: 2.5mm 0; }
  ul, ol { padding-left: 7mm; }
  li { margin: 1mm 0; }
  code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 8.8pt; background: #f0f2f4; padding: .3mm 1mm; border-radius: 1mm; overflow-wrap: anywhere; }
  pre { padding: 4mm; border: 1px solid #d7dce2; border-radius: 2mm; background: #f7f8f9; white-space: pre-wrap; overflow-wrap: anywhere; break-inside: avoid; }
  pre code { padding: 0; background: transparent; }
  .meta { display: grid; grid-template-columns: 26mm 1fr; gap: 1.2mm 3mm; color: #5e6672; font-size: 8.5pt; }
  .meta dt { font-weight: 700; }
  .meta dd { margin: 0; overflow-wrap: anywhere; }
  .content > p:first-child { margin-top: 0; }
  footer { position: fixed; bottom: -12mm; left: 0; right: 0; text-align: right; color: #858c96; font-size: 7.5pt; }
  @media screen { body { max-width: 210mm; min-height: 297mm; margin: 12mm auto; padding: 18mm 17mm; box-shadow: 0 2mm 12mm #0003; } footer { display: none; } }
</style></head><body>
<header><h1>${escapeHtml(meta.title)}</h1>
<dl class="meta"><dt>${escapeHtml(t('target'))}</dt><dd>${escapeHtml(meta.path)}</dd><dt>${escapeHtml(t('model'))}</dt><dd>${escapeHtml(meta.model)}</dd><dt>${escapeHtml(t('host'))}</dt><dd>${escapeHtml(meta.host)}</dd><dt>${escapeHtml(t('created'))}</dt><dd>${escapeHtml(meta.created)}</dd></dl></header>
<main class="content">${renderMarkdown(state.answerRaw)}</main>
<footer>Generated by Ollama Code Browser</footer>
<script>window.addEventListener('load', () => setTimeout(() => window.print(), 250));<\/script>
</body></html>`;
  popup.document.open();
  popup.document.write(documentHtml);
  popup.document.close();
  $('#assistantMeta').textContent = t('pdfPrint');
}

function renderMarkdown(source) {
  if (!source) return '';
  let html = escapeHtml(source);
  html = html.replace(/```[^\n]*\n([\s\S]*?)```/g, '<pre><code>$1</code></pre>');
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/^[-*] (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>')
    .replace(/\n{2,}/g, '</p><p>')
    .replace(/\n/g, '<br>');
  return `<p>${html}</p>`.replace(/<p>\s*(<(?:h\d|pre|ul))/g, '$1').replace(/(<\/(?:h\d|pre|ul)>)\s*<\/p>/g, '$1');
}

function applyFilter() {
  const value = state.filter.trim().toLowerCase();
  document.querySelectorAll('.tree-row[data-name]').forEach(row => {
    row.classList.toggle('filtered-out', value && !row.dataset.name.includes(value));
  });
}

function showTreeError(message) { tree.innerHTML = `<div class="tree-row"><span>!</span><span>${escapeHtml(message)}</span></div>`; }
function formatBytes(bytes) { return bytes < 1024 ? `${bytes} B` : bytes < 1048576 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1048576).toFixed(1)} MB`; }
function fileIcon(name) { const ext = name.split('.').pop().toLowerCase(); return ['js','ts','tsx','jsx'].includes(ext) ? 'JS' : ['py'].includes(ext) ? 'Py' : ['md'].includes(ext) ? 'M↓' : ['json','yaml','yml','toml'].includes(ext) ? '{}' : '·'; }
function escapeHtml(value) { return String(value).replace(/[&<>"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[ch])); }

document.querySelectorAll('.action').forEach(button => button.addEventListener('click', () => {
  document.querySelectorAll('.action').forEach(el => el.classList.remove('active'));
  button.classList.add('active');
  state.mode = button.dataset.mode;
  updateAnalyzeLabel();
}));
$('#languageSelect').addEventListener('change', event => {
  state.language = event.target.value === 'en' ? 'en' : 'ja';
  localStorage.setItem('code-browser-language', state.language);
  applyLanguage();
});
$('#analyzeButton').addEventListener('click', () => analyze());
$('#loopButton').addEventListener('click', () => startLoop('', 'project'));
$('#stopLoopButton').addEventListener('click', stopLoop);
$('#askButton').addEventListener('click', () => { const q = $('#questionInput').value.trim(); if (q) analyze('ask', q); });
$('#questionInput').addEventListener('keydown', event => { if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') $('#askButton').click(); });
$('#clearButton').addEventListener('click', () => {
  if (state.activeAnalysisTabId) closeAnalysisTab(state.activeAnalysisTabId);
  else clearAnswer();
});
$('#fullscreenButton').addEventListener('click', () => toggleAssistantFullscreen());
$('#saveMarkdownButton').addEventListener('click', saveMarkdown);
$('#savePdfButton').addEventListener('click', savePdf);
$('#copyPathButton').addEventListener('click', async () => {
  if (!state.file?.absolutePath) return;
  try {
    await navigator.clipboard.writeText(state.file.absolutePath);
    $('#assistantMeta').textContent = t('pathCopied');
  } catch (_) {
    $('#assistantMeta').textContent = t('pathCopyFailed');
  }
});
$('#readOnlyButton').addEventListener('click', () => setReadOnly(!state.readOnly));
$('#editFileButton').addEventListener('click', startEditing);
$('#saveFileButton').addEventListener('click', saveEditedFile);
$('#cancelEditButton').addEventListener('click', cancelEditing);
$('#gitCommitButton').addEventListener('click', openCommitDialog);
$('#codeEditor').addEventListener('input', () => {
  state.editDirty = $('#codeEditor').value !== state.file?.content;
  $('#saveFileButton').disabled = state.readOnly || !state.editDirty;
  $('.file-dot')?.classList.toggle('dirty', state.editDirty);
});
$('#codeEditor').addEventListener('keydown', event => {
  if (event.key === 'Tab') {
    event.preventDefault();
    const editor = event.currentTarget;
    const start = editor.selectionStart;
    editor.setRangeText('  ', start, editor.selectionEnd, 'end');
    editor.dispatchEvent(new Event('input'));
  }
});
$('#commitForm').addEventListener('submit', async event => {
  event.preventDefault();
  if (event.submitter?.value === 'cancel') {
    $('#commitDialog').close();
    return;
  }
  if (state.readOnly || !state.file) return;
  const button = $('#confirmCommitButton');
  button.disabled = true;
  $('#commitError').textContent = '';
  try {
    const response = await api('/api/git/commit', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({path: state.file.path, message: $('#commitMessage').value.trim()}),
    });
    const result = await response.json();
    state.file.git = result.git;
    updateGitStatus();
    $('#commitDialog').close();
    $('#assistantMeta').textContent = `${t('committed')}${result.output ? ` — ${result.output.split('\n')[0]}` : ''}`;
  } catch (error) {
    $('#commitError').textContent = error.message;
  } finally {
    button.disabled = false;
  }
});
$('#answer').addEventListener('click', event => {
  const reference = event.target.closest('[data-code-reference]');
  if (!reference) return;
  event.preventDefault();
  navigateToCodeReference(reference.dataset.codeReference);
});
$('#answer').addEventListener('keydown', event => {
  const reference = event.target.closest('[data-code-reference]');
  if (!reference || !['Enter', ' '].includes(event.key)) return;
  event.preventDefault();
  navigateToCodeReference(reference.dataset.codeReference);
});
$('#refreshButton').addEventListener('click', () => loadDirectory('', tree, 0));
$('#projectImproveButton').addEventListener('click', () => analyzeProjectImprovements(''));
function showRootProjectMenu(event) {
  const config = state.config;
  if (!config) return;
  showTreeContextMenu(event, {name: config.rootName, path: '', type: 'directory'}, null);
}
$('#rootProjectMenuButton').addEventListener('click', event => {
  const rect = event.currentTarget.getBoundingClientRect();
  showRootProjectMenu({preventDefault() {}, stopPropagation() {}, clientX: rect.right, clientY: rect.bottom});
});
$('#rootPath').addEventListener('contextmenu', showRootProjectMenu);
$('#explorerLabel').addEventListener('contextmenu', showRootProjectMenu);
tree.addEventListener('contextmenu', event => {
  if (event.target === tree) showRootProjectMenu(event);
});
$('#parentButton').addEventListener('click', () => {
  if (state.config?.parent && state.config.parent !== state.config.root) changeRoot(state.config.parent);
});
$('#openFolderButton').addEventListener('click', () => {
  $('#folderPath').value = state.config?.root || '';
  $('#folderError').textContent = '';
  $('#folderDialog').showModal();
  setTimeout(() => { $('#folderPath').focus(); $('#folderPath').select(); }, 0);
});
$('#folderForm').addEventListener('submit', event => {
  event.preventDefault();
  if (event.submitter?.value === 'cancel') {
    $('#folderDialog').close();
    return;
  }
  changeRoot($('#folderPath').value.trim());
});
document.querySelectorAll('[data-folder]').forEach(button => button.addEventListener('click', () => {
  $('#folderPath').value = button.dataset.folder;
  $('#folderPath').focus();
}));
document.querySelectorAll('.mobile-nav [data-mobile-panel]').forEach(button => {
  button.addEventListener('click', () => switchMobilePanel(button.dataset.mobilePanel));
});
document.addEventListener('pointerdown', event => {
  if (!$('#treeContextMenu').contains(event.target)) closeTreeContextMenu();
});
document.addEventListener('keydown', event => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 's' && state.editing) {
    event.preventDefault();
    saveEditedFile();
    return;
  }
  if (event.key === 'Escape') {
    closeTreeContextMenu();
    if ($('.assistant').classList.contains('fullscreen')) toggleAssistantFullscreen(false);
  }
});
window.addEventListener('blur', closeTreeContextMenu);
window.addEventListener('scroll', closeTreeContextMenu, true);
$('#filterInput').addEventListener('input', event => { state.filter = event.target.value; applyFilter(); });
document.addEventListener('keydown', event => { if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); $('#filterInput').focus(); } });
document.addEventListener('selectionchange', () => {
  updateSelectionNote();
});
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden') writeWorkspaceState().catch(() => {});
});

state.language = localStorage.getItem('code-browser-language') === 'en' ? 'en' : 'ja';
applyLanguage();
initAssistantResizer();
switchMobilePanel('explorer');
init();
