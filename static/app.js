const stateUrl = "/api/state";
const brainCanvas = document.getElementById("brain-maze");
const youCanvas = document.getElementById("you-maze");
const rewardSpark = document.getElementById("reward-spark");
const arousalSpark = document.getElementById("arousal-spark");
const veil = document.getElementById("veil");
const pad = document.getElementById("pad");

const NOTES = {
  idle: "The brain is composed. It has not lived a moment yet.",
  youth: "Young brain. Outcomes still change its connections.",
  aroused: "Surprise or want woke it. It is exploring and learning.",
  routine: "Calm. It answers from what it already settled, and does not learn.",
};

const runners = {
  brain: freshRunner(),
  you: freshRunner(),
};

let latest = null;
let held = null;
let layoutKey = "";
let challengeSig = "";
let primedChallenges = false;
let knownDone = new Set();
let toastText = "";
let toastUntil = 0;
const keys = [];

function freshRunner() {
  return { x: 0, y: 0, fromX: 0, fromY: 0, toX: 0, toY: 0, t0: -1e9, drawX: 0, drawY: 0 };
}

async function post(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  if (!response.ok) throw new Error(url);
  return response.json();
}

async function poll() {
  try {
    const response = await fetch(stateUrl, { cache: "no-store" });
    latest = await response.json();
    const key = `${latest.level}:${latest.width}:${latest.phase}:${latest.step}`;
    const snap = latest.phase !== "race" || (layoutKey && !layoutKey.startsWith(`${latest.level}:${latest.width}:race`));
    layoutKey = key;
    paintHud(latest);
    place("brain", latest.brain, snap);
    place("you", latest.you, snap);
  } catch (_error) {
    /* keep the last frame while the server catches up */
  }
}

function place(name, body, snap) {
  const runner = runners[name];
  if (snap) {
    runner.x = body.x;
    runner.y = body.y;
    runner.fromX = runner.toX = runner.drawX = body.x;
    runner.fromY = runner.toY = runner.drawY = body.y;
    runner.t0 = -1e9;
    return;
  }
  if (runner.x !== body.x || runner.y !== body.y) {
    runner.fromX = runner.drawX;
    runner.fromY = runner.drawY;
    runner.toX = body.x;
    runner.toY = body.y;
    runner.t0 = performance.now();
    runner.x = body.x;
    runner.y = body.y;
  }
}

function drawPos(name, tickMs) {
  const runner = runners[name];
  const u = Math.min(1, (performance.now() - runner.t0) / tickMs);
  const eased = 1 - (1 - u) ** 3;
  runner.drawX = runner.fromX + (runner.toX - runner.fromX) * eased;
  runner.drawY = runner.fromY + (runner.toY - runner.fromY) * eased;
  return runner;
}

function paintHud(data) {
  document.getElementById("level-label").textContent = `Level ${data.level}`;
  document.getElementById("kind-label").textContent = data.kind;
  document.getElementById("score-you").textContent = data.scores.you;
  document.getElementById("score-brain").textContent = data.scores.brain;
  document.getElementById("brain-dist").textContent = distanceLine(data.brain, data);
  document.getElementById("you-dist").textContent = distanceLine(data.you, data);

  const telemetry = data.telemetry;
  const mode = document.getElementById("mode");
  mode.textContent = telemetry.mode;
  mode.dataset.mode = telemetry.mode;
  document.getElementById("mode-note").textContent = NOTES[telemetry.mode] || NOTES.idle;
  renderStats(telemetry, data);
  spark(rewardSpark, telemetry.rewards, "#e4a15a", true);
  spark(arousalSpark, telemetry.arousal_trace, "#d7c6f0", false);
  paintBanner("brain-banner", data, "brain");
  paintBanner("you-banner", data, "you");
  paintChallenges(data.challenges || []);
  paintVeil(data);
}

function distanceLine(body, data) {
  if (body.done) return "Through the door";
  if (data.phase === "lobby") return "Waiting at the entrance";
  const steps = body.dist === 1 ? "1 step from the door" : `${body.dist} steps from the door`;
  return steps;
}

