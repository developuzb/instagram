/* ════════════════════════════════
   Instagram Chatbot — Admin Panel JS
   ════════════════════════════════ */

const API = '';
let TOKEN = localStorage.getItem('admin_token') || '';
let accounts = [];

// ──────────── AUTH ────────────

async function login() {
  const pwd = document.getElementById('loginPassword').value;
  if (!pwd) return;
  try {
    const r = await fetch(`${API}/api/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: pwd })
    });
    const d = await r.json();
    if (d.success) {
      TOKEN = d.token;
      localStorage.setItem('admin_token', TOKEN);
      document.getElementById('loginScreen').style.display = 'none';
      document.getElementById('mainApp').style.display = 'flex';
      initApp();
    } else {
      showError('loginError', 'Noto\'g\'ri parol!');
    }
  } catch (e) {
    showError('loginError', 'Server bilan bog\'lanib bo\'lmadi!');
  }
}

function logout() {
  TOKEN = '';
  localStorage.removeItem('admin_token');
  location.reload();
}

function showError(id, msg) {
  const el = document.getElementById(id);
  el.textContent = msg;
  el.style.display = 'block';
  setTimeout(() => el.style.display = 'none', 3000);
}

// ──────────── INIT ────────────

async function initApp() {
  updateTime();
  setInterval(updateTime, 1000);
  await loadAccounts();
  await loadStats();
  loadRecentMessages();
  await updateWebhookInfo();

  // Agar token bor bo'lsa login ekranini yashir
  if (TOKEN) {
    document.getElementById('loginScreen').style.display = 'none';
    document.getElementById('mainApp').style.display = 'flex';
  }
}

function updateTime() {
  const el = document.getElementById('currentTime');
  if (el) el.textContent = new Date().toLocaleTimeString('uz-UZ');
}

// ──────────── API HELPER ────────────

async function api(method, path, body = null) {
  const opts = {
    method,
    headers: {
      'Content-Type': 'application/json',
      'X-Admin-Token': TOKEN
    }
  };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(API + path, opts);
  const d = await r.json();
  if (!r.ok) throw new Error(d.detail || 'Xato yuz berdi');
  return d;
}

// ──────────── NAVIGATION ────────────

function showPage(name) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.getElementById(`page-${name}`).classList.add('active');
  document.querySelectorAll('.nav-item').forEach(n => {
    if (n.getAttribute('onclick')?.includes(`'${name}'`)) n.classList.add('active');
  });
  const titles = {
    dashboard: 'Dashboard',
    accounts: 'Akkauntlar',
    triggers: 'Triggerlar',
    posts: 'Postlar',
    subscribers: 'Obunachlar',
    messages: 'Xabarlar',
    polling: '🔄 Polling Rejimi',
    webhook: 'Webhook',
    testdm: 'Test DM'
  };
  document.getElementById('pageTitle').textContent = titles[name] || name;

  // Sahifaga kirish paytida ma'lumot yuklash
  if (name === 'triggers') loadTriggers();
  else if (name === 'posts') loadPosts();
  else if (name === 'subscribers') loadSubscribers();
  else if (name === 'messages') loadMessages();
  else if (name === 'testdm') populateTestDmAccounts();
  else if (name === 'polling') loadPollingStatus();
}

function toggleSidebar() {
  document.querySelector('.sidebar').classList.toggle('open');
}

// ──────────── COUNT-UP ANIMATION ────────────

function animateCount(el, target, duration = 800) {
  const start = parseInt(el.textContent) || 0;
  if (start === target) return;
  const range = target - start;
  const startTime = performance.now();
  function update(now) {
    const elapsed = now - startTime;
    const progress = Math.min(elapsed / duration, 1);
    // easeOutQuart
    const ease = 1 - Math.pow(1 - progress, 4);
    el.textContent = Math.round(start + range * ease);
    if (progress < 1) requestAnimationFrame(update);
    else el.textContent = target;
  }
  requestAnimationFrame(update);
}

// ──────────── STATS ────────────

async function loadStats() {
  try {
    const s = await api('GET', '/api/stats');
    animateCount(document.getElementById('stat-accounts'),    s.total_accounts,    600);
    animateCount(document.getElementById('stat-triggers'),    s.total_triggers,    700);
    animateCount(document.getElementById('stat-subscribers'), s.total_subscribers, 800);
    animateCount(document.getElementById('stat-messages'),    s.total_messages,    900);
    animateCount(document.getElementById('stat-today'),       s.today_messages,    500);
    animateCount(document.getElementById('stat-posts'),       s.total_posts,       650);
  } catch (e) {
    console.error('Stats xatosi:', e);
  }
}

async function loadRecentMessages() {
  try {
    const msgs = await api('GET', '/api/messages?limit=5');
    const el = document.getElementById('recentMessages');
    if (!msgs.length) {
      el.innerHTML = '<div class="empty"><i class="fas fa-inbox"></i>Hali xabar yuborilmagan</div>';
      return;
    }
    el.innerHTML = `<div class="table-wrap"><table>
      <tr><th>Foydalanuvchi</th><th>Kommentariya</th><th>Status</th><th>Vaqt</th></tr>
      ${msgs.map(m => `
        <tr>
          <td>${m.username || m.subscriber_id || '—'}</td>
          <td>${escHtml(m.comment_text || '—')}</td>
          <td><span class="badge ${m.status === 'sent' ? 'badge-green' : 'badge-red'}">${m.status === 'sent' ? '✅ Yuborildi' : '❌ Xato'}</span></td>
          <td style="color:var(--text3);font-size:12px">${formatDate(m.created_at)}</td>
        </tr>
      `).join('')}
    </table></div>`;
  } catch (e) {
    document.getElementById('recentMessages').innerHTML = '<div class="empty">Ma\'lumot yuklanmadi</div>';
  }
}

// ──────────── ACCOUNTS ────────────

function showSkeleton(id, rows = 3) {
  const el = document.getElementById(id);
  if (!el) return;
  el.innerHTML = Array.from({ length: rows }, () =>
    `<div style="padding:14px;border-bottom:1px solid rgba(255,255,255,0.04);display:flex;gap:12px;align-items:center">
      <div class="skeleton" style="width:80px;height:30px;border-radius:20px"></div>
      <div style="flex:1;display:flex;flex-direction:column;gap:6px">
        <div class="skeleton" style="height:14px;width:60%"></div>
        <div class="skeleton" style="height:11px;width:40%"></div>
      </div>
      <div class="skeleton" style="width:60px;height:24px;border-radius:12px"></div>
    </div>`
  ).join('');
}

async function loadAccounts() {
  showSkeleton('accountsList', 2);
  try {
    accounts = await api('GET', '/api/accounts');
    renderAccounts();
    populateAccountSelects();
  } catch (e) {
    document.getElementById('accountsList').innerHTML = '<div class="empty"><i class="fas fa-exclamation-triangle"></i>Yuklanmadi</div>';
  }
}

function renderAccounts() {
  const el = document.getElementById('accountsList');
  if (!accounts.length) {
    el.innerHTML = `<div class="empty">
      <i class="fas fa-user-circle"></i>
      Hali akkaunt qo'shilmagan.<br>
      <small>Page Access Token orqali Instagram akkauntingizni ulang</small>
    </div>`;
    return;
  }
  el.innerHTML = `<div class="table-wrap"><table>
    <tr><th>#</th><th>Username</th><th>Instagram ID</th><th>Holat</th><th>Qo'shilgan</th><th>Amallar</th></tr>
    ${accounts.map(a => `
      <tr>
        <td style="color:var(--text3)">${a.id}</td>
        <td><strong>@${a.username}</strong></td>
        <td style="font-family:monospace;font-size:12px;color:var(--text3)">${a.instagram_id}</td>
        <td>
          <span class="badge ${a.is_active ? 'badge-green' : 'badge-gray'}">${a.is_active ? '✅ Faol' : '⏸️ To\'xtatilgan'}</span>
          <span class="badge ${a.auth_type === 'instagrapi' ? 'badge-purple' : 'badge-blue'}" style="margin-left:4px;font-size:10px">
            ${a.auth_type === 'instagrapi' ? '🔐 Login' : '🔑 Token'}
          </span>
        </td>
        <td style="color:var(--text3);font-size:12px">${formatDate(a.created_at)}</td>
        <td>
          <div style="display:flex;gap:6px">
            ${a.auth_type !== 'instagrapi' ? `<button class="btn btn-sm btn-ghost btn-icon" onclick="verifyToken(${a.id})" title="Token tekshirish"><i class="fas fa-check-circle"></i></button>` : ''}
            <button class="btn btn-sm btn-danger btn-icon" onclick="deleteAccount(${a.id})" title="O'chirish">
              <i class="fas fa-trash"></i>
            </button>
          </div>
        </td>
      </tr>
    `).join('')}
  </table></div>`;
}

function populateAccountSelects() {
  const selects = ['newTriggerAccount', 'newPostAccount', 'triggerAccountFilter', 'testDmAccount'];
  selects.forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    const hasAll = id === 'triggerAccountFilter';
    el.innerHTML = (hasAll ? '<option value="">Barcha akkauntlar</option>' : '') +
      accounts.map(a => `<option value="${a.id}">@${a.username}</option>`).join('');
  });
}

let _currentAuthTab = 'ig';

function switchAuthTab(tab) {
  _currentAuthTab = tab;
  document.querySelectorAll('.auth-tab').forEach(t => t.classList.remove('active'));
  event.target.closest('.auth-tab').classList.add('active');
  document.getElementById('authTabIg').style.display = tab === 'ig' ? '' : 'none';
  document.getElementById('authTabToken').style.display = tab === 'token' ? '' : 'none';
}

async function createAccount() {
  const btn = document.getElementById('addAccountBtn');
  btn.disabled = true;
  btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Ulanmoqda...';

  try {
    if (_currentAuthTab === 'ig') {
      await _createAccountIG();
    } else {
      await _createAccountToken();
    }
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i class="fab fa-instagram"></i> Ulash';
  }
}

let _ig2faPendingUsername = null;

async function _createAccountIG() {
  const username = document.getElementById('igLoginUsername').value.trim().replace('@', '');
  const password = document.getElementById('igLoginPassword').value;
  const statusEl = document.getElementById('igLoginStatus');

  if (!username) return toast('Foydalanuvchi nomi kiriting!', 'error');
  if (!password) return toast('Parolni kiriting!', 'error');

  statusEl.style.display = 'block';
  statusEl.innerHTML = `<div class="info-box"><i class="fas fa-spinner fa-spin"></i><div>Instagram ga ulanmoqda... (30-60 soniya ketishi mumkin)</div></div>`;

  const btn = document.getElementById('addAccountBtn');
  btn.disabled = true;

  try {
    const res = await api('POST', '/api/accounts/ig-login', { username, password });

    // 2FA kerak
    if (res.need_2fa) {
      _ig2faPendingUsername = res.username || username;
      document.getElementById('ig2faUsername').textContent = '@' + _ig2faPendingUsername;
      document.getElementById('igStep1').style.display = 'none';
      document.getElementById('igStep2').style.display = 'block';
      document.querySelectorAll('.auth-tab').forEach(t => t.style.display = 'none');
      statusEl.style.display = 'none';
      btn.disabled = false;
      btn.onclick = _submit2FA;
      btn.innerHTML = '<i class="fas fa-key"></i> Kodni tasdiqlash';
      return;
    }

    // Muvaffaqiyatli login
    _resetIgLoginForm();
    closeModal('addAccountModal');
    await loadAccounts();
    await loadStats();
    toast(`@${res.username} ulandi!`, 'success');
  } catch (e) {
    statusEl.innerHTML = `<div class="info-box warning"><i class="fas fa-exclamation-triangle"></i><div><strong>Xato:</strong> ${e.message}</div></div>`;
    btn.disabled = false;
  }
}

async function _submit2FA() {
  const code = document.getElementById('ig2faCode').value.trim().replace(/\s/g, '');
  const statusEl = document.getElementById('igLoginStatus');
  const btn = document.getElementById('addAccountBtn');

  if (!code || code.length !== 6) return toast('6 xonali kodni kiriting!', 'error');

  btn.disabled = true;
  statusEl.style.display = 'block';
  statusEl.innerHTML = `<div class="info-box"><i class="fas fa-spinner fa-spin"></i><div>Kod tekshirilmoqda...</div></div>`;

  try {
    const res = await api('POST', '/api/accounts/ig-2fa', { username: _ig2faPendingUsername, code });
    _resetIgLoginForm();
    closeModal('addAccountModal');
    await loadAccounts();
    await loadStats();
    toast(`@${res.username} ulandi! (2FA)`, 'success');
  } catch (e) {
    statusEl.innerHTML = `<div class="info-box warning"><i class="fas fa-exclamation-triangle"></i><div><strong>Xato:</strong> ${e.message}</div></div>`;
    document.getElementById('ig2faCode').value = '';
    btn.disabled = false;
  }
}

function _resetIgLoginForm() {
  _ig2faPendingUsername = null;
  document.getElementById('igLoginUsername').value = '';
  document.getElementById('igLoginPassword').value = '';
  document.getElementById('ig2faCode').value = '';
  document.getElementById('igLoginStatus').style.display = 'none';
  document.getElementById('igStep1').style.display = 'block';
  document.getElementById('igStep2').style.display = 'none';
  document.querySelectorAll('.auth-tab').forEach(t => t.style.display = '');
  const btn = document.getElementById('addAccountBtn');
  btn.disabled = false;
  btn.onclick = createAccount;
  btn.innerHTML = '<i class="fab fa-instagram"></i> Ulash';
}

async function _createAccountToken() {
  const token = document.getElementById('newAccountToken').value.trim();
  if (!token) return toast('Token kiriting!', 'error');
  try {
    toast('Tekshirilmoqda...', 'info');
    const a = await api('POST', '/api/accounts', { page_access_token: token });
    closeModal('addAccountModal');
    document.getElementById('newAccountToken').value = '';
    await loadAccounts();
    await loadStats();
    toast(`✅ @${a.username} qo'shildi!`, 'success');
  } catch (e) {
    toast('❌ ' + e.message, 'error');
  }
}

async function verifyToken(accountId) {
  try {
    const r = await api('POST', `/api/accounts/${accountId}/verify-token`);
    if (r.valid) toast('✅ Token yaroqli! ' + (r.name || ''), 'success');
    else toast('❌ Token muddati o\'tgan yoki noto\'g\'ri', 'error');
  } catch (e) {
    toast('❌ ' + e.message, 'error');
  }
}

async function deleteAccount(id) {
  if (!confirm('Akkauntni o\'chirishni tasdiqlaysizmi? Barcha triggerlar va ma\'lumotlar ham o\'chadi.')) return;
  try {
    await api('DELETE', `/api/accounts/${id}`);
    await loadAccounts();
    await loadStats();
    toast('Akkaunt o\'chirildi', 'success');
  } catch (e) {
    toast('❌ ' + e.message, 'error');
  }
}

// ──────────── TRIGGERS ────────────

async function loadTriggers() {
  showSkeleton('triggersList', 3);
  const accountId = document.getElementById('triggerAccountFilter')?.value;
  const url = accountId ? `/api/triggers?account_id=${accountId}` : '/api/triggers';
  try {
    const triggers = await api('GET', url);
    renderTriggers(triggers);
  } catch (e) {
    document.getElementById('triggersList').innerHTML = '<div class="empty"><i class="fas fa-bolt"></i>Yuklanmadi</div>';
  }
}

function renderTriggers(triggers) {
  const el = document.getElementById('triggersList');
  if (!triggers.length) {
    el.innerHTML = `<div class="empty">
      <i class="fas fa-bolt"></i>
      Hali trigger yaratilmagan.<br>
      <small>Masalan: "+" yoki "manzil" kalit so'zlariga DM qo'shing</small>
    </div>`;
    return;
  }
  el.innerHTML = triggers.map(t => {
    const acc = accounts.find(a => a.id === t.account_id);
    const typeLabel = t.trigger_type === 'dm'
      ? '<span class="badge badge-blue" style="font-size:11px"><i class="fas fa-envelope"></i> DM trigger</span>'
      : '<span class="badge badge-purple" style="font-size:11px"><i class="fas fa-comment"></i> Kommentariya</span>';
    const matchAllLabel = t.match_all
      ? '<span class="badge badge-orange" style="font-size:11px"><i class="fas fa-users"></i> Barcha</span>'
      : '';
    const keywordDisplay = t.match_all
      ? '<div class="trigger-keyword trigger-keyword-all">👥 Barcha kommentariyalar</div>'
      : `<div class="trigger-keyword">${escHtml(t.keyword)}</div>`;
    return `<div class="trigger-card">
      ${keywordDisplay}
      <div class="trigger-body">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;flex-wrap:wrap">
          <span class="badge ${t.is_active ? 'badge-green' : 'badge-gray'}" style="font-size:11px">
            ${t.is_active ? '✅ Faol' : '⏸️ To\'xtatilgan'}
          </span>
          ${typeLabel}
          ${matchAllLabel}
          ${acc ? `<span style="font-size:12px;color:var(--text3)">@${acc.username}</span>` : ''}
          <span style="font-size:12px;color:var(--text3)">
            <i class="fas fa-fire" style="color:var(--orange)"></i> ${t.trigger_count} marta
          </span>
        </div>
        <div class="trigger-message">${escHtml(t.reply_message)}</div>
        <div class="trigger-meta">
          <span><i class="fas fa-calendar"></i> ${formatDate(t.created_at)}</span>
        </div>
      </div>
      <div class="trigger-actions">
        <button class="btn btn-sm btn-ghost btn-icon" onclick="openEditTrigger(${t.id}, '${escJs(t.keyword)}', \`${escJs(t.reply_message)}\`, ${t.is_active}, ${t.match_all || 0}, '${t.trigger_type || 'comment'}')" title="Tahrirlash">
          <i class="fas fa-edit"></i>
        </button>
        <button class="btn btn-sm btn-danger btn-icon" onclick="deleteTrigger(${t.id})" title="O'chirish">
          <i class="fas fa-trash"></i>
        </button>
      </div>
    </div>`;
  }).join('');
}

function toggleKeywordField(prefix) {
  const isMatchAll = document.getElementById(`${prefix}TriggerMatchAll`)?.checked;
  const kwGroup = document.getElementById(`${prefix}KeywordGroup`);
  if (kwGroup) kwGroup.style.display = isMatchAll ? 'none' : '';

  // DM trigger bo'lsa match_all option ko'rsatmaslik
  const triggerType = document.querySelector(`input[name="${prefix}TriggerType"]:checked`)?.value || 'comment';
  const matchAllGroup = document.getElementById(`${prefix}MatchAllGroup`);
  if (matchAllGroup) matchAllGroup.style.display = triggerType === 'dm' ? 'none' : '';
  if (triggerType === 'dm') {
    const maCheck = document.getElementById(`${prefix}TriggerMatchAll`);
    if (maCheck) maCheck.checked = false;
    if (kwGroup) kwGroup.style.display = '';
  }
}

function insertVar(textareaId, text) {
  const el = document.getElementById(textareaId);
  if (!el) return;
  const start = el.selectionStart;
  const end = el.selectionEnd;
  el.value = el.value.substring(0, start) + text + el.value.substring(end);
  el.selectionStart = el.selectionEnd = start + text.length;
  el.focus();
}

async function createTrigger() {
  const account_id = parseInt(document.getElementById('newTriggerAccount').value);
  const match_all = document.getElementById('newTriggerMatchAll').checked ? 1 : 0;
  const trigger_type = document.querySelector('input[name="newTriggerType"]:checked')?.value || 'comment';
  const keyword = match_all ? '*' : document.getElementById('newTriggerKeyword').value.trim();
  const reply_message = document.getElementById('newTriggerMessage').value.trim();
  if (!match_all && !keyword) return toast('Kalit so\'z kiriting!', 'error');
  if (!reply_message) return toast('DM xabari kiriting!', 'error');
  try {
    await api('POST', '/api/triggers', { account_id, keyword, reply_message, match_all, trigger_type });
    closeModal('addTriggerModal');
    document.getElementById('newTriggerKeyword').value = '';
    document.getElementById('newTriggerMessage').value = '';
    document.getElementById('newTriggerMatchAll').checked = false;
    document.querySelector('input[name="newTriggerType"][value="comment"]').checked = true;
    toggleKeywordField('new');
    await loadTriggers();
    await loadStats();
    toast('✅ Trigger yaratildi!', 'success');
  } catch (e) {
    toast('❌ ' + e.message, 'error');
  }
}

function openEditTrigger(id, keyword, message, is_active, match_all, trigger_type) {
  document.getElementById('editTriggerId').value = id;
  document.getElementById('editTriggerKeyword').value = match_all ? '' : keyword;
  document.getElementById('editTriggerMessage').value = message;
  document.getElementById('editTriggerActive').value = is_active;
  document.getElementById('editTriggerMatchAll').checked = !!match_all;

  const tt = trigger_type || 'comment';
  document.querySelectorAll('input[name="editTriggerType"]').forEach(r => {
    r.checked = (r.value === tt);
  });

  toggleKeywordField('edit');
  openModal('editTriggerModal');
}

async function updateTrigger() {
  const id = document.getElementById('editTriggerId').value;
  const match_all = document.getElementById('editTriggerMatchAll').checked ? 1 : 0;
  const trigger_type = document.querySelector('input[name="editTriggerType"]:checked')?.value || 'comment';
  const keyword = match_all ? '*' : document.getElementById('editTriggerKeyword').value.trim();
  const reply_message = document.getElementById('editTriggerMessage').value.trim();
  const is_active = parseInt(document.getElementById('editTriggerActive').value);
  if (!match_all && !keyword) return toast('Kalit so\'z kiriting!', 'error');
  if (!reply_message) return toast('Xabar matnini kiriting!', 'error');
  try {
    await api('PUT', `/api/triggers/${id}`, { keyword, reply_message, is_active, match_all, trigger_type });
    closeModal('editTriggerModal');
    await loadTriggers();
    toast('✅ Trigger yangilandi!', 'success');
  } catch (e) {
    toast('❌ ' + e.message, 'error');
  }
}

async function deleteTrigger(id) {
  if (!confirm('Triggerni o\'chirishni tasdiqlaysizmi?')) return;
  try {
    await api('DELETE', `/api/triggers/${id}`);
    await loadTriggers();
    await loadStats();
    toast('Trigger o\'chirildi', 'success');
  } catch (e) {
    toast('❌ ' + e.message, 'error');
  }
}

// ──────────── POSTS ────────────

async function loadPosts() {
  try {
    const posts = await api('GET', '/api/posts');
    const el = document.getElementById('postsList');
    if (!posts.length) {
      el.innerHTML = `<div class="empty"><i class="fas fa-image"></i>Hali post qo'shilmagan</div>`;
      return;
    }
    el.innerHTML = `<div class="table-wrap"><table>
      <tr><th>Post ID</th><th>Izoh</th><th>Akkaunt</th><th>Holat</th><th>URL</th><th>Amallar</th></tr>
      ${posts.map(p => {
        const acc = accounts.find(a => a.id === p.account_id);
        return `<tr>
          <td style="font-family:monospace;font-size:12px">${p.post_id}</td>
          <td>${escHtml(p.caption || '—')}</td>
          <td>${acc ? '@' + acc.username : '—'}</td>
          <td>
            <button onclick="togglePost(${p.id}, ${p.is_monitoring ? 0 : 1})" class="badge ${p.is_monitoring ? 'badge-green' : 'badge-gray'}" style="cursor:pointer;border:none">
              ${p.is_monitoring ? '✅ Kuzatilmoqda' : '⏸️ To\'xtatilgan'}
            </button>
          </td>
          <td><a href="${p.post_url}" target="_blank" style="font-size:12px"><i class="fas fa-external-link-alt"></i> Ochish</a></td>
          <td>
            <button class="btn btn-sm btn-danger btn-icon" onclick="deletePost(${p.id})">
              <i class="fas fa-trash"></i>
            </button>
          </td>
        </tr>`;
      }).join('')}
    </table></div>`;
  } catch (e) {
    document.getElementById('postsList').innerHTML = '<div class="empty">Yuklanmadi</div>';
  }
}

async function createPost() {
  const account_id = parseInt(document.getElementById('newPostAccount').value);
  const post_url = document.getElementById('newPostUrl').value.trim();
  const caption = document.getElementById('newPostCaption').value.trim();
  if (!post_url) return toast('Post URL kiriting!', 'error');
  try {
    await api('POST', '/api/posts', { account_id, post_url, caption });
    closeModal('addPostModal');
    document.getElementById('newPostUrl').value = '';
    document.getElementById('newPostCaption').value = '';
    await loadPosts();
    await loadStats();
    toast('✅ Post qo\'shildi!', 'success');
  } catch (e) {
    toast('❌ ' + e.message, 'error');
  }
}

async function togglePost(id, val) {
  await api('PATCH', `/api/posts/${id}/toggle?is_monitoring=${val}`);
  await loadPosts();
}

async function deletePost(id) {
  if (!confirm('Postni o\'chirishni tasdiqlaysizmi?')) return;
  await api('DELETE', `/api/posts/${id}`);
  await loadPosts();
  toast('Post o\'chirildi', 'success');
}

// ──────────── SUBSCRIBERS ────────────

async function loadSubscribers() {
  try {
    const subs = await api('GET', '/api/subscribers');
    document.getElementById('subscriberCount').textContent = subs.length;
    const el = document.getElementById('subscribersList');
    if (!subs.length) {
      el.innerHTML = `<div class="empty"><i class="fas fa-users"></i>Hali obunachi yo'q</div>`;
      return;
    }
    el.innerHTML = `<div class="table-wrap"><table>
      <tr><th>#</th><th>Username</th><th>Instagram ID</th><th>Akkaunt</th><th>Xabarlar</th><th>Oxirgi faollik</th></tr>
      ${subs.map(s => {
        const acc = accounts.find(a => a.id === s.account_id);
        return `<tr>
          <td style="color:var(--text3)">${s.id}</td>
          <td><strong>${s.username || '—'}</strong></td>
          <td style="font-family:monospace;font-size:12px;color:var(--text3)">${s.instagram_user_id}</td>
          <td>${acc ? '@' + acc.username : '—'}</td>
          <td><span class="badge badge-blue">${s.message_count}</span></td>
          <td style="color:var(--text3);font-size:12px">${formatDate(s.last_interaction)}</td>
        </tr>`;
      }).join('')}
    </table></div>`;
  } catch (e) {
    document.getElementById('subscribersList').innerHTML = '<div class="empty">Yuklanmadi</div>';
  }
}

// ──────────── MESSAGES ────────────

async function loadMessages() {
  try {
    const msgs = await api('GET', '/api/messages?limit=200');
    const el = document.getElementById('messagesList');
    if (!msgs.length) {
      el.innerHTML = `<div class="empty"><i class="fas fa-paper-plane"></i>Hali xabar yuborilmagan</div>`;
      return;
    }
    el.innerHTML = `<div class="table-wrap"><table>
      <tr><th>Foydalanuvchi</th><th>Kommentariya</th><th>Yuborilgan xabar</th><th>Status</th><th>Vaqt</th></tr>
      ${msgs.map(m => `<tr>
        <td>${m.username || m.subscriber_id || '—'}</td>
        <td style="max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${escHtml(m.comment_text)}">
          ${escHtml(m.comment_text || '—')}
        </td>
        <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${escHtml(m.sent_message)}">
          ${escHtml(m.sent_message || '—')}
        </td>
        <td><span class="badge ${m.status === 'sent' ? 'badge-green' : 'badge-red'}">${m.status === 'sent' ? '✅ Yuborildi' : '❌ Xato'}</span></td>
        <td style="color:var(--text3);font-size:12px;white-space:nowrap">${formatDate(m.created_at)}</td>
      </tr>`).join('')}
    </table></div>`;
  } catch (e) {
    document.getElementById('messagesList').innerHTML = '<div class="empty">Yuklanmadi</div>';
  }
}

// ──────────── POLLING ────────────

async function loadPollingStatus() {
  try {
    const s = await api('GET', '/api/polling/status');
    const el = document.getElementById('pollingInfo');

    document.getElementById('poll-status-val').textContent = s.running ? '🟢 Aktiv' : '🔴 To\'xtatilgan';
    animateCount(document.getElementById('poll-count'), s.polls_done || 0, 600);
    animateCount(document.getElementById('poll-comments'), s.comments_found || 0, 700);
    animateCount(document.getElementById('poll-dms'), s.dms_sent || 0, 700);
    if (document.getElementById('pollIntervalInput')) {
      document.getElementById('pollIntervalInput').value = s.poll_interval || 60;
    }

    const lastPoll = s.last_poll ? new Date(s.last_poll).toLocaleString('uz-UZ') : 'Hali tekshirilmagan';
    const startTime = s.server_start ? new Date(s.server_start).toLocaleString('uz-UZ') : '—';

    el.innerHTML = `
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px">
        <div class="info-row">
          <label>Holat</label>
          <div style="display:flex;align-items:center;gap:8px">
            <span class="status-dot ${s.running ? 'online' : ''}"></span>
            <span>${s.running ? 'Polling ishlayapti' : 'To\'xtatilgan'}</span>
          </div>
        </div>
        <div class="info-row">
          <label>Oxirgi tekshiruv</label>
          <code style="color:var(--green);font-size:13px">${lastPoll}</code>
        </div>
        <div class="info-row">
          <label>Server ishga tushdi</label>
          <code style="color:var(--text2);font-size:13px">${startTime}</code>
        </div>
        <div class="info-row">
          <label>Interval</label>
          <code style="color:var(--orange);font-size:13px">Har ${s.poll_interval} soniyada</code>
        </div>
        <div class="info-row">
          <label>Kesh (kommentariya)</label>
          <span class="badge badge-blue">${s.processed_comments} ta saqlangan</span>
        </div>
        <div class="info-row">
          <label>Kesh (DM)</label>
          <span class="badge badge-purple">${s.processed_dms} ta saqlangan</span>
        </div>
      </div>
      ${s.errors > 0 ? `<div class="info-box warning" style="margin-top:12px"><i class="fas fa-exclamation-triangle"></i><div><strong>${s.errors} ta xato</strong> yuz berdi. Konsolni tekshiring.</div></div>` : ''}
    `;
  } catch (e) {
    document.getElementById('pollingInfo').innerHTML = '<div class="empty">Server bilan bog\'lanib bo\'lmadi</div>';
  }
}

async function triggerPoll() {
  try {
    await api('POST', '/api/polling/trigger');
    toast('✅ Polling ishga tushirildi!', 'success');
    setTimeout(loadPollingStatus, 3000);
  } catch (e) {
    toast('❌ ' + e.message, 'error');
  }
}

async function setPollInterval() {
  const sec = parseInt(document.getElementById('pollIntervalInput').value);
  if (!sec || sec < 15) return toast('Minimum 15 soniya!', 'error');
  try {
    await api('PUT', `/api/polling/interval?seconds=${sec}`);
    toast(`✅ Interval ${sec}s ga o'rnatildi`, 'success');
  } catch (e) {
    toast('❌ ' + e.message, 'error');
  }
}

// ──────────── WEBHOOK ────────────

async function updateWebhookInfo() {
  const host = location.origin;
  document.getElementById('webhookUrl').textContent = `${host}/webhook`;
  try {
    const h = await fetch('/health');
    const d = await h.json();
    document.getElementById('verifyToken').textContent = d.webhook_token || 'my_secret_verify_token_123';
  } catch {
    document.getElementById('verifyToken').textContent = 'Server .env faylidan olinadi';
  }
}

function copyWebhook() {
  const text = document.getElementById('webhookUrl').textContent;
  navigator.clipboard.writeText(text).then(() => toast('📋 Nusxa olindi!', 'success'));
}

function copyVerifyToken() {
  const text = document.getElementById('verifyToken').textContent;
  navigator.clipboard.writeText(text).then(() => toast('📋 Nusxa olindi!', 'success'));
}

// ──────────── TEST DM ────────────

function populateTestDmAccounts() {
  const el = document.getElementById('testDmAccount');
  if (el) {
    el.innerHTML = accounts.map(a => `<option value="${a.id}">@${a.username}</option>`).join('');
  }
}

async function sendTestDm() {
  const account_id = parseInt(document.getElementById('testDmAccount').value);
  const recipient_id = document.getElementById('testDmRecipient').value.trim();
  const message = document.getElementById('testDmMessage').value.trim();
  if (!recipient_id) return toast('IGSID kiriting!', 'error');
  if (!message) return toast('Xabar kiriting!', 'error');
  const el = document.getElementById('testDmResult');
  el.innerHTML = '<div style="color:var(--text2)"><i class="fas fa-spinner fa-spin"></i> Yuborilmoqda...</div>';
  try {
    await api('POST', '/api/test-dm', { account_id, recipient_id, message });
    el.innerHTML = '<div class="badge badge-green" style="font-size:14px;padding:10px 16px">✅ DM muvaffaqiyatli yuborildi!</div>';
    toast('✅ Test DM yuborildi!', 'success');
  } catch (e) {
    el.innerHTML = `<div class="badge badge-red" style="font-size:14px;padding:10px 16px">❌ ${e.message}</div>`;
    toast('❌ ' + e.message, 'error');
  }
}

// ──────────── MODALS ────────────

function openModal(id) {
  document.getElementById(id).classList.add('open');
}

function closeModal(id) {
  document.getElementById(id).classList.remove('open');
  if (id === 'addAccountModal') _resetIgLoginForm();
}

// ESC bilan modalni yopish
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    document.querySelectorAll('.modal.open').forEach(m => m.classList.remove('open'));
  }
});
// Modal tashqarisiga bosish
document.addEventListener('click', e => {
  if (e.target.classList.contains('modal')) {
    e.target.classList.remove('open');
  }
});

