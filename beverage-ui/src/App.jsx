import React, { useEffect, useMemo, useRef, useState } from 'react';
import BeverageTown from './BeverageTown.jsx';

// 從 beverage_town.jpg 萃取的粉彩暖色票
const C = {
  bg: '#c1ab94',          // 米杏街道
  panel: '#f9e9d0',       // 奶油
  panel2: '#efe0c8',      // 深一點的奶油
  ink: '#4a2e2e',         // 深酒紅文字
  ink2: '#7a6250',        // 咖啡棕
  line: 'rgba(74,46,46,.16)', line2: 'rgba(74,46,46,.30)',
  gold: '#60232b',        // 酒紅屋頂
  sky: '#8ac8e1',         // 天藍
  coke: '#c8463a', pepsi: '#3f7fbf',
  disp: '"Songti SC","STSong","Source Han Serif TC","Noto Serif CJK TC","PMingLiU",serif',
  ui: '"PingFang TC","Source Han Sans TC","Noto Sans CJK TC","Microsoft JhengHei",sans-serif',
};

const GROUP_LABELS = {
  CG: '對照組（可樂固定 $2.00、百事自由）',
  TG1: '衝擊組 +5%（可樂漲到 $2.10）',
  TG2: '衝擊組 +10%（可樂漲到 $2.20）',
  TG3: '衝擊組 +20%（可樂漲到 $2.40）',
  SYM: '對稱競價（兩家都自由）',
  PEP12: '2022 重現（百事 +12% = $2.24）',
  BF: '純參數基線（兩家固定 $2.00）',
  BF5: '純參數 +5%',
  BF10: '純參數 +10%',
  BF20: '純參數 +20%',
};

export default function App() {
  const [index, setIndex] = useState(null);
  const [group, setGroup] = useState('TG2');
  const [cell, setCell] = useState('n200_w4');
  const [seed, setSeed] = useState(0);
  const [run, setRun] = useState(null);
  const [day, setDay] = useState(1);
  const [playing, setPlaying] = useState(false);
  const dayRef = useRef(1);
  dayRef.current = day;

  useEffect(() => {
    fetch('/data/index.json')
      .then((r) => r.json())
      .then((d) => {
        setIndex(d);
        const first = d.runs.find(
          (x) => x.group === 'TG2' && x.cell === 'n200_w4' && x.seed === 0,
        ) || d.runs[0];
        if (first) {
          setGroup(first.group);
          setCell(first.cell);
          setSeed(first.seed);
        }
      });
  }, []);

  const groups = useMemo(() => {
    if (!index) return [];
    return [...new Set(index.runs.map((r) => r.group))];
  }, [index]);

  const cells = useMemo(() => {
    if (!index) return [];
    return [...new Set(index.runs.filter((r) => r.group === group).map((r) => r.cell))];
  }, [index, group]);

  const seeds = useMemo(() => {
    if (!index) return [];
    return index.runs.filter((r) => r.group === group && r.cell === cell)
      .map((r) => r.seed).sort((a, b) => a - b);
  }, [index, group, cell]);

  useEffect(() => {
    if (!index) return;
    const meta = index.runs.find(
      (r) => r.group === group && r.cell === cell && r.seed === seed,
    );
    if (!meta) return;
    fetch(`/data/${group}/${cell}/seed${seed}.json`)
      .then((r) => r.json())
      .then((d) => {
        setRun(d);
        setDay(1);
        setPlaying(false);
      });
  }, [index, group, cell, seed]);

  // play loop
  useEffect(() => {
    if (!playing || !run) return;
    const id = setInterval(() => {
      setDay((d) => {
        if (d >= run.meta.n_days) {
          setPlaying(false);
          return d;
        }
        return d + 1;
      });
    }, 600);
    return () => clearInterval(id);
  }, [playing, run]);

  const meta = run?.meta;
  const daily = run?.daily?.[day - 1];

  return (
    <div style={{
      display: 'flex', flexDirection: 'column',
      height: '100vh', overflow: 'hidden',
      background: C.bg, color: C.ink, fontFamily: C.ui,
    }}>
      {/* 標題（單行，不換行） */}
      <header style={{
        padding: '8px 18px', background: C.panel, borderBottom: `1px solid ${C.line2}`,
        textAlign: 'center', whiteSpace: 'nowrap', overflow: 'hidden',
      }}>
        <span style={{ fontSize: 20, color: C.gold, fontFamily: C.disp, letterSpacing: '.04em', fontWeight: 700 }}>
          🥤 飲料鎮 BeverageTown 重放
        </span>
        <span style={{ fontSize: 12.5, color: C.ink2, marginLeft: 14 }}>
          可口可樂 vs 百事可樂 · 競價模擬實驗
        </span>
      </header>

      {/* 控制列：所有選單與按鈕 */}
      <div style={{
        padding: '8px 18px', background: C.panel2, borderBottom: `1px solid ${C.line}`,
        display: 'flex', gap: '14px', alignItems: 'center', flexWrap: 'wrap',
        justifyContent: 'center',
      }}>
        <label style={{ fontSize: 13, display: 'flex', alignItems: 'center', gap: 5 }}>
          實驗組{' '}
          <select value={group} onChange={(e) => setGroup(e.target.value)}
            style={selectStyle}>
            {groups.map((g) => (
              <option key={g} value={g}>{g} — {GROUP_LABELS[g] || g}</option>
            ))}
          </select>
        </label>
        <label style={{ fontSize: 13, display: 'flex', alignItems: 'center', gap: 5 }}>
          情境{' '}
          <select value={cell} onChange={(e) => setCell(e.target.value)}
            style={selectStyle}>
            {cells.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>
        <label style={{ fontSize: 13, display: 'flex', alignItems: 'center', gap: 5 }}>
          Seed{' '}
          <select value={seed} onChange={(e) => setSeed(Number(e.target.value))}
            style={selectStyle}>
            {seeds.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>

        <button onClick={() => setPlaying((p) => !p)} style={btnStyle}>
          {playing ? '⏸ 暫停' : '▶ 播放'}
        </button>
        <button onClick={() => setDay(1)} style={btnStyle}>⏮ 第一天</button>

        <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 240 }}>
          <span style={{ fontSize: 12, color: C.ink2 }}>
            Day {day} / {meta?.n_days ?? '—'}
          </span>
          <input
            type="range" min={1} max={meta?.n_days ?? 1} value={day}
            onChange={(e) => setDay(Number(e.target.value))}
            style={{ flex: 1, accentColor: C.gold }}
          />
        </div>
      </div>

      {/* 主畫面：填滿剩餘空間（overflow hidden 防止畫布溢出） */}
      <div style={{
        flex: 1, minHeight: 0, padding: '10px 12px', display: 'flex',
        justifyContent: 'center', alignItems: 'center',
        overflow: 'hidden',
      }}>
        <BeverageTown run={run} day={day} playing={playing} />
      </div>

      {/* 資訊面板：固定高度，置於主畫面下方 */}
      <div style={{
        padding: '10px 18px', background: C.panel2, borderTop: `1px solid ${C.line}`,
        flexShrink: 0,
      }}>
        {run ? <InfoPanel meta={meta} daily={daily} day={day} /> : <p>載入中…</p>}
      </div>
    </div>
  );
}

