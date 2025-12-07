// AgenticGen 前端应用主文件

// 全局变量
let currentThread = null;
let eventSource = null;
let messages = [];

// DOM 元素
const elements = {
    messageInput: document.getElementById('messageInput'),
    sendBtn: document.getElementById('sendBtn'),
    attachBtn: document.getElementById('attachBtn'),
    newChatBtn: document.getElementById('newChatBtn'),
    knowledgeBtn: document.getElementById('knowledgeBtn'),
    settingsBtn: document.getElementById('settingsBtn'),
    agentType: document.getElementById('agentType'),
    chatMessages: document.getElementById('chatMessages'),
    chatHistory: document.getElementById('chatHistory'),
    knowledgeModal: document.getElementById('knowledgeModal'),
    settingsModal: document.getElementById('settingsModal'),
    fileInput: document.getElementById('fileInput'),
    createKbBtn: document.getElementById('createKbBtn'),
    uploadBtn: document.getElementById('uploadBtn'),
    kbList: document.getElementById('kbList'),
    apiKey: document.getElementById('apiKey'),
    baseUrl: document.getElementById('baseUrl'),
    darkMode: document.getElementById('darkMode'),
    fontSize: document.getElementById('fontSize'),
    saveSettingsBtn: document.getElementById('saveSettingsBtn'),
    loadingIndicator: document.getElementById('loadingIndicator'),
    toast: document.getElementById('toast'),
};

// 配置
const config = {
    apiBaseUrl: localStorage.getItem('baseUrl') || 'http://localhost:9000',
    apiKey: localStorage.getItem('apiKey') || '',
    theme: localStorage.getItem('theme') || 'light',
};

// 初始化应用
document.addEventListener('DOMContentLoaded', () => {
    initializeApp();
    attachEventListeners();
    loadChatHistory();
    loadSettings();
});

// 初始化应用
function initializeApp() {
    // 设置初始主题
    if (config.theme === 'dark') {
        document.documentElement.setAttribute('data-theme', 'dark');
    }

    // 检查API配置
    if (!config.apiKey) {
        showToast('请先配置API密钥', 'error');
        openModal('settingsModal');
    }
}

// 事件监听器
function attachEventListeners() {
    // 消息输入
    elements.messageInput.addEventListener('keydown', handleMessageKeydown);
    elements.sendBtn.addEventListener('click', sendMessage);

    // 文件上传
    elements.attachBtn.addEventListener('click', () => elements.fileInput.click());
    elements.fileInput.addEventListener('change', handleFileUpload);

    // 新建对话
    elements.newChatBtn.addEventListener('click', createNewChat);

    // 知识库
    elements.knowledgeBtn.addEventListener('click', () => openModal('knowledgeModal'));
    elements.createKbBtn.addEventListener('click', createKnowledgeBase);

    // 设置
    elements.settingsBtn.addEventListener('click', () => openModal('settingsModal'));
    elements.saveSettingsBtn.addEventListener('click', saveSettings);

    // 模态框关闭
    document.querySelectorAll('.close-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const modal = e.target.closest('.modal');
            closeModal(modal.id);
        });
    });

    // 点击模态框外部关闭
    document.querySelectorAll('.modal').forEach(modal => {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                closeModal(modal.id);
            }
        });
    });

    // 自动调整输入框高度
    elements.messageInput.addEventListener('input', autoResizeTextarea);
}

// 处理消息输入
function handleMessageKeydown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
}

// 发送消息
async function sendMessage() {
    const message = elements.messageInput.value.trim();
    if (!message) return;

    // 禁用输入
    setInputEnabled(false);

    // 添加用户消息
    addMessage('user', message);

    // 清空输入框
    elements.messageInput.value = '';
    autoResizeTextarea();

    try {
        // 开始流式响应
        await streamResponse(message);
    } catch (error) {
        console.error('发送消息失败:', error);
        addMessage('system', '发送失败，请检查网络连接');
        setInputEnabled(true);
    }
}

