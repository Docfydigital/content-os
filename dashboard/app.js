// Content OS — dashboard vitrine (read-only)
// Lê data/latest.json e desenha tudo. Sem framework, sem build.

const fmt = (n) => {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1).replace('.0', '') + 'M';
  if (n >= 1_000) return (n / 1_000).toFixed(1).replace('.0', '') + 'K';
  return String(n);
};

const el = (tag, cls, html) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html != null) e.innerHTML = html;
  return e;
};

const esc = (s) => String(s == null ? '' : s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

// botão de copiar reutilizável
function copyBtn(getText, label = 'Copiar') {
  const b = el('button', 'copy-btn', '<span class="ci">⧉</span> ' + label);
  b.onclick = async (e) => {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(getText());
      b.innerHTML = '<span class="ci">✓</span> Copiado!';
      b.classList.add('done');
      setTimeout(() => { b.innerHTML = '<span class="ci">⧉</span> ' + label; b.classList.remove('done'); }, 1600);
    } catch (err) {
      b.innerHTML = 'Erro ao copiar';
    }
  };
  return b;
}

async function load() {
  let data;
  try {
    const res = await fetch('data/latest.json?_=' + Date.now());
    if (!res.ok) throw new Error('HTTP ' + res.status);
    data = await res.json();
  } catch (err) {
    document.querySelector('main').innerHTML =
      '<section><h2 class="section-title">Sem dados ainda</h2>' +
      '<p class="subtitle">O sistema ainda não publicou dados. Rode o engine para popular a dashboard.</p></section>';
    console.error(err);
    return;
  }
  render(data);
}

function render(data) {
  document.getElementById('nicho-pill').textContent = 'Nicho: ' + (data.nicho || '—');
  document.getElementById('updated').textContent = 'Atualizado em ' + (data.generated_at || '—');
  document.getElementById('foot-date').textContent = data.generated_at || '—';

  renderStats(data.resumo || {});

  if (data.multi_network) {
    renderMultiNetwork(data);
  } else {
    // formato single-rede (o pipeline gera assim): hooks/roteiros no topo
    renderAnalysis(data.analise);
    renderNetworks(data.networks || {});
    renderHooks(data.hooks || []);
    renderScripts(data.roteiros || []);
    renderPatterns(data.patterns || []);
    renderTakeaway(data.takeaway);
    renderCalendar(data.calendar || []);
  }
}

// ---- MULTI-REDE: o seletor troca TODO o conteúdo da rede ----
let MULTI = null;
function renderMultiNetwork(data) {
  MULTI = data.networks || {};
  const order = (data.network_order && data.network_order.length)
    ? data.network_order : Object.keys(MULTI);
  const tabs = document.getElementById('net-tabs');
  tabs.innerHTML = '';
  order.forEach((k, i) => {
    const n = MULTI[k];
    if (!n) return;
    const t = el('button', 'net-tab' + (i === 0 ? ' active' : ''), (n.emoji || '') + ' ' + esc(n.label || k));
    t.onclick = () => {
      document.querySelectorAll('.net-tab').forEach((x) => x.classList.remove('active'));
      t.classList.add('active');
      selectNetwork(k);
    };
    tabs.appendChild(t);
  });
  if (order.length) selectNetwork(order[0]);
}

function selectNetwork(key) {
  const n = MULTI[key];
  if (!n) return;
  if (n.resumo) renderStats(n.resumo);
  renderAnalysis(n.analise);
  renderPostsList(n.posts || []);
  renderHooks(n.hooks || []);
  renderScripts(n.roteiros || []);
  renderPatterns(n.patterns || []);
  renderTakeaway(n.takeaway);
  renderCalendar(n.calendar || []);
}

// desenha posts a partir de uma lista (multi-rede) — reusa o mesmo card
function renderPostsList(posts) {
  const wrap = document.getElementById('posts');
  wrap.innerHTML = '';
  posts.forEach((p) => wrap.appendChild(buildPostCard(p)));
}

function hide(id) { const s = document.getElementById(id); if (s) s.style.display = 'none'; }

function renderStats(r) {
  const wrap = document.getElementById('stats');
  wrap.innerHTML = '';
  const items = [
    { num: r.posts_analisados ?? '—', lbl: 'Vídeos analisados' },
    { num: r.redes ?? '—', lbl: 'Redes cruzadas' },
    { num: r.melhor_rede ?? '—', lbl: 'Rede que mais bomba' },
    { num: r.melhor_formato ?? '—', lbl: 'Formato campeão' },
  ];
  items.forEach((it) => {
    const s = el('div', 'stat');
    s.appendChild(el('div', 'num', esc(it.num)));
    s.appendChild(el('div', 'lbl', esc(it.lbl)));
    wrap.appendChild(s);
  });
}

