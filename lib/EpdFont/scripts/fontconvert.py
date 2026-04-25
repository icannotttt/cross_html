#!python3
import freetype
import zlib
import sys
import re
import math
import argparse
from collections import namedtuple
import os

# Originally from https://github.com/vroland/epdiy

parser = argparse.ArgumentParser(description="Generate a header file from a font to be used with epdiy.")
parser.add_argument("name", action="store", help="name of the font.")
parser.add_argument("size", type=int, help="font size to use.")
parser.add_argument("fontstack", action="store", nargs='+', help="list of font files, ordered by descending priority.")
parser.add_argument("--2bit", dest="is2Bit", action="store_true", help="generate 2-bit greyscale bitmap instead of 1-bit black and white.")
parser.add_argument("--additional-intervals", dest="additional_intervals", action="append", help="Additional code point intervals to export as min,max. This argument can be repeated.")
parser.add_argument("--output-dir", dest="output_dir", default=".", help="Output directory for the .h file (default: current directory)")
args = parser.parse_args()

# 生成的.h文件路径
output_file = os.path.join(args.output_dir, f"{args.name}.h")

GlyphProps = namedtuple("GlyphProps", ["width", "height", "advance_x", "left", "top", "data_length", "data_offset", "code_point"])

# 加载字体
font_stack = [freetype.Face(f) for f in args.fontstack]
is2Bit = args.is2Bit
size = args.size
font_name = args.name

# ===================== 核心修改：精简CJK区间（只保留常用字） =====================
# ===================== 完整字符集区间（包含所有常见及扩展字符） =====================
# 覆盖多语言场景，包括完整CJK、日韩文字、符号等（体积较大）
intervals = [
    # 基础字符
    (0x0000, 0x007F),  # ASCII 字符（英文字母、数字、基础标点）
    #(0x0080, 0x00FF),  # 拉丁扩展字符（西欧语言符号）
    #(0x0100, 0x017F),  # 拉丁扩展-A（东欧、北欧语言字符）
    #(0x0180, 0x024F),  # 拉丁扩展-B（更多欧洲语言字符）
    
    # 东亚文字（完整CJK）
    (0x3000, 0x303F),  # 中文标点（全角符号、括号等）
    ##(0x3040, 0x309F),  # 日语平假名
    ##(0x30A0, 0x30FF),  # 日语片假名
    (0x4E00, 0x9FFF),  # 统一汉字（包含所有常用字、次常用字、生僻字，约2万汉字）
    ##(0xAC00, 0xD7AF),  # 朝鲜语Hangul音节（韩文）
    (0xF900, 0xFAFF),  # CJK兼容汉字（康熙字典部首等）
    (0xFE30, 0xFE4F),  # CJK兼容符号（竖排标点等）
    (0xFF00, 0xFFEF),  # 全角ASCII及标点（全角字母、数字、符号）
    
    # 扩展字符与符号
    (0x2000, 0x206F),  # 通用标点与排版符号（空格、连字符等）
    ##(0x2100, 0x214F),  # 数学符号（分数、箭头等）
    ##(0x2200, 0x22FF),  # 数学运算符（加减乘除、逻辑符号等）
    ##(0x2E80, 0x2EFF),  # 中日韩部首补充（汉字部首扩展）
    ##(0x31C0, 0x31EF),  # 中日韩笔画（汉字笔画符号）
]

# 追加用户自定义区间（如需）
add_ints = []
if args.additional_intervals:
    add_ints = [tuple([int(n, base=0) for n in i.split(",")]) for i in args.additional_intervals]

# 原函数保留（无需修改）
def norm_floor(val):
    return int(math.floor(val / (1 << 6)))

def norm_ceil(val):
    return int(math.ceil(val / (1 << 6)))

def chunks(l, n):
    for i in range(0, len(l), n):
        yield l[i:i + n]

# 优化：只提示常用汉字缺失（减少冗余提示）
def load_glyph(code_point):
    face_index = 0
    while face_index < len(font_stack):
        face = font_stack[face_index]
        glyph_index = face.get_char_index(code_point)
        if glyph_index > 0:
            face.load_glyph(glyph_index, freetype.FT_LOAD_RENDER)
            return face
        face_index += 1
    # 只提示常用汉字缺失（其他字符忽略）
    if 0x4E00 <= code_point <= 0x5FFF:
        print(f"常用汉字缺失：0x{code_point:X} ({chr(code_point)})", file=sys.stderr)
    return None

# 区间合并逻辑（原逻辑保留）
unmerged_intervals = sorted(intervals + add_ints)
intervals = []
unvalidated_intervals = []
for i_start, i_end in unmerged_intervals:
    if len(unvalidated_intervals) > 0 and i_start + 1 <= unvalidated_intervals[-1][1]:
        unvalidated_intervals[-1] = (unvalidated_intervals[-1][0], max(unvalidated_intervals[-1][1], i_end))
        continue
    unvalidated_intervals.append((i_start, i_end))

# 验证区间（跳过缺失字符）
for i_start, i_end in unvalidated_intervals:
    start = i_start
    for code_point in range(i_start, i_end + 1):
        face = load_glyph(code_point)
        if face is None:
            if start < code_point:
                intervals.append((start, code_point - 1))
            start = code_point + 1
    if start != i_end + 1:
        intervals.append((start, i_end))

# 设置字体大小（原逻辑保留）
for face in font_stack:
    face.set_char_size(size << 6, size << 6, 150, 150)