// 流式响应
async function streamResponse(message) {
    const agentType = elements.agentType.value;
    const url = `${config.apiBaseUrl}/api/chat/`;
    const data = {
        message,
        agent_type: agentType,
        stream: true,
        thread_id: currentThread,
    };

    // 添加助手消息占位符
    const assistantMessageEl = addMessage('assistant', '', true);
    let fullResponse = '';

    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${config.apiKey}`,
            },
            body: JSON.stringify(data),
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { done, value } = await reader.read();

            if (done) break;

            const chunk = decoder.decode(value);
            const lines = chunk.split('\n');

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        handleStreamEvent(data, assistantMessageEl);

                        if (data.type === 'content') {
                            fullResponse += data.content;
                        } else if (data.type === 'end') {
                            currentThread = data.thread_id;
                            updateChatHistory();
                            break;
                        }
                    } catch (e) {
                        console.error('解析流数据失败:', e);
                    }
                }
            }
        }
    } catch (error) {
        console.error('流式响应失败:', error);
        assistantMessageEl.textContent = '响应失败，请重试';
    } finally {
        // 移除加载指示器
        assistantMessageEl.classList.remove('loading');
        setInputEnabled(true);
    }
}

// 处理流事件
function handleStreamEvent(data, messageEl) {
    switch (data.type) {
        case 'start':
            messageEl.classList.add('loading');
            break;
        case 'content':
            messageEl.textContent += data.content;
            // 滚动到底部
            messageEl.scrollIntoView({ behavior: 'smooth', block: 'end' });
            break;
        case 'error':
            messageEl.textContent = `错误: ${data.error}`;
            messageEl.classList.remove('loading');
            break;
        case 'end':
            messageEl.classList.remove('loading');
            break;
    }
}

// 添加消息
function addMessage(role, content, isLoading = false) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;

    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.textContent = getAvatarIcon(role);

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';

    if (isLoading) {
        contentDiv.innerHTML = '<span class="loading-text">...</span>';
    } else {
        contentDiv.innerHTML = formatMessage(content);
    }

    if (role === 'user') {
        messageDiv.appendChild(avatar);
        messageDiv.appendChild(contentDiv);
    } else {
        messageDiv.appendChild(contentDiv);
        messageDiv.appendChild(avatar);
    }

    elements.chatMessages.appendChild(messageDiv);
    messageDiv.scrollIntoView({ behavior: 'smooth', block: 'end' });

    return contentDiv;
}

// 获取头像图标
function getAvatarIcon(role) {
    const icons = {
        user: '👤',
        assistant: '🤖',
        system: 'ℹ️',
    };
    return icons[role] || '❓';
}

// 格式化消息内容
function formatMessage(content) {
    // 基本的Markdown转HTML
    let formatted = content
        // 代码块
        .replace(/```(\w+)?\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>')
        // 内联代码
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        // 粗体
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        // 斜体
        replace(/\*(.*?)\*/g, '<em>$1</em>')
        // 链接
        .replace(/(https?:\/\/[^\s]+)/g, '<a href="$1" target="_blank">$1</a>')
        // 换行
        .replace(/\n/g, '<br>');

    return formatted;
}

// 设置输入状态
function setInputEnabled(enabled) {
    elements.messageInput.disabled = !enabled;
    elements.sendBtn.disabled = !enabled;
    elements.attachBtn.disabled = !enabled;

    if (enabled) {
        elements.messageInput.focus();
    }
}

// 自动调整文本框高度
function autoResizeTextarea() {
    const textarea = elements.messageInput;
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px';
}

// 创建新对话
function createNewChat() {
    currentThread = null;
    elements.chatMessages.innerHTML = `
        <div class="message system">
            <div class="message-content">
                <p>👋 开始新的对话！</p>
            </div>
        </div>
    `;
    elements.messageInput.focus();
}

// 加载聊天历史
async function loadChatHistory() {
    try {
        const response = await fetch(`${config.apiBaseUrl}/api/chat/threads`, {
            headers: {
                'Authorization': `Bearer ${config.apiKey}`,
            },
        });

        if (response.ok) {
            const data = await response.json();
            renderChatHistory(data.threads || []);
        }
    } catch (error) {
        console.error('加载聊天历史失败:', error);
    }
}

// 渲染聊天历史
function renderChatHistory(threads) {
    elements.chatHistory.innerHTML = '';

    if (threads.length === 0) {
        elements.chatHistory.innerHTML = '<p style="text-align: center; opacity: 0.7;">暂无对话历史</p>';
        return;
    }

    threads.forEach(thread => {
        const item = document.createElement('div');
        item.className = 'chat-item';
        item.innerHTML = `
            <div class="chat-item-title">${thread.title || '新对话'}</div>
            <div class="chat-item-preview">${thread.last_message || '暂无消息'}</div>
        `;
        item.addEventListener('click', () => loadThread(thread.id));
        elements.chatHistory.appendChild(item);
    });
}

