"""商品目录查询服务 —— 规格 v1（修改前基线）

本文件是业务工程的规格基线。上下文模块会把本规格导入 seekdb，
作为"当前应遵守哪些要求"的来源之一。
"""
# 领域模型
#   Product：
#     id        整数，唯一
#     name      商品名称（字符串）
#     category  分类（字符串）
#     price     单价（元，非负浮点数）
#     in_stock  是否在售（布尔）
#     stock     库存量（非负整数）
#
# 查询规则 search_products(products, category=None, in_stock_only=False)
#   1. category 指定时，仅返回该分类下的商品。
#   2. in_stock_only=True 时，仅返回 in_stock 为真且 stock > 0 的商品。
#   3. 未指定任何条件时，返回全部商品。
#   4. 结果保持输入顺序。
#   5. 任何情况下都不修改输入数据。
#
# 不变式
#   price >= 0，stock >= 0。
