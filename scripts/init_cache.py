#!/usr/bin/env python3
"""
缓存系统初始化脚本
初始化多级缓存系统并预热数据
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import logging
from cache import init_cache, advanced_cache_manager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def main():
    """主函数"""
    print("=" * 50)
    print("AgenticGen 缓存系统初始化")
    print("=" * 50)

    try:
        # 1. 初始化缓存系统
        print("\n1. 初始化多级缓存系统...")
        await init_cache()
        print("✅ 缓存系统初始化完成")

        # 2. 预热数据
        print("\n2. 预热热点数据...")
        await advanced_cache_manager.warm_up_on_startup()
        print("✅ 数据预热完成")

        # 3. 获取缓存健康状态
        print("\n3. 缓存健康检查...")
        health = await advanced_cache_manager.get_cache_health()
        print(f"   状态: {health['status']}")
        print(f"   总命中率: {health['metrics']['total_hit_rate']}")

        if health['warnings']:
            print("\n⚠️  警告:")
            for warning in health['warnings']:
                print(f"   - {warning}")

        if health['recommendations']:
            print("\n💡 建议:")
            for rec in health['recommendations']:
                print(f"   - {rec}")

        print("\n✅ 缓存系统已就绪！")

    except Exception as e:
        print(f"\n❌ 初始化失败: {str(e)}")
        logger.error(f"Cache initialization failed: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())