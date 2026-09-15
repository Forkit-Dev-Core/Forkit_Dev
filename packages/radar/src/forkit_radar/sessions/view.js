"use strict";
const report = JSON.parse(document.getElementById("report").textContent);
const cards = JSON.parse(document.getElementById("cards").textContent);
const records = report.records;
let selectedView = "latest";
const titles = {latest:"Latest session",today:"Today",week:"This week",history:"History"};
const status = document.getElementById("share-status");
const search = document.getElementById("search");
function visibleRecord(record,index) {
  if (selectedView === "latest") return index === 0;
  if (selectedView === "history") return true;
  const period = report.periods[selectedView];
  return record.local_date >= period.start_date && record.local_date < period.end_date_exclusive && record.receipt.finished_at <= report.generated_at;
}
function stats() {
  if (selectedView !== "latest") return report.periods[selectedView];
  const first = records[0];
  return {receipts:first?1:0,meaningful_changes:first?first.during_count+first.between_count:0,reconstructable_changes:first?first.reconstructable_changes:0,partial_receipts:first&&first.partial?1:0};
}
function refresh() {
  document.querySelectorAll("[data-view]").forEach(button => button.setAttribute("aria-pressed",String(button.dataset.view === selectedView)));
  document.getElementById("view-title").textContent = titles[selectedView];
  const summary = stats();
  [["receipts","receipts"],["changes","meaningful_changes"],["traces","reconstructable_changes"],["partial","partial_receipts"]].forEach(([node,key]) => {
    document.getElementById("metric-"+node).textContent = summary[key].toLocaleString();
  });
  document.getElementById("view-description").textContent = selectedView === "latest" ? "Captured changes and declared metadata." : selectedView === "history" ? "Observed revisions and selected Passport versions across your saved sessions." : report.periods[selectedView].start_date + " to " + report.periods[selectedView].end_date_exclusive + " (end exclusive) · grouped by receipt completion";
  const query = search.value.trim().toLowerCase();
  let shown = 0;
  document.querySelectorAll(".receipt").forEach(node => {
    const index = Number(node.dataset.index);
    const matches = visibleRecord(records[index],index) && (!query || node.textContent.toLowerCase().includes(query));
    node.hidden = !matches;
    if (matches) shown++;
  });
  document.getElementById("empty").hidden = shown !== 0;
  document.getElementById("shown").textContent = shown + " matching receipts shown · timeline contains the latest " + report.displayed_receipts + " of " + report.total_receipts + ". Calendar totals use all retained receipts; search filters the shown timeline only.";
  const share = document.getElementById("share");
  share.disabled = !cards[selectedView];
  share.textContent = selectedView === "history" ? "Choose day, week or latest to share" : "Save aggregate share card";
}
function save(blob,name) {
  const url=URL.createObjectURL(blob),link=document.createElement("a");
  link.href=url;link.download=name;document.body.append(link);link.click();link.remove();
  setTimeout(()=>URL.revokeObjectURL(url),10000);
}
document.querySelectorAll("[data-view]").forEach(button=>button.addEventListener("click",()=>{selectedView=button.dataset.view;refresh();}));
search.addEventListener("input",refresh);
document.getElementById("share").addEventListener("click",()=>{
  if (!cards[selectedView]) return;
  const bytes=Uint8Array.from(atob(cards[selectedView]),c=>c.charCodeAt(0));
  save(new Blob([bytes],{type:"text/html"}),"forkit-"+selectedView+"-share-card.html");
  status.textContent="Aggregate card saved locally. Open it to review and save PNG or SVG. Nothing uploaded.";
});
document.querySelectorAll("[data-receipt]").forEach(button=>button.addEventListener("click",()=>{
  const record=records[Number(button.dataset.receipt)];
  save(new Blob([JSON.stringify(record.receipt,null,2)],{type:"application/json"}),"forkit-private-receipt.json");
  status.textContent="Private receipt JSON saved locally. It contains filenames and identity details; use an aggregate card for public sharing.";
}));
refresh();
