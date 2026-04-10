async function loadDashboard() {
  const response = await fetch("data/project-data.json");
  if (!response.ok) {
    throw new Error("Unable to load dashboard data");
  }
  return response.json();
}

function createElement(tag, className, text) {
  const node = document.createElement(tag);
  if (className) {
    node.className = className;
  }
  if (text) {
    node.textContent = text;
  }
  return node;
}

function renderStats(stats) {
  const container = document.getElementById("project-stats");
  stats.forEach((stat) => {
    const card = createElement("div", "stat-card");
    card.append(createElement("span", "", stat.label));
    card.append(createElement("strong", "", stat.value));
    container.append(card);
  });
}

function renderInfoGrid(targetId, items) {
  const container = document.getElementById(targetId);
  items.forEach((item) => {
    const card = createElement("div", "info-card");
    card.append(createElement("h3", "", item.title));
    card.append(createElement("p", "", item.body));
    container.append(card);
  });
}

function renderStack(targetId, items) {
  const container = document.getElementById(targetId);
  items.forEach((item) => {
    const block = createElement("article", "stack-item");
    const heading = createElement("h3", "", item.title);
    block.append(heading);
    if (item.tag) {
      block.append(createElement("span", "pill", item.tag));
    }
    block.append(createElement("p", "", item.body));
    container.append(block);
  });
}

function renderLinks(items) {
  const container = document.getElementById("docs-list");
  items.forEach((item) => {
    const link = createElement("a");
    link.href = item.href;
    link.target = item.external ? "_blank" : "_self";
    link.rel = item.external ? "noreferrer" : "";
    link.append(createElement("h3", "", item.title));
    link.append(createElement("p", "", item.body));
    container.append(link);
  });
}

function renderTimeline(items) {
  const container = document.getElementById("changes-list");
  items.forEach((item) => {
    const card = createElement("article", "timeline-item");
    card.append(createElement("h3", "", item.title));
    card.append(createElement("p", "", item.body));
    container.append(card);
  });
}

function renderDashboard(data) {
  document.getElementById("project-title").textContent = data.title;
  document.getElementById("project-summary").textContent = data.summary;
  document.getElementById("last-updated").textContent = `Last updated: ${data.lastUpdated}`;

  renderStats(data.stats);
  renderInfoGrid("overview-grid", data.overview);
  renderStack("tools-grid", data.tools);
  renderStack("architecture-grid", data.architecture);
  renderLinks(data.docs);
  renderStack("issues-list", data.openIssues);
  renderStack("limitations-list", data.limitations);
  renderInfoGrid("dependencies-grid", data.dependencies);
  renderTimeline(data.recentChanges);
}

loadDashboard()
  .then(renderDashboard)
  .catch((error) => {
    const summary = document.getElementById("project-summary");
    summary.textContent = error.message;
  });
