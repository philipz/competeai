import React, { useEffect, useRef, useState } from 'react';

// ── 飲料鎮：以 beverage_town.jpeg 為背景 + truman 風格 pixel man 疊加 ──
// 背景直接使用圖片（css cover），pixel man 在上層 canvas。
// 色票從圖片萃取：天藍天空 #8ac8e1、米杏街道 #c1ab94、奶油 #f9e9d0、酒紅 #60232b

const W = 880;
const H = 560;
const ART = 16;
const TS = 40;
const DPR = Math.min(window.devicePixelRatio || 1, 2);

// 商店目標位置（虛擬座標，疊在圖片上。可樂店在左、百事店在右、廣場中央）
const COKE_POS = { x: W * 0.18, y: H * 0.62 };
const PEPSI_POS = { x: W * 0.82, y: H * 0.62 };
const PLAZA_POS = { x: W * 0.50, y: H * 0.55 };

const SKIN = '#f0c8a0';
const SKIN_D = '#d8a878';
const DARK = '#2a2220';
const SOLO_HAIR = ['#5c4632', '#7a5a42', '#8a6a4a', '#3a3028', '#4a3a28', '#6b4f3a', '#2e2a2e'];
const SOLO_SHIRT = ['#60232b', '#c8463a', '#3f7fbf', '#4c9a6a', '#c8a02e', '#9a6ab0', '#3aa0a8', '#d08040'];
const GROUP_COLORS = [
  ['#60232b', '#3f7fbf'], ['#3f7fbf', '#4c9a6a'], ['#4c9a6a', '#c8a02e'],
  ['#c8a02e', '#9a6ab0'], ['#9a6ab0', '#3aa0a8'], ['#3aa0a8', '#d08040'],
  ['#d08040', '#c8463a'], ['#5aa38f', '#60232b'], ['#b98ede', '#3f7fbf'],
  ['#f0c8a0', '#4c9a6a'], ['#e8e0d0', '#9a6ab0'], ['#c8463a', '#3aa0a8'],
];

function hash(x, y, s) {
  let h = Math.sin(x * 127.1 + y * 311.7 + s * 74.7) * 43758.5453;
  return h - Math.floor(h);
}

function shade(hex, amt) {
  const n = parseInt(hex.slice(1), 16);
  const r = Math.max(0, Math.min(255, (n >> 16) + Math.round(255 * amt)));
  const g = Math.max(0, Math.min(255, ((n >> 8) & 255) + Math.round(255 * amt)));
  const b = Math.max(0, Math.min(255, (n & 255) + Math.round(255 * amt)));
  return `rgb(${r},${g},${b})`;
}

// 消費者「家」位置（散佈在圖片上半部）
function homeOf(cid, n) {
  const perRow = Math.ceil(Math.sqrt(n * 1.2));
  const row = Math.floor(cid / perRow);
  const col = cid % perRow;
  return {
    x: W * 0.08 + (col % perRow) * (W * 0.84 / Math.max(perRow, 1)),
    y: H * 0.10 + (row % 4) * H * 0.09,
  };
}

function targetOf(choice, cid) {
  const s = (hash(cid, 3, 0) - 0.5) * 60;
  const s2 = (hash(cid, 7, 0) - 0.5) * 40;
  if (choice === 0) return { x: COKE_POS.x + s * 0.5, y: COKE_POS.y + s2 };
  if (choice === 1) return { x: PEPSI_POS.x + s * 0.5, y: PEPSI_POS.y + s2 };
  return { x: PLAZA_POS.x + s, y: PLAZA_POS.y + s2 };
}

