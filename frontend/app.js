/* Okey 101 — istemci. Sunucu otoriter; burada yalnızca niyet gönderilir. */
"use strict";

let WS = null;
let PID = localStorage.getItem("okey_pid") || null;
let IS_HOST = false;
let ROOM = null;
let S = null;                 // son private_state
let selected = new Set();     // seçili tid'ler (elimde)
let staged = [];              // [[tid,...], ...] açılış için hazırlanan gruplar
let selectedMeld = null;      // işleme için seçili masa grubu meld_id
let handOrder = [];           // elimdeki taş sırası (yerel, sürükle-bırak)

const $ = (id) => document.getElementById(id);
const COLOR_TR = { kirmizi: "Kırmızı", mavi: "Mavi", siyah: "Siyah", sari: "Sarı" };

/* ---------------- Bağlantı ---------------- */
function connect(room, name) {
  ROOM = room;
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  WS = new WebSocket(`${proto}//${location.host}/ws/${encodeURIComponent(room)}`);
  WS.onopen = () => WS.send(JSON.stringify({ type: "hello", room, name, pid: PID }));
  WS.onmessage = (ev) => onMessage(JSON.parse(ev.data));
  WS.onclose = () => { toast("Bağlantı koptu, yeniden deneniyor…"); setTimeout(() => connect(room, name), 1500); };
}

function send(obj) {
  if (WS && WS.readyState === WebSocket.OPEN) WS.send(JSON.stringify(obj));
}

function onMessage(msg) {
  if (msg.type === "joined") {
    PID = msg.pid; IS_HOST = msg.is_host;
    localStorage.setItem("okey_pid", PID);
  } else if (msg.type === "state") {
    S = msg.state;
    syncHandOrder();
    render();
  } else if (msg.type === "error") {
    toast(msg.message);
  }
}

/* ---------------- Yardımcılar ---------------- */
function me() { return S ? S.you : null; }
function myTurn() { return S && S.turn === PID; }
function isWild(t) { return !t.is_fake_joker && S.okey && t.color === S.okey.color && t.number === S.okey.number; }

function syncHandOrder() {
  if (!S || !S.you) return;
  const ids = S.you.hand.map((t) => t.tid);
  handOrder = handOrder.filter((id) => ids.includes(id));     // gidenleri çıkar
  for (const id of ids) if (!handOrder.includes(id)) handOrder.push(id); // yenileri ekle
}

function orderedHand() {
  const byId = {}; S.you.hand.forEach((t) => (byId[t.tid] = t));
  return handOrder.map((id) => byId[id]).filter(Boolean);
}

/* ---------------- Taş render ---------------- */
function tileEl(t, cls = "") {
  const d = document.createElement("div");
  if (t.is_fake_joker) { d.className = `tile fake ${cls}`; return d; }
  d.className = `tile c-${t.color} ${cls}`;
  d.textContent = t.number;
  const dot = document.createElement("span"); dot.className = "dot"; d.appendChild(dot);
  if (isWild(t)) { const r = document.createElement("span"); r.className = "okey-rib"; r.textContent = "OKEY"; d.appendChild(r); }
  return d;
}

/* ---------------- Render: lobi / masa ---------------- */
function render() {
  if (!S) return;
  const inGame = S.phase !== "waiting";
  $("lobby").style.display = inGame ? "none" : "";
  $("table").classList.toggle("active", inGame);
  if (!inGame) renderLobby(); else renderTable();
  renderResult();
}

function renderLobby() {
  $("lobby-room").style.display = "";
  const list = $("seat-list"); list.innerHTML = "";
  S.players.forEach((p) => {
    const el = document.createElement("div"); el.className = "seat";
    el.innerHTML = `<span class="dot ${p.connected ? "" : "off"}"></span>${escapeHtml(p.name)}${p.pid === PID ? " (sen)" : ""}`;
    if (p.is_bot) { const b = document.createElement("span"); b.className = "bot-badge"; b.textContent = "bot"; el.appendChild(b); }
    list.appendChild(el);
  });
  const full = S.players.length === 4;
  $("btn-start").disabled = !(IS_HOST && full);
  $("btn-addbots").style.display = IS_HOST && !full ? "" : "none";
  $("lobby-hint").textContent = IS_HOST
    ? (full ? "Her şey hazır — başlat!" : `Oyuncu: ${S.players.length}/4. Arkadaşların oda kodunu girsin ya da bota doldur.`)
    : "Oda sahibinin başlatması bekleniyor…";
}

