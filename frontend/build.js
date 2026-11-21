// Vercel 빌드 스크립트 (프레임워크 없이 Node 기본 모듈만 사용)
// 1) 정적 파일을 dist/로 복사  2) 환경 변수 API_BASE_URL로 dist/config.js 생성
const fs = require("fs");
const path = require("path");

const out = path.join(__dirname, "dist");
fs.rmSync(out, { recursive: true, force: true });
fs.mkdirSync(out);

for (const file of ["index.html", "style.css", "app.js"]) {
  fs.copyFileSync(path.join(__dirname, file), path.join(out, file));
}

const apiBase = (process.env.API_BASE_URL || "").trim().replace(/\/+$/, "");
if (!apiBase) {
  console.error("❌ 환경 변수 API_BASE_URL이 없습니다. Vercel 프로젝트 Settings → Environment Variables에서 설정하세요.");
  process.exit(1);
}
fs.writeFileSync(
  path.join(out, "config.js"),
  `window.APP_CONFIG = ${JSON.stringify({ API_BASE_URL: apiBase })};\n`
);
console.log(`✅ build complete → dist/ (API_BASE_URL=${apiBase})`);
