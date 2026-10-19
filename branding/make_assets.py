"""Builds every TEJAS branding asset from branding/src/tejas-logo-original.png.
Run: python3 branding/make_assets.py  (needs pillow + numpy)"""
import os, numpy as np
from PIL import Image
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'branding', 'out'); os.makedirs(OUT, exist_ok=True)
INC = os.path.join(ROOT, 'config', 'includes.chroot')
src = Image.open(os.path.join(ROOT, 'branding', 'src', 'tejas-logo-original.png')).convert('RGB')

def cutout(img):
    a = np.asarray(img).astype(np.float32) / 255.0
    bg = a[2:6, 2:6].reshape(-1, 3).mean(0)
    diff = np.max(np.abs(a - bg), axis=2)
    alpha = np.clip((diff - 0.015) / 0.09, 0, 1)
    return Image.fromarray((np.dstack([a, alpha]) * 255).round().astype('uint8'), 'RGBA')

def square(im, margin=0.08):
    w, h = im.size; s = int(max(w, h) * (1 + 2 * margin))
    c = Image.new('RGBA', (s, s), (0, 0, 0, 0)); c.paste(im, ((s - w) // 2, (s - h) // 2), im); return c

mark = cutout(src.crop((206, 210, 1049, 855)))
word = cutout(src.crop((133, 875, 1118, 1017)))
full = cutout(src.crop((120, 200, 1134, 1105)))
mark.save(f'{OUT}/tejas-mark.png'); word.save(f'{OUT}/tejas-wordmark.png'); full.save(f'{OUT}/tejas-logo-full.png')
w = np.asarray(word).copy(); w[..., :3] = 255
Image.fromarray(w, 'RGBA').save(f'{OUT}/tejas-wordmark-white.png')

# app-menu / system icons
sq = square(mark)
for s in (16, 22, 24, 32, 48, 64, 128, 256, 512):
    d = f'{INC}/usr/share/icons/hicolor/{s}x{s}/apps'; os.makedirs(d, exist_ok=True)
    sq.resize((s, s), Image.LANCZOS).save(f'{d}/tejas-logo.png')

# boot splash logo (mark + white wordmark, for a dark screen)
m = mark.resize((int(mark.width * .5), int(mark.height * .5)), Image.LANCZOS)
ww = Image.open(f'{OUT}/tejas-wordmark-white.png'); ww = ww.resize((int(ww.width * .42), int(ww.height * .42)), Image.LANCZOS)
W = max(m.width, ww.width) + 40; H = m.height + ww.height + 60
pl = Image.new('RGBA', (W, H), (0, 0, 0, 0)); pl.paste(m, ((W - m.width) // 2, 0), m); pl.paste(ww, ((W - ww.width) // 2, m.height + 50), ww)
d = f'{INC}/usr/share/tejas/branding'; os.makedirs(d, exist_ok=True)
pl.save(f'{d}/plymouth-logo.png')
sq.resize((256, 256), Image.LANCZOS).save(f'{d}/logo-256.png')
full.resize((int(full.width * .6), int(full.height * .6)), Image.LANCZOS).save(f'{d}/logo-full.png')

# wallpapers
Wd, Hd = 3840, 2160
yy, xx = np.mgrid[0:Hd, 0:Wd].astype(np.float32)
hexc = lambda h: np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)], np.float32)
def sky(top, bot, blooms):
    t = (yy / Hd)[..., None]; img = hexc(top) * (1 - t) + hexc(bot) * t
    for cx, cy, rx, ry, col in blooms:
        dd = np.sqrt(((xx - cx * Wd) / (rx * Wd)) ** 2 + ((yy - cy * Hd) / (ry * Hd)) ** 2)
        a = np.clip(1 - dd / .7, 0, 1)[..., None] ** 1.6; img = img * (1 - a) + hexc(col) * a
    return img
def sphere(img, cx, cy, r):
    dd = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    t = np.clip(np.sqrt((xx - (cx - .4 * r)) ** 2 + (yy - (cy - .5 * r)) ** 2) / (1.6 * r), 0, 1)[..., None]
    col = np.where(t < .35, hexc('#ffffff') * (1 - t / .35) + hexc('#5aa9ff') * (t / .35),
                   hexc('#5aa9ff') * (1 - (t - .35) / .65) + hexc('#0b4fb8') * ((t - .35) / .65))
    ds = np.sqrt((xx - cx) ** 2 + ((yy - (cy + r * 1.05)) / .25) ** 2)
    sh = np.clip(1 - ds / (r * .9), 0, 1)[..., None] ** 2 * .18
    img = img * (1 - sh) + hexc('#2a5a9a') * sh
    e = np.clip((r - dd) / 2.5, 0, 1)[..., None]; return img * (1 - e) + col * e
SKIES = {
 'Morning': ('#cfe6fb', '#eaf5ff', [(.15, .1, .6, .4, '#ffffff'), (.9, .3, .5, .45, '#7fb4ec'), (.4, 1, .6, .5, '#a9d0f5')]),
 'Noon':    ('#9ecbf7', '#dff0ff', [(.8, .05, .5, .4, '#ffffff'), (.1, .6, .55, .5, '#4f9cf0'), (.7, 1, .6, .5, '#7fc0ff')]),
 'Dusk':    ('#d9d6fb', '#f4ecff', [(.2, .15, .55, .4, '#ffffff'), (.85, .25, .5, .45, '#b9a8f2'), (.3, 1, .6, .5, '#f6c6d8')]),
 'Mint':    ('#cdf1ea', '#eefaff', [(.15, .1, .6, .4, '#ffffff'), (.85, .3, .5, .45, '#7fdcc4'), (.4, 1, .6, .5, '#a9d0f5')]),
}
bigmark = mark.resize((int(mark.width * 1.45), int(mark.height * 1.45)), Image.LANCZOS)
for name, (top, bot, bl) in SKIES.items():
    img = sphere(sky(top, bot, bl), Wd * .13, Hd * .78, 190)
    out = Image.fromarray(np.clip(img, 0, 255).astype('uint8'), 'RGB').convert('RGBA')
    out.alpha_composite(bigmark, (int(Wd * .61), int(Hd * .27))); out = out.convert('RGB')
    base = f'{INC}/usr/share/wallpapers/TEJAS-{name}'; os.makedirs(f'{base}/contents/images', exist_ok=True)
    for (a, b) in ((3840, 2160), (2560, 1440), (1920, 1080)):
        out.resize((a, b), Image.LANCZOS).save(f'{base}/contents/images/{a}x{b}.png', optimize=True)
    out.resize((480, 270), Image.LANCZOS).save(f'{base}/contents/screenshot.png')
    with open(f'{base}/metadata.json', 'w') as f:
        f.write('{\n  "KPlugin": {\n    "Id": "TEJAS-%s",\n    "Name": "TEJAS %s",\n    "Authors": [{"Name": "JK Design"}],\n    "License": "CC-BY-SA-4.0"\n  }\n}\n' % (name, name))
print('assets done')
