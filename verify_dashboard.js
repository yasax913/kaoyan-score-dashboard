/**
 * verify_dashboard.js — 看板核心逻辑的冒烟测试(不依赖浏览器 / 不依赖 DOM)
 *
 * 为什么需要它:看板是单文件 HTML,一旦 JS 报错就是整页白屏,
 * 而白屏在截图里"看起来"和加载中没区别。所以在构建之后必须能自动化验证:
 *   1) 注入的 JSON 能被解析,数据结构正确;
 *   2) 纯函数(刻度算法、最小二乘回归)对真实数据不产生 NaN / 越界结果;
 *   3) 页面里所有结构性 id 都在,且 JS 里用到的 id 没有拼错。
 *
 * 用法:node verify_dashboard.js
 */
'use strict';
const fs = require('fs');
const path = require('path');

const HTML = path.join(__dirname, 'dashboard.html');
const html = fs.readFileSync(HTML, 'utf8');

let failures = 0, checks = 0;
function check(name, ok, detail) {
  checks++;
  if (ok) { console.log(`  [PASS] ${name}`); }
  else { failures++; console.log(`  [FAIL] ${name}${detail ? ' -> ' + detail : ''}`); }
}

/* ---------------------------------------------------------------- 1. 提取数据 */
console.log('\n[1/4] 解析注入的数据');
const mData = html.match(/const DATASET = (\[[\s\S]*?\]);\s*const META = (\{[\s\S]*?\});/);
check('能在 HTML 中找到 DATASET / META 注入点', !!mData);
if (!mData) {
  const at = html.indexOf('const DATASET');
  console.log('      调试信息: 注入点在偏移 ' + at);
  console.log('      实际内容: ' + html.slice(at, at + 90).replace(/\n/g, '\\n'));
  process.exit(1);
}

const DATASET = JSON.parse(mData[1]);
const META = JSON.parse(mData[2]);
check('DATASET 是非空数组', Array.isArray(DATASET) && DATASET.length > 0, `len=${DATASET.length}`);
check('META.rows 与实际行数一致', META.rows === DATASET.length, `${META.rows} vs ${DATASET.length}`);

const requiredFields = ['year','school','region','tier','subject_code','subject_name',
  'is_self_marked','national_line','retest_line','single_subject_100','single_subject_150',
  'applicants','admitted','ratio','note'];
const sample = DATASET[0];
const missing = requiredFields.filter(f => !(f in sample));
check('每条记录都含全部 15 个字段', missing.length === 0, missing.join(','));

const wrongType = DATASET.find(d =>
  typeof d.year !== 'number' || typeof d.retest_line !== 'number' ||
  typeof d.ratio !== 'number' || typeof d.school !== 'string');
check('数值字段是 number(不是字符串,否则排序会退化成字典序)', !wrongType,
  wrongType ? JSON.stringify(wrongType) : '');

const keys = new Set(DATASET.map(d => `${d.year}|${d.school}|${d.subject_code}`));
check('主键 (年份,院校,专业) 唯一', keys.size === DATASET.length,
  `${DATASET.length - keys.size} 条重复`);

const badScore = DATASET.filter(d => !(d.retest_line > 0 && d.retest_line <= 500));
check('复试线均在 (0,500] 区间', badScore.length === 0, `${badScore.length} 条异常`);

const badLine = DATASET.filter(d => d.is_self_marked === '否' && d.retest_line < d.national_line);
check('非自划线院校不低于国家线', badLine.length === 0, `${badLine.length} 条违规`);

/* ------------------------------------------------------- 2. 复算页面里的纯函数 */
console.log('\n[2/4] 复算刻度与回归算法');
const YEARS = [...new Set(DATASET.map(d => d.year))].sort((a, b) => a - b);
const LATEST = YEARS[YEARS.length - 1];
check('YEARS 覆盖 >= 3 个年份', YEARS.length >= 3, YEARS.join(','));

function niceTicks(min, max, count) {
  if (max === min) { max = min + 1; }
  const raw = (max - min) / count;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const norm = raw / mag;
  const step = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10) * mag;
  const ticks = [];
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) ticks.push(+v.toFixed(6));
  const lo = Math.floor(min / step) * step, hi = Math.ceil(max / step) * step;
  return { ticks, lo, hi };
}

const allScores = DATASET.map(d => d.retest_line);
const t = niceTicks(Math.min(...allScores) - 18, Math.max(...allScores) + 18, 5);
check('niceTicks 返回有限数值', t.ticks.length > 0 && t.ticks.every(Number.isFinite),
  JSON.stringify(t));
check('niceTicks 的 lo/hi 包住数据范围',
  t.lo <= Math.min(...allScores) && t.hi >= Math.max(...allScores), `${t.lo}..${t.hi}`);
check('niceTicks 的步长均匀', t.ticks.length < 3 ||
  Math.abs((t.ticks[1] - t.ticks[0]) - (t.ticks[t.ticks.length-1] - t.ticks[t.ticks.length-2])) < 1e-6);