function renderAnalysis(a) {
  const wrap = document.getElementById('analysis');
  const sec = document.getElementById('analise-sec');
  if (sec) sec.style.display = a ? '' : 'none';
  if (!a) return;
  document.getElementById('analise-sub').textContent = a.titulo || 'Você vs. os campeões';
  wrap.innerHTML = '';

  const ic = el('div', 'insight-card');
  ic.appendChild(el('span', 'badge', '🎯 Diagnóstico'));
  ic.appendChild(el('h3', null, esc(a.titulo || 'Você vs. os campeões')));
  ic.appendChild(el('p', null, esc(a.insight || '')));
  wrap.appendChild(ic);

  const comp = el('div', 'compare');
  const head = el('div', 'crow');
  head.appendChild(el('div', 'chead', 'Critério'));
  head.appendChild(el('div', 'chead', 'Você'));
  head.appendChild(el('div', 'chead', 'Campeões'));
  head.appendChild(el('div', 'chead', ''));
  comp.appendChild(head);
  (a.comparacao || []).forEach((c) => {
    const row = el('div', 'crow');
    row.appendChild(el('div', 'crit', esc(c.criterio)));
    row.appendChild(el('div', 'val', esc(c.voce)));
    row.appendChild(el('div', 'val camp', esc(c.campeoes)));
    row.appendChild(el('div', 'dot ' + (c.status || 'ok')));
    comp.appendChild(row);
  });
  wrap.appendChild(comp);
}

let NETWORKS = {};
function renderNetworks(nets) {
  NETWORKS = nets;
  const tabs = document.getElementById('net-tabs');
  tabs.innerHTML = '';
  const keys = Object.keys(nets);
  keys.forEach((k, i) => {
    const n = nets[k];
    const t = el('button', 'net-tab' + (i === 0 ? ' active' : ''), (n.emoji || '') + ' ' + esc(n.label || k));
    t.onclick = () => {
      document.querySelectorAll('.net-tab').forEach((x) => x.classList.remove('active'));
      t.classList.add('active');
      renderPosts(k);
    };
    tabs.appendChild(t);
  });
  if (keys.length) renderPosts(keys[0]);
}

function renderPosts(key) {
  const wrap = document.getElementById('posts');
  wrap.innerHTML = '';
  const net = NETWORKS[key];
  if (!net || !net.posts) return;
  net.posts.forEach((p) => wrap.appendChild(buildPostCard(p)));
}

// card de vídeo reutilizável (usado no modo single e multi-rede)
function buildPostCard(p) {
  const c = el('div', 'card');
  const top = el('div', 'card-top');
  top.appendChild(el('div', 'rank' + (p.rank === 1 ? ' top1' : ''), '#' + p.rank));
  top.appendChild(el('div', 'score-badge', 'Score ' + p.score));
  c.appendChild(top);
  // thumbnail real (YouTube)
  if (p.thumbnail_url) {
    const th = el('div', 'card-thumb');
    const img = document.createElement('img');
    img.src = p.thumbnail_url; img.alt = 'thumbnail'; img.loading = 'lazy';
    th.appendChild(img);
    c.appendChild(th);
  }
  c.appendChild(el('div', 'profile', esc(p.profile)));
  c.appendChild(el('div', 'hook', '“' + esc(p.hook) + '”'));
  const stats = el('div', 'card-stats');
  stats.appendChild(el('div', 'cs', '<b>' + fmt(p.views) + '</b>views'));
  if (!p.no_likes) stats.appendChild(el('div', 'cs', '<b>' + fmt(p.likes) + '</b>likes'));
  if (p.comments > 0) stats.appendChild(el('div', 'cs', '<b>' + fmt(p.comments) + '</b>coment.'));
  if (p.saves > 0) stats.appendChild(el('div', 'cs', '<b>' + fmt(p.saves) + '</b>saves'));
  c.appendChild(stats);
  // power words (título + thumb) — chips
  if (p.power_words && p.power_words.length) {
    const pw = el('div', 'powerwords');
    p.power_words.slice(0, 6).forEach(function (w) {
      pw.appendChild(el('span', 'pw-chip', esc(w)));
    });
    c.appendChild(pw);
  }
  // análise de thumbnail (por que gera clique)
  if (p.thumbnail_analysis) {
    const ta = el('div', 'thumb-analysis');
    ta.appendChild(el('div', 'ta-label', '🖼️ Por que a thumb funciona'));
    ta.appendChild(el('div', 'ta-text', esc(p.thumbnail_analysis)));
    c.appendChild(ta);
  }
  const foot = el('div', 'card-foot');
  foot.appendChild(el('span', 'fmt', esc(p.format) + ' · ' + p.posted_days_ago + 'd atrás'));
  const link = el('a', 'link', 'Ver post →');
  link.href = p.url; link.target = '_blank'; link.rel = 'noopener';
  foot.appendChild(link);
  c.appendChild(foot);
  return c;
}

