import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(__dirname, "..");
const portfolioHtmlPath = path.join(frontendDir, "portfolio.html");
const stylesCss = fs.readFileSync(path.join(frontendDir, "styles.css"), "utf8");

test("portfolio case page presents StoryCraft as a Chinese product case study", () => {
  assert.equal(fs.existsSync(portfolioHtmlPath), true);
  const html = fs.readFileSync(portfolioHtmlPath, "utf8");

  assert.match(html, /lang="zh-CN"/);
  assert.match(html, /AI 原生互动叙事产品案例/);
  assert.match(html, /剧情与智能 NPC 对话生产后台/);
  assert.match(html, /StoryCraft Studio/);
});

test("portfolio case page exposes demo and product evidence entry points", () => {
  const html = fs.readFileSync(portfolioHtmlPath, "utf8");

  assert.match(html, /href="\.\/index\.html\?demo=1"/);
  assert.match(html, /http:\/\/127\.0\.0\.1:5500\/index\.html\?demo=1/);
  assert.match(html, /window\.location\.protocol === "file:"/);
  assert.match(html, /data-local-demo-hint/);
  assert.match(html, /href="#product-definition"/);
  assert.match(html, /href="#evaluation"/);
  assert.match(html, /href="#demo-walkthrough"/);
  assert.match(html, /产品定义/);
  assert.match(html, /测试集/);
  assert.match(html, /项目演示/);
  assert.match(html, /产品路线/);
});

test("portfolio case page embeds a guided demo walkthrough", () => {
  const html = fs.readFileSync(portfolioHtmlPath, "utf8");

  assert.match(html, /id="demo-walkthrough"/);
  assert.match(html, /Demo Walkthrough/);
  assert.match(html, /进入剧情生产后台/);
  assert.match(html, /查看章节与场景/);
  assert.match(html, /点击角色头像进入 NPC 单聊/);
  assert.match(html, /观察好感度、记忆标签、情绪如何影响回复/);
  assert.match(html, /查看 AI Agent \/ Reviewer/);
  assert.match(html, /请尝试和薇岚导师对话/);
  assert.match(html, /询问规则、表达困惑、请求陪伴/);
  assert.match(html, /href="\.\/index\.html\?demo=1"[^>]*data-demo-entry/);
});

test("portfolio case page shows an AI PM output loop instead of a feature list", () => {
  const html = fs.readFileSync(portfolioHtmlPath, "utf8");

  assert.match(html, /id="output-loop"/);
  assert.match(html, /闭环输出/);
  assert.match(html, /黑客级输入/);
  assert.match(html, /技术取舍/);
  assert.match(html, /可评测输出/);
  assert.match(html, /踩坑与迭代/);
  assert.match(html, /为什么做/);
  assert.match(html, /如何做/);
  assert.match(html, /怎么判断好不好/);
});

test("portfolio case page explains hacker-level AI competitive research", () => {
  const html = fs.readFileSync(portfolioHtmlPath, "utf8");

  assert.match(html, /id="technical-research"/);
  assert.match(html, /RAG 策略/);
  assert.match(html, /Prompt 结构/);
  assert.match(html, /Agent 架构/);
  assert.match(html, /模型边界/);
  assert.match(html, /产品设计和技术边界之间的取舍/);
});

test("portfolio case page upgrades evaluation into measurable AI PM evidence", () => {
  const html = fs.readFileSync(portfolioHtmlPath, "utf8");

  assert.match(html, /评分方法/);
  assert.match(html, /1-5 分/);
  assert.match(html, /失败样本/);
  assert.match(html, /改进动作/);
  assert.match(html, /从评测到迭代/);
  assert.match(html, /A 模型或原始 Prompt/);
  assert.match(html, /B 方案/);
});

test("portfolio case page tells the product story in scannable sections", () => {
  const html = fs.readFileSync(portfolioHtmlPath, "utf8");

  for (const text of [
    "闭环输出",
    "黑客级输入",
    "为什么做这个产品",
    "用户场景",
    "产品假设",
    "项目演示",
    "AI 工作流",
    "产品创新点",
    "竞品观察",
    "类似产品",
    "差异化定位",
    "智能 NPC 单聊",
    "验收标准",
    "产品路线",
  ]) {
    assert.match(html, new RegExp(text));
  }
});

test("portfolio copy avoids explicit job-hunting framing in visible content", () => {
  const html = fs.readFileSync(portfolioHtmlPath, "utf8");
  const visibleText = html
    .replace(/<script[\s\S]*?<\/script>/g, "")
    .replace(/<style[\s\S]*?<\/style>/g, "")
    .replace(/<[^>]+>/g, " ");

  for (const forbiddenText of ["实习", "求职", "面试官", "作品集案例", "AI 产品经理作品集"]) {
    assert.equal(
      visibleText.includes(forbiddenText),
      false,
      `portfolio visible copy should avoid ${forbiddenText}`,
    );
  }
});

test("portfolio styles define a dedicated case page visual system", () => {
  assert.match(stylesCss, /\.portfolio-shell\s*\{/);
  assert.match(stylesCss, /\.portfolio-hero\s*\{/);
  assert.match(stylesCss, /\.portfolio-evidence-grid/);
  assert.match(stylesCss, /\.portfolio-section\s*\{/);
  assert.match(stylesCss, /\.portfolio-demo-frame\s*\{/);
});
