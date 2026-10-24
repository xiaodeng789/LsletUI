from PIL import Image, ImageDraw
import os

base = os.path.dirname(os.path.abspath(__file__))
ico_path = os.path.join(base, "img", "default_icon.ico")

# 根据 SVG 设计绘制图标 (圆形 + 十字线)
sizes = [256, 128, 64, 48, 32, 16]
images = []
for size in sizes:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # 外圆
    r = size * 0.45
    cx, cy = size // 2, size // 2
    draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=(74, 144, 226, 230))
    # 内圆
    r2 = size * 0.35
    draw.ellipse([cx-r2, cy-r2, cx+r2, cy+r2], fill=(53, 122, 189, 204))
    # 中心点
    r3 = size * 0.15
    draw.ellipse([cx-r3, cy-r3, cx+r3, cy+r3], fill=(255, 255, 255, 230))
    # 十字线
    lw = max(1, size // 64)
    draw.line([(cx, cy-r*0.5), (cx, cy+r*0.5)], fill=(255, 255, 255, 153), width=lw)
    draw.line([(cx-r*0.5, cy), (cx+r*0.5, cy)], fill=(255, 255, 255, 153), width=lw)
    images.append(img)

images[0].save(ico_path, format="ICO", sizes=[(s, s) for s in sizes], append_images=images[1:])
print(f"Created: {ico_path}")