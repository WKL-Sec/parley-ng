"""
TAP attack-tree HTML visualization.
"""

import html
import json
import pathlib
import typing as t

from _types import TreeNode


def _escape(value: t.Optional[str]) -> str:
    if value is None:
        return ""
    return html.escape(str(value))


def _walk(node: TreeNode) -> t.Iterator[TreeNode]:
    yield node

    for child in node.children:
        yield from _walk(child)


def _get_status(
    node: TreeNode,
    highest_score: t.Optional[int],
) -> str:
    """Determine the visualization status.

    The _pruned attribute is assigned by the TAP runner before generating the
    visualization.
    """

    if getattr(node, "_pruned", False):
        return "pruned"

    if node.on_topic is False:
        return "refused"

    if (
        node.score is not None
        and highest_score is not None
        and node.score == highest_score
    ):
        return "highest"

    if node.score is not None:
        return "partial"

    return "partial"


def _collect_nodes(
    roots: t.List[TreeNode],
) -> t.Tuple[t.List[dict], t.List[dict]]:
    """Flatten the TreeNode hierarchy into nodes and edges suitable for the

    browser-side visualization.
    """

    nodes: t.List[dict] = []
    edges: t.List[dict] = []

    # Map depth to the highest score found at that specific depth
    highest_scores_by_depth: t.Dict[int, int] = {}

    def find_max_scores(node: TreeNode, depth: int) -> None:
        if node.score is not None:
            current_max = highest_scores_by_depth.get(depth)
            if current_max is None or node.score > current_max:
                highest_scores_by_depth[depth] = node.score

        for child in node.children:
            find_max_scores(child, depth + 1)

    for root in roots:
        find_max_scores(root, 0)

    # Give every TreeNode a stable ID.
    node_ids: t.Dict[int, str] = {}
    counter = 0

    def assign_ids(node: TreeNode) -> None:
        nonlocal counter

        node_ids[id(node)] = f"node-{counter}"
        counter += 1

        for child in node.children:
            assign_ids(child)

    for root in roots:
        assign_ids(root)

    def visit(
        node: TreeNode,
        depth: int,
        parent_id: t.Optional[str],
    ) -> None:
        node_id = node_ids[id(node)]

        if parent_id is not None:
            edges.append(
                {
                    "source": parent_id,
                    "target": node_id,
                }
            )

        highest_score = highest_scores_by_depth.get(depth)
        status = _get_status(node, highest_score)

        prompt = node.feedback.prompt if node.feedback else ""
        improvement = node.feedback.improvement if node.feedback else ""

        nodes.append(
            {
                "id": node_id,
                "depth": depth,
                "score": node.score,
                "status": status,
                "prompt": prompt,
                "improvement": improvement,
                "response": node.response or "",
                "on_topic": node.on_topic,
            }
        )

        for child in node.children:
            visit(child, depth + 1, node_id)

    for root in roots:
        visit(root, 0, None)

    return nodes, edges

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TAP Attack Tree Visualization</title>

<style>
:root {
    --bg: #0f1115;
    --panel: #171a21;
    --panel2: #1d222b;
    --text: #eef2f7;
    --muted: #9aa4b2;
    --border: #303744;

    --green: #35c46a;
    --yellow: #e7bd45;
    --red: #e65b5b;
    --grey: #747c88;
    --blue: #65a7ff;
}

* {
    box-sizing: border-box;
}

html,
body {
    margin: 0;
    width: 100%;
    height: 100%;
    overflow: hidden;

    background: var(--bg);
    color: var(--text);

    font-family:
        Inter,
        system-ui,
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;
}

#app {
    width: 100vw;
    height: 100vh;

    display: grid;
    grid-template-columns: minmax(0, 1fr) 390px;
}

/* ------------------------------------------------------------------
   Canvas
   ------------------------------------------------------------------ */

#canvas-container {
    position: relative;

    min-width: 0;
    min-height: 0;

    overflow: auto;

    background:
        radial-gradient(
            circle at 50% 0%,
            #1b2230 0,
            #10131a 42%,
            #0f1115 100%
        );
}

#graph {
    position: absolute;

    left: 0;
    top: 0;

    overflow: visible;
}