function renderStats(telemetry, data) {
  const cells = [
    ["Choice", telemetry.choice || "—"],
    ["Think", `${telemetry.think_ms.toFixed(1)} ms`],
    ["Reward", signed(telemetry.reward)],
    ["This heat", signed(telemetry.episode_return)],
    ["Error", num(telemetry.forecast_error)],
    ["Dopamine", num(telemetry.dopamine)],
    ["Surprise", num(telemetry.surprise)],
    ["Want", num(telemetry.want)],
    ["Residual", residual(telemetry)],
    ["Sweeps", telemetry.sweeps == null ? "—" : `${telemetry.sweeps}`],
    ["Updates", String(telemetry.updates)],
    ["Moments", String(telemetry.age)],
    ["Learned", telemetry.learned ? "yes" : "no"],
    ["Memory", telemetry.recorded ? "yes" : "no"],
    ["Doors", `${data.doors_reached}`],
    ["Walked", `${telemetry.walked} / ${telemetry.shortest}`],
  ];
  document.getElementById("stats").innerHTML = cells
    .map(([label, value]) => `<div><dt>${label}</dt><dd>${value}</dd></div>`)
    .join("");
}

function residual(telemetry) {
  if (telemetry.residual == null) return "—";
  const mark = telemetry.qualified ? "ok" : "refused";
  return `${telemetry.residual.toFixed(4)} ${mark}`;
}

function signed(value) {
  const number = Number(value) || 0;
  return `${number >= 0 ? "+" : ""}${number.toFixed(2)}`;
}

function num(value) {
  return value == null ? "—" : Number(value).toFixed(3);
}

