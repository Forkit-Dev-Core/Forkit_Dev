"use strict";
const report = JSON.parse(document.getElementById("report").textContent);
const cards = JSON.parse(document.getElementById("cards").textContent);
const records = report.records;
let selectedView = "latest";
const titles = {latest:"Latest session",today:"Today",week:"This week",history:"History"};
const status = document.getElementById("share-status");
const search = document.getElementById("search");
function countIntent(event, action) {
  if (!event.isTrusted || document.hidden || document.body.dataset.native !== "true") return;
  window.webkit?.messageHandlers?.forkitUsage?.postMessage(action);
}
function visibleRecord(record,index) {
  if (selectedView === "latest") return index === 0;
  if (selectedView === "history") return true;
  const period = report.periods[selectedView];
  return record.local_date >= period.start_date && record.local_date < period.end_date_exclusive && record.receipt.finished_at <= report.generated_at;
}
function stats() {
  if (selectedView !== "latest") return report.periods[selectedView];
  const first = records[0];
  return {receipts:first?1:0,file_changes:first?first.receipt.file_changes.length:0,meaningful_changes:first?first.during_count+first.between_count:0,partial_receipts:first&&first.partial?1:0};
}
function refresh() {
  document.querySelectorAll("[data-view]").forEach(button => button.setAttribute("aria-pressed",String(button.dataset.view === selectedView)));
  document.getElementById("view-title").textContent = titles[selectedView];
  const summary = stats();
  [["receipts","receipts"],["files","file_changes"],["changes","meaningful_changes"]].forEach(([node,key]) => {
    document.getElementById("metric-"+node).textContent = summary[key].toLocaleString();
  });
  const latest = selectedView === "latest";
  document.querySelectorAll('.change-map').forEach(node => {node.hidden = !latest;});
  document.querySelector(".metrics").hidden = latest;
  document.querySelector(".search").hidden = latest;
  const description = document.getElementById("view-description");
  description.textContent = latest ? "" : selectedView === "history" ? "Your saved sessions" : "Sessions completed in your local calendar " + (selectedView === "today" ? "day" : "week");
  description.hidden = latest;
  const coverage = document.getElementById("coverage-note");
  coverage.hidden = latest || !summary.partial_receipts;
  coverage.textContent = summary.partial_receipts + " receipts have partial coverage. Counts may be incomplete.";
  const query = search.value.trim().toLowerCase();
  let shown = 0;
  document.querySelectorAll(".receipt").forEach(node => {
    const index = Number(node.dataset.index);
    const matches = visibleRecord(records[index],index) && (!query || node.textContent.toLowerCase().includes(query));
    node.hidden = !matches;
    if (matches) shown++;
  });
  document.getElementById("empty").hidden = shown !== 0;
  document.getElementById("empty-description").textContent = query ? "Try another search." : report.total_receipts ? "No completed sessions in this view. Check History." : document.body.dataset.native === "true" ? "Finish a coding session. Its receipt will appear here." : "Finish a coding session, then reopen Forkit.";
  const shownLabel = document.getElementById("shown");
  shownLabel.hidden = latest || (!query && report.displayed_receipts === report.total_receipts);
  shownLabel.textContent = query ? shown + " matching receipts" : "Showing the latest " + report.displayed_receipts + " of " + report.total_receipts + " receipts. Totals include all saved history.";
  const share = document.getElementById("share");
  share.disabled = !cards[selectedView];
  share.hidden = selectedView === "history" || (latest && !cards.latest);
  status.hidden = share.hidden;
  share.textContent = "Share card";
}
function save(blob,name) {
  const url=URL.createObjectURL(blob),link=document.createElement("a");
  link.href=url;link.download=name;document.body.append(link);link.click();link.remove();
  setTimeout(()=>URL.revokeObjectURL(url),10000);
}
document.querySelectorAll('[data-activity]').forEach(button=>button.addEventListener('click',()=>{
  const record=records[Number(button.dataset.activity)];
  save(new Blob([JSON.stringify({kind:'forkit_private_tool_activity',session_id:record.receipt.session_id,...record.activity},null,2)],{type:'application/json'}),'forkit-private-activity.json');
}));
document.querySelectorAll("[data-view]").forEach(button=>button.addEventListener("click",event=>{
  selectedView=button.dataset.view;
  if (selectedView === "latest") search.value="";
  status.textContent="Counts only. Saved locally.";
  refresh();
  countIntent(event, selectedView === "history" ? "history" : "view");
}));
document.querySelectorAll("a[href^='#']").forEach(link=>link.addEventListener("click",()=>{
  const target=document.getElementById(link.getAttribute("href").slice(1));
  if (target && target.tagName === "DETAILS") target.open=true;
}));
search.addEventListener("input",refresh);
document.getElementById("share").addEventListener("click",()=>{
  if (!cards[selectedView]) return;
  const bytes=Uint8Array.from(atob(cards[selectedView]),c=>c.charCodeAt(0));
  save(new Blob([bytes],{type:"text/html"}),"forkit-"+selectedView+"-share-card.html");
  status.textContent=document.body.dataset.native === "true" ? "Choose where to save your card." : "Card saved. Open it to save PNG or SVG.";
});
document.querySelectorAll("[data-receipt]").forEach(button=>button.addEventListener("click",()=>{
  const record=records[Number(button.dataset.receipt)];
  save(new Blob([JSON.stringify(record.receipt,null,2)],{type:"application/json"}),"forkit-private-receipt.json");
  status.hidden=false;
  status.textContent=document.body.dataset.native === "true" ? "Choose where to save this private receipt." : "JSON saved with private filenames and identity details. Use a share card for public sharing.";
}));
refresh();

