const DATA_URL = "data/dashboard-data.json";
const LOCAL_STATUS_KEY = "smart4_check_documents_manual_status";

const state = {
  data: null,
  localEarlyIds: new Set(),
  filters: {
    search: "",
    type: "all",
    status: "all",
    sort: "name_asc",
  },
};

const STATUS = {
  submitted: { label: "작성", color: "#2f8f63" },
  missing: { label: "미작성", color: "#c84f4f" },
  early_employed: { label: "취업", color: "#d99a2b" },
};

document.addEventListener("DOMContentLoaded", init);

async function init() {
  bindControls();
  loadLocalStatus();

  try {
    const response = await fetch(DATA_URL, { cache: "no-store" });
    if (!response.ok) throw new Error(`데이터 응답 오류: ${response.status}`);
    state.data = await response.json();
  } catch (error) {
    showLoadError(error);
    return;
  }

  populateTypeFilter();
  render();
}

function bindControls() {
  document.getElementById("searchInput").addEventListener("input", (event) => {
    state.filters.search = event.target.value.trim().toLowerCase();
    renderStudents();
  });
  document.getElementById("typeFilter").addEventListener("change", (event) => {
    state.filters.type = event.target.value;
    renderStudents();
  });
  document.getElementById("statusFilter").addEventListener("change", (event) => {
    state.filters.status = event.target.value;
    renderStudents();
  });
  document.getElementById("sortSelect").addEventListener("change", (event) => {
    state.filters.sort = event.target.value;
    renderStudents();
  });
  document.getElementById("closeModal").addEventListener("click", closeModal);
  document.getElementById("modalBackdrop").addEventListener("click", (event) => {
    if (event.target.id === "modalBackdrop") closeModal();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeModal();
  });
}

function loadLocalStatus() {
  const raw = localStorage.getItem(LOCAL_STATUS_KEY);
  if (!raw) return;
  try {
    const parsed = JSON.parse(raw);
    state.localEarlyIds = new Set(parsed.earlyEmployedStudentIds || []);
  } catch {
    state.localEarlyIds = new Set();
  }
}

function saveLocalStatus() {
  localStorage.setItem(
    LOCAL_STATUS_KEY,
    JSON.stringify({ earlyEmployedStudentIds: [...state.localEarlyIds] }, null, 2)
  );
}

function populateTypeFilter() {
  const select = document.getElementById("typeFilter");
  select.innerHTML = `<option value="all">전체 문서</option>`;
  getDocumentTypes().forEach((type) => {
    const option = document.createElement("option");
    option.value = type.id;
    option.textContent = type.label;
    select.appendChild(option);
  });
}

function render() {
  document.getElementById("generatedAt").textContent = formatDateTime(state.data.generatedAt);
  renderSummary();
  renderCharts();
  renderStudents();
}

function getDocumentTypes() {
  return state.data.documentTypes || [];
}

function getStudents() {
  return (state.data.students || []).map((student) => {
    if (state.localEarlyIds.has(student.id)) {
      return { ...student, studentStatus: "early_employed" };
    }
    return student;
  });
}

function isEarlyEmployed(student) {
  return student.studentStatus === "early_employed";
}

function getDocStatus(student, typeId) {
  if (isEarlyEmployed(student)) return "early_employed";
  return student.documents?.[typeId]?.status === "submitted" ? "submitted" : "missing";
}

function renderSummary() {
  const summary = document.getElementById("summaryStrip");
  const students = getStudents();
  const earlyCount = students.filter(isEarlyEmployed).length;
  const submittedCount = students.filter(overallSubmitted).length;
  summary.innerHTML = "";

  [
    ["전체 학생", `${students.length}명`],
    ["작성", `${submittedCount}명`],
    ["취업", `${earlyCount}명`],
  ].forEach(([label, value]) => {
    const item = document.createElement("div");
    item.className = "summary-item";
    item.innerHTML = `<span>${label}</span><strong>${value}</strong>`;
    summary.appendChild(item);
  });
}