const selectStyle = {
  background: C.panel, color: C.ink, border: `1px solid ${C.line2}`,
  borderRadius: 6, padding: '4px 8px', fontSize: 13,
};
const btnStyle = {
  background: C.panel, color: C.ink, border: `1px solid ${C.line2}`,
  borderRadius: 6, padding: '5px 12px', fontSize: 13, cursor: 'pointer',
};
btnStyle[':hover'] = { borderColor: C.gold };

function InfoPanel({ meta, daily, day }) {
  if (!daily) return <p>無資料</p>;
  const fmt = (x) => (x === null || x === undefined || Number.isNaN(x) ? '—' : Number(x).toFixed(2));
  const Row = ({ k, v, strong }) => (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '3px 0',
      borderBottom: `1px solid ${C.line}`, fontWeight: strong ? 600 : 400 }}>
      <span style={{ color: C.ink2 }}>{k}</span><span>{v}</span>
    </div>
  );
  const Card = ({ title, color, children }) => (
    <div style={{
      flex: 1, minWidth: 200, background: C.panel, border: `1px solid ${C.line2}`,
      borderRadius: 8, padding: '12px 14px',
    }}>
      <h4 style={{ margin: '0 0 8px', color, fontSize: 14, fontFamily: C.disp }}>{title}</h4>
      {children}
    </div>
  );
  return (
    <div style={{ maxWidth: 1200, margin: '0 auto' }}>
      <h3 style={{
        margin: '0 0 10px', fontSize: 15, color: C.gold, fontFamily: C.disp,
      }}>
        📊 第 {day} 天市場狀態
      </h3>
      <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
        <Card title="🥤 可口可樂" color={C.coke}>
          <Row k="售價" v={`$${fmt(daily.price_coke)}`} strong />
          <Row k="品質" v={fmt(daily.quality_coke)} />
          <Row k="行銷預算" v={`$${fmt(daily.marketing_coke)}`} />
          <Row k="銷量" v={`${daily.sales_coke} 罐`} />
          <Row k="市占率" v={`${(daily.share_coke * 100).toFixed(1)}%`} />
          <Row k="營收" v={`$${fmt(daily.revenue_coke)}`} />
        </Card>
        <Card title="🧃 百事可樂" color={C.pepsi}>
          <Row k="售價" v={`$${fmt(daily.price_pepsi)}`} strong />
          <Row k="品質" v={fmt(daily.quality_pepsi)} />
          <Row k="行銷預算" v={`$${fmt(daily.marketing_pepsi)}`} />
          <Row k="銷量" v={`${daily.sales_pepsi} 罐`} />
          <Row k="市占率" v={`${(daily.share_pepsi * 100).toFixed(1)}%`} />
          <Row k="營收" v={`$${fmt(daily.revenue_pepsi)}`} />
        </Card>
        <Card title="🏙️ 市場總覽" color={C.gold}>
          <Row k="不購買 (opt-out)" v={`${daily.optout} 人`} />
          <Row k="HHI 集中度" v={fmt(daily.hhi)} strong />
          <p style={{ marginTop: 12, fontSize: 12, color: C.ink2 }}>
            {meta.rule === 'sum'
              ? '群體決策規則：效用加總（sum）'
              : '群體決策規則：多數決 + 探索傾向'}
            <br />{meta.n_consumers} 位消費者 · {meta.n_days} 天
          </p>
        </Card>
      </div>
    </div>
  );
}
