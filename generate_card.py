#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Генератор карточки тыквы из профиля ИТД (кнопка 'Скопировать').
Использует оригинальные ассеты с CDN:
- courtyard.webp (оригинальный фон двора/замка)
- pumpkin-body.webp (оригинальное тело тыквы)
- шрифт Pangolin
- Полноценное свечение фонаря от glow (0..5), окутывающее всю тыкву
- Настоящие эмодзи и аккуратный блок статистики
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

# Константы оригинального Canvas из исходников фронтенда
CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1350
PUMPKIN_SIZE = 860
TOP_OFFSET = 150

SCRIPT_DIR = Path(__file__).resolve().parent

PANGOLIN_FONT_PATH = SCRIPT_DIR / "pangolin.ttf"
COURTYARD_PATH = SCRIPT_DIR / "courtyard.webp"
PUMPKIN_BODY_PATH = SCRIPT_DIR / "pumpkin-body.webp"
FALLBACK_PUMPKIN_PATH = SCRIPT_DIR / "pumpkin.png"
DB_PATH = SCRIPT_DIR / "all_pumpkins.json"

# Кроссплатформенный поиск шрифта эмодзи (локальный в папке, Windows Segoe UI Emoji, macOS Apple Color Emoji, Linux Noto)
EMOJI_FONT_CANDIDATES = [
    SCRIPT_DIR / "noto-color-emoji.ttf",
    SCRIPT_DIR / "NotoColorEmoji.ttf",
    # Windows
    Path("C:/Windows/Fonts/seguiemj.ttf"),
    Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "seguiemj.ttf",
    # macOS
    Path("/System/Library/Fonts/Apple Color Emoji.ttc"),
    Path("/Library/Fonts/Apple Color Emoji.ttc"),
    # Linux
    Path("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"),
    Path("/usr/share/fonts/noto/NotoColorEmoji.ttf"),
]


def resolve_emoji_font() -> Optional[Path]:
    for p in EMOJI_FONT_CANDIDATES:
        try:
            if p.exists():
                return p
        except Exception:
            pass
    return None


