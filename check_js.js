/**
 * check_js.js — 对构建产物做 JS 语法冒烟测试(不执行,不需要 DOM)
 *
 * 为什么单独做这一步:dashboard.html 是单文件页面,内联脚本一旦有语法错误,
 * 浏览器里就是整页白屏,而白屏和"还在加载"在肉眼上几乎无法区分。
 * 用 new Function 让 V8 解析一遍,几毫秒就能把语法错误挡在提交之前。
 *
 * 用法:node check_js.js
 */
'use strict';
const fs = require('fs');
const path = require('path');

const file = path.join(__dirname, 'dashboard.html');
const html = fs.readFileSync(file, 'utf8');

const start = html.indexOf('const DATASET =');
const end = html.lastIndexOf('</script>');
if (start < 0 || end < 0) {
  console.log('语法校验: FAIL -> 没找到内联脚本区段');
  process.exit(1);
}
const code = html.slice(start, end);

try {
  new Function(code);            // 只解析不执行,因此不需要 document / window
  console.log(`语法校验: PASS (${code.length} 字符)`);
} catch (err) {
  console.log(`语法校验: FAIL -> ${err.message}`);
  process.exit(1);
}