// ──────────── TOAST ────────────

function toast(msg, type = 'info') {
  const el = document.getElementById('toast');
  const icons = { success: 'fa-check-circle', error: 'fa-times-circle', info: 'fa-info-circle' };
  el.innerHTML = `<i class="fas ${icons[type] || icons.info}"></i><span>${msg}</span>`;
  el.className = `toast ${type}`;
  // force reflow for re-animation
  void el.offsetWidth;
  el.classList.add('show');
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.remove('show'), 3500);
}

// ──────────── HELPERS ────────────

function escHtml(str) {
  return String(str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function escJs(str) {
  return String(str || '').replace(/\\/g, '\\\\').replace(/`/g, '\\`').replace(/\$/g, '\\$').replace(/\n/g, '\\n');
}

function formatDate(str) {
  if (!str) return '—';
  try {
    return new Date(str).toLocaleString('uz-UZ', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  } catch { return str; }
}

// ──────────── AUTO-REFRESH ────────────

setInterval(() => {
  const activePage = document.querySelector('.page.active');
  if (activePage?.id === 'page-dashboard') {
    loadStats();
    loadRecentMessages();
  }
}, 30000); // 30 soniyada yangilash

// ──────────── START ────────────

window.addEventListener('DOMContentLoaded', () => {
  // Auto-login agar token saqlangan bo'lsa
  if (TOKEN) {
    // Token mavjud — tekshirmasdan kirish (sahifani yuklash paytida server xatolarini ko'rsatamiz)
    document.getElementById('loginScreen').style.display = 'none';
    document.getElementById('mainApp').style.display = 'flex';
    initApp();
  }

  // Enter bilan login
  document.getElementById('loginPassword')?.addEventListener('keydown', e => {
    if (e.key === 'Enter') login();
  });
});