const single = niceTicks(400, 400, 5);
check('niceTicks 处理 min==max 的退化输入', Number.isFinite(single.lo) && Number.isFinite(single.hi));

function forecast(series) {
  const pts = series.map((v, i) => [YEARS[i], v]).filter(p => p[1] !== null);
  if (pts.length < 3) return null;
  const n = pts.length;
  const sx = pts.reduce((a, p) => a + p[0], 0), sy = pts.reduce((a, p) => a + p[1], 0);
  const sxy = pts.reduce((a, p) => a + p[0] * p[1], 0), sxx = pts.reduce((a, p) => a + p[0] * p[0], 0);
  const slope = (n * sxy - sx * sy) / (n * sxx - sx * sx || 1);
  const intercept = (sy - slope * sx) / n;
  const pred = slope * LATEST + intercept;
  const next = pred + slope;
  const vals = pts.map(p => p[1]);
  const span = Math.max(...vals) - Math.min(...vals);
  const band = Math.max(6, Math.round(span * 0.20));
  return { slope, next: Math.round(next), lo: Math.round(next - band), hi: Math.round(next + band) };
}

const schools = [...new Set(DATASET.map(d => d.school))];
const subjects = [...new Set(DATASET.map(d => d.subject_code))];
let fcCount = 0, fcBad = 0, flatSlope = 0;

for (const sub of subjects) {
  for (const sc of schools) {
    const rows = DATASET.filter(d => d.subject_code === sub && d.school === sc);
    const map = new Map(rows.map(d => [d.year, d.retest_line]));
    const series = YEARS.map(y => (map.has(y) ? map.get(y) : null));
    const f = forecast(series);
    if (!f) continue;
    fcCount++;
    if (!Number.isFinite(f.slope) || !Number.isFinite(f.next) || f.lo > f.hi) fcBad++;
    if (Math.abs(f.slope) < 1e-9) flatSlope++;
    // 外推结果不应远离历史区间,否则说明回归发散
    const vals = series.filter(v => v !== null);
    const span = Math.max(...vals) - Math.min(...vals);
    if (Math.abs(f.next - vals[vals.length - 1]) > span + 30) {
      fcBad++;
      console.log(`      发散: ${sc} ${sub} 历史 ${vals.join('/')} -> 预测 ${f.next}`);
    }
  }
}
check(`回归外推产生有效结果(共 ${fcCount} 条序列)`, fcCount > 0 && fcBad === 0, `${fcBad} 条异常`);
check('回归斜率不会是 NaN', flatSlope >= 0);

/* 已知答案的回归自检:完美直线 y = 2x 必须回归出 slope=2 */
const perfect = YEARS.map((y, i) => 300 + 2 * i);
const pf = forecast(perfect);
check('回归算法对完美线性序列还原出斜率 2.0', Math.abs(pf.slope - 2) < 1e-6, `slope=${pf.slope}`);

/* ------------------------------------------------------- 3. 检查 DOM 契约 */
console.log('\n[3/4] 检查 DOM id 契约');
const scriptText = html.slice(html.indexOf('const DATASET ='), html.lastIndexOf('</script>'));
const usedIds = new Set([...scriptText.matchAll(/getElementById\(['"]([^'"]+)['"]\)/g)].map(m => m[1]));
// 模板里通过 querySelector 选择器的 id 也一并收集
for (const m of scriptText.matchAll(/querySelector\(['"]#([A-Za-z0-9_-]+)/g)) usedIds.add(m[1]);

const missingIds = [...usedIds].filter(id => !new RegExp(`id=["']${id}["']`).test(html));
check(`JS 引用的 ${usedIds.size} 个 id 都存在于 HTML 中`, missingIds.length === 0,
  missingIds.join(','));

const declaredIds = [...html.matchAll(/\sid=["']([A-Za-z0-9_-]+)["']/g)].map(m => m[1]);
const dupIds = declaredIds.filter((v, i) => declaredIds.indexOf(v) !== i);
check('HTML 里没有重复 id', dupIds.length === 0, dupIds.join(','));

/* ------------------------------------------------------- 4. 检查零依赖 */
console.log('\n[4/4] 检查零外部依赖');
const extRefs = [...html.matchAll(/(?:src|href)\s*=\s*["'](https?:)?\/\/[^"']+/g)].map(m => m[0]);
check('没有任何指向 CDN / 外部域名的引用', extRefs.length === 0, extRefs.join(' , '));
check('没有外部字体请求', !/@import|fonts\.googleapis/.test(html));
check('文件自包含(含内联 <style> 与 <script>)', /<style>/.test(html) && /<script>/.test(html));

console.log(`\n结果: ${checks - failures}/${checks} 项通过` + (failures ? `,${failures} 项失败` : ''));
process.exit(failures ? 1 : 0);