// ── pixel man（移植 truman drawFigure，Canvas2D 版）───────────────────
function drawPixelMan(g, cx, footY, T, opts) {
  const u = T / ART;
  const face = opts.face || 'down';
  const fr = opts.frame || 0;
  const flip = face === 'left';
  const side = face === 'left' || face === 'right';
  const back = face === 'up';
  const skin = opts.skin || SKIN;
  const skinD = opts.skinD || SKIN_D;
  const hair = opts.hair || SOLO_HAIR[0];
  const shirt = opts.shirt || SOLO_SHIRT[0];
  const shirtD = shade(shirt, -0.25);
  const shirtL = shade(shirt, 0.12);
  const pants = '#3a3f4a';
  const bob = opts.bob || 0;

  const R = (ax, ay, aw, ah, c) => {
    if (aw <= 0 || ah <= 0) return;
    g.fillStyle = c;
    g.fillRect(Math.round(cx - 8 * u + (flip ? 16 - ax - aw : ax) * u),
               Math.round(footY - 15.6 * u + ay * u + bob * u),
               Math.max(1, Math.round(aw * u)), Math.max(1, Math.round(ah * u)));
  };

  g.fillStyle = 'rgba(0,0,0,.32)';
  g.beginPath();
  g.ellipse(cx, footY - 0.6 * u, 5 * u, 1.9 * u, 0, 0, 6.3);
  g.fill();

  const step = fr === 1 ? 1 : fr === 3 ? -1 : 0;

  R(5.5, 3.0, 5.0, 4.6, skin);
  R(5.5, 7.2, 5.0, 0.6, skinD);
  R(6.9, 7.6, 2.2, 1.0, skinD);
  if (back) {
    R(5.2, 2.4, 5.6, 5.2, hair);
  } else {
    R(5.2, 2.4, 5.6, 1.6, hair);
    R(5.2, 3.6, 0.9, 2.6, hair); R(9.9, 3.6, 0.9, 2.6, hair);
    if (!side) { R(6.6, 5.3, 0.9, 1.0, DARK); R(8.5, 5.3, 0.9, 1.0, DARK); }
    else { R(9.2, 5.3, 0.9, 1.0, DARK); R(10.5, 4.6, 0.7, 1.6, skin); }
  }

  const bw = side ? 5.2 : 6.0;
  const bx = 8 - bw / 2;
  R(bx, 8.4, bw, 4.3, shirt);
  R(bx, 8.4, bw, 0.5, shirtL);
  R(bx + bw - 0.6, 8.9, 0.6, 3.8, shirtD);
  if (!side && !back) {
    R(6.7, 8.4, 1.0, 1.1, '#efe7d5'); R(8.3, 8.4, 1.0, 1.1, '#efe7d5');
    R(7.3, 9.3, 1.4, 0.8, '#efe7d5');
    R(6.2, 8.4, 0.6, 1.5, '#e8e0d0'); R(9.2, 8.4, 0.6, 1.5, '#e8e0d0');
  } else if (back) {
    R(7.6, 8.4, 0.8, 4.3, shirtD);
  }
  R(bx - 0.2, 11.3, bw + 0.4, 0.9, '#4a4238');
  R(4.3, 12.5, 7.4, 1.8, shirtD);
  R(4.3, 12.5, 7.4, 0.4, shade(shirt, -0.45));

  if (side) {
    R(9.8, 8.8, 1.9, 3.0, shirtD); R(9.9, 11.5, 1.7, 0.6, '#e8e0d0'); R(10.1, 12.0, 1.3, 1.1, skin);
  } else {
    R(3.6, 8.8, 1.8, 2.9, shirtD); R(10.6, 8.8, 1.8, 2.9, shirtD);
    R(3.6, 11.4, 1.8, 0.6, '#e8e0d0'); R(10.6, 11.4, 1.8, 0.6, '#e8e0d0');
    R(3.8, 11.9, 1.4, 1.1, skin); R(10.8, 11.9, 1.4, 1.1, skin);
  }

  R(5.9, 14.2 - Math.max(0, step) * 0.4, 2.0, 1.3, pants);
  R(8.1, 14.2 - Math.max(0, -step) * 0.4, 2.0, 1.3, pants);
}

