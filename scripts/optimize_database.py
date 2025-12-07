#!/usr/bin/env python3
"""
数据库优化执行脚本
执行索引优化和查询性能提升
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.migrations.optimize_indexes import run_index_optimization
from db.connection import test_database_connection, get_db_stats
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """主函数"""
    print("=" * 50)
    print("AgenticGen 数据库优化")
    print("=" * 50)

    # 1. 测试数据库连接
    print("\n1. 测试数据库连接...")
    if not test_database_connection():
        print("❌ 数据库连接失败，请检查配置")
        sys.exit(1)
    print("✅ 数据库连接正常")

    # 2. 获取优化前状态
    print("\n2. 获取优化前状态...")
    stats_before = get_db_stats()
    print(f"   当前查询数: {stats_before['queries']['query_count']}")
    print(f"   平均查询时间: {stats_before['queries']['avg_time']:.3f}s")

    # 3. 执行索引优化
    print("\n3. 执行索引优化...")
    try:
        run_index_optimization()
        print("✅ 索引优化完成")
    except Exception as e:
        print(f"❌ 索引优化失败: {str(e)}")
        sys.exit(1)

    # 4. 验证优化效果
    print("\n4. 验证优化效果...")
    print("✅ 数据库优化完成！")
    print("\n建议:")
    print("   - 重启应用以应用所有优化")
    print("   - 监控查询性能指标")
    print("   - 定期执行此脚本维护索引")

if __name__ == "__main__":
    main()