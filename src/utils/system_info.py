# 在导入 opuslib 之前处理 opus 动态库
import ctypes
import os
import sys


def setup_opus():
    """设置 opus 动态库 (仅支持Windows)"""
    if sys.platform != 'win32':
        return

    # 尝试多个可能的基准路径
    possible_base_dirs = [
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),  # 当前方式
        os.getcwd(),  # 当前工作目录
        getattr(sys, '_MEIPASS', None),  # PyInstaller 打包路径
    ]
    
    lib_path = None
    for base_dir in filter(None, possible_base_dirs):
        libs_dir = os.path.join(base_dir, 'libs', 'windows')
        temp_lib_path = os.path.join(libs_dir, 'opus.dll')
        
        if os.path.exists(temp_lib_path):
            lib_path = temp_lib_path
            break
    
    if lib_path is None:
        print("错误: 未能找到 opus 库文件")
        return

    # 添加DLL搜索路径
    if hasattr(os, 'add_dll_directory'):
        os.add_dll_directory(libs_dir)

    # 设置环境变量
    os.environ['PATH'] = libs_dir + os.pathsep + os.environ.get('PATH', '')

    # 修补库路径
    _patch_find_library('opus', lib_path)

    # 尝试直接加载
    try:
        opus_lib = ctypes.CDLL(lib_path)
        print(f"已成功加载 opus.dll: {lib_path}")
    except Exception as e:
        print(f"加载 opus.dll 失败: {e}")


def _patch_find_library(lib_name, lib_path):
    """修补 ctypes.util.find_library 函数"""
    import ctypes.util
    original_find_library = ctypes.util.find_library

    def patched_find_library(name):
        if name == lib_name:
            return lib_path
        return original_find_library(name)

    ctypes.util.find_library = patched_find_library