function spark(canvas, values, color, zeroLine) {
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  ctx.clearRect(0, 0, width, height);
  ctx.strokeStyle = "rgba(243,236,223,0.12)";
  ctx.lineWidth = 1;
  if (zeroLine) {
    ctx.beginPath();
    ctx.moveTo(0, height / 2);
    ctx.lineTo(width, height / 2);
    ctx.stroke();
  }
  if (!values || values.length < 2) return;
  let lo = Math.min(...values);
  let hi = Math.max(...values);
  if (zeroLine) {
    lo = Math.min(lo, 0);
    hi = Math.max(hi, 0);
  }
  if (hi - lo < 1e-6) {
    lo -= 1;
    hi += 1;
  }
  ctx.beginPath();
  values.forEach((value, index) => {
    const x = (index / (values.length - 1)) * (width - 8) + 4;
    const y = height - 6 - ((value - lo) / (hi - lo)) * (height - 12);
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.6;
  ctx.stroke();
}

function paintBanner(id, data, who) {
  const node = document.getElementById(id);
  if (data.phase !== "race" || !data.result) {
    node.hidden = true;
    return;
  }
  node.hidden = false;
  if (data.winner === "tie") node.textContent = "Dead heat.";
  else if (data.winner === who) node.textContent = who === "you" ? "You reached the door." : "Brain reached the door.";
  else if (who === "you") node.textContent = "Brain is through. You can still finish.";
  else node.textContent = "You are through. The brain is still searching.";
}

function paintVeil(data) {
  const title = document.getElementById("veil-title");
  const copy = document.getElementById("veil-copy");
  const start = document.getElementById("start");
  if (data.phase === "lobby") {
    veil.hidden = false;
    title.textContent = "Beat the brain to the door";
    title.className = "";
    copy.hidden = false;
    copy.textContent = "Two copies of one procedural labyrinth. The brain learns from nearby walls, the door’s bearing, and whether it got closer. Your side is the maze and the arrow keys.";
    start.hidden = false;
    return;
  }
  if (data.phase === "countdown") {
    toastText = "";
    veil.hidden = false;
    title.textContent = String(data.countdown || 1);
    title.className = "count";
    copy.hidden = true;
    start.hidden = true;
    return;
  }
  if (data.phase === "interlude") {
    veil.hidden = false;
    title.textContent = data.result || "Heat closed";
    title.className = "";
    copy.hidden = false;
    copy.textContent = toastText
      ? `${toastText} Next labyrinth is larger, with fewer shortcuts.`
      : "Next labyrinth is larger, with fewer shortcuts.";
    start.hidden = true;
    return;
  }
  veil.hidden = true;
}

function paintChallenges(items) {
  const doneNow = new Set(items.filter((item) => item.done).map((item) => item.id));
  if (primedChallenges && doneNow.size < knownDone.size) toastText = "";
  if (primedChallenges) {
    const fresh = items.filter((item) => item.done && !knownDone.has(item.id));
    if (fresh.length) {
      toastText = fresh.map((item) => item.title).join(" · ");
      const toast = document.getElementById("toast");
      toast.hidden = false;
      toast.textContent = `Unlocked: ${toastText}`;
      toastUntil = performance.now() + 3600;
    }
  }
  knownDone = doneNow;
  primedChallenges = true;
  const doneCount = doneNow.size;
  document.getElementById("challenge-count").textContent = `${doneCount}/${items.length}`;
  const next = items.find((item) => !item.done);
  document.getElementById("challenge-hint").textContent = next
    ? `Next: ${next.title}. ${next.detail}`
    : "Every challenge for this brain is done.";
  const signature = items.map((item) => `${item.id}:${item.done}`).join("|");
  if (signature === challengeSig) return;
  challengeSig = signature;
  document.getElementById("challenges").innerHTML = items
    .map(
      (item) =>
        `<p class="challenge${item.done ? " done" : ""}" title="${item.detail}"><strong>${item.title}</strong><span>${item.detail}</span></p>`,
    )
    .join("");
}

function frame() {
  if (toastUntil && performance.now() > toastUntil) {
    document.getElementById("toast").hidden = true;
    toastUntil = 0;
  }
  if (latest) {
    const tick = latest.tick_ms || 180;
    drawMaze(brainCanvas, latest, "brain", drawPos("brain", tick));
    drawMaze(youCanvas, latest, "you", drawPos("you", tick));
  }
  requestAnimationFrame(frame);
}

function drawMaze(canvas, data, who, runner) {
  const rect = canvas.getBoundingClientRect();
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const width = Math.max(1, Math.floor(rect.width * dpr));
  const height = Math.max(1, Math.floor(rect.height * dpr));
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  const ctx = canvas.getContext("2d");
  const brain = who === "brain";
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = brain ? "#100e0c" : "#0d1211";
  ctx.fillRect(0, 0, width, height);

  const cols = data.width;
  const rows = data.height;
  const pad = 22 * dpr;
  const cell = Math.min((width - pad * 2) / cols, (height - pad * 2) / rows);
  const ox = (width - cell * cols) / 2;
  const oy = (height - cell * rows) / 2;
  const wall = Math.max(3 * dpr, cell * 0.16);
  const floor = brain ? "#3c342a" : "#243833";
  const gap = floor;
  const body = data[who];

  ctx.fillStyle = floor;
  for (let y = 0; y < rows; y += 1) {
    for (let x = 0; x < cols; x += 1) {
      ctx.fillRect(ox + x * cell + wall / 2, oy + y * cell + wall / 2, cell - wall, cell - wall);
    }
  }
  ctx.fillStyle = gap;
  for (let y = 0; y < rows; y += 1) {
    for (let x = 0; x < cols; x += 1) {
      const bits = data.walls[y * cols + x];
      if ((bits & 2) === 0 && x + 1 < cols) {
        ctx.fillRect(ox + (x + 1) * cell - wall / 2, oy + y * cell + wall / 2, wall, cell - wall);
      }
      if ((bits & 4) === 0 && y + 1 < rows) {
        ctx.fillRect(ox + x * cell + wall / 2, oy + (y + 1) * cell - wall / 2, cell - wall, wall);
      }
    }
  }

  const [doorX, doorY] = data.exit;
  const pulse = 0.55 + 0.45 * (0.5 + 0.5 * Math.sin(performance.now() / 280));
  ctx.fillStyle = brain ? `rgba(242, 211, 154, ${0.28 + pulse * 0.35})` : `rgba(215, 255, 243, ${0.25 + pulse * 0.4})`;
  roundRect(ctx, ox + doorX * cell + wall, oy + doorY * cell + wall, cell - wall * 2, cell - wall * 2, 6 * dpr);
  ctx.fill();
  ctx.strokeStyle = brain ? "#f2d39a" : "#d7fff3";
  ctx.lineWidth = Math.max(1, dpr);
  ctx.stroke();

  ctx.strokeStyle = brain ? "rgba(228,161,90,0.45)" : "rgba(143,208,190,0.4)";
  ctx.lineWidth = Math.max(2, cell * 0.08);
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.beginPath();
  body.trail.forEach(([x, y], index) => {
    const px = ox + (x + 0.5) * cell;
    const py = oy + (y + 0.5) * cell;
    if (index === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  });
  ctx.stroke();

  const px = ox + (runner.drawX + 0.5) * cell;
  const py = oy + (runner.drawY + 0.5) * cell;
  const radius = cell * 0.22;
  if (body.bumped) {
    ctx.strokeStyle = "rgba(224,122,104,0.9)";
    ctx.lineWidth = 3 * dpr;
    ctx.beginPath();
    ctx.arc(px, py, radius + 7 * dpr, 0, Math.PI * 2);
    ctx.stroke();
  }
  ctx.fillStyle = brain ? "#e4a15a" : "#8fd0be";
  ctx.beginPath();
  ctx.arc(px, py, radius, 0, Math.PI * 2);
  ctx.fill();
  if (brain) {
    ctx.strokeStyle = "#f2d39a";
    ctx.lineWidth = 2 * dpr;
    ctx.beginPath();
    ctx.arc(px, py, radius + 4 * dpr, 0, Math.PI * 2);
    ctx.stroke();
  }
  const facing = { north: [0, -1], east: [1, 0], south: [0, 1], west: [-1, 0] }[body.facing] || [1, 0];
  ctx.fillStyle = brain ? "#24180e" : "#10211c";
  ctx.beginPath();
  ctx.arc(px + facing[0] * radius * 0.45, py + facing[1] * radius * 0.45, radius * 0.28, 0, Math.PI * 2);
  ctx.fill();
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function setHold(direction) {
  if (held === direction) return;
  held = direction;
  document.querySelectorAll("#pad button").forEach((button) => {
    button.classList.toggle("lit", button.dataset.dir === direction);
  });
  post("/api/hold", { dir: direction }).catch(() => {});
}

function syncKeys() {
  setHold(keys.length ? keys[keys.length - 1] : null);
}

window.addEventListener("keydown", (event) => {
  const map = { ArrowUp: "n", ArrowDown: "s", ArrowLeft: "w", ArrowRight: "e" };
  if (event.key === "Enter" && latest && latest.phase === "lobby") {
    event.preventDefault();
    post("/api/start").catch(() => {});
    return;
  }
  const direction = map[event.key];
  if (!direction) return;
  event.preventDefault();
  if (!keys.includes(direction)) keys.push(direction);
  syncKeys();
});

window.addEventListener("keyup", (event) => {
  const map = { ArrowUp: "n", ArrowDown: "s", ArrowLeft: "w", ArrowRight: "e" };
  const direction = map[event.key];
  if (!direction) return;
  const index = keys.indexOf(direction);
  if (index >= 0) keys.splice(index, 1);
  syncKeys();
});

pad.addEventListener("pointerdown", (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  button.setPointerCapture(event.pointerId);
  setHold(button.dataset.dir);
});

pad.addEventListener("pointerup", () => setHold(null));
pad.addEventListener("pointercancel", () => setHold(null));

document.getElementById("start").addEventListener("click", () => {
  post("/api/start").catch(() => {});
});

document.getElementById("hatch").addEventListener("click", () => {
  post("/api/hatch").catch(() => {});
});

window.addEventListener("blur", () => {
  keys.length = 0;
  setHold(null);
});

poll();
setInterval(poll, 90);
requestAnimationFrame(frame);