// 加载特定线程
async function loadThread(threadId) {
    showLoading(true);

    try {
        // 这里应该加载线程的消息
        // 简化实现
        currentThread = threadId;
        createNewChat();
    } catch (error) {
        console.error('加载线程失败:', error);
    } finally {
        showLoading(false);
    }
}

// 更新聊天历史
function updateChatHistory() {
    loadChatHistory();
}

// 文件上传
async function handleFileUpload(e) {
    const files = e.target.files;
    if (files.length === 0) return;

    showLoading(true);

    try {
        const formData = new FormData();
        for (const file of files) {
            formData.append('files', file);
        }

        const response = await fetch(`${config.apiBaseUrl}/api/files/batch-upload`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${config.apiKey}`,
            },
            body: formData,
        });

        const data = await response.json();

        if (data.success) {
            showToast(`成功上传 ${data.summary.success} 个文件`, 'success');
        } else {
            showToast('文件上传失败', 'error');
        }
    } catch (error) {
        console.error('文件上传失败:', error);
        showToast('文件上传失败', 'error');
    } finally {
        showLoading(false);
        e.target.value = '';
    }
}

// 知识库功能
async function createKnowledgeBase() {
    const name = prompt('请输入知识库名称:');
    if (!name) return;

    showLoading(true);

    try {
        const response = await fetch(`${config.apiBaseUrl}/api/knowledge/create`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${config.apiKey}`,
            },
            body: JSON.stringify({
                name,
                description: `知识库: ${name}`,
            }),
        });

        const data = await response.json();

        if (data.success) {
            showToast('知识库创建成功', 'success');
            loadKnowledgeBases();
        } else {
            showToast('知识库创建失败', 'error');
        }
    } catch (error) {
        console.error('创建知识库失败:', error);
        showToast('创建知识库失败', 'error');
    } finally {
        showLoading(false);
    }
}

async function loadKnowledgeBases() {
    try {
        const response = await fetch(`${config.apiBaseUrl}/api/knowledge/list`, {
            headers: {
                'Authorization': `Bearer ${config.apiKey}`,
            },
        });

        if (response.ok) {
            const data = await response.json();
            renderKnowledgeBases(data.knowledge_bases || []);
        }
    } catch (error) {
        console.error('加载知识库失败:', error);
    }
}

// 渲染知识库列表
function renderKnowledgeBases(kbsList) {
    elements.kbList.innerHTML = '';

    if (kbList.length === 0) {
        elements.kbList.innerHTML = '<p style="text-align: center; opacity: 0.7;">暂无知识库</p>';
        return;
    }

    kbList.forEach(kb => {
        const item = document.createElement('div');
        item.className = 'kb-item';
        item.innerHTML = `
            <div class="kb-item-header">
                <div class="kb-item-title">${kb.name}</div>
                <div class="kb-item-stats">
                    ${kb.total_documents} 文档 | ${kb.total_chunks} 块
                </div>
            </div>
            ${kb.description ? `<p class="kb-item-description">${kb.description}</p>` : ''}
        `;
        item.addEventListener('click', () => selectKnowledgeBase(kb.id));
        elements.kbList.appendChild(item);
    });
}

// 选择知识库
function selectKnowledgeBase(kbId) {
    console.log('选择知识库:', kbId);
    showToast(`已选择知识库 ${kbId}`, 'success');
}

// 设置功能
function loadSettings() {
    elements.apiKey.value = config.apiKey;
    elements.baseUrl.value = config.apiBaseUrl;
    elements.darkMode.checked = config.theme === 'dark';
    elements.fontSize.value = localStorage.getItem('fontSize') || 'medium';

    // 应用字体大小
    document.documentElement.style.fontSize = getFontSize(elements.fontSize.value);
}

function saveSettings() {
    config.apiKey = elements.apiKey.value;
    config.apiBaseUrl = elements.baseUrl.value;
    config.theme = elements.darkMode.checked ? 'dark' : 'light';

    // 保存到本地存储
    localStorage.setItem('apiKey', config.apiKey);
    localStorage.setItem('baseUrl', config.apiBaseUrl);
    localStorage.setItem('theme', config.theme);
    localStorage.setItem('fontSize', elements.fontSize.value);

    // 应用主题
    document.documentElement.setAttribute('data-theme', config.theme);

    // 应用字体大小
    document.documentElement.style.fontSize = getFontSize(elements.fontSize.value);

    closeModal('settingsModal');
    showToast('设置保存成功', 'success');
}