// ── 主元件：圖片背景 + 上層 canvas 的 pixel man ─────────────────────────
export default function BeverageTown({ run, day }) {
  const canvasRef = useRef(null);
  const wrapRef = useRef(null);
  const stateRef = useRef([]);
  const dayRef = useRef(day);
  dayRef.current = day;
  const runRef = useRef(run);
  runRef.current = run;
  const frameRef = useRef(0);
  // 依父容器計算的顯示尺寸，保持 880:560 比例（不拉伸）
  const [display, setDisplay] = useState({ w: W, h: H });

  // ResizeObserver：依容器尺寸算等比顯示尺寸（量測包住自己的容器）
  useEffect(() => {
    const wrap = wrapRef.current;
    if (!wrap) return;
    const ratio = W / H;
    // 找最接近的定位容器 = 主畫面容器（BeverageTown 的 parent）
    const host = wrap.parentElement;
    if (!host) return;
    const compute = () => {
      // 量測 host 的內容區（不含 padding）
      const hs = getComputedStyle(host);
      const pw = host.clientWidth - parseFloat(hs.paddingLeft || 0) - parseFloat(hs.paddingRight || 0);
      const ph = host.clientHeight - parseFloat(hs.paddingTop || 0) - parseFloat(hs.paddingBottom || 0);
      let w = pw, h = pw / ratio;
      if (h > ph) { h = ph; w = ph * ratio; }
      setDisplay({ w: Math.max(1, Math.round(w)), h: Math.max(1, Math.round(h)) });
    };
    compute();
    const ro = new ResizeObserver(compute);
    ro.observe(host);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    if (!run) { stateRef.current = []; return; }
    const { meta, consumers, choices } = run;
    const n = meta.n_consumers;
    const agents = [];
    for (let cid = 0; cid < n; cid++) {
      const info = consumers[String(cid)] || { solo: true, group_id: null };
      const home = homeOf(cid, n);
      const solo = info.solo;
      const gid = solo ? 0 : Number(info.group_id || 0);
      const palette = solo
        ? [SOLO_HAIR[cid % SOLO_HAIR.length], SOLO_SHIRT[cid % SOLO_SHIRT.length]]
        : GROUP_COLORS[gid % GROUP_COLORS.length];
      const choice = choices[cid]?.[0] ?? 2;
      const t = targetOf(choice, cid);
      agents.push({
        cid, solo, group_id: info.group_id,
        hair: palette[0], shirt: palette[1],
        x: home.x, y: home.y, tx: t.x, ty: t.y,
        face: 'down', frame: 0, bob: 0,
      });
    }
    stateRef.current = agents;
  }, [run]);

  useEffect(() => {
    if (!run) return;
    const { meta, choices } = run;
    const idx = Math.min(day - 1, meta.n_days - 1);
    for (const a of stateRef.current) {
      const choice = choices[a.cid]?.[idx] ?? 2;
      const t = targetOf(choice, a.cid);
      a.tx = t.x; a.ty = t.y;
    }
  }, [run, day]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    canvas.width = W * DPR;
    canvas.height = H * DPR;
    const g = canvas.getContext('2d');
    g.scale(DPR, DPR);
    let raf;
    const loop = () => {
      frameRef.current = (frameRef.current + 1) % 60;
      const speed = 0.12;
      const walkFrame = Math.floor(frameRef.current / 12) % 4;
      for (const a of stateRef.current) {
        const dx = a.tx - a.x, dy = a.ty - a.y;
        a.x += dx * speed;
        a.y += dy * speed;
        const moving = Math.abs(dx) + Math.abs(dy) > 1;
        a.frame = moving ? walkFrame : 0;
        a.face = Math.abs(dx) > Math.abs(dy) ? (dx < 0 ? 'left' : 'right') : (dy < 0 ? 'up' : 'down');
        a.bob = moving ? Math.sin(frameRef.current * 0.35) * 1.2 : 0;
      }
      g.clearRect(0, 0, W, H);
      // 商店招牌（疊在圖片上，標示此地為可樂/百事）
      drawShopSign(g, COKE_POS, '🥤 可口可樂', '#c8463a');
      drawShopSign(g, PEPSI_POS, '🧃 百事可樂', '#3f7fbf');
      // 廣場標籤
      g.fillStyle = 'rgba(60,32,40,.7)';
      g.font = '11px "PingFang TC","Noto Sans TC",sans-serif';
      g.textAlign = 'center';
      g.fillText('廣場（不購買）', PLAZA_POS.x, PLAZA_POS.y - 34);
      // pixel men
      for (const a of stateRef.current) {
        drawPixelMan(g, a.x, a.y, TS, {
          face: a.face || 'down', frame: a.frame || 0, bob: a.bob || 0,
          skin: SKIN, skinD: SKIN_D, hair: a.hair, shirt: a.shirt,
        });
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);

  return (
    <div ref={wrapRef} style={{
      position: 'relative', overflow: 'hidden',
      width: display.w, height: display.h,   // 保持 880:560 比例，不拉伸
      maxWidth: '100%',
    }}>
      {/* 背景圖片 */}
      <div style={{
        position: 'absolute', inset: 0,
        backgroundImage: 'url(/beverage_town.jpg)',
        backgroundSize: 'cover', backgroundPosition: 'center',
      }} />
      {/* 上方略壓暗，讓招牌與人物清楚 */}
      <div style={{
        position: 'absolute', inset: 0,
        background: 'linear-gradient(180deg, rgba(60,32,40,.18) 0%, rgba(60,32,40,0) 30%)',
        pointerEvents: 'none',
      }} />
      {/* pixel man 畫布：邏輯解析度固定 W×H，CSS 縮放填滿（比例正確） */}
      <canvas ref={canvasRef} style={{
        position: 'absolute', top: 0, left: 0,
        width: '100%', height: '100%',
      }} />
    </div>
  );
}

function drawShopSign(g, pos, label, color) {
  const w = 110, h = 30;
  const x = pos.x - w / 2, y = pos.y - 50;
  g.fillStyle = 'rgba(40,22,28,.85)';
  g.beginPath();
  if (g.roundRect) g.roundRect(x, y, w, h, 8); else g.rect(x, y, w, h);
  g.fill();
  g.fillStyle = '#f9e9d0';
  g.font = 'bold 14px "PingFang TC","Noto Sans TC",sans-serif';
  g.textAlign = 'center';
  g.fillText(label, pos.x, y + 20);
  // 店前柱子
  g.fillStyle = color;
  g.fillRect(pos.x - 3, y + h, 6, 22);
}
