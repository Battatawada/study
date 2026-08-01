/**
 * Algorithm visualization renderer.
 * Consumes a pre-planned timeline (from Python planner).
 * Motion = computation. Renderer only draws — never decides choreography.
 */
(function () {
  "use strict";

  const ease = (t) => {
    const p = Math.max(0, Math.min(1, t));
    return p * p * (3 - 2 * p);
  };
  const easeOut = (t) => 1 - ease(1 - t);
  const lerp = (a, b, t) => a + (b - a) * t;

  function sampleCamera(spec, t, w, h) {
    const channel = spec.camera || [];
    if (!channel.length) {
      return { cx: w / 2, cy: h / 2, zoom: 1 };
    }
    let cx = w / 2;
    let cy = h / 2;
    let zoom = 1;
    for (let i = 0; i < channel.length; i++) {
      const seg = channel[i];
      const at = seg.at_sec || 0;
      const dur = seg.duration_sec ?? 0.65;
      const tcx = seg.center_x ?? w / 2;
      const tcy = seg.center_y ?? h / 2;
      const tz = seg.zoom ?? 1;
      if (t < at) break;
      if (t >= at + dur) {
        cx = tcx;
        cy = tcy;
        zoom = tz;
      } else {
        const p = ease((t - at) / dur);
        cx = lerp(cx, tcx, p);
        cy = lerp(cy, tcy, p);
        zoom = lerp(zoom, tz, p);
      }
    }
    return { cx, cy, zoom };
  }

  function applyCamera(ctx, cam, w, h) {
    const { cx, cy, zoom } = cam;
    ctx.translate(w / 2, h / 2);
    ctx.scale(zoom, zoom);
    ctx.translate(-cx, -cy);
  }

  function fontToken(typography, role, fallback) {
    const tok = (typography && typography[role]) || {};
    const size = tok.size || fallback.size || 20;
    const weight = tok.weight || fallback.weight || 400;
    const family = tok.family || fallback.family || "Segoe UI";
    return `${weight} ${size}px '${family}', system-ui, sans-serif`;
  }

  function attentionState(spec, t) {
    const timeline = spec.attention_timeline || [];
    let primary = null;
    let salience = [];
    for (const item of timeline) {
      const start = item.start_sec ?? 0;
      const end = item.end_sec ?? start + 0.5;
      if (t >= start && t < end) {
        primary = item.primary_entity_id;
        salience = item.salience || [];
        break;
      }
    }
    return { primary, salience };
  }

  function layoutCellsFromIR(spec, width, height) {
    const layout = spec.layout;
    if (!layout || !Array.isArray(layout.entities)) return null;
    const drawable = layout.entities.filter((e) => e.type !== "region");
    if (!drawable.length) return null;
    const values = spec.values || [];
    const stageW = layout.stage?.width || width;
    const stageH = layout.stage?.height || height;
    const scaleX = width / stageW;
    const scaleY = height / stageH;
    return drawable.map((ent, i) => {
      const box = ent.box || {};
      const cellW = (box.w || 88) * scaleX;
      const cellH = (box.h || 56) * scaleY;
      return {
        value: String(values[i] ?? ent.label ?? ""),
        addr: ent.entity_id || "",
        entityId: ent.entity_id,
        baseX: (box.x || 0) * scaleX,
        baseY: (box.y || 0) * scaleY,
        cellW,
        cellH,
        offsetX: 0,
        offsetY: 0,
        opacity: 0,
        highlight: false,
        dimmed: false,
        visible: false,
      };
    });
  }

  function layoutCells(values, addresses, width, height, spec) {
    const fromIR = spec ? layoutCellsFromIR(spec, width, height) : null;
    if (fromIR) return fromIR;
    const n = values.length;
    const cellW = 88;
    const cellH = 56;
    const gap = 10;
    const totalW = n * cellW + (n - 1) * gap;
    const startX = (width - totalW) / 2;
    const y = height / 2 - cellH / 2 - 16;
    return values.map((v, i) => ({
      value: String(v),
      addr: (addresses && addresses[i]) || `0x${(i * 8).toString(16).toUpperCase().padStart(3, "0")}`,
      baseX: startX + i * (cellW + gap),
      baseY: y,
      cellW,
      cellH,
      offsetX: 0,
      offsetY: 0,
      opacity: 0,
      highlight: false,
      dimmed: false,
      visible: false,
    }));
  }

  function cellCenter(cells, index) {
    const c = cells[index];
    if (!c || !c.visible) return null;
    return { x: c.baseX + c.offsetX + c.cellW / 2, y: c.baseY + c.offsetY + c.cellH / 2 };
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

  function drawCell(ctx, cell, accent, muted, typography) {
    if (!cell.visible || cell.opacity <= 0.01) return;
    const x = cell.baseX + cell.offsetX;
    const y = cell.baseY + cell.offsetY;
    const w = cell.cellW;
    const h = cell.cellH;
    const labelFont = fontToken(typography, "entity_label", { size: 20, weight: 600 });
    const addrFont = fontToken(typography, "entity_address", { size: 13, weight: 400 });
    ctx.save();
    ctx.globalAlpha = cell.dimmed ? cell.opacity * 0.32 : cell.opacity;
    if (cell.highlight) {
      ctx.shadowColor = accent;
      ctx.shadowBlur = 20;
    }
    ctx.fillStyle = "rgba(22,22,36,0.96)";
    ctx.strokeStyle = cell.highlight ? accent : "rgba(100,130,200,0.65)";
    ctx.lineWidth = cell.highlight ? 3 : 2;
    roundRect(ctx, x, y, w, h, 8);
    ctx.fill();
    ctx.stroke();
    ctx.shadowBlur = 0;
    ctx.fillStyle = "#f0f0f5";
    ctx.font = labelFont;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    if (cell.value) ctx.fillText(cell.value, x + w / 2, y + h / 2 - 4);
    if (cell.addr) {
      ctx.fillStyle = muted;
      ctx.font = addrFont;
      ctx.fillText(cell.addr, x + w / 2, y + h + 16);
    }
    ctx.restore();
  }

  function drawPointer(ctx, ptr, accent) {
    if (!ptr || ptr.opacity <= 0.01) return;
    ctx.save();
    ctx.globalAlpha = ptr.opacity;
    ctx.fillStyle = accent;
    ctx.font = "600 15px 'Segoe UI', system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(ptr.label, ptr.x, ptr.y - 10);
    ctx.beginPath();
    ctx.moveTo(ptr.x, ptr.y);
    ctx.lineTo(ptr.x - 7, ptr.y + 12);
    ctx.lineTo(ptr.x + 7, ptr.y + 12);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
  }

  function drawArrow(ctx, arrow, accent) {
    const { x1, y1, x2, y2, progress } = arrow;
    const px = lerp(x1, x2, progress);
    const py = lerp(y1, y2, progress);
    ctx.save();
    ctx.strokeStyle = accent;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(px, py);
    ctx.stroke();
    const angle = Math.atan2(y2 - y1, x2 - x1);
    const size = 9;
    ctx.fillStyle = accent;
    ctx.beginPath();
    ctx.moveTo(px, py);
    ctx.lineTo(px - size * Math.cos(angle - 0.4), py - size * Math.sin(angle - 0.4));
    ctx.lineTo(px - size * Math.cos(angle + 0.4), py - size * Math.sin(angle + 0.4));
    ctx.closePath();
    ctx.fill();
    ctx.restore();
  }

  function drawComparison(ctx, spec, step, accent, width, height) {
    const p = ease(step.progress);
    const boxW = 360;
    const boxH = 160;
    const gap = 60;
    const leftX = width / 2 - boxW - gap / 2;
    const rightX = width / 2 + gap / 2;
    const y = height / 2 - boxH / 2;
    const hl = step.highlight || "left";

    function box(x, text, active, delay) {
      const slide = lerp(-36, 0, ease(Math.max(0, p - delay)));
      ctx.save();
      ctx.globalAlpha = ease(Math.max(0, p - delay * 0.5));
      ctx.fillStyle = "rgba(22,22,36,0.95)";
      ctx.strokeStyle = active ? accent : "rgba(100,130,200,0.6)";
      ctx.lineWidth = active ? 3 : 2;
      if (active) { ctx.shadowColor = accent; ctx.shadowBlur = 16; }
      roundRect(ctx, x + slide, y, boxW, boxH, 14);
      ctx.fill();
      ctx.stroke();
      ctx.shadowBlur = 0;
      ctx.fillStyle = "#f0f0f5";
      ctx.font = "22px 'Segoe UI', system-ui, sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      const words = String(text).split(" ");
      let line = "";
      const lines = [];
      for (const w of words) {
        const test = line ? `${line} ${w}` : w;
        if (ctx.measureText(test).width > boxW - 32 && line) { lines.push(line); line = w; }
        else line = test;
      }
      if (line) lines.push(line);
      const startY = y + boxH / 2 - ((lines.length - 1) * 26) / 2;
      lines.forEach((ln, i) => ctx.fillText(ln, x + slide + boxW / 2, startY + i * 26));
      ctx.restore();
    }

    box(leftX, step.left, hl === "left" || hl === "both", 0);
    box(rightX, step.right, hl === "right" || hl === "both", 0.08);
    ctx.save();
    ctx.globalAlpha = ease(p);
    ctx.fillStyle = "#666";
    ctx.font = "700 30px 'Segoe UI', system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("vs", width / 2, height / 2);
    ctx.restore();
  }

  function applyTimeline(spec, t, width, height) {
    const kind = spec.kind || "memory";
    if (kind === "comparison") {
      return { kind, comparison: spec, caption: "", captionOpacity: 0 };
    }

    const values = spec.values || [];
    const n = Math.max(values.length, 1);
    const padded = values.length ? values : Array(n).fill("");
    const cells = layoutCells(padded, spec.addresses || [], width, height, spec);
    cells.forEach((c) => {
      c.visible = false;
      c.opacity = 0;
    });
    const pointers = {};
    const links = [];
    let caption = "";
    let captionOpacity = 0;
    const highlights = new Set();

    const timeline = spec.timeline || [];
    const cellW = cells[0]?.cellW || 88;
    const gap = 10;
    const stride = cellW + gap;
    const memory = padded.map((v) => String(v));

    for (const step of timeline) {
      const at = step.at || 0;
      const dur = step.duration ?? 0.4;
      if (t < at) continue;
      const progress = dur > 0 ? ease((t - at) / dur) : 1;

      switch (step.op) {
        case "appear_all": {
          const vals = step.values || [];
          const addrs = step.addresses || [];
          const stagger = step.stagger ?? 0.09;
          vals.forEach((v, i) => {
            if (!cells[i]) return;
            const cellAt = at + i * stagger;
            if (t < cellAt) return;
            const cp = dur > 0 ? ease(Math.min(1, (t - cellAt) / dur)) : 1;
            cells[i].value = String(v);
            if (addrs[i]) cells[i].addr = addrs[i];
            cells[i].visible = true;
            cells[i].opacity = cp;
            cells[i].offsetX = lerp(24, 0, cp);
          });
          break;
        }
        case "sync_cells": {
          const vals = step.values || [];
          vals.forEach((v, i) => {
            if (cells[i]) {
              cells[i].value = String(v);
              cells[i].visible = true;
              cells[i].opacity = progress;
              memory[i] = String(v);
            }
          });
          break;
        }
        case "pointer_set": {
          const pos = cellCenter(cells, step.index);
          if (pos) {
            pointers[step.name] = {
              x: pos.x, y: pos.y - cells[0].cellH / 2 - 26,
              label: step.name, opacity: progress,
            };
          }
          break;
        }
        case "pointer": {
          const from = cellCenter(cells, step.from);
          const to = cellCenter(cells, step.to);
          if (from && to) {
            pointers[step.name] = {
              x: lerp(from.x, to.x, progress),
              y: lerp(from.y - cells[0].cellH / 2 - 26, to.y - cells[0].cellH / 2 - 26, progress),
              label: step.name,
              opacity: 1,
            };
            if (progress > 0.4) highlights.add(step.to);
          }
          break;
        }
        case "highlight": {
          (step.indices || []).forEach((i) => highlights.add(i));
          break;
        }
        case "shift": {
          const from = step.from ?? 0;
          const dir = step.direction === "left" ? -1 : 1;
          const dist = stride * dir * progress;
          for (let i = from; i < cells.length; i++) {
            if (!cells[i].visible) {
              cells[i].visible = true;
              cells[i].opacity = Math.max(cells[i].opacity, progress);
            }
            cells[i].offsetX = dist;
          }
          if (progress >= 1) {
            for (let i = from; i < cells.length; i++) cells[i].offsetX = 0;
          }
          break;
        }
        case "swap": {
          const a = step.a ?? 0;
          const b = step.b ?? 1;
          if (cells[a] && cells[b]) {
            const dist = (cells[b].baseX - cells[a].baseX) * progress;
            cells[a].offsetX = dist;
            cells[b].offsetX = -dist;
            highlights.add(a);
            highlights.add(b);
          }
          if (progress >= 1) {
            const tmp = memory[a];
            memory[a] = memory[b];
            memory[b] = tmp;
            cells[a].value = memory[a];
            cells[b].value = memory[b];
            cells[a].offsetX = 0;
            cells[b].offsetX = 0;
          }
          break;
        }
        case "set_value": {
          const idx = step.index ?? 0;
          if (cells[idx]) {
            cells[idx].visible = true;
            cells[idx].value = String(step.value ?? "");
            cells[idx].opacity = progress;
            cells[idx].offsetY = lerp(-18, 0, progress);
            memory[idx] = String(step.value ?? "");
            highlights.add(idx);
          }
          break;
        }
        case "link": {
          const from = cellCenter(cells, step.from);
          const to = cellCenter(cells, step.to);
          if (from && to) {
            links.push({
              x1: from.x + 38, y1: from.y,
              x2: to.x - 38, y2: to.y,
              progress,
            });
          }
          break;
        }
        case "caption": {
          caption = step.text || "";
          captionOpacity = progress;
          break;
        }
        default:
          break;
      }
    }

    const hlArr = [...highlights];
    const att = attentionState(spec, t);
    const salienceMap = {};
    (att.salience || []).forEach((s) => {
      if (s.entity_id) salienceMap[s.entity_id] = s.weight ?? 0.45;
    });
    cells.forEach((c, i) => {
      c.highlight = hlArr.includes(i);
      if (c.entityId && att.primary === c.entityId) {
        c.highlight = true;
      }
      const weight = c.entityId ? salienceMap[c.entityId] : null;
      c.dimmed = hlArr.length > 0 && !c.highlight;
      if (weight !== null && weight < 0.55) c.dimmed = true;
      if (c.visible && c.opacity < 0.01) c.opacity = 1;
    });

    return { kind: "memory", cells, pointers, links, caption, captionOpacity };
  }

  function renderFrame(canvas, spec, accent, t) {
    const ctx = canvas.getContext("2d");
    const w = canvas.width;
    const h = canvas.height;
    const typography = spec.typography || {};
    const muted = "#a0a0b0";
    const captionFont = fontToken(typography, "caption", { size: 24, weight: 600 });
    ctx.save();
    ctx.clearRect(0, 0, w, h);
    applyCamera(ctx, sampleCamera(spec, t, w, h), w, h);

    if (spec.kind === "comparison") {
      const timeline = spec.timeline || [];
      let active = null;
      for (const step of timeline) {
        if (step.op !== "comparison") continue;
        const at = step.at || 0;
        const dur = step.duration ?? 0.5;
        if (t >= at) {
          active = { ...step, progress: dur > 0 ? Math.min(1, (t - at) / dur) : 1 };
        }
      }
      if (active) drawComparison(ctx, spec, active, accent, w, h);
      for (const step of timeline) {
        if (step.op === "caption" && t >= step.at) {
          const p = ease(Math.min(1, (t - step.at) / (step.duration || 0.3)));
          ctx.save();
          ctx.globalAlpha = p;
          ctx.fillStyle = "#f0f0f5";
          ctx.font = captionFont;
          ctx.textAlign = "center";
          ctx.fillText(step.text, w / 2, h - 28);
          ctx.restore();
        }
      }
      ctx.restore();
      return;
    }

    const state = applyTimeline(spec, t, w, h);
    state.links.forEach((a) => drawArrow(ctx, a, accent));
    state.cells.forEach((c) => drawCell(ctx, c, accent, muted, typography));
    Object.values(state.pointers).forEach((p) => drawPointer(ctx, p, accent));

    if (state.caption) {
      ctx.save();
      ctx.globalAlpha = state.captionOpacity;
      ctx.fillStyle = "#f0f0f5";
      ctx.font = "600 24px 'Segoe UI', system-ui, sans-serif";
      ctx.textAlign = "center";
      ctx.fillText(state.caption, w / 2, h - 28);
      ctx.restore();
    }
    ctx.restore();
  }

  window.__initAlgoViz = function (canvas, spec, accent) {
    window.__renderAt = function (t) {
      renderFrame(canvas, spec, accent, t);
    };
    window.__renderAt(0);
  };
})();