function getFontSize(size) {
    const sizes = {
        small: '14px',
        medium: '16px',
        large: '18px',
    };
    return sizes[size] || sizes.medium;
}

// 模态框功能
function openModal(modalId) {
    document.getElementById(modalId).classList.add('active');
}

function closeModal(modalId) {
    document.getElementById(modalId).classList.remove('active');
}

// 加载提示
function showLoading(show) {
    if (show) {
        elements.loadingIndicator.classList.remove('hidden');
    } else {
        elements.loadingIndicator.classList.add('hidden');
    }
}

// Toast 提示
function showToast(message, type = 'info') {
    elements.toast.textContent = message;
    elements.toast.className = `toast ${type}`;
    elements.toast.classList.remove('hidden');

    setTimeout(() => {
        elements.toast.classList.add('hidden');
    }, 3000);
}

// 键盘快捷键
document.addEventListener('keydown', (e) => {
    // Ctrl/Cmd + K: 新建对话
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        createNewChat();
    }

    // Ctrl/Cmd + /: 聚焦搜索
    if ((e.ctrlKey || e.metaKey) && e.key === '/') {
        e.preventDefault();
        elements.messageInput.focus();
    }

    // Ctrl/Cmd + B: 切换侧边栏（移动端）
    if ((e.ctrlKey || e.metaKey) && e.key === 'b') {
        e.preventDefault();
        toggleSidebar();
    }

    // Ctrl/Cmd + D: 切换暗黑模式
    if ((e.ctrlKey || e.metaKey) && e.key === 'd') {
        e.preventDefault();
        toggleDarkMode();
    }

    // Ctrl/Cmd + 1-5: 快速切换Agent类型
    if ((e.ctrlKey || e.metaKey) && e.key >= '1' && e.key <= '5') {
        e.preventDefault();
        const agentIndex = parseInt(e.key) - 1;
        const agentTypes = elements.agentType.options;
        if (agentIndex < agentTypes.length) {
            elements.agentType.selectedIndex = agentIndex;
            showToast(`切换到 ${agentTypes[agentIndex].text}`, 'success');
        }
    }

    // Ctrl/Cmd + Enter: 发送消息（无需Shift）
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        sendMessage();
    }

    // Ctrl/Cmd + I: 打开设置
    if ((e.ctrlKey || e.metaKey) && e.key === 'i') {
        e.preventDefault();
        openModal('settingsModal');
    }

    // Ctrl/Cmd + L: 打开知识库
    if ((e.ctrlKey || e.metaKey) && e.key === 'l') {
        e.preventDefault();
        openModal('knowledgeModal');
    }

    // Ctrl/Cmd + F: 搜索对话历史
    if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
        e.preventDefault();
        searchChatHistory();
    }

    // F1-F12: 功能键快捷键
    if (!e.ctrlKey && !e.metaKey && !e.altKey) {
        switch(e.key) {
            case 'F1':
                e.preventDefault();
                showHelp();
                break;
            case 'F2':
                e.preventDefault();
                clearChat();
                break;
            case 'F3':
                e.preventDefault();
                exportChat();
                break;
            case 'F4':
                e.preventDefault();
                toggleVoiceInput();
                break;
            case 'F5':
                e.preventDefault();
                refreshChat();
                break;
        }
    }

    // Esc: 关闭模态框
    if (e.key === 'Escape') {
        document.querySelectorAll('.modal.active').forEach(modal => {
            modal.classList.remove('active');
        });
    }
});

// 切换侧边栏
function toggleSidebar() {
    const sidebar = document.querySelector('.sidebar');
    if (sidebar) {
        sidebar.classList.toggle('collapsed');

        // 移动端处理
        if (window.innerWidth <= 768) {
            if (sidebar.classList.contains('collapsed')) {
                sidebar.style.display = 'none';
            } else {
                sidebar.style.display = 'block';
            }
        }
    }
}

// 切换暗黑模式
function toggleDarkMode() {
    const currentTheme = document.documentElement.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', newTheme);
    elements.darkMode.checked = newTheme === 'dark';
    localStorage.setItem('theme', newTheme);
    showToast(`切换到${newTheme === 'dark' ? '暗黑' : '明亮'}模式`, 'success');
}