function renderHooks(hooks) {
  const wrap = document.getElementById('hooks');
  const sec = document.getElementById('hooks-sec');
  if (sec) sec.style.display = hooks.length ? '' : 'none';
  if (!hooks.length) return;
  wrap.innerHTML = '';
  hooks.forEach((h, i) => {
    const d = el('div', 'hook-item');
    d.appendChild(el('div', 'hook-n', String(i + 1)));
    const body = el('div', 'hook-body');
    body.appendChild(el('div', 'hook-txt', '“' + esc(h.hook) + '”'));
    if (h.why) body.appendChild(el('div', 'hook-why', esc(h.why)));
    d.appendChild(body);
    d.appendChild(copyBtn(() => h.hook, ''));
    wrap.appendChild(d);
  });
}

function renderScripts(roteiros) {
  const wrap = document.getElementById('scripts');
  wrap.innerHTML = '';
  roteiros.forEach((r) => {
    const s = el('div', 'script');
    const head = el('div', 'script-head');
    const htop = el('div', 'script-head-top');
    htop.appendChild(el('h3', null, esc(r.titulo)));
    // botão copiar roteiro inteiro (hook + A/V)
    htop.appendChild(copyBtn(() => {
      let out = r.titulo + '\n';
      if (r.hook_ref) out += 'Hook: ' + r.hook_ref + '\n\n';
      if (r.av) out += r.av;
      return out;
    }, 'Copiar roteiro'));
    head.appendChild(htop);
    const meta = el('div', 'rt-meta');
    if (r.rede) meta.appendChild(el('span', 'rt-tag', esc(r.rede)));
    if (r.duracao) meta.appendChild(el('span', 'rt-tag', '⏱ ' + esc(r.duracao)));
    if (r.baseado_em) meta.appendChild(el('span', 'rt-tag', '📊 ' + esc(r.baseado_em)));
    head.appendChild(meta);
    s.appendChild(head);

    const body = el('div', 'script-body');
    if (r.hook_ref) {
      const g = el('div', 'gancho');
      g.appendChild(el('span', null, 'Hook'));
      g.appendChild(document.createTextNode('“' + r.hook_ref + '”'));
      body.appendChild(g);
    }
    if (r.av) {
      const av = el('pre', 'av');
      av.textContent = r.av;
      body.appendChild(av);
    }
    if (r.estrutura) {
      r.estrutura.forEach((st) => {
        const step = el('div', 'step');
        step.appendChild(el('div', 't', st.tempo));
        step.appendChild(el('div', 'a', esc(st.acao)));
        body.appendChild(step);
      });
    }
    s.appendChild(body);
    wrap.appendChild(s);
  });
}

function renderPatterns(patterns) {
  const wrap = document.getElementById('patterns');
  wrap.innerHTML = '';
  patterns.forEach((p) => {
    const d = el('div', 'pattern');
    d.appendChild(el('h3', null, esc(p.titulo)));
    d.appendChild(el('p', null, esc(p.detalhe)));
    const bar = el('div', 'bar');
    bar.appendChild(el('span', null, '')).style.width = (p.forca || 0) + '%';
    d.appendChild(bar);
    d.appendChild(el('div', 'bar-lbl', 'Força do padrão: ' + (p.forca || 0) + '%'));
    wrap.appendChild(d);
  });
}

function renderTakeaway(t) {
  const wrap = document.getElementById('takeaway');
  const sec = document.getElementById('takeaway-sec');
  if (sec) sec.style.display = t ? '' : 'none';
  if (!t) return;
  wrap.innerHTML = '';
  const card = el('div', 'takeaway-card');
  card.appendChild(el('p', 'tk-text', esc(t.texto || '')));
  if (t.acoes && t.acoes.length) {
    const ul = el('ul', 'tk-list');
    t.acoes.forEach((a) => ul.appendChild(el('li', null, esc(a))));
    card.appendChild(ul);
  }
  wrap.appendChild(card);
}

function renderCalendar(cal) {
  const wrap = document.getElementById('calendar');
  wrap.innerHTML = '';
  cal.forEach((c) => {
    const d = el('div', 'day');
    d.appendChild(el('div', 'dow', esc(c.dia)));
    d.appendChild(el('div', 'net', esc(c.rede) + ' · ' + esc(c.formato)));
    d.appendChild(el('div', 'idea', esc(c.ideia)));
    if (c.hook_sugerido) d.appendChild(el('span', 'hooktag', '💡 ' + esc(c.hook_sugerido)));
    wrap.appendChild(d);
  });
}

load();