// The native window restores only this bounded local view state after a refresh.
window.forkitViewState = () => ({view:selectedView,query:search.value.slice(0,256),scroll:window.scrollY,
  opened:Array.from(document.querySelectorAll('.receipt-detail[open]')).map(n=>records[Number(n.closest('.receipt').dataset.index)].receipt.session_id)});
window.forkitRestoreView = state => {
  if (!state || !Object.prototype.hasOwnProperty.call(titles,state.view)) return;
  selectedView=state.view;search.value=typeof state.query==='string'?state.query.slice(0,256):'';
  refresh();
  if (Array.isArray(state.opened)) document.querySelectorAll('.receipt-detail').forEach(n=>{n.open=state.opened.includes(records[Number(n.closest('.receipt').dataset.index)].receipt.session_id);});
  if (Number.isFinite(state.scroll)) window.scrollTo(0,Math.max(0,state.scroll));
};
window.forkitExportStatus = message => {if (typeof message === 'string') {status.hidden=false;status.textContent=message.slice(0,256);}};

// Highlight stored areas only after a click. No polling, live route or inferred
// chronology. Hidden pages and reduced-motion users never run the animation.
document.querySelectorAll('.change-map').forEach(map => {
  const replay = map.querySelector('.map-replay');
  const zones = Array.from(map.querySelectorAll('[data-map-zone]'));
  let timer;
  function stop() {
    clearTimeout(timer);map.classList.remove('map-replaying');replay.disabled=false;
  }
  zones.forEach(zone => zone.addEventListener('click', () => {
    stop();
    zones.forEach(other => other.setAttribute('aria-pressed',String(other === zone)));
    map.querySelectorAll('[data-map-detail]').forEach(detail => {
      detail.hidden = detail.dataset.mapDetail !== zone.dataset.mapZone;
    });
  }));
  replay.addEventListener('click', () => {
    stop();
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      zones[0]?.click();return;
    }
    replay.disabled=true;map.classList.add('map-replaying');
    timer=setTimeout(stop,zones.length*800+100);
  });
  document.addEventListener('visibilitychange', () => {if (document.hidden) stop();});
  document.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click',stop));
});