// 搜索对话历史
function searchChatHistory() {
    const query = prompt('搜索对话历史:');
    if (!query) return;

    const items = document.querySelectorAll('.chat-item');
    let found = false;

    items.forEach(item => {
        const title = item.querySelector('.chat-item-title')?.textContent || '';
        const preview = item.querySelector('.chat-item-preview')?.textContent || '';

        if (title.includes(query) || preview.includes(query)) {
            item.style.backgroundColor = 'var(--primary-color)';
            item.style.color = 'white';
            found = true;

            // 滚动到第一个匹配项
            if (!document.querySelector('.chat-item.highlighted')) {
                item.scrollIntoView({ behavior: 'smooth', block: 'center' });
                item.classList.add('highlighted');
            }
        } else {
            item.style.backgroundColor = '';
            item.style.color = '';
        }
    });

    if (found) {
        showToast(`找到匹配的对话`, 'success');
    } else {
        showToast('未找到匹配的对话', 'warning');
    }
}

// 清空当前聊天
function clearChat() {
    if (confirm('确定要清空当前对话吗？')) {
        elements.chatMessages.innerHTML = `
            <div class="message system">
                <div class="message-content">
                    <p>对话已清空，开始新的对话吧！</p>
                </div>
            </div>
        `;
        currentThread = null;
        showToast('对话已清空', 'success');
    }
}

