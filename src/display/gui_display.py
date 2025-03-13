import threading
import tkinter as tk
from tkinter import ttk
import queue
import logging
import time
from typing import Optional, Callable
from PIL import Image, ImageTk

from src.display.base_display import BaseDisplay


class GuiDisplay(BaseDisplay):
    def __init__(self):
        """创建 GUI 界面"""
        # 初始化日志
        self.logger = logging.getLogger("Display")

        # 创建主窗口
        self.root = tk.Tk()
        self.root.title("云睿探知者")
        self.root.geometry("600x400")

        # 创建连接状态显示区域 - 移到最上方
        self.connection_frame = tk.Frame(self.root)
        self.connection_frame.pack(pady=10)
        
        # 使用Canvas创建圆角背景 - 恢复原来的尺寸但增大圆角
        self.connection_canvas = tk.Canvas(
            self.connection_frame,
            width=100,
            height=30,
            bg=self.root.cget('bg'),
            highlightthickness=0
        )
        self.connection_canvas.pack()
        
        # 初始状态为未连接（红色）- 增大圆角半径
        self.connection_bg = self._create_rounded_rectangle(
            self.connection_canvas, 5, 5, 95, 25, radius=20, fill="#ffdddd"
        )
        
        # 在Canvas上创建文本 - 调整位置
        self.connection_text = self.connection_canvas.create_text(
            50, 15, text="● 未连接", fill="#aa0000", font=("Arial", 10)
        )

        # 状态显示 - 放在连接状态下方
        self.status_frame = ttk.Frame(self.root)
        self.status_frame.pack(pady=5)
        self.status_label = ttk.Label(self.status_frame, text="状态: 未连接")
        self.status_label.pack(side=tk.LEFT)

        # 表情显示
        self.emotion_label = tk.Label(self.root, text="😊", font=("Segoe UI Emoji", 16))
        self.emotion_label.pack(padx=20, pady=20)

        # TTS文本显示
        self.tts_text_label = ttk.Label(self.root, text="待命", wraplength=250)
        self.tts_text_label.pack(padx=20, pady=10)

        # 音量控制
        self.volume_frame = ttk.Frame(self.root)
        self.volume_frame.pack(pady=10)
        ttk.Label(self.volume_frame, text="音量:").pack(side=tk.LEFT)
        self.volume_scale = ttk.Scale(
            self.volume_frame,
            from_=0,
            to=100,
            command=lambda v: self.update_volume(int(float(v)))
        )
        self.volume_scale.set(70)
        self.volume_scale.pack(side=tk.LEFT, padx=10)

        # 控制按钮
        self.btn_frame = ttk.Frame(self.root)
        self.btn_frame.pack(pady=20)
        
        # 手动模式按钮 - 默认显示
        self.manual_btn = ttk.Button(self.btn_frame, text="按住说话")
        self.manual_btn.bind("<ButtonPress-1>", self._on_manual_button_press)
        self.manual_btn.bind("<ButtonRelease-1>", self._on_manual_button_release)
        self.manual_btn.pack(side=tk.LEFT, padx=10)
        
        # 自动模式按钮 - 默认隐藏
        self.auto_btn = ttk.Button(self.btn_frame, text="开始对话", command=self._on_auto_button_click)
        # 不立即pack，等切换到自动模式时再显示
        
        # 模式切换按钮
        self.mode_btn = ttk.Button(self.btn_frame, text="手动对话", command=self._on_mode_button_click)
        self.mode_btn.pack(side=tk.LEFT, padx=10)
        
        # 对话模式标志
        self.auto_mode = False

        # 视觉功能控制
        self.vision_frame = ttk.Frame(self.root)
        self.vision_frame.pack(pady=10)
        
        self.vision_btn = ttk.Button(self.vision_frame, text="拍摄识别", command=self._on_vision_button_click)
        self.vision_btn.pack(side=tk.LEFT, padx=10)
        
        self.vision_result_label = ttk.Label(self.root, text="", wraplength=500)
        self.vision_result_label.pack(padx=20, pady=10)
        
        # 视觉回调
        self.vision_callback = None

        # 回调函数
        self.button_press_callback = None
        self.button_release_callback = None
        self.status_update_callback = None
        self.text_update_callback = None
        self.emotion_update_callback = None
        self.mode_callback = None
        self.auto_callback = None

        # 更新队列
        self.update_queue = queue.Queue()

        # 运行标志
        self._running = True

        # 设置窗口关闭处理
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # 启动更新处理
        self.root.after(100, self._process_updates)

    def set_callbacks(self,
                      press_callback: Optional[Callable] = None,
                      release_callback: Optional[Callable] = None,
                      status_callback: Optional[Callable] = None,
                      text_callback: Optional[Callable] = None,
                      emotion_callback: Optional[Callable] = None,
                      mode_callback: Optional[Callable] = None,
                      auto_callback: Optional[Callable] = None,
                      vision_callback: Optional[Callable] = None):
        """设置回调函数"""
        self.button_press_callback = press_callback
        self.button_release_callback = release_callback
        self.status_update_callback = status_callback
        self.text_update_callback = text_callback
        self.emotion_update_callback = emotion_callback
        self.mode_callback = mode_callback
        self.auto_callback = auto_callback
        self.vision_callback = vision_callback

    def _process_updates(self):
        """处理更新队列"""
        try:
            while True:
                try:
                    # 非阻塞方式获取更新
                    update_func = self.update_queue.get_nowait()
                    update_func()
                    self.update_queue.task_done()
                except queue.Empty:
                    break
        finally:
            if self._running:
                self.root.after(100, self._process_updates)

    def _on_manual_button_press(self, event):
        """手动模式按钮按下事件处理"""
        try:
            # 更新按钮文本为"松开以停止"
            self.manual_btn.config(text="松开以停止")
            
            # 调用回调函数
            if self.button_press_callback:
                self.button_press_callback()
        except Exception as e:
            self.logger.error(f"按钮按下回调执行失败: {e}")

    def _on_manual_button_release(self, event):
        """手动模式按钮释放事件处理"""
        try:
            # 更新按钮文本为"按住说话"
            self.manual_btn.config(text="按住说话")
            
            # 调用回调函数
            if self.button_release_callback:
                self.button_release_callback()
        except Exception as e:
            self.logger.error(f"按钮释放回调执行失败: {e}")
            
    def _on_auto_button_click(self):
        """自动模式按钮点击事件处理"""
        try:
            if self.auto_callback:
                self.auto_callback()
        except Exception as e:
            self.logger.error(f"自动模式按钮回调执行失败: {e}")

    def _on_mode_button_click(self):
        """对话模式切换按钮点击事件"""
        try:
            # 检查是否可以切换模式（通过回调函数询问应用程序当前状态）
            if self.mode_callback:
                # 如果回调函数返回False，表示当前不能切换模式
                if not self.mode_callback(not self.auto_mode):
                    return
                    
            # 切换模式
            self.auto_mode = not self.auto_mode
            
            # 更新按钮显示
            if self.auto_mode:
                # 切换到自动模式
                self.update_mode_button_status("自动对话")
                
                # 隐藏手动按钮，显示自动按钮
                self.update_queue.put(lambda: self._switch_to_auto_mode())
            else:
                # 切换到手动模式
                self.update_mode_button_status("手动对话")
                
                # 隐藏自动按钮，显示手动按钮
                self.update_queue.put(lambda: self._switch_to_manual_mode())
                
        except Exception as e:
            self.logger.error(f"模式切换按钮回调执行失败: {e}")
            
    def _switch_to_auto_mode(self):
        """切换到自动模式的UI更新"""
        self.manual_btn.pack_forget()  # 移除手动按钮
        self.auto_btn.pack(side=tk.LEFT, padx=10, before=self.mode_btn)  # 显示自动按钮
        
    def _switch_to_manual_mode(self):
        """切换到手动模式的UI更新"""
        self.auto_btn.pack_forget()  # 移除自动按钮
        self.manual_btn.pack(side=tk.LEFT, padx=10, before=self.mode_btn)  # 显示手动按钮

    def update_status(self, status: str):
        """更新状态文本"""
        self.update_queue.put(lambda: self.status_label.config(text=f"状态: {status}"))

    def update_text(self, text: str):
        """更新TTS文本"""
        self.update_queue.put(lambda: self.tts_text_label.config(text=text))

    def update_emotion(self, emotion: str):
        """更新表情"""
        self.update_queue.put(lambda: self.emotion_label.config(text=emotion))

    def update_volume(self, volume: int):
        """更新系统音量 - 跨平台实现"""
        try:
            import platform
            system = platform.system()

            if system == "Windows":
                # Windows实现 (使用pycaw)
                self._set_windows_volume(volume)
            elif system == "Darwin":  # macOS
                # macOS实现 (使用applescript)
                self._set_macos_volume(volume)
            elif system == "Linux":
                # Linux实现 (尝试多种方法)
                self._set_linux_volume(volume)
            else:
                self.logger.warning(f"不支持的操作系统: {system}，无法调整音量")
        except Exception as e:
            self.logger.error(f"设置音量失败: {e}")

    def _set_windows_volume(self, volume: int):
        """设置Windows系统音量"""
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume_control = cast(interface, POINTER(IAudioEndpointVolume))

        # 将百分比转换为分贝值 (范围约为 -65.25dB 到 0dB)
        volume_db = -65.25 * (1 - volume / 100.0)
        volume_control.SetMasterVolumeLevel(volume_db, None)
        self.logger.debug(f"Windows音量已设置为: {volume}%")

    def _set_macos_volume(self, volume: int):
        """设置macOS系统音量"""
        try:
            import applescript
            # 将0-100的音量值应用到macOS的0-100范围
            applescript.run(f'set volume output volume {volume}')
            self.logger.debug(f"macOS音量已设置为: {volume}%")
        except Exception as e:
            self.logger.warning(f"设置macOS音量失败: {e}")

    def _set_linux_volume(self, volume: int):
        """设置Linux系统音量 (尝试多种方法)"""
        import subprocess
        import shutil

        # 检查命令是否存在
        def cmd_exists(cmd):
            return shutil.which(cmd) is not None

        # 尝试使用不同的音量控制命令
        if cmd_exists("amixer"):
            try:
                # 首先尝试PulseAudio
                result = subprocess.run(
                    ["amixer", "-D", "pulse", "sset", "Master", f"{volume}%"],
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    self.logger.debug(f"Linux音量(amixer/pulse)已设置为: {volume}%")
                    return

                # 如果失败，尝试默认设备
                result = subprocess.run(
                    ["amixer", "sset", "Master", f"{volume}%"],
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    self.logger.debug(f"Linux音量(amixer)已设置为: {volume}%")
                    return
            except Exception as e:
                self.logger.debug(f"amixer设置音量失败: {e}")

        if cmd_exists("pactl"):
            try:
                result = subprocess.run(
                    ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{volume}%"],
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    self.logger.debug(f"Linux音量(pactl)已设置为: {volume}%")
                    return
            except Exception as e:
                self.logger.debug(f"pactl设置音量失败: {e}")

        # 如果所有方法都失败
        self.logger.error("无法设置Linux音量，请确保安装了ALSA或PulseAudio")

    def start_update_threads(self):
        """启动更新线程"""

        def update_loop():
            while self._running:
                try:
                    # 更新状态
                    if self.status_update_callback:
                        status = self.status_update_callback()
                        if status:
                            self.update_status(status)

                    # 更新文本
                    if self.text_update_callback:
                        text = self.text_update_callback()
                        if text:
                            self.update_text(text)

                    # 更新表情
                    if self.emotion_update_callback:
                        emotion = self.emotion_update_callback()
                        if emotion:
                            self.update_emotion(emotion)

                except Exception as e:
                    self.logger.error(f"更新失败: {e}")
                time.sleep(0.1)

        threading.Thread(target=update_loop, daemon=True).start()

    def on_close(self):
        """关闭窗口处理"""
        self._running = False
        self.root.destroy()

    def start(self):
        """启动GUI"""
        # 启动更新线程
        self.start_update_threads()
        # 在主线程中运行主循环
        self.root.mainloop()

    def update_mode_button_status(self, text: str):
        """更新模式按钮状态"""
        self.update_queue.put(lambda: self.mode_btn.config(text=text))

    def update_button_status(self, text: str):
        """更新按钮状态 - 保留此方法以满足抽象基类要求"""
        # 根据当前模式更新相应的按钮
        if self.auto_mode:
            self.update_queue.put(lambda: self.auto_btn.config(text=text))
        else:
            # 在手动模式下，不通过此方法更新按钮文本
            # 因为按钮文本由按下/释放事件直接控制
            pass

    def _create_circle_image(self, radius, color):
        """创建圆形图标"""
        # 创建一个新的图像，带有透明背景
        image = Image.new("RGBA", (radius*2, radius*2), (0, 0, 0, 0))
        # 创建绘图对象
        from PIL import ImageDraw
        draw = ImageDraw.Draw(image)
        # 绘制圆形
        draw.ellipse((0, 0, radius*2-1, radius*2-1), fill=color)
        # 转换为PhotoImage
        return ImageTk.PhotoImage(image)

    def _create_rounded_rectangle(self, canvas, x1, y1, x2, y2, radius=25, **kwargs):
        points = [
            x1+radius, y1,
            x2-radius, y1,
            x2, y1,
            x2, y1+radius,
            x2, y2-radius,
            x2, y2,
            x2-radius, y2,
            x1+radius, y2,
            x1, y2,
            x1, y2-radius,
            x1, y1+radius,
            x1, y1
        ]
        return canvas.create_polygon(points, **kwargs, smooth=True)

    def update_connection_status(self, connected):
        """更新连接状态显示"""
        def _update():
            if connected:
                self.connection_canvas.itemconfig(
                    self.connection_bg, fill="#ddffdd"
                )
                self.connection_canvas.itemconfig(
                    self.connection_text, text="● 已连接", fill="#00aa00"
                )
            else:
                self.connection_canvas.itemconfig(
                    self.connection_bg, fill="#ffdddd"
                )
                self.connection_canvas.itemconfig(
                    self.connection_text, text="● 未连接", fill="#aa0000"
                )
        
        self.update_queue.put(_update)

    def _on_vision_button_click(self):
        """视觉按钮点击事件处理"""
        try:
            if self.vision_callback:
                self.vision_callback()
        except Exception as e:
            self.logger.error(f"视觉按钮回调执行失败: {e}")

    def update_vision_result(self, text: str):
        """更新视觉识别结果"""
        self.update_queue.put(lambda: self.vision_result_label.config(text=text))