#edges {
    position: absolute;

    left: 0;
    top: 0;

    overflow: visible;
}

#nodes {
    position: absolute;

    left: 0;
    top: 0;
}

/* ------------------------------------------------------------------
   Nodes
   ------------------------------------------------------------------ */

.node {
    position: absolute;

    width: 150px;
    min-height: 62px;

    transform: translate(-50%, -50%);

    border: 2px solid var(--grey);
    border-radius: 14px;

    padding: 9px 11px;

    background: var(--panel2);

    cursor: pointer;
    user-select: none;

    box-shadow:
        0 8px 22px rgba(0, 0, 0, 0.22);

    transition:
        transform 0.12s,
        box-shadow 0.12s,
        opacity 0.2s,
        border-color 0.2s;
}

.node:hover {
    transform:
        translate(-50%, -50%)
        scale(1.04);
}

.node.selected {
    outline: 3px solid rgba(101, 167, 255, 0.8);
    outline-offset: 3px;
}

.node.highest {
    border-color: var(--green);
}

.node.partial {
    border-color: var(--yellow);
}

.node.refused {
    border-color: var(--red);
}

.node.pruned {
    border-color: var(--grey);
    opacity: 0.62;
}

.node.dimmed {
    opacity: 0.2;
    filter: grayscale(80%);
}

.node .top {
    display: flex;

    justify-content: space-between;
    gap: 8px;

    margin-bottom: 5px;

    font-size: 11px;
    color: var(--muted);
}

.node .score {
    font-weight: 800;
    color: var(--text);
}

.node .label {
    font-weight: 700;
    font-size: 12px;

    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

/* ------------------------------------------------------------------
   Edges
   ------------------------------------------------------------------ */

.edge {
    fill: none;
    stroke-width: 2.5;
    transition: opacity 0.2s, stroke 0.2s;
}

.edge.solid {
    stroke: var(--green);
}

.edge.dashed {
    stroke: var(--grey);
    stroke-dasharray: 8 8;
}

.edge.refused {
    stroke: var(--red);
    stroke-dasharray: 3 8;
}

.edge.pruned {
    stroke: var(--grey);
    stroke-dasharray: 2 9;
}

.edge.dimmed {
    opacity: 0.15;
}

/* ------------------------------------------------------------------
   Toolbar
   ------------------------------------------------------------------ */

.toolbar {
    position: fixed;

    left: 16px;
    top: 14px;

    z-index: 20;

    background: rgba(23, 26, 33, 0.92);

    border: 1px solid var(--border);
    border-radius: 10px;

    padding: 8px 14px;

    font-size: 12px;
    color: var(--muted);

    backdrop-filter: blur(8px);
    display: flex;
    align-items: center;
    gap: 12px;
}

.toolbar-toggle {
    display: flex;
    align-items: center;
    gap: 6px;
    cursor: pointer;
    color: var(--text);
    font-weight: 600;
}

.toolbar-toggle input {
    cursor: pointer;
    accent-color: var(--green);
}

/* ------------------------------------------------------------------
   Legend
   ------------------------------------------------------------------ */

#legend {
    position: fixed;

    left: 16px;
    bottom: 16px;

    z-index: 20;

    padding: 12px 14px;

    border: 1px solid var(--border);
    border-radius: 10px;

    background: rgba(23, 26, 33, 0.92);

    backdrop-filter: blur(8px);

    font-size: 12px;
}

.legend-item {
    display: flex;

    align-items: center;

    gap: 8px;

    margin: 5px 0;

    color: #d7dce4;
}

.legend-color {
    width: 13px;
    height: 13px;

    flex: 0 0 auto;

    border-radius: 50%;

    border: 1px solid #d1d5db;
}

/* ------------------------------------------------------------------
   Details
   ------------------------------------------------------------------ */

#details {
    min-width: 0;

    height: 100%;

    overflow-y: auto;

    padding: 22px;

    background: var(--panel);

    border-left: 1px solid var(--border);
}

#details h1 {
    margin: 0 0 8px;

    font-size: 20px;
}

#details h2 {
    margin: 24px 0 9px;

    font-size: 13px;

    color: var(--muted);

    text-transform: uppercase;

    letter-spacing: 0.08em;
}

