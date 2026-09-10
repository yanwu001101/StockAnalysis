#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
在容器内直接执行的patch脚本
"""

# 读取app.py
with open('/app/app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 找到sector_rotation函数的位置
start_line = None
end_line = None

for i, line in enumerate(lines):
    if 'def sector_rotation():' in line:
        start_line = i
    if start_line is not None and i > start_line:
        if line.startswith('@app.route') or line.startswith('def '):
            end_line = i
            break

if start_line is None:
    print("ERROR: Could not find sector_rotation function")
    exit(1)

print(f"Found sector_rotation at lines {start_line+1} to {end_line+1}")

# 新的实现
new_function = '''def sector_rotation():
    """板块涨跌 (使用数据库行业数据)"""
    try:
        from sector_data import fetch_sector_rotation_from_db

        # 获取spot数据
        spot = fetch_spot()
        if spot is None or spot.empty:
            logger.warning("sector_rotation: no spot data")
            return jsonify([])

        # 使用新的sector_data模块
        sectors = fetch_sector_rotation_from_db(spot)

        # 添加flow和momentum字段（兼容前端）
        for i, sector in enumerate(sectors):
            sector['flow'] = 0
            sector['momentum'] = 0
            sector['rank'] = i + 1

        return jsonify(sectors)

    except Exception as e:
        logger.error(f"sector_rotation failed: {e}", exc_info=True)
        traceback.print_exc()
        return jsonify([])


'''

# 替换
new_lines = lines[:start_line] + [new_function] + lines[end_line:]

# 写回
with open('/app/app.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("✓ Successfully patched app.py")
print("✓ Restart the service to apply changes")
