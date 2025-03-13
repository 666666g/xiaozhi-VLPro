import os
import sys
import shutil
from pathlib import Path

def clean_old_files():
    """清理旧的构建文件"""
    print("🧹 正在清理旧文件...")
    
    # 要清理的目录和文件
    to_clean = ['build', 'dist', '__pycache__', '*.spec']
    
    for item in to_clean:
        paths = list(Path('.').glob(item))
        for path in paths:
            try:
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    shutil.rmtree(path)
            except Exception as e:
                print(f"⚠️ 清理 {path} 时出错: {e}")
                
    print("✅ 清理完成")

def create_spec_file():
    """创建 spec 文件"""
    spec_content = '''# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('src', 'src'),
        ('opus.dll', '.'),
    ],
    hiddenimports=[
        'PIL._tkinter_finder',
        'customtkinter',
        'paho.mqtt.client',
        'opuslib',
        'cryptography',
        'pyaudio',
        'pycaw',
        'comtypes',
        'numpy',
        'psutil',
        'future'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='云睿探知者',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
'''
    with open('xiaozhi.spec', 'w', encoding='utf-8') as f:
        f.write(spec_content)
    print("✅ spec 文件创建成功")

def install_requirements():
    """安装必要的包"""
    print("📦 正在安装必要的包...")
    try:
        # 升级 pip
        os.system(f'{sys.executable} -m pip install --upgrade pip')
        
        # 安装依赖
        print("📥 安装依赖...")
        os.system(f'{sys.executable} -m pip install -r requirements.txt')
        
        # 安装 PyInstaller
        print("📥 安装 PyInstaller...")
        os.system(f'{sys.executable} -m pip install pyinstaller')
        
        print("✅ 包安装完成")
        return True
    except Exception as e:
        print(f"❌ 安装包时出错: {e}")
        return False

def build_exe():
    """构建可执行文件"""
    print("🚀 开始构建...")
    try:
        # 使用 spec 文件构建
        import subprocess
        result = subprocess.run([sys.executable, '-m', 'PyInstaller', 'xiaozhi.spec'], 
                              capture_output=True, 
                              text=True)
        
        print("构建输出:")
        print(result.stdout)
        
        if result.stderr:
            print("错误输出:")
            print(result.stderr)
        
        if result.returncode == 0:
            exe_path = os.path.join("dist", "云睿探知者.exe")
            if os.path.exists(exe_path):
                size_mb = os.path.getsize(exe_path) / (1024 * 1024)
                print(f"✅ 构建成功！")
                print(f"📦 文件大小: {size_mb:.2f}MB")
                print(f"📂 输出路径: {os.path.abspath(exe_path)}")
                return True
            else:
                print(f"❌ 构建可能成功但未找到输出文件: {exe_path}")
        else:
            print(f"❌ 构建失败，返回码: {result.returncode}")
        return False
        
    except Exception as e:
        print(f"❌ 构建过程出错: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主函数"""
    try:
        # 清理旧文件
        clean_old_files()
        
        # 创建 spec 文件
        create_spec_file()
        
        # 安装依赖
        if not install_requirements():
            print("❌ 安装依赖失败，终止构建")
            return
        
        # 构建可执行文件
        if not build_exe():
            print("❌ 构建失败")
            return
            
    except Exception as e:
        print(f"❌ 程序出错: {e}")
        print("详细错误信息:")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 