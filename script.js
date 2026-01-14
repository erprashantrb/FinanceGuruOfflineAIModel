const modelInput = document.getElementById('modelInput');
const progressWrap = document.getElementById('progressWrap');
const progressFill = document.getElementById('progressFill');
const progressText = document.getElementById('progressText');
const statusMsg = document.getElementById('statusMsg');
const sendBtn = document.getElementById('sendBtn');
const userMsg = document.getElementById('userMsg');
const messages = document.getElementById('messages');
const chatArea = document.getElementById('chatArea');
const welcomePanel = document.getElementById('welcomePanel');
const clearBtn = document.getElementById('clearBtn');
const reloadBtn = document.getElementById('reloadBtn');

function appendMessage(who, text){
  const d = document.createElement('div');
  d.className = 'msg ' + (who==='user' ? 'user' : 'ai');
  d.innerHTML = `<div>${text}</div>`;
  messages.appendChild(d);
  messages.scrollTop = messages.scrollHeight;
}

if (modelInput){
  modelInput.addEventListener('change', uploadModel);
}

async function uploadModel(){
  const f = modelInput.files[0];
  if (!f) return;

  progressWrap.style.display = 'block';
  statusMsg.innerText = 'Uploading...';

  const fd = new FormData();
  fd.append('file', f);

  const xhr = new XMLHttpRequest();
  xhr.open('POST','/upload', true);

  xhr.upload.onprogress = (e) => {
    if (e.lengthComputable){
      const p = Math.round((e.loaded/e.total)*100);
      progressFill.style.width = p + '%';
      progressText.innerText = `Uploading ${p}%`;
    }
  };

  xhr.onload = () => {
    try {
      const resp = JSON.parse(xhr.responseText);
      progressFill.style.width = '100%';
      progressText.innerText = resp.message || 'Upload complete — starting model...';
      statusMsg.innerText = 'Starting model...';
      pollReady();
    } catch(e){
      progressFill.style.width = '100%';
      progressText.innerText = 'Upload complete — starting model...';
      statusMsg.innerText = 'Starting model...';
      pollReady();
    }
  };

  xhr.onerror = () => {
    statusMsg.innerText = 'Upload error';
  };

  xhr.send(fd);
}

async function pollReady(){
  let tries = 0;
  while (tries < 90){
    try {
      const r = await fetch('/check_status');
      const j = await r.json();
      if (j.ready){
        statusMsg.innerText = '✅ Model ready';
        welcomePanel.style.display = 'none';
        chatArea.style.display = 'flex';
        return;
      } else {
        statusMsg.innerText = 'Starting model... (' + (tries+1) + 's)';
      }
    } catch(e){
      statusMsg.innerText = 'Waiting for model...';
    }
    await new Promise(res=>setTimeout(res,2000));
    tries++;
  }
  statusMsg.innerText = 'Model start timeout — check console';
}

if (sendBtn){
  sendBtn.addEventListener('click', sendMessage);
  userMsg.addEventListener('keypress', (e)=>{ if (e.key==='Enter') sendMessage(); });
}

async function sendMessage(){
  const text = userMsg.value.trim();
  if (!text) return;
  appendMessage('user', text);
  userMsg.value = '';
  appendMessage('ai', '…');

  try {
    const res = await fetch('/chat', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({message:text})
    });
    const j = await res.json();
    const bots = document.querySelectorAll('.msg.ai');
    const last = bots[bots.length-1];
    if (last) last.innerHTML = `<div>${j.reply}</div>`;
    messages.scrollTop = messages.scrollHeight;
  } catch(err){
    const bots = document.querySelectorAll('.msg.ai');
    const last = bots[bots.length-1];
    if (last) last.innerHTML = `<div>⚠️ Error: ${err}</div>`;
  }
}

if (clearBtn) clearBtn.addEventListener('click', ()=>{ messages.innerHTML=''; });
if (reloadBtn) reloadBtn.addEventListener('click', ()=>{ location.reload(); });
