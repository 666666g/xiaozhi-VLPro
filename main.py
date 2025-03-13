'''
Author: 666666g 1605670940@qq.com
Date: 2025-03-03 20:16:47
LastEditors: 666666g 1605670940@qq.com
LastEditTime: 2025-03-09 22:37:10
FilePath: \py-xiaozhi-main\main.py
Description: 这是默认设置,请设置`customMade`, 打开koroFileHeader查看配置 进行设置: https://github.com/OBKoro1/koro1FileHeader/wiki/%E9%85%8D%E7%BD%AE
'''
import argparse
import logging
import sys
import signal
import time
from src.application import Application
from src.utils.logging_config import setup_logging
logger = logging.getLogger("Main")
# 配置日志

def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='云睿探知者')
    
    # 添加界面模式参数
    parser.add_argument(
        '--mode', 
        choices=['gui', 'cli'],
        default='gui',
        help='运行模式：gui(图形界面) 或 cli(命令行)'
    )
    
    # 添加协议选择参数
    parser.add_argument(
        '--protocol', 
        choices=['mqtt', 'websocket'], 
        default='websocket',
        help='通信协议：mqtt 或 websocket'
    )
    
    # 修改视觉功能参数 - 默认启用，使用 --no-vision 禁用
    parser.add_argument(
        '--no-vision',
        dest='vision',
        action='store_false',
        help='禁用视觉识别功能'
    )
    parser.set_defaults(vision=True)  # 设置默认值为 True
    
    # 添加摄像头ID参数
    parser.add_argument(
        '--camera',
        type=int,
        default=0,
        help='摄像头ID，默认为0'
    )
    
    return parser.parse_args()

def signal_handler(sig, frame):
    """处理Ctrl+C信号"""
    logger.info("接收到中断信号，正在关闭...")
    app = Application.get_instance()
    app.shutdown()
    sys.exit(0)


def main():
    """程序入口点"""
    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    # 解析命令行参数
    args = parse_args()
    try:
        # 日志
        setup_logging()
        # 创建并运行应用程序
        app = Application.get_instance()

        logger.info("应用程序已启动，按Ctrl+C退出")

        # 启动应用，传入参数
        app.run(
            mode=args.mode,
            protocol=args.protocol,
            vision=args.vision,
            camera=args.camera
        )

        # 如果是CLI模式，需要保持主线程运行
        if args.mode == 'cli':
            # 保持主线程运行，直到收到中断信号
            while True:
                time.sleep(1)

    except KeyboardInterrupt:
        logger.info("接收到中断信号，正在关闭...")
        app = Application.get_instance()
        app.shutdown()
    except Exception as e:
        logger.error(f"程序发生错误: {e}", exc_info=True)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())