// 导出聊天记录
function exportChat() {
    const messages = document.querySelectorAll('.message');
    let content = `# AgenticGen 聊天记录\n\n导出时间: ${new Date().toLocaleString()}\n\n`;

    messages.forEach(msg => {
        const role = msg.classList.contains('user') ? '用户' :
                   msg.classList.contains('assistant') ? '助手' : '系统';
        const content = msg.querySelector('.message-content')?.textContent || '';

        content += `## ${role}\n${content}\n\n`;
    });

    // 创建下载链接
    const blob = new Blob([content], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `agenticgen-chat-${Date.now()}.md`;
    a.click();
    URL.revokeObjectURL(url);

    showToast('聊天记录已导出', 'success');
}

// 语音输入切换
function toggleVoiceInput() {
    if (!('webkitSpeechRecognition' in window || 'SpeechRecognition' in window)) {
        showToast('您的浏览器不支持语音输入', 'error');
        return;
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

    if (window.voiceRecognition) {
        // 停止录音
        window.voiceRecognition.stop();
        window.voiceRecognition = null;
        elements.sendBtn.innerHTML = '➤';
        showToast('语音输入已关闭', 'info');
    } else {
        // 开始录音
        window.voiceRecognition = new SpeechRecognition();
        window.voiceRecognition.lang = 'zh-CN';
        window.voiceRecognition.continuous = true;
        window.voiceRecognition.interimResults = true;

        window.voiceRecognition.onresult = (event) => {
            let finalTranscript = '';
            let interimTranscript = '';

            for (let i = event.resultIndex; i < event.results.length; i++) {
                const transcript = event.results[i][0].transcript;
                if (event.results[i].isFinal) {
                    finalTranscript += transcript;
                } else {
                    interimTranscript += transcript;
                }
            }

            elements.messageInput.value = finalTranscript + interimTranscript;
            autoResizeTextarea();
        };

        window.voiceRecognition.onerror = (event) => {
            console.error('语音识别错误:', event.error);
            showToast('语音识别出错: ' + event.error, 'error');
            toggleVoiceInput();
        };

        window.voiceRecognition.onend = () => {
            toggleVoiceInput();
        };

        window.voiceRecognition.start();
        elements.sendBtn.innerHTML = '🔴';
        showToast('语音输入已开启', 'success');
    }
}

// 刷新聊天
function refreshChat() {
    location.reload();
}

// 显示帮助信息
function showHelp() {
    const helpContent = `
# 快捷键帮助

## 基础快捷键
- Ctrl/Cmd + K: 新建对话
- Ctrl/Cmd + /: 聚焦输入框
- Ctrl/Cmd + Enter: 发送消息
- Ctrl/Cmd + B: 切换侧边栏
- Ctrl/Cmd + D: 切换暗黑模式
- Ctrl/Cmd + I: 打开设置
- Ctrl/Cmd + L: 打开知识库
- Ctrl/Cmd + F: 搜索对话

## Agent快捷键
- Ctrl/Cmd + 1: 通用助手
- Ctrl/Cmd + 2: 编程助手
- Ctrl/Cmd + 3: 数据分析
- Ctrl/Cmd + 4: SQL助手
- Ctrl/Cmd + 5: 知识库助手

## 功能键
- F1: 显示帮助
- F2: 清空当前对话
- F3: 导出聊天记录
- F4: 开启/关闭语音输入
- F5: 刷新页面

## 移动端优化
- 支持触摸操作
- 自适应布局
- 离线PWA支持
    `;

    // 创建帮助模态框
    const helpModal = document.createElement('div');
    helpModal.className = 'modal active';
    helpModal.id = 'helpModal';
    helpModal.innerHTML = `
        <div class="modal-content">
            <div class="modal-header">
                <h2>快捷键帮助</h2>
                <button class="close-btn" onclick="this.closest('.modal').remove()">&times;</button>
            </div>
            <div class="modal-body">
                <pre style="white-space: pre-wrap; font-family: monospace; font-size: 0.9rem;">${helpContent}</pre>
            </div>
        </div>
    `;
    document.body.appendChild(helpModal);
}

// PWA安装提示
function showInstallPrompt() {
    let deferredPrompt;

    window.addEventListener('beforeinstallprompt', (e) => {
        e.preventDefault();
        deferredPrompt = e;

        // 显示安装按钮
        const installBtn = document.createElement('button');
        installBtn.className = 'install-btn';
        installBtn.innerHTML = '📱 安装应用';
        installBtn.style.cssText = `
            position: fixed;
            bottom: 20px;
            right: 20px;
            padding: 12px 20px;
            background: var(--primary-color);
            color: white;
            border: none;
            border-radius: 24px;
            cursor: pointer;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            z-index: 1000;
            font-size: 14px;
        `;

        installBtn.addEventListener('click', async () => {
            if (deferredPrompt) {
                deferredPrompt.prompt();
                const { outcome } = await deferredPrompt.userChoice;
                if (outcome === 'accepted') {
                    showToast('应用安装成功！', 'success');
                }
                deferredPrompt = null;
            }
            installBtn.remove();
        });

        document.body.appendChild(installBtn);

        // 5秒后自动隐藏
        setTimeout(() => {
            if (installBtn.parentNode) {
                installBtn.remove();
            }
        }, 5000);
    });
}

// 检测网络状态
function setupNetworkStatus() {
    const updateNetworkStatus = () => {
        const isOnline = navigator.onLine;
        const statusIndicator = document.createElement('div');
        statusIndicator.id = 'network-status';
        statusIndicator.style.cssText = `
            position: fixed;
            top: 10px;
            right: 10px;
            padding: 5px 10px;
            background: ${isOnline ? 'var(--success-color)' : 'var(--error-color)'};
            color: white;
            border-radius: 4px;
            font-size: 12px;
            z-index: 1000;
        `;
        statusIndicator.textContent = isOnline ? '在线' : '离线';

        const existing = document.getElementById('network-status');
        if (existing) {
            existing.remove();
        }

        if (!isOnline) {
            document.body.appendChild(statusIndicator);
            showToast('网络连接已断开', 'warning');
        } else {
            showToast('网络连接已恢复', 'success');
        }
    };

    window.addEventListener('online', updateNetworkStatus);
    window.addEventListener('offline', updateNetworkStatus);
}

// 初始化增强功能
document.addEventListener('DOMContentLoaded', () => {
    // PWA安装提示
    showInstallPrompt();

    // 网络状态检测
    setupNetworkStatus();

    // 检测是否在移动设备
    if (window.innerWidth <= 768) {
        document.body.classList.add('mobile-device');

        // 添加触摸优化
        let touchStartY = 0;
        document.addEventListener('touchstart', (e) => {
            touchStartY = e.touches[0].clientY;
        });

        document.addEventListener('touchend', (e) => {
            const touchEndY = e.changedTouches[0].clientY;
            const deltaY = touchStartY - touchEndY;

            // 下拉刷新
            if (deltaY > 100 && window.scrollY === 0) {
                location.reload();
            }
        });
    }
});

// 页面卸载时关闭连接
window.addEventListener('beforeunload', () => {
    if (eventSource) {
        eventSource.close();
    }
});