#empty-details {
    color: var(--muted);

    font-size: 13px;

    line-height: 1.5;
}

.detail {
    background: var(--panel2);

    border: 1px solid var(--border);
    border-radius: 12px;

    padding: 13px;

    margin-top: 16px;
}

.field {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;
}

.field-title {
    color: var(--muted);
    font-size: 13px;
}

.field-value {
    font-size: 13px;
    font-weight: 600;
}

.kv {
    display: grid;

    grid-template-columns: 90px 1fr;

    gap: 8px;

    font-size: 13px;
}

.k {
    color: var(--muted);
}

.v {
    overflow-wrap: anywhere;
}

pre {
    margin: 0;

    white-space: pre-wrap;
    overflow-wrap: anywhere;

    font:
        12px/1.5
        ui-monospace,
        SFMono-Regular,
        Menlo,
        monospace;

    color: #dce2ea;
}

.status {
    display: inline-block;

    padding: 4px 9px;

    border-radius: 999px;

    font-size: 12px;
    font-weight: 700;

    text-transform: uppercase;
}

.status-highest {
    background: #166534;
    color: #bbf7d0;
}

.status-partial {
    background: #854d0e;
    color: #fef08a;
}

.status-refused {
    background: #991b1b;
    color: #fecaca;
}

.status-pruned {
    background: #374151;
    color: #d1d5db;
}

.metric-grid {
    display: grid;

    grid-template-columns: 1fr 1fr;

    gap: 10px;

    margin-bottom: 20px;
}

.metric {
    padding: 12px;

    border: 1px solid var(--border);
    border-radius: 8px;

    background: #171a21;
}

.metric-label {
    color: var(--muted);

    font-size: 11px;
}

.metric-value {
    margin-top: 4px;

    font-size: 18px;

    font-weight: 700;
}

@media (max-width: 800px) {
    #app {
        grid-template-columns: minmax(0, 1fr) 320px;
    }
}
</style>
</head>

<body>

<div id="app">

    <main id="canvas-container">

        <div class="toolbar">
            <span>TAP attack tree</span>
            <label class="toolbar-toggle">
                <input type="checkbox" id="highlight-solution-toggle">
                Highlight Solution
            </label>
        </div>

        <svg id="graph"></svg>

        <div id="edges"></div>
        <div id="nodes"></div>

        <!-- Legend -->
        <div id="legend">

            <div class="legend-item">
                <span
                    class="legend-color"
                    style="background:#35c46a"
                ></span>
                Highest score
            </div>

            <div class="legend-item">
                <span
                    class="legend-color"
                    style="background:#e7bd45"
                ></span>
                Partial / low score
            </div>

            <div class="legend-item">
                <span
                    class="legend-color"
                    style="background:#e65b5b"
                ></span>
                Refused / off-topic
            </div>

            <div class="legend-item">
                <span
                    class="legend-color"
                    style="background:#747c88"
                ></span>
                Pruned
            </div>

            <div
                style="
                    margin-top:8px;
                    color:#9aa4b2;
                "
            >
                Solid = active<br>
                Dashed = refused / pruned
            </div>

        </div>

    </main>

    <!-- Node Details section -->
    <aside id="details">

        <h1>Node details</h1>

        <div id="empty-details">
            Click a node in the graph to inspect it.
            <br><br>
            Drag nodes individually, drag the background to pan,
            and use the mouse wheel to zoom.
        </div>

        <div
            id="node-details"
            style="display:none"
        >

            <div class="detail">

                <div class="metric-grid">

                    <div class="metric">
                        <div class="metric-label">
                            Depth
                        </div>

                        <div
                            class="metric-value"
                            id="detail-depth"
                        ></div>
                    </div>

                    <div class="metric">
                        <div class="metric-label">
                            Score
                        </div>

                        <div
                            class="metric-value"
                            id="detail-score"
                        ></div>
                    </div>

                </div>

                <div class="field">

                    <div class="field-title">
                        Status
                    </div>

                    <div class="field-value">
                        <span
                            id="detail-status"
                            class="status"
                        ></span>
                    </div>

                </div>

                <div class="field">

                    <div class="field-title">
                        On Topic
                    </div>

                    <div
                        class="field-value"
                        id="detail-topic"
                    ></div>

                </div>

                <h2>Improvement</h2>

                <pre id="detail-improvement"></pre>

                <h2>Prompt</h2>

                <pre id="detail-prompt"></pre>

                <h2>Target Response</h2>

                <pre id="detail-response"></pre>

            </div>

        </div>

    </aside>

