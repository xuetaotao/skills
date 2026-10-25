# 测试网站列表
# 用于音视频下载功能测试（最近一次验证：2026-10-25，yt-dlp 2026.10.21）

## Bilibili
- https://www.bilibili.com/video/BV1GJ411x7h7
  - yt-dlp 下载；旧版 yt-dlp 会报 HTTP 412，升级后正常
  - 画质选择、音频提取、字幕 (`--subtitle`)，大会员视频需要 `--cookie-file`

## YouTube
- https://www.youtube.com/watch?v=dQw4w9WgXcQ
  - yt-dlp 下载；`-q 360` 实测视频 + 音频分别下载后合并为 mp4（8.7 MB）
  - 需要 JavaScript 运行时（deno / node / bun 任一），程序已同时启用三者，本机有 Node.js 即可
  - 依赖 `yt-dlp[default]`（带 yt-dlp-ejs），否则提示 “No supported JavaScript runtime”

## 抖音
- https://www.douyin.com/video/7697068086607813297（可用样例，2026-10 验证）
  - video 模式：无水印 mp4（78.5 MB）
  - audio 模式：作品没有 music.play_url，自动用 ffmpeg 从视频提取音轨（aac，313 秒）
- https://www.douyin.com/video/7620404072419577134（已失效：作品被删除）
  - 日志会显示 “抖音提示: 抱歉，作品不见了”
- 要点
  - 请求分享页前必须先 GET https://www.iesdouyin.com/ 拿到 `__ac_nonce` / `ttwid` Cookie，否则页面里没有 `videoInfoRes`
  - 短链 v.douyin.com 逐跳解析重定向
  - 无水印地址由 play_addr.uri + /aweme/v1/play/ 构造
  - 部分短剧视频平台限制外部访问，会 404
  - 用户主页链接不支持批量下载

## Twitter/X
- https://x.com/i/status/2042831963380138290
  - yt-dlp 解析正常（http / hls 共 8 种格式，最高 1080p），无需 Cookie

## MacCMS 视频站
- https://kanav.ad/index.php/vod/play/id/107201/sid/1/nid/1.html（encrypt=2，dplayer，186 个分片）
- https://91md.me/index.php/vod/play/id/33062/sid/1/nid/1.html（encrypt=0，mahua，418 个分片）
  - 解析 `player_aaaa`，支持 encrypt 0/1/2
  - 自有 m3u8 下载器抽查分片均为合法 TS
  - 降级：自有下载器 → yt-dlp → ffmpeg
  - Referer 必须是带末尾斜杠的站点根地址（如 `https://kanav.ad/`）

## RouVideo
- https://rou.video/v/cl5u28gi6007112f20wdkcz61（181 个分片，约 9 MB/s）
  - 2026-10 改版：页面从 Next.js 换成 TanStack Start，数据不再在 `__NEXT_DATA__` 里，而是 seroval 序列化的 `$R[n]={video:{...},ev:{d,k}}`
  - `ev` 解密不变：base64 解码 → 每字节减 `k` → JSON，得到相对地址 `/api/hls/{id}`
  - `/api/hls/{id}` 302 到 CDN 的 `index.png`：m3u8 和每个分片都包在 PNG 里，数据在自定义块 `roUd` 中，块内首字节 bit0=1 表示其余内容经 zlib 压缩
  - 因为是 PNG 外壳，yt-dlp / ffmpeg 兜底无法处理，只能靠自有下载器（`unwrap_png`）
  - 不需要登录
