# AGENTS.md

给 AI 编程助手的部署说明。人类用户请看 [README.md](README.md)。

## 这个项目是什么

一个 Windows 桌面 AI 伴侣窗口：Electron 风格的网页界面（pywebview + FastAPI），角色立绘来自《甜蜜女友2》。
默认**静音**——只显示立绘、换装、打字聊天。声音和语音输入都是可选件。

## 目录结构

```
app/server.py             FastAPI + pywebview 窗口
app/web/                  前端（index.html / app.js / style.css / gaze.js）
app/web/assets/           立绘、背景、layers.json、rooms.json
scripts/launch_all.py     启动入口（--ui / --text / --stop）
scripts/chitose_chat.py   模型调用、人设、TTS 调用
scripts/cc_tts_shim.py    GPT-SoVITS 转接头（9882 → 9881）
scripts/sfx.py            心情音效拼接（out/sfx）
config.example.json       配置模板
requirements.txt          核心依赖
requirements-ears.txt     可选：按住说话
```

## 部署步骤（Windows）

1. 确认 `python --version` 是 3.10+。
2. 运行 `setup.bat`，或手动：
   ```
   py -3 -m venv venv
   venv\Scripts\python.exe -m pip install -r requirements.txt
   ```
3. 复制配置：
   ```
   copy config.example.json config.json
   ```
4. 编辑 `config.json`，至少填 `brain`：
   ```json
   {
     "brain": {
       "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
       "api_key": "<用户自己的钥匙>",
       "model": "deepseek-v4.1-flash-1017"
     },
     "voice": { "enabled": false }
   }
   ```
   `base_url` 写到 `/v1` 这一层即可；代码会自动补 `/chat/completions`。
5. 双击 `start.bat` 验证窗口能打开、能打字聊天。

## 可选：声音

1. 下载 GPT-SoVITS **v2Pro** 整合包，解压到 `tools/` 下（目录名以 `GPT-SoVITS` 开头）。
2. 从仓库 Releases 下载 `chitose-voice.zip`，按 README 放：
   - 权重 → `SoVITS_weights_v2Pro/`、`GPT_weights_v2Pro/`
   - 参考音频 → `ref_wav/calm/`、`ref_wav/cheer/`
   - 音效 → `out/sfx/`
3. 把 `config.json` 的 `voice.enabled` 改成 `true`，或运行 `start-voice.bat`。
4. 需要 NVIDIA 显卡。

## 可选：按住说话

1. `venv\Scripts\python.exe -m pip install -r requirements-ears.txt`
2. 下载 `Systran/faster-whisper-large-v3` 到 `tools/whisper/`（约 2.9GB）。
3. 没有 NVIDIA 显卡时设置 `CHITOSE_WHISPER_DEVICE=cpu`。

## 不要做的事

- **不要自己训练声音权重。** Releases 里的权重已经训练好，直接推理；用参考音频重新训练会得到完全不同的声音。
- **不要提交 `config.json`。** 里面有用户的 API key，`.gitignore` 已经排除。
- **不要上传 `app/web/assets/voice/`。** 那是作者本人的预合成问候声，`.gitignore` 已排除。
- **不要改参考音频。** `ref_wav/calm/` 和 `ref_wav/cheer/` 必须用声音包里那两条，换成别人的音频会改变音色。
- 声音权重只配 **v2Pro** 本体；v2/v3/v4 格式不兼容。

## 验证清单

- `curl http://127.0.0.1:9890/api/status` 返回 `{"brain": true, ...}`
- 窗口打开后显示按钟点的文字问候
- 在输入框打字回车，字幕板出现回复
- `python scripts/launch_all.py --stop` 能关掉后台服务

## 平台

只在 Windows 上验证过。`setup.bat` / `start*.bat` 是 cmd 脚本；其他平台需要手动建 venv 并运行 `python scripts/launch_all.py --ui`。