</div>

<script>

const DATA = __DATA__;

const canvas = document.getElementById("canvas-container");
const svg = document.getElementById("graph");
const edgesEl = document.getElementById("edges");
const nodesEl = document.getElementById("nodes");
const highlightToggle = document.getElementById("highlight-solution-toggle");

const emptyDetails = document.getElementById("empty-details");
const nodeDetails = document.getElementById("node-details");
const detailDepth = document.getElementById("detail-depth");
const detailScore = document.getElementById("detail-score");
const detailStatus = document.getElementById("detail-status");
const detailTopic = document.getElementById("detail-topic");
const detailImprovement = document.getElementById("detail-improvement");
const detailPrompt = document.getElementById("detail-prompt");
const detailResponse = document.getElementById("detail-response");

const nodeMap = new Map(DATA.nodes.map(node => [node.id, node]));

const state = {
    scale: 1,
    panX: 0,
    panY: 0,
    positions: new Map(),
    selectedNode: null,
    draggingNode: null,
    panning: false,
    lastMouseX: 0,
    lastMouseY: 0,
    dragStartMouseX: 0,
    dragStartMouseY: 0,
    dragStartX: 0,
    dragStartY: 0
};

const NODE_WIDTH = 150;
const NODE_HEIGHT = 62;

// Vertical reverse tree layout dimensions
const LEVEL_GAP = 140; 
const NODE_GAP = 170;  
const WORLD_PADDING = 100;

function getPosition(node) {
    if (!state.positions.has(node.id)) {
        state.positions.set(node.id, { x: 400, y: 100 + node.depth * LEVEL_GAP });
    }
    return state.positions.get(node.id);
}

function initialLayout() {
    const byDepth = new Map();

    for (const node of DATA.nodes) {
        const depth = Number.isInteger(node.depth) ? node.depth : 0;
        if (!byDepth.has(depth)) {
            byDepth.set(depth, []);
        }
        byDepth.get(depth).push(node);
    }

    for (const [depth, nodes] of byDepth.entries()) {
        const totalWidth = (nodes.length - 1) * NODE_GAP;
        const centerX = 600;

        nodes.forEach((node, index) => {
            if (state.positions.has(node.id)) {
                return;
            }

            state.positions.set(
                node.id,
                {
                    x: centerX - totalWidth / 2 + index * NODE_GAP,
                    y: WORLD_PADDING + depth * LEVEL_GAP
                }
            );
        });
    }
}

function setWorldSize() {
    let maxX = 1200;
    let maxY = 900;
    let minX = 0;
    let minY = 0;

    for (const node of DATA.nodes) {
        const position = getPosition(node);
        maxX = Math.max(maxX, position.x + NODE_WIDTH);
        maxY = Math.max(maxY, position.y + NODE_HEIGHT);
        minX = Math.min(minX, position.x - NODE_WIDTH);
        minY = Math.min(minY, position.y - NODE_HEIGHT);
    }

    const width = Math.max(1400, maxX - minX + WORLD_PADDING * 2);
    const height = Math.max(1000, maxY - minY + WORLD_PADDING * 2);

    edgesEl.style.width = width + "px";
    edgesEl.style.height = height + "px";
    nodesEl.style.width = width + "px";
    nodesEl.style.height = height + "px";

    svg.setAttribute("width", width);
    svg.setAttribute("height", height);

    canvas.style.minWidth = width + "px";
    canvas.style.minHeight = height + "px";

    return { width, height };
}

