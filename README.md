# 千岁 · 桌面 AI 伴侣

把《甜蜜女友2》里的茑町千岁请到桌面上来：她站在窗边，会呼吸、会眨眼、会跟着情绪换表情，可以换衣服、换场景，也可以坐下来和你聊两句。

这是一个粉丝向的学习项目，代码本身不含任何游戏资源；立绘、背景和声音素材请在遵守版权的前提下使用（见文末）。

---

## 能做什么

- 桌面窗口里显示千岁，站着会呼吸、会眨眼
- 说话时嘴型跟着声音动，表情跟着情绪变
- 13 套衣服、29 个场景，点右上角「换衣」随便换
- 打字聊天，人设是温柔的大姐姐
- 可选：接上 GPT-SoVITS，用千岁本来的声音说话
- 可选：按住说话（需要额外的语音识别模型）

默认是**静音版**：不用显卡、不用下载几个 G 的模型，装好 Python 就能看、能换装、能打字聊天。

---

## 快速开始（Windows）

### 1. 装 Python

去 [python.org](https://www.python.org/downloads/) 下载 3.10 或更新的版本。

安装时**一定要勾选**「Add Python to PATH」，然后一路下一步。

### 2. 把项目弄到本地

在 GitHub 页面点绿色的 **Code → Download ZIP**，解压到一个文件夹。

会用 git 的话：

```
git clone https://github.com/ISAGI85/chitose.git
```

### 3. 双击 `setup.bat`

它会自动建虚拟环境、装依赖。第一次要几分钟，跑完会停在窗口里。

### 4. 填 `config.json`

`setup.bat` 会帮你从 `config.example.json` 复制一份 `config.json`。

用记事本打开它，把 `brain` 里的三项填好：

- `base_url`：模型服务的地址（写到 `/v1` 这一层）
- `api_key`：你自己的钥匙
- `model`：模型名字

几个常见服务的填法：

**阿里云百炼（有免费额度）**

```
base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
model:    deepseek-v4.1-flash-1017
```

**DeepSeek 官方**

```
base_url: https://api.deepseek.com/v1
model:    deepseek-chat
```

**本机 Ollama（完全免费，但要自己装 Ollama）**

```
base_url: http://127.0.0.1:11434/v1
model:    qwen3
api_key:  留空
```

### 5. 双击 `start.bat`

窗口就弹出来了。第一次打开会按当前时间跟你打个招呼。

---

## 可选一：让她出声

这一步需要 **NVIDIA 显卡**。没有显卡的话跳过，静音版一样能聊。

### 1. 下载 GPT-SoVITS v2Pro

去 [GPT-SoVITS 官方仓库](https://github.com/RVC-Boss/GPT-SoVITS) 下载 **v2Pro** 版本的整合包。

> ⚠ 一定要 v2Pro。v2、v3、v4 的权重格式不一样，加载不了这个声音。

解压到项目的 `tools/` 文件夹里，目录名以 `GPT-SoVITS` 开头就行，比如：

```
tools/GPT-SoVITS-v2pro/
```

### 2. 下载声音包

去本仓库的 **Releases** 页面，下载 `chitose-voice.zip`。

解压后是这样：

```
chitose-voice/
  chitose_e10_s6600.pth     ← SoVITS 权重
  chitose-e9.ckpt           ← GPT 权重
  calm/CC_02_cit_mo_05_003.wav
  cheer/cheer_01.wav
  sfx/                      ← 音效（真笑、叹气那些）
```

### 3. 按位置放好

- 两个权重文件 → `tools/GPT-SoVITS-v2pro/SoVITS_weights_v2Pro/` 和 `GPT_weights_v2Pro/`
- `calm/` 和 `cheer/` → 项目根目录的 `ref_wav/` 下（变成 `ref_wav/calm/...`）
- `sfx/` → 项目根目录的 `out/sfx/`

### 4. 打开声音

把 `config.json` 里的 `voice.enabled` 改成 `true`。

或者直接双击 `start-voice.bat`，它会临时打开声音，不改配置文件。

### 5. 等它起来

第一次要加载模型，一两分钟，黑窗口里能看到进度。之后说话就是千岁本人的声音了。

> 注意：**不要自己拿那两个参考音频去训练**。权重已经是训练好的，直接推理就行；自己训反而会不像。

### 6. 关掉嗓子

窗口关了之后，嗓子和转接头还在后台跑（下次打开更快）。想彻底关掉：

```
venv\Scripts\python.exe -X utf8 scripts\launch_all.py --stop
```

---

## 可选二：按住说话

默认建议打字，打字就够用了，不用折腾这一块。

想按住说话的人，往下看。

### 1. 装耳朵依赖

```
venv\Scripts\python.exe -m pip install -r requirements-ears.txt
```

### 2. 下载语音识别模型

去 Hugging Face 下载 `Systran/faster-whisper-large-v3` 的模型文件（约 2.9GB）。

国内下不动的话，用镜像：`https://hf-mirror.com/Systran/faster-whisper-large-v3`

下载后放进 `tools/whisper/`，要有 `model.bin`、`config.json`、`tokenizer.json` 这些文件。

### 3. 看你的电脑

- 有 NVIDIA 显卡：直接跑，显存留 4G 左右
- 没有显卡：设置环境变量 `CHITOSE_WHISPER_DEVICE=cpu`，慢一点但能用

### 4. 重新打开

`start.bat` 会自己检测到耳朵，「按住说话」按钮就会出现。

---

## 换衣服 / 换场景

点右上角的「换衣」，里面有：

- 衣服：13 套
- 场景：29 张

选过的会记在这台电脑上，下次打开还是它。

---

## 目录说明

```
app/
  server.py         窗口和网页服务
  web/              前端（立绘、字幕、换装面板）
  web/assets/       立绘、背景等素材
scripts/
  launch_all.py     一键启动
  chitose_chat.py   和模型说话、调用声音
  cc_tts_shim.py    GPT-SoVITS 转接头
  sfx.py            心情音效拼接
config.example.json 配置模板
setup.bat           一键安装
start.bat           静音版启动
start-voice.bat     声音版启动
```

---

## 常见问题

**窗口打不开 / 一片黑**

装一下微软的 [WebView2 运行库](https://developer.microsoft.com/microsoft-edge/webview2/)。Windows 11 一般自带，Windows 10 可能要手动装。

**聊天报「没接上话」**

检查 `config.json` 里的 `base_url`、`api_key`、`model` 三项。`base_url` 要写到 `/v1` 这一层，不要带 `/chat/completions`。

**没有声音**

按顺序检查：

1. `config.json` 里 `voice.enabled` 是不是 `true`
2. `tools/` 下的 GPT-SoVITS 是不是 **v2Pro** 版本
3. 两个权重文件放对位置没有
4. 有没有 NVIDIA 显卡

**声音不像千岁**

确认用的是 Releases 里下载的权重，并且 `ref_wav/calm/` 和 `ref_wav/cheer/` 里放的是声音包里的那两条参考音频。不要换成别的音频，也不要自己训练。

**按住说话按钮不见了**

说明耳朵没装好。检查 `requirements-ears.txt` 装了没有、`tools/whisper/` 里有没有模型。只有打字需求的话，可以不管它。

**想加更多音效**

`out/sfx/其它/` 里是没分类的备选音频，默认不会响。

想用的话，自己听一遍，把喜欢的拖进 `out/sfx/轻笑/`、`out/sfx/叹气/` 这些文件夹里，文件名不用改。

---

## 素材与版权

- 角色「茑町千岁」及立绘、背景、语音素材版权归 **《甜蜜女友2》/ ENTERGRAM** 及相关权利方所有
- 本项目的**代码**仅供学习交流，不用于任何商业用途
- Releases 里的声音权重是从游戏语音训练得到的，仅供个人学习，请勿传播、商用或用于其他角色
- 如有侵权，请联系删除

如果你是版权方并希望移除相关素材，请开 issue，我会尽快处理。

---

## 致谢

- [GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS)：声音合成
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)：语音识别
- [pywebview](https://pywebview.flowrl.com/)：桌面窗口
- 以及《甜蜜女友2》原作