# 加载字形数据（原逻辑保留）
total_size = 0
all_glyphs = []
for i_start, i_end in intervals:
    for code_point in range(i_start, i_end + 1):
        face = load_glyph(code_point)
        if not face:
            continue
        bitmap = face.glyph.bitmap

        # 4-bit位图构建（原逻辑保留）
        pixels4g = []
        px = 0
        for i, v in enumerate(bitmap.buffer):
            y = i / bitmap.width
            x = i % bitmap.width
            if x % 2 == 0:
                px = (v >> 4)
            else:
                px = px | (v & 0xF0)
                pixels4g.append(px);
                px = 0
            if x == bitmap.width - 1 and bitmap.width % 2 > 0:
                pixels4g.append(px)
                px = 0

        # 2bit/1bit转换（原逻辑保留）
        if is2Bit:
            pixels2b = []
            px = 0
            pitch = (bitmap.width // 2) + (bitmap.width % 2)
            for y in range(bitmap.rows):
                for x in range(bitmap.width):
                    px = px << 2
                    bm = pixels4g[y * pitch + (x // 2)]
                    bm = (bm >> ((x % 2) * 4)) & 0xF
                    if bm >= 12:
                        px += 3
                    elif bm >= 8:
                        px += 2
                    elif bm >= 4:
                        px += 1
                    if (y * bitmap.width + x) % 4 == 3:
                        pixels2b.append(px)
                        px = 0
            if (bitmap.width * bitmap.rows) % 4 != 0:
                px = px << (4 - (bitmap.width * bitmap.rows) % 4) * 2
                pixels2b.append(px)
            pixels = pixels2b
        else:
            pixelsbw = []
            px = 0
            pitch = (bitmap.width // 2) + (bitmap.width % 2)
            for y in range(bitmap.rows):
                for x in range(bitmap.width):
                    px = px << 1
                    bm = pixels4g[y * pitch + (x // 2)]
                    px += 1 if ((x & 1) == 0 and bm & 0xE > 0) or ((x & 1) == 1 and bm & 0xE0 > 0) else 0
                    if (y * bitmap.width + x) % 8 == 7:
                        pixelsbw.append(px)
                        px = 0
            if (bitmap.width * bitmap.rows) % 8 != 0:
                px = px << (8 - (bitmap.width * bitmap.rows) % 8)
                pixelsbw.append(px)
            pixels = pixelsbw

        # 打包字形数据（原逻辑保留）
        packed = bytes(pixels)
        glyph = GlyphProps(
            width = bitmap.width,
            height = bitmap.rows,
            advance_x = norm_floor(face.glyph.advance.x),
            left = face.glyph.bitmap_left,
            top = face.glyph.bitmap_top,
            data_length = len(packed),
            data_offset = total_size,
            code_point = code_point,
        )
        total_size += len(packed)
        all_glyphs.append((glyph, packed))

# 基准字形（原逻辑保留）
face = load_glyph(ord('|')) or load_glyph(ord('丨'))

# 整理数据（原逻辑保留）
glyph_data = []
glyph_props = []
for index, glyph in enumerate(all_glyphs):
    props, packed = glyph
    glyph_data.extend([b for b in packed])
    glyph_props.append(props)

# 写入.h文件（原格式保留）
with open(output_file, 'w', encoding='utf-8') as f:
    f.write(f"/**\n * generated by fontconvert.py\n * name: {font_name}\n * size: {size}\n * mode: {'2-bit' if is2Bit else '1-bit'}\n */\n")
    f.write("#pragma once\n")
    f.write("#include \"EpdFontData.h\"\n\n")
    
    # 位图数据
    f.write(f"static const uint8_t {font_name}Bitmaps[{len(glyph_data)}] = {{\n")
    for c in chunks(glyph_data, 16):
        f.write("    " + " ".join(f"0x{b:02X}," for b in c) + "\n")
    f.write("};\n\n")
    
    # 字形属性
    f.write(f"static const EpdGlyph {font_name}Glyphs[] = {{\n")
    for i, g in enumerate(glyph_props):
        char_repr = chr(g.code_point) if g.code_point != 92 else '<backslash>'
        f.write(f"    {{ " + ", ".join([f"{a}" for a in list(g[:-1])]) + f"}},\t// {char_repr}\n")
    f.write("};\n\n")
    
    # Unicode区间
    f.write(f"static const EpdUnicodeInterval {font_name}Intervals[] = {{\n")
    offset = 0
    for i_start, i_end in intervals:
        f.write(f"    {{ 0x{i_start:X}, 0x{i_end:X}, 0x{offset:X} }},\n")
        offset += i_end - i_start + 1
    f.write("};\n\n")
    
    # 字体数据结构体
    f.write(f"static const EpdFontData {font_name} = {{\n")
    f.write(f"    {font_name}Bitmaps,\n")
    f.write(f"    {font_name}Glyphs,\n")
    f.write(f"    {font_name}Intervals,\n")
    f.write(f"    {len(intervals)},\n")
    f.write(f"    {norm_ceil(face.size.height) if face else 0},\n")
    f.write(f"    {norm_ceil(face.size.ascender) if face else 0},\n")
    f.write(f"    {norm_floor(face.size.descender) if face else 0},\n")
    f.write(f"    {'true' if is2Bit else 'false'},\n")
    f.write("};\n")

# 输出统计信息（方便确认体积）
file_size = os.path.getsize(output_file)
print(f"✅ 生成成功：{output_file}")
print(f"📊 统计：")
print(f"   - 字符数量：{len(glyph_props)} 个")
print(f"   - 文件大小：{file_size / 1024:.1f} KB")
print(f"   - 位图数据：{len(glyph_data) / 1024:.1f} KB")