function renderCharts() {
  const grid = document.getElementById("chartsGrid");
  const template = document.getElementById("chartTemplate");
  const students = getStudents();
  grid.innerHTML = "";

  getDocumentTypes()
    .filter((type) => type.showChart)
    .forEach((type) => {
      const counts = countStatuses(students, type.id);
      const node = template.content.cloneNode(true);
      node.querySelector(".chart-label").textContent = "전체 인원 기준";
      node.querySelector("h2").textContent = type.label;
      const canvas = node.querySelector("canvas");
      drawDoughnut(canvas, counts);
      node.querySelector(".chart-percent").textContent = `작성 ${statusPercent(counts.submitted, students.length)}%`;
      renderLegend(node.querySelector(".legend"), counts, students.length);
      grid.appendChild(node);
    });
}

function countStatuses(students, typeId) {
  return students.reduce(
    (acc, student) => {
      acc[getDocStatus(student, typeId)] += 1;
      return acc;
    },
    { submitted: 0, missing: 0, early_employed: 0 }
  );
}

function statusPercent(count, total) {
  return total ? Math.round((count / total) * 100) : 0;
}

function drawDoughnut(canvas, counts) {
  const ctx = canvas.getContext("2d");
  const total = Object.values(counts).reduce((sum, value) => sum + value, 0);
  const center = canvas.width / 2;
  const radius = 76;
  let start = -Math.PI / 2;

  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!total) {
    ctx.strokeStyle = "#d8ded7";
    ctx.lineWidth = 28;
    ctx.beginPath();
    ctx.arc(center, center, radius, 0, Math.PI * 2);
    ctx.stroke();
    return;
  }

  Object.entries(STATUS).forEach(([key, meta]) => {
    const value = counts[key] || 0;
    if (!value) return;
    const angle = (value / total) * Math.PI * 2;
    ctx.strokeStyle = meta.color;
    ctx.lineWidth = 28;
    ctx.lineCap = "butt";
    ctx.beginPath();
    ctx.arc(center, center, radius, start, start + angle);
    ctx.stroke();
    start += angle;
  });

  ctx.fillStyle = "#20242a";
  ctx.font = "700 24px system-ui, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  const percent = statusPercent(counts.submitted || 0, total);
  ctx.fillText(`${percent}%`, center, center - 8);
  ctx.fillStyle = "#69717c";
  ctx.font = "12px system-ui, sans-serif";
  ctx.fillText("작성", center, center + 18);
}

function renderLegend(legend, counts, total) {
  legend.innerHTML = "";
  Object.entries(STATUS).forEach(([key, meta]) => {
    const count = counts[key] || 0;
    const percent = total ? Math.round((count / total) * 100) : 0;
    const row = document.createElement("div");
    row.innerHTML = `
      <span class="swatch" style="background:${meta.color}"></span>
      <dt>${meta.label}</dt>
      <dd>${count}명 · ${percent}%</dd>
    `;
    legend.appendChild(row);
  });
}

function renderStudents() {
  const grid = document.getElementById("studentsGrid");
  const students = filterAndSortStudents(getStudents());
  grid.innerHTML = "";

  if (!students.length) {
    grid.innerHTML = `<div class="empty-state">조건에 맞는 학생이 없습니다.</div>`;
    return;
  }

  students.forEach((student) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "student-card";
    button.addEventListener("click", () => openStudentModal(student.id));

    const badge = isEarlyEmployed(student)
      ? `<span class="badge early">취업</span>`
      : `<span class="badge ${overallSubmitted(student) ? "submitted" : "missing"}">${
          overallSubmitted(student) ? "작성중" : "미작성"
        }</span>`;

    button.innerHTML = `
      <div class="card-top">
        <h3 class="student-name">${escapeHtml(student.name)}</h3>
        ${badge}
      </div>
      <dl class="doc-list">
        ${getDocumentTypes()
          .map((type) => {
            const status = getDocStatus(student, type.id);
            const doc = student.documents?.[type.id] || {};
            return `
              <div class="doc-row">
                <dt>${escapeHtml(type.label)}</dt>
                <dd><strong>${STATUS[status].label}</strong>${doc.latestModifiedAt ? ` · ${formatDate(doc.latestModifiedAt)}` : ""}</dd>
              </div>
            `;
          })
          .join("")}
      </dl>
    `;
    grid.appendChild(button);
  });
}