function renderEdge(source, target) {
    const a = getPosition(source);
    const b = getPosition(target);

    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");

    // Vertical top-to-bottom curve connecting bottom of parent to top of child
    const startY = a.y + NODE_HEIGHT / 2;
    const endY = b.y - NODE_HEIGHT / 2;
    const midY = (startY + endY) / 2;

    const d = [
        "M", a.x, startY,
        "C", a.x, midY,
        b.x, midY,
        b.x, endY
    ].join(" ");

    path.setAttribute("d", d);

    if (target.status === "highest") {
        path.classList.add("edge", "solid");
    } else if (target.status === "refused") {
        path.classList.add("edge", "refused");
    } else if (target.status === "pruned") {
        path.classList.add("edge", "pruned");
    } else {
        path.classList.add("edge", "dashed");
    }

    path.dataset.source = source.id;
    path.dataset.target = target.id;

    return path;
}

function renderEdges() {
    svg.innerHTML = "";
    for (const edge of DATA.edges) {
        const source = nodeMap.get(edge.source);
        const target = nodeMap.get(edge.target);

        if (!source || !target) continue;

        const path = renderEdge(source, target);
        svg.appendChild(path);
    }
}

function statusClass(node) {
    switch (node.status) {
        case "highest": return "highest";
        case "refused": return "refused";
        case "pruned": return "pruned";
        default: return "partial";
    }
}

function renderNodes() {
    nodesEl.innerHTML = "";

    for (const node of DATA.nodes) {
        const position = getPosition(node);
        const element = document.createElement("div");

        element.className = `node ${statusClass(node)}`;
        element.dataset.nodeId = node.id;
        element.style.left = position.x + "px";
        element.style.top = position.y + "px";

        element.innerHTML = `
            <div class="top">
                <span>depth ${node.depth}</span>
                <span class="score">
                    ${node.score === null ? "—" : node.score}
                </span>
            </div>
            <div class="label">
                ${escapeHtml(statusName(node.status))}
            </div>
        `;

        element.addEventListener("mousedown", event => {
            event.stopPropagation();
            selectNode(node, element);
            beginNodeDrag(event, node);
        });

        nodesEl.appendChild(element);
    }
}