def render_pumpkin_card(
    user_record: Dict[str, Any],
    output_path: Path,
) -> Path:
    St = CANVAS_WIDTH
    Io = CANVAS_HEIGHT
    gs = PUMPKIN_SIZE
    qn = TOP_OFFSET

    u = (St - gs) // 2   # 110
    d = gs / 100.0       # 8.6

    pumpkin_data = user_record.get("pumpkin", {})
    contours = pumpkin_data.get("contours", [])
    glow_level = pumpkin_data.get("glow", 0)
    thanks_count = pumpkin_data.get("thanks", 0)

    # 1. ЗАДНИК: оригинальный courtyard.webp (center crop)
    canvas = Image.new("RGBA", (St, Io), (14, 10, 20, 255))
    if COURTYARD_PATH.exists():
        cw = Image.open(COURTYARD_PATH).convert("RGBA")
        # c = Math.max(St / o.width, Io / o.height)
        c_scale = max(St / cw.width, Io / cw.height)
        nw = int(cw.width * c_scale)
        nh = int(cw.height * c_scale)
        cw_resized = cw.resize((nw, nh), Image.Resampling.LANCZOS)
        x_off = (St - nw) // 2
        y_off = (Io - nh) // 2
        canvas.paste(cw_resized, (x_off, y_off))
    else:
        # Резервный ночной градиент
        grad = Image.new("RGBA", (St, Io), (0, 0, 0, 0))
        g_draw = ImageDraw.Draw(grad)
        for y in range(Io):
            ratio = y / Io
            g_draw.line([(0, y), (St, y)], fill=(int(20*(1-ratio)+10*ratio), int(16*(1-ratio)+8*ratio), int(32*(1-ratio)+16*ratio), 255))
        canvas = Image.alpha_composite(canvas, grad)

    # Вуаль: rgba(14, 10, 20, 0.62)
    veil = Image.new("RGBA", (St, Io), (14, 10, 20, int(255 * 0.62)))
    canvas = Image.alpha_composite(canvas, veil)

    # Радиальный градиент свечения позади тыквы (r.createRadialGradient)
    glow_bg = Image.new("RGBA", (St, Io), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_bg)
    cx, cy = St // 2, qn + 500
    max_r = 620
    for radius in range(max_r, 40, -12):
        t = (radius - 40) / (max_r - 40)
        alpha = int((1 - t) * (255 * 0.35))
        glow_draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=(255, 150, 40, alpha))
    glow_bg = glow_bg.filter(ImageFilter.GaussianBlur(25))
    canvas = Image.alpha_composite(canvas, glow_bg)

    # 2. ТЫКВА (оригинальное тело)
    body_path = PUMPKIN_BODY_PATH if PUMPKIN_BODY_PATH.exists() else FALLBACK_PUMPKIN_PATH
    pumpkin_body = Image.open(body_path).convert("RGBA").resize((gs, gs), Image.Resampling.LANCZOS)
    pumpkin_layer = Image.new("RGBA", (St, Io), (0, 0, 0, 0))
    pumpkin_layer.paste(pumpkin_body, (u, qn), mask=pumpkin_body)

    # Контуры выреза
    canvas_polygons = []
    for c in contours:
        if len(c) >= 2:
            poly = [(u + (pt[0] / 10.0) * d, qn + (pt[1] / 10.0) * d) for pt in c]
            canvas_polygons.append(poly)

    # 3. ЭЛЛИПТИЧЕСКАЯ МАСКА ЛИЦА ТЫКВЫ:
    # r.ellipse(u + 50*d, qn + 58*d, 33.5*d, 27.5*d)
    clip_mask = Image.new("L", (St, Io), 0)
    mask_draw = ImageDraw.Draw(clip_mask)
    ex = u + 50 * d
    ey = qn + 58 * d
    rx = 33.5 * d
    ry = 27.5 * d
    mask_draw.ellipse([ex - rx, ey - ry, ex + rx, ey + ry], fill=255)

    # 4. ВЫРЕЗЫ ЛИЦА ТЫКВЫ (Оригинальные цвета: fill=#ffd35a, stroke=#5a2410)
    carve_sharp = Image.new("RGBA", (St, Io), (0, 0, 0, 0))
    cs_draw = ImageDraw.Draw(carve_sharp)
    for poly in canvas_polygons:
        closed = poly + ([poly[0]] if len(poly) >= 3 else [])
        if len(poly) >= 3:
            cs_draw.polygon(poly, fill="#ffd35a")
        cs_draw.line(closed, fill="#5a2410", width=int(1.1 * d), joint="curve")

    # Применяем эллиптический клип к вырезу
    carve_face = Image.new("RGBA", (St, Io), (0, 0, 0, 0))
    carve_face.paste(carve_sharp, (0, 0), mask=clip_mask)

    # Собираем композит тыквы с лицом
    pumpkin_composite = Image.alpha_composite(pumpkin_layer, carve_face)

    # 5. ТОЧНЫЙ ЭФФЕКТ СВЕЧЕНИЯ ИЗ ИСХОДНИКА САЙТА (функция Ik):
    # drop-shadow(0 0 N px rgba(255, 160, 50, alpha)) brightness(1 + e*0.05)
    # Делаем радиус и плотность чуть умереннее, чтобы свечение было аккуратным и чистым
    drop_radius = int((2.5 + glow_level * 1.6) * d)
    drop_alpha = min(0.85, 0.35 + glow_level * 0.08)

    # Аура свечения всей тыквы (drop-shadow по силуэту)
    alpha_silh = pumpkin_composite.getchannel("A")
    glow_color_block = Image.new("RGBA", (St, Io), (255, 160, 50, int(255 * drop_alpha)))
    pumpkin_glow_base = Image.new("RGBA", (St, Io), (0, 0, 0, 0))
    pumpkin_glow_base.paste(glow_color_block, (0, 0), mask=alpha_silh)
    pumpkin_drop_shadow = pumpkin_glow_base.filter(ImageFilter.GaussianBlur(drop_radius // 2))

    # СВЕЧЕНИЕ САМОГО ВЫРЕЗА ИЗНУТРИ (подсветка контуров и вырезов пламенем)
    carve_alpha = carve_face.getchannel("A")
    flame_color = Image.new("RGBA", (St, Io), (255, 215, 80, 190))
    carve_glow_base = Image.new("RGBA", (St, Io), (0, 0, 0, 0))
    carve_glow_base.paste(flame_color, (0, 0), mask=carve_alpha)
    carve_fire_glow = carve_glow_base.filter(ImageFilter.GaussianBlur(int(1.6 * d)))

    # Увеличиваем яркость всей тыквы пропорционально glow (brightness(1 + e * 0.05))
    enhancer = ImageEnhance.Brightness(pumpkin_composite)
    pumpkin_brightened = enhancer.enhance(1.0 + glow_level * 0.04)

    # Композитинг тыквы на холст:
    # 1. Внешний drop-shadow (светится ВСЯ тыква наружу)
    canvas = Image.alpha_composite(canvas, pumpkin_drop_shadow)
    # 2. Сама тыква
    canvas = Image.alpha_composite(canvas, pumpkin_brightened)
    # 3. Раскаленное свечение контуров и вырезов (светятся изнутри наружу)
    canvas = Image.alpha_composite(canvas, carve_fire_glow)

    # 6. ТЕКСТОВЫЙ БЛОК
    draw = ImageDraw.Draw(canvas)

    font_name = ImageFont.truetype(str(PANGOLIN_FONT_PATH), 64)
    font_user = ImageFont.truetype(str(PANGOLIN_FONT_PATH), 40)
    font_foot = ImageFont.truetype(str(PANGOLIN_FONT_PATH), 38)

    y_base = qn + gs + 60   # 1070
    dname = user_record.get("displayName") or user_record.get("username") or ""
    if len(dname) > 24:
        dname = dname[:23] + "…"
    username = user_record.get("username")
    avatar = user_record.get("avatar")

    has_avatar = bool(avatar and not avatar.startswith("http"))
    name_bbox = draw.textbbox((0, 0), dname, font=font_name)
    name_w = name_bbox[2] - name_bbox[0]

    total_w = (112 if has_avatar else 0) + name_w
    start_x = (St - total_w) // 2

    if has_avatar:
        ava_cx = start_x + 44
        ava_cy = y_base
        # Круг аватара #1f1c26 (радиус 44)
        draw.ellipse([ava_cx - 44, ava_cy - 44, ava_cx + 44, ava_cy + 44], fill="#1f1c26")

        rendered_emoji = False
        emoji_font_path = resolve_emoji_font()

        if emoji_font_path:
            # Разные шрифты эмодзи поддерживают разные размеры/страйки
            for test_size in [109, 64, 48, 52]:
                try:
                    e_font = ImageFont.truetype(str(emoji_font_path), test_size)
                    box_dim = int(test_size * 1.3)
                    emoji_img = Image.new("RGBA", (box_dim, box_dim), (0, 0, 0, 0))
                    e_draw = ImageDraw.Draw(emoji_img)
                    e_draw.text((box_dim // 2, box_dim // 2), avatar, font=e_font, embedded_color=True, anchor="mm")
                    emoji_scaled = emoji_img.resize((56, 56), Image.Resampling.LANCZOS)
                    canvas.paste(emoji_scaled, (ava_cx - 28, ava_cy - 28), mask=emoji_scaled)
                    rendered_emoji = True
                    break
                except Exception:
                    continue

        if not rendered_emoji:
            try:
                fallback_font = ImageFont.truetype(str(PANGOLIN_FONT_PATH), 52)
                draw.text((ava_cx, ava_cy), avatar, font=fallback_font, fill="#ffffff", anchor="mm")
            except Exception:
                draw.text((ava_cx, ava_cy), avatar, fill="#ffffff", anchor="mm")

        text_x = start_x + 112
    else:
        text_x = start_x

    # Имя пользователя
    draw.text((text_x, y_base), dname, font=font_name, fill="#f4efe6", anchor="lm")

    # Юзернейм
    if username:
        draw.text((St // 2, y_base + 66), f"@{username}", font=font_user, fill="#a49dae", anchor="mm")

    # Статистика: правильное склонение
    def plural_people(n: int) -> str:
        if n % 10 == 1 and n % 100 != 11:
            return f"{n} человека"
        return f"{n} человек"

    stats_y = y_base + 128
    font_stats = ImageFont.truetype(str(PANGOLIN_FONT_PATH), 32)
    stats_text = f"Спасибо от {plural_people(thanks_count)}  •  Уровень фонаря: {glow_level}/5"

    bbox = draw.textbbox((0, 0), stats_text, font=font_stats)
    tw = bbox[2] - bbox[0]
    badge_w = tw + 48
    badge_h = 46
    bx1 = (St - badge_w) // 2
    by1 = stats_y - 23
    bx2 = bx1 + badge_w
    by2 = by1 + badge_h

    # Полупрозрачная плашка под статистику
    badge_layer = Image.new("RGBA", (St, Io), (0, 0, 0, 0))
    b_draw = ImageDraw.Draw(badge_layer)
    b_draw.rounded_rectangle([bx1, by1, bx2, by2], radius=23, fill=(30, 24, 40, 190), outline=(255, 177, 74, 90), width=1)
    canvas = Image.alpha_composite(canvas, badge_layer)
    draw = ImageDraw.Draw(canvas)

    draw.text((St // 2, stats_y), stats_text, font=font_stats, fill="#ffd38a", anchor="mm")

    # Нижняя надпись
    draw.text((St // 2, Io - 50), "Тыква с Хеллоуина в ИТД", font=font_foot, fill="#ffb14a", anchor="mm")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, format="PNG")
    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Генерация карточки тыквы пользователя (в стиле 'Скопировать' из ИТД)."
    )
    parser.add_argument("user", nargs="?", help="Username или порядковый индекс в базе", default=None)
    parser.add_argument("-o", "--output", help="Выходной PNG файл", default=None)
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"[!] База данных {DB_PATH} не найдена!")
        sys.exit(1)

    with open(DB_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    user_query = args.user
    if not user_query:
        user_query = input("Введите username (например zpvlc) или номер в базе: ").strip()

    if not user_query:
        print("[!] Не указан пользователь.")
        sys.exit(1)

    selected_user = None
    if user_query.isdigit():
        idx = int(user_query)
        if 0 <= idx < len(data):
            selected_user = data[idx]
    else:
        clean_q = user_query.lstrip("@").lower()
        for u in data:
            if u.get("username", "").lower() == clean_q:
                selected_user = u
                break

    if not selected_user:
        print(f"[!] Пользователь '{user_query}' не найден в базе ({len(data)} записей)!")
        sys.exit(1)

    uname = selected_user.get("username") or "user"
    dname = selected_user.get("displayName") or uname

    out_file = Path(args.output) if args.output else (SCRIPT_DIR / f"card_{uname}.png")
    render_pumpkin_card(selected_user, out_file)

    print("\n" + "=" * 60)
    print("🎃 КАРТОЧКА ТЫКВЫ УСПЕШНО СОЗДАНА!")
    print("=" * 60)
    print(f"Пользователь: {dname} (@{uname})")
    print(f"Аватар:       {selected_user.get('avatar') or '—'}")
    print(f"Файл:         {out_file.resolve()}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