function renderTable() {
  $("room-code").textContent = `Oda: ${ROOM}`;
  $("indicator").innerHTML = ""; if (S.indicator) $("indicator").appendChild(tileEl(S.indicator, "small"));
  $("okey-info").textContent = S.okey ? `${COLOR_TR[S.okey.color]} ${S.okey.number}` : "—";
  $("draw-pile").textContent = S.draw_count;

  // oyuncu konumları: ben alttayım; sağım = benden önceki (atını alırım)
  const n = S.players.length, myIdx = S.players.findIndex((p) => p.pid === PID);
  const at = (off) => S.players[(myIdx + off) % n];
  renderPlayer($("p-left"), at(1), "left");
  renderPlayer($("p-top"), at(2), "top");
  renderPlayer($("p-right"), at(3), "right");

  renderTableMelds();
  renderMyHand();
  renderControls();
  renderLog();
}

function renderPlayer(el, p, pos) {
  if (!p) { el.style.display = "none"; return; }
  el.style.display = "";
  el.classList.toggle("turn", S.turn === p.pid);
  const mini = Array.from({ length: Math.min(p.hand_count, 16) }, () => '<span class="mini"></span>').join("");
  const disc = S.discards[p.pid] && S.discards[p.pid][0];
  el.innerHTML = `
    <div class="pname">${escapeHtml(p.name)} ${p.opened ? '<span class="opened-badge">açık</span>' : ""}</div>
    <div class="pstat">Taş: ${p.hand_count} · Puan: ${p.score}</div>
    <div class="mini-hand">${mini}</div>`;
  const dd = document.createElement("div"); dd.className = "their-discard";
  if (disc) dd.appendChild(tileEl(disc, "small"));
  el.appendChild(dd);
}

function renderTableMelds() {
  const wrap = $("table-melds"); wrap.innerHTML = "";
  if (!S.table.length) { wrap.innerHTML = '<div class="hint">Henüz açılan grup yok</div>'; return; }
  S.table.forEach((m) => {
    const g = document.createElement("div");
    g.className = "meld" + (me().opened && myTurn() && S.phase === "action" ? " selectable" : "") + (selectedMeld === m.meld_id ? " selected" : "");
    const own = S.players.find((p) => p.pid === m.owner);
    const lbl = document.createElement("span"); lbl.className = "owner"; lbl.textContent = own ? own.name : ""; g.appendChild(lbl);
    m.tiles.forEach((t) => g.appendChild(tileEl(t, "small")));
    if (me().opened) g.onclick = () => { selectedMeld = selectedMeld === m.meld_id ? null : m.meld_id; render(); };
    wrap.appendChild(g);
  });
}

function renderMyHand() {
  const info = $("myinfo");
  const meP = S.players.find((p) => p.pid === PID);
  info.innerHTML = `<span class="me-name">${escapeHtml(meP.name)}</span>
    <span>Puan: ${meP.score}</span>
    ${meP.opened ? '<span class="opened-badge">açıldın</span>' : '<span class="hint">açılmadın (101 gerek)</span>'}
    ${myTurn() ? '<span style="color:var(--gold);font-weight:700">● Sıra sende</span>' : '<span class="hint">sıra: ' + escapeHtml((S.players.find(p=>p.pid===S.turn)||{}).name||"") + "</span>"}`;

  const hand = $("myhand"); hand.innerHTML = "";
  const stagedIds = new Set(staged.flat());
  orderedHand().forEach((t) => {
    const cls = "selectable" + (selected.has(t.tid) ? " selected" : "") + (stagedIds.has(t.tid) ? " staged" : "");
    const el = tileEl(t, cls);
    el.draggable = true;
    el.ondragstart = (e) => e.dataTransfer.setData("tid", t.tid);
    el.ondragover = (e) => e.preventDefault();
    el.ondrop = (e) => { e.preventDefault(); reorder(parseInt(e.dataTransfer.getData("tid")), t.tid); };
    el.onclick = () => {
      if (stagedIds.has(t.tid)) return;
      selected.has(t.tid) ? selected.delete(t.tid) : selected.add(t.tid);
      render();
    };
    hand.appendChild(el);
  });

  // hazırlanan açılış grupları
  const st = $("staging"); st.innerHTML = "";
  if (staged.length) {
    staged.forEach((grp, i) => {
      const box = document.createElement("div"); box.className = "staged-group";
      grp.forEach((tid) => { const t = S.you.hand.find((x) => x.tid === tid); if (t) box.appendChild(tileEl(t, "small")); });
      box.title = "Kaldırmak için tıkla";
      box.onclick = () => { staged.splice(i, 1); render(); };
      st.appendChild(box);
    });
    const total = document.createElement("span"); total.className = "hint";
    st.appendChild(total);
  }
}

function reorder(dragTid, dropTid) {
  if (dragTid === dropTid) return;
  const from = handOrder.indexOf(dragTid), to = handOrder.indexOf(dropTid);
  if (from < 0 || to < 0) return;
  handOrder.splice(from, 1);
  handOrder.splice(handOrder.indexOf(dropTid) + (from < to ? 1 : 0), 0, dragTid);
  render();
}