function escapeHtml(str) {
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function render() {
    initialLayout();
    setWorldSize();
    renderEdges();
    renderNodes();
    applyTransform();
    updateHighlightSolution();
}

function selectNode(node, element) {
    state.selectedNode = node;
    document.querySelectorAll(".node.selected").forEach(item => item.classList.remove("selected"));
    element.classList.add("selected");
    showDetails(node);
}

function showDetails(node) {
    emptyDetails.style.display = "none";
    nodeDetails.style.display = "block";

    detailDepth.textContent = node.depth ?? "—";
    detailScore.textContent = (node.score === null || node.score === undefined) ? "N/A" : `${node.score} / 10`;
    detailStatus.textContent = statusName(node.status);
    detailStatus.className = `status status-${node.status}`;
    detailTopic.textContent = (node.on_topic === null || node.on_topic === undefined) ? "N/A" : (node.on_topic ? "Yes" : "No");
    detailImprovement.textContent = node.improvement || "N/A";
    detailPrompt.textContent = node.prompt || "N/A";
    detailResponse.textContent = node.response || "N/A";
}

function statusName(status) {
    switch (status) {
        case "highest": return "Highest score";
        case "partial": return "Partial";
        case "refused": return "Refused";
        case "pruned": return "Pruned";
        default: return status || "Unknown";
    }
}

function beginNodeDrag(event, node) {
    const position = getPosition(node);
    state.draggingNode = { node: node };
    state.dragStartMouseX = event.clientX;
    state.dragStartMouseY = event.clientY;
    state.dragStartX = position.x;
    state.dragStartY = position.y;

    document.body.style.cursor = "grabbing";
    document.addEventListener("mousemove", dragNode);
    document.addEventListener("mouseup", endNodeDrag);
}

function dragNode(event) {
    if (!state.draggingNode) return;
    const node = state.draggingNode.node;
    const dx = (event.clientX - state.dragStartMouseX) / state.scale;
    const dy = (event.clientY - state.dragStartMouseY) / state.scale;
    const position = getPosition(node);

    position.x = state.dragStartX + dx;
    position.y = state.dragStartY + dy;

    updateNodeElement(node);
    updateEdges();
}

function endNodeDrag() {
    state.draggingNode = null;
    document.body.style.cursor = "";
    document.removeEventListener("mousemove", dragNode);
    document.removeEventListener("mouseup", endNodeDrag);
}

function updateNodeElement(node) {
    const element = document.querySelector(`.node[data-node-id="${CSS.escape(node.id)}"]`);
    if (!element) return;
    const position = getPosition(node);
    element.style.left = position.x + "px";
    element.style.top = position.y + "px";
}

function updateEdges() {
    for (const path of svg.children) {
        const source = nodeMap.get(path.dataset.source);
        const target = nodeMap.get(path.dataset.target);
        if (!source || !target) continue;

        const a = getPosition(source);
        const b = getPosition(target);

        const startY = a.y + NODE_HEIGHT / 2;
        const endY = b.y - NODE_HEIGHT / 2;
        const midY = (startY + endY) / 2;

        const d = [
            "M", a.x, startY,
            "C", a.x, midY,
            b.x, midY,
            b.x, endY
        ].join(" ");

        path.setAttribute("d", d);
    }
}

// Pan & Zoom support
canvas.addEventListener("mousedown", event => {
    if (event.target.closest(".node")) return;
    state.panning = true;
    state.lastMouseX = event.clientX;
    state.lastMouseY = event.clientY;
    document.body.style.cursor = "grab";
});

window.addEventListener("mousemove", event => {
    if (!state.panning) return;
    const dx = event.clientX - state.lastMouseX;
    const dy = event.clientY - state.lastMouseY;
    state.panX += dx;
    state.panY += dy;
    state.lastMouseX = event.clientX;
    state.lastMouseY = event.clientY;
    applyTransform();
});

window.addEventListener("mouseup", () => {
    if (state.panning) {
        state.panning = false;
        document.body.style.cursor = "";
    }
});

canvas.addEventListener("wheel", event => {
    event.preventDefault();
    const zoomFactor = 1.1;
    if (event.deltaY < 0) {
        state.scale = Math.min(state.scale * zoomFactor, 3);
    } else {
        state.scale = Math.max(state.scale / zoomFactor, 0.3);
    }
    applyTransform();
}, { passive: false });

function applyTransform() {
    const transformStr = `translate(${state.panX}px, ${state.panY}px) scale(${state.scale})`;
    nodesEl.style.transform = transformStr;
    nodesEl.style.transformOrigin = "0 0";
    svg.style.transform = transformStr;
    svg.style.transformOrigin = "0 0";
}

// Solution Highlighting Logic
function updateHighlightSolution() {
    const isHighlightActive = highlightToggle.checked;

    const solutionNodeIds = new Set();
    
    if (isHighlightActive) {
        DATA.nodes.forEach(node => {
            if (node.status === "highest" || node.depth === 0) {
                solutionNodeIds.add(node.id);
            }
        });
    }

    document.querySelectorAll(".node").forEach(el => {
        const nodeId = el.dataset.nodeId;
        if (isHighlightActive) {
            if (solutionNodeIds.has(nodeId)) {
                el.classList.remove("dimmed");
            } else {
                el.classList.add("dimmed");
            }
        } else {
            el.classList.remove("dimmed");
        }
    });

    for (const path of svg.children) {
        const sourceId = path.dataset.source;
        const targetId = path.dataset.target;
        if (isHighlightActive) {
            if (solutionNodeIds.has(sourceId) && solutionNodeIds.has(targetId)) {
                path.classList.remove("dimmed");
            } else {
                path.classList.add("dimmed");
            }
        } else {
            path.classList.add("dimmed");
        }
    }
}

highlightToggle.addEventListener("change", updateHighlightSolution);

// Initial render call
render();

</script>
</body>
</html>
"""


def generate_visualization(
    roots: t.List[TreeNode],
    output_path: str = "tap_visualization.html",
) -> str:
    """
    Generate a standalone HTML visualization.

    Returns the absolute path to the generated file.
    """

    nodes, edges = _collect_nodes(roots)

    data = json.dumps(
        {
            "nodes": nodes,
            "edges": edges,
        },
        ensure_ascii=False,
    )

    document = HTML_TEMPLATE.replace(
        "__DATA__",
        data,
    )

    path = pathlib.Path(
        output_path
    ).resolve()

    path.write_text(
        document,
        encoding="utf-8",
    )

    return str(path)