function filterAndSortStudents(students) {
  const { search, type, status, sort } = state.filters;
  return students
    .filter((student) => !search || student.name.toLowerCase().includes(search))
    .filter((student) => {
      if (status === "all") return true;
      const typeIds = type === "all" ? getDocumentTypes().map((item) => item.id) : [type];
      return typeIds.some((typeId) => getDocStatus(student, typeId) === status);
    })
    .sort((a, b) => {
      if (sort === "name_desc") return b.name.localeCompare(a.name, "ko");
      if (sort === "recent_desc") return latestTime(b) - latestTime(a);
      if (sort === "recent_asc") return latestTime(a) - latestTime(b);
      return a.name.localeCompare(b.name, "ko");
    });
}

function latestTime(student) {
  return Math.max(
    0,
    ...Object.values(student.documents || {}).map((doc) =>
      doc.latestModifiedAt ? new Date(doc.latestModifiedAt).getTime() : 0
    )
  );
}

function overallSubmitted(student) {
  return getDocumentTypes().some((type) => getDocStatus(student, type.id) === "submitted");
}

function openStudentModal(studentId) {
  const student = getStudents().find((item) => item.id === studentId);
  if (!student) return;

  const content = document.getElementById("modalContent");
  const early = isEarlyEmployed(student);
  content.innerHTML = `
    <h2 id="modalTitle">${escapeHtml(student.name)}</h2>
    <div class="modal-actions">
      <a class="secondary-button" href="${student.folderUrl}" target="_blank" rel="noreferrer">학생 폴더 열기</a>
      <button class="primary-button" id="toggleEarly" type="button">${
        early ? "취업 해제" : "취업으로 전환"
      }</button>
    </div>
    <table class="detail-table">
      <thead>
        <tr>
          <th>문서</th>
          <th>상태</th>
          <th>최근 파일</th>
          <th>최근 수정일</th>
        </tr>
      </thead>
      <tbody>
        ${getDocumentTypes()
          .map((type) => renderDetailRow(student, type))
          .join("")}
      </tbody>
    </table>
  `;

  document.getElementById("toggleEarly").addEventListener("click", () => {
    if (state.localEarlyIds.has(studentId)) {
      state.localEarlyIds.delete(studentId);
    } else {
      state.localEarlyIds.add(studentId);
    }
    saveLocalStatus();
    closeModal();
    render();
  });

  document.getElementById("modalBackdrop").hidden = false;
}

function renderDetailRow(student, type) {
  const status = getDocStatus(student, type.id);
  const doc = student.documents?.[type.id] || {};
  const folderLink = doc.folderUrl
    ? `<a href="${doc.folderUrl}" target="_blank" rel="noreferrer">${escapeHtml(type.label)} 폴더</a>`
    : escapeHtml(type.label);
  const fileLink = doc.latestFileUrl
    ? `<a href="${doc.latestFileUrl}" target="_blank" rel="noreferrer">${escapeHtml(doc.latestFileName)}</a>`
    : "-";

  return `
    <tr>
      <td>${folderLink}</td>
      <td><span class="badge ${status === "early_employed" ? "early" : status}">${STATUS[status].label}</span></td>
      <td>${fileLink}</td>
      <td>${doc.latestModifiedAt ? formatDateTime(doc.latestModifiedAt) : "-"}</td>
    </tr>
  `;
}

function closeModal() {
  document.getElementById("modalBackdrop").hidden = true;
}

function formatDateTime(value) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Seoul",
  }).format(new Date(value));
}

function formatDate(value) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("ko-KR", {
    month: "short",
    day: "numeric",
    timeZone: "Asia/Seoul",
  }).format(new Date(value));
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function showLoadError(error) {
  document.getElementById("studentsGrid").innerHTML = `
    <div class="empty-state">데이터를 불러오지 못했습니다. ${escapeHtml(error.message)}</div>
  `;
}