/* ---------------- Kontroller ---------------- */
function renderControls() {
  const c = $("controls"); c.innerHTML = "";
  if (!myTurn()) { c.innerHTML = '<span class="hint">Sıranı bekle…</span>'; return; }

  if (S.phase === "draw") {
    c.appendChild(btn("Desteden Çek", () => send({ type: "draw", source: "pile" }), "gold"));
    // sağdaki oyuncunun (benden önceki) attığını al
    const n = S.players.length, myIdx = S.players.findIndex((p) => p.pid === PID);
    const prev = S.players[(myIdx + n - 1) % n];
    const hasDisc = S.discards[prev.pid] && S.discards[prev.pid][0];
    const b = btn(hasDisc ? "Atılanı Al" : "Alınacak taş yok", () => send({ type: "draw", source: "discard" }));
    b.disabled = !hasDisc; c.appendChild(b);
    return;
  }

  if (S.phase === "action") {
    if (!me().opened) {
      c.appendChild(btn("Seçilenleri gruba ekle", stageGroup));
      const openBtn = btn(`Aç (${staged.length} grup)`, doOpen, staged.length ? "gold" : "");
      openBtn.disabled = staged.length === 0;
      c.appendChild(openBtn);
      c.appendChild(hintSpan(`Grupları hazırla, sonra Aç. Toplam ≥101 olmalı (sunucu kontrol eder). Seçili: ${selected.size} taş.`));
    } else {
      // işleme
      const pb = btn("Seçilenleri işle (masaya ekle)", doProcess);
      pb.disabled = !(selectedMeld && selected.size);
      c.appendChild(pb);
      c.appendChild(hintSpan(selectedMeld ? "Bir masa grubu seçili. Elinden taş seç ve işle." : "İşlemek için bir masa grubuna tıkla."));
    }
    // atma
    const db = btn("Seçili taşı AT", doDiscard, "danger");
    db.disabled = selected.size !== 1;
    c.appendChild(db);
  }
}

function stageGroup() {
  if (selected.size < 3) { toast("Grup en az 3 taş olmalı"); return; }
  staged.push([...selected]); selected.clear(); render();
}
function doOpen() {
  if (!staged.length) return;
  send({ type: "open", groups: staged });
  staged = []; selected.clear();
}
function doProcess() {
  if (!selectedMeld || !selected.size) return;
  send({ type: "process", meld_id: selectedMeld, tids: [...selected] });
  selected.clear(); selectedMeld = null;
}
function doDiscard() {
  if (selected.size !== 1) return;
  send({ type: "discard", tid: [...selected][0] });
  selected.clear();
}

/* ---------------- Sonuç ekranı ---------------- */
function renderResult() {
  const show = S && S.phase === "finished";
  $("result").classList.toggle("show", show);
  if (!show) return;
  const winner = S.players.find((p) => p.pid === S.winner);
  $("result-title").textContent = winner ? `🏆 ${winner.name} kazandı!` : "El berabere (deste bitti)";
  const tbl = $("result-table"); tbl.innerHTML = "";
  S.players.slice().sort((a, b) => a.score - b.score).forEach((p) => {
    const d = S.last_delta[p.pid] || 0;
    const cls = d === 0 ? "zero" : "plus";
    tbl.innerHTML += `<tr><td>${escapeHtml(p.name)}${p.pid === PID ? " (sen)" : ""}</td>
      <td class="delta ${cls}">${d === 0 ? "±0" : "+" + d}</td>
      <td style="text-align:right">toplam ${p.score}</td></tr>`;
  });
  $("btn-newhand").style.display = IS_HOST ? "" : "none";
}

/* ---------------- UI ufak parçalar ---------------- */
function btn(label, onclick, cls = "") { const b = document.createElement("button"); if (cls) b.className = cls; b.textContent = label; b.onclick = onclick; return b; }
function hintSpan(txt) { const s = document.createElement("span"); s.className = "hint"; s.textContent = txt; return s; }
function renderLog() { const b = $("log-body"); b.innerHTML = (S.log || []).slice().reverse().map((l) => `<div>${escapeHtml(l)}</div>`).join(""); }
let toastTimer = null;
function toast(msg) { const t = $("toast"); t.textContent = msg; t.classList.add("show"); clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove("show"), 2600); }
function escapeHtml(s) { return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }

/* ---------------- Olay bağlama ---------------- */
$("btn-join").onclick = () => {
  const name = $("in-name").value.trim() || "Oyuncu";
  const room = $("in-room").value.trim() || "salon1";
  localStorage.setItem("okey_name", name);
  connect(room, name);
  $("btn-join").disabled = true; $("in-name").disabled = $("in-room").disabled = true;
};
$("btn-addbots").onclick = () => send({ type: "add_bots" });
$("btn-start").onclick = () => send({ type: "start" });
$("btn-newhand").onclick = () => { send({ type: "new_hand" }); };
$("btn-log").onclick = () => $("log").classList.toggle("show");

// kayıtlı ad/oda ön-doldur
$("in-name").value = localStorage.getItem("okey_name") || "";
