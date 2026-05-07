/* Baseball Oracle — chat UI logic.
   Phase 3C Layer 2: stateless server, browser-side history.
   Layer 5 will add trace rendering ("How did I get this answer?" expander).
*/

// ---- State ---------------------------------------------------------------

// Conversation history. null on first turn; backend builds fresh.
// After each turn, the server returns the updated history list (which now
// includes our new question and its response). We store it and pass it
// back on the next turn.
let history = null;

// In-flight guard: prevents double-submission while a /chat request is open.
let inFlight = false;

// ---- DOM references (cached at module load) ------------------------------

const messagesEl = document.getElementById('messages');
const loadingEl = document.getElementById('loading');
const formEl = document.getElementById('input-form');
const inputEl = document.getElementById('question-input');
const sendBtn = document.getElementById('send-btn');
const newConvBtn = document.getElementById('new-conversation-btn');

// ---- Rendering helpers ---------------------------------------------------

function roleLabel(role) {
    if (role === 'user') return 'You';
    if (role === 'assistant') return 'Oracle';
    return 'Error';
}

function appendMessage(role, content, { markdown = false, trace = null } = {}) {
    const wrapper = document.createElement('div');
    wrapper.className = `message ${role}`;

    const roleEl = document.createElement('div');
    roleEl.className = 'message-role';
    roleEl.textContent = roleLabel(role);
    wrapper.appendChild(roleEl);

    const contentEl = document.createElement('div');
    contentEl.className = 'message-content';
    if (markdown) {
        try {
            contentEl.innerHTML = marked.parse(content);
        } catch (err) {
            // marked.js failed to load or parse — fall back to plain text
            // so the response content isn't lost.
            contentEl.textContent = content;
        }
    } else {
        contentEl.textContent = content;
    }
    wrapper.appendChild(contentEl);

    if (role === 'assistant' && Array.isArray(trace) && trace.length > 0) {
        wrapper.appendChild(renderTrace(trace));
    }

    messagesEl.appendChild(wrapper);
    messagesEl.scrollTop = messagesEl.scrollHeight;
}

function renderTrace(trace) {
    const traceEl = document.createElement('div');
    traceEl.className = 'message-trace';

    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'trace-toggle';
    const showLabel = `Show ${trace.length} tool call${trace.length === 1 ? '' : 's'}`;
    toggle.textContent = showLabel;

    const body = document.createElement('div');
    body.className = 'trace-body';
    body.hidden = true;

    trace.forEach((call, idx) => {
        body.appendChild(renderTraceCall(call, idx + 1));
    });

    toggle.addEventListener('click', () => {
        if (body.hidden) {
            body.hidden = false;
            toggle.textContent = 'Hide tool calls';
        } else {
            body.hidden = true;
            toggle.textContent = showLabel;
        }
    });

    traceEl.appendChild(toggle);
    traceEl.appendChild(body);
    return traceEl;
}

function renderTraceCall(call, num) {
    const callEl = document.createElement('div');
    callEl.className = 'trace-call';

    const header = document.createElement('div');
    header.className = 'trace-call-header';
    const numSpan = document.createElement('span');
    numSpan.className = 'trace-call-num';
    numSpan.textContent = `${num}.`;
    header.appendChild(numSpan);
    header.appendChild(document.createTextNode(call.tool_name || '(unknown tool)'));
    callEl.appendChild(header);

    callEl.appendChild(makeFieldLabel('Input'));
    callEl.appendChild(makeCodeBlock(call.tool_input));

    callEl.appendChild(makeFieldLabel('Output'));
    callEl.appendChild(makeCodeBlock(call.tool_output));

    return callEl;
}

function makeFieldLabel(text) {
    const el = document.createElement('div');
    el.className = 'trace-field-label';
    el.textContent = text;
    return el;
}

function makeCodeBlock(value) {
    const pre = document.createElement('pre');
    const code = document.createElement('code');
    let text;
    try {
        text = JSON.stringify(value, null, 2);
    } catch (err) {
        text = String(value);
    }
    if (text === undefined) text = '';
    code.textContent = text;
    pre.appendChild(code);
    return pre;
}

function setLoading(isLoading) {
    inFlight = isLoading;
    loadingEl.hidden = !isLoading;
    sendBtn.disabled = isLoading;
    if (!isLoading) inputEl.focus();
}

// ---- Network -------------------------------------------------------------

async function sendMessage(question) {
    if (inFlight) return;
    appendMessage('user', question);
    setLoading(true);

    try {
        const response = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question, history }),
        });

        if (!response.ok) {
            const errBody = await response.json().catch(() => ({}));
            const msg = errBody.error || `HTTP ${response.status}`;
            appendMessage('error', `Error: ${msg}`);
            return;
        }

        const data = await response.json();
        history = data.history;
        appendMessage('assistant', data.response, {
            markdown: true,
            trace: data.trace,
        });
    } catch (err) {
        appendMessage('error', `Error: ${err.message || err}`);
    } finally {
        setLoading(false);
    }
}

// ---- Event wiring --------------------------------------------------------

formEl.addEventListener('submit', (e) => {
    e.preventDefault();
    if (inFlight) return;
    const question = inputEl.value.trim();
    if (!question) return;
    inputEl.value = '';
    sendMessage(question);
});

// Enter to submit, Shift+Enter for newline (chat-app convention).
inputEl.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        formEl.requestSubmit();
    }
});

newConvBtn.addEventListener('click', () => {
    history = null;
    messagesEl.innerHTML = '';
    inputEl.value = '';
    inputEl.focus();
});
