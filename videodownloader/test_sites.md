# 测试网站列表
# 用于音视频下载功能测试

## 已验证可用的网站

### Bilibili (哔哩哔哩)
- https://www.bilibili.com/video/BV1GJ411x7h7
  - 通过 yt-dlp 下载
  - 支持最高画质 / 1080p / 720p 等画质选择
  - 支持音频提取 (mp3/flac/wav 等格式)
  - 支持 `--cookie-file` 下载大会员视频
  - 支持字幕下载 (`--subtitle`)

### YouTube
- https://www.youtube.com/watch?v=dQw4w9WgXcQ
  - 通过 yt-dlp 下载
  - 支持最高画质 (需要 ffmpeg 合并音视频流)
  - 支持音频提取
  - 支持自动字幕和手动字幕下载
  - 支持缩略图下载
  - 某些视频需要代理 (`--proxy`)

### 抖音 (Douyin)
- https://v.douyin.com/OKWd6BfV5MA/ (短链接，自动解析)
- https://www.douyin.com/video/7620404072419577134 (视频页直链)
  - 使用内置抖音专用下载器 (无水印)
  - 短链接 v.douyin.com 自动解析重定向
  - 通过 iesdouyin.com 获取视频数据
  - 无水印视频通过 play_addr.uri + /aweme/v1/play/ 构造
  - 支持 video/audio/info 三种模式
  - 需要登录的视频需提供 `--cookie-file`
  - 注意：用户主页链接 (user/self) 不支持批量下载

### Twitter/X
- https://x.com/i/status/2042831963380138290
  - 通过 yt-dlp 下载
  - 可能需要登录 Cookie
  - 可能需要代理

### MacCMS 视频站 (苹果CMS)
- https://kanav.ad/index.php/vod/play/id/107201/sid/1/nid/1.html
- https://91md.me/index.php/vod/play/id/33062/sid/1/nid/1.html
  - 使用内置 MacCMS 专用解析器
  - 自动检测 MacCMS 站点 URL 模式 (`/vod/play/` 等)
  - 支持 `player_aaaa` 变量解析，encrypt 0/1/2 三种加密级别
  - 自有 m3u8 下载器（保持 session cookies 绕过 Cloudflare）
  - 降级策略：自有下载器 → yt-dlp → ffmpeg
  - 注意：Referer 必须带末尾斜杠（如 `https://kanav.ad/`）
  - 适用于所有基于 MacCMS 模板的视频站

### RouVideo
- https://rou.video/v/cl5u28gi6007112f20wdkcz61
  - 使用内置 RouVideo 专用解析器
  - 自动检测 rou.video 域名
  - 从 `__NEXT_DATA__` 提取加密数据 (`ev.d` + `ev.k`)，解密算法：base64 解码 → 每字节减 `k` → JSON 解析
  - 解密后得到伪装为 .jpg 后缀的 m3u8 URL，通过 HLS 下载 TS 分片并合并为 MP4
  - 支持 video/audio/info 三种模式
  - 不需要登录即可下载
