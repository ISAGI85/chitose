r"""把「补头顶」的活交给 ComfyUI，用千岁本人的 LoRA 画。

用 Illustrious 当底，叠两个 LoRA：
    Chitose_2plus_ilxl    —— 千岁本人
    Amakano2_style        —— 甜蜜女友的画风

用法：
    python head_fix_run.py            # 默认强度
    python head_fix_run.py --denoise 0.85 --seed 123
产出：
    D:/chitose/out/headfix/out_*.png
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import uuid

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

HOST = 'http://127.0.0.1:8188'
D = r'D:/chitose/out/headfix'

POS = ('hair, top of head, crown of head, forehead hair, '
       'amakano2, masterpiece, best quality, amazing quality, very aesthetic, '
       'absurdres, soft lighting, light brown hair, pinkish hair')
NEG = ('background, scenery, sky, face, eyes, mouth, body, '
       'bad quality, worst quality, lowres, blurry, jpeg artifacts, '
       'sketch, extra hair, messy, cut off')


def post(path, payload):
    req = urllib.request.Request(
        HOST + path, data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json'})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def get(path):
    return json.loads(urllib.request.urlopen(HOST + path, timeout=60).read())


def build(ckpt, loras, denoise, seed, steps):
    wf = {}
    n = [0]

    def add(cls, inputs):
        n[0] += 1
        k = str(n[0])
        wf[k] = {'class_type': cls, 'inputs': inputs}
        return k

    img = add('LoadImage', {'image': 'input.png', 'upload': 'image'})
    msk = add('LoadImage', {'image': 'mask.png', 'upload': 'image'})
    m = add('ImageToMask', {'image': [msk, 0], 'channel': 'red'})

    ck = add('CheckpointLoaderSimple', {'ckpt_name': ckpt})
    model, clip, vae = [ck, 0], [ck, 1], [ck, 2]
    for name, strength in loras:
        model = add('LoraLoader', {'model': model, 'clip': clip,
                                   'lora_name': name, 'strength_model': strength,
                                   'strength_clip': strength})
        clip = [model, 1]
        model = [model, 0]

    pos = add('CLIPTextEncode', {'clip': clip, 'text': POS})
    neg = add('CLIPTextEncode', {'clip': clip, 'text': NEG})
    enc = add('VAEEncodeForInpaint', {'pixels': [img, 0], 'vae': vae,
                                      'mask': [m, 0], 'grow_mask_by': 12})
    ks = add('KSampler', {'model': model, 'positive': [pos, 0],
                          'negative': [neg, 0], 'latent_image': [enc, 0],
                          'seed': seed, 'steps': steps,
                          'cfg': 5.5, 'sampler_name': 'dpmpp_2m_sde',
                          'scheduler': 'karras', 'denoise': denoise})
    dec = add('VAEDecode', {'samples': [ks, 0], 'vae': vae})
    add('SaveImage', {'images': [dec, 0], 'filename_prefix': 'headfix'})
    return wf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ckpt', default='Illustrious-XL-v2.0.safetensors')
    ap.add_argument('--denoise', type=float, default=0.78)
    ap.add_argument('--steps', type=int, default=30)
    ap.add_argument('--seed', type=int, default=None)
    ap.add_argument('--loras', default=('Chitose_2plus_ilxl.safetensors:0.85,'
                                        'Amakano2_style_AzarashiSoft.safetensors:0.55'))
    args = ap.parse_args()

    loras = []
    for part in args.loras.split(','):
        if ':' in part:
            nm, s = part.rsplit(':', 1)
            loras.append((nm, float(s)))
        else:
            loras.append((part, 1.0))
    seed = args.seed if args.seed is not None else int(time.time()) % 2 ** 31

    print('模型 %s' % args.ckpt)
    print('LoRA %s' % loras)
    print('强度 %.2f  步数 %d  种子 %d' % (args.denoise, args.steps, seed))

    wf = build(args.ckpt, loras, args.denoise, seed, args.steps)
    cid = str(uuid.uuid4())
    r = post('/prompt', {'prompt': wf, 'client_id': cid})
    pid = r['prompt_id']
    print('已提交 %s，等它画…' % pid)

    t0 = time.time()
    while time.time() - t0 < 900:
        h = get('/history/%s' % pid)
        if pid in h:
            outs = h[pid].get('outputs', {})
            files = []
            for node in outs.values():
                for im in node.get('images', []):
                    files.append(im)
            print('画完了，用了 %.0f 秒' % (time.time() - t0))
            import shutil
            for im in files:
                src = os.path.join(
                    r'D:/Comfy-Desktop/ComfyUI-Shared', 'output',
                    im.get('subfolder', ''), im['filename'])
                # ComfyUI 的输出目录可能不在共享目录，两个都找一下
                for base in (r'D:/Comfy-Desktop/ComfyUI-Shared/output',
                             r'D:/Comfy-Desktop/ComfyUI-Installs/ComfyUI/ComfyUI/output'):
                    p = os.path.join(base, im.get('subfolder', ''), im['filename'])
                    if os.path.exists(p):
                        dst = os.path.join(D, 'out_%d_%s' % (seed, im['filename']))
                        shutil.copy(p, dst)
                        print('  ->', dst)
                        break
                else:
                    print('  找不到输出文件', im['filename'])
            return
        time.sleep(2)
    print('等太久了，可能卡住了')


if __name__ == '__main__':
    main()
