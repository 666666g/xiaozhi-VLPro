import asyncio
import json
import logging
import threading
import time
import queue
import pyaudio
import numpy as np
import opuslib

from src.protocols.mqtt_protocol import MqttProtocol
from src.constants.constants import DeviceState, EventType, AudioConfig, AbortReason, ListeningMode
from src.display import gui_display, cli_dispaly
from src.protocols.websocket_protocol import WebsocketProtocol
from src.utils.config_manager import ConfigManager
from src.vision.vision_processor import VisionProcessor
from src.vision.vision_config import VisionConfig

# 配置日志
logger = logging.getLogger("Application")


class Application:
    """智能音箱应用程序主类"""
    _instance = None

    @classmethod
    def get_instance(cls):
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = Application()
        return cls._instance

    def __init__(self):
        """初始化应用程序"""
        # 确保单例模式
        if Application._instance is not None:
            raise Exception("Application是单例类，请使用get_instance()获取实例")
        Application._instance = self

        # 状态变量
        self.device_state = DeviceState.IDLE
        self.voice_detected = False
        self.keep_listening = False
        self.aborted = False
        self.current_text = ""
        self.current_emotion = "neutral"

        # 音频处理相关
        self.audio = pyaudio.PyAudio()
        self.input_stream = None
        self.output_stream = None
        self.opus_encoder = None
        self.opus_decoder = None
        self.opus_decode_sample_rate = AudioConfig.SAMPLE_RATE

        # 音频数据队列
        self.audio_decode_queue = queue.Queue()

        # 事件循环和线程
        self.loop = asyncio.new_event_loop()
        self.loop_thread = None
        self.running = False

        # 任务队列和锁
        self.main_tasks = []
        self.mutex = threading.Lock()

        # 协议实例
        self.protocol = None

        # 回调函数
        self.on_state_changed_callbacks = []

        # 初始化事件对象
        self.events = {
            EventType.SCHEDULE_EVENT: threading.Event(),
            EventType.AUDIO_INPUT_READY_EVENT: threading.Event(),
            EventType.AUDIO_OUTPUT_READY_EVENT: threading.Event()
        }

        # 创建显示界面
        self.display = None

        # 获取配置管理器实例
        self.config = ConfigManager.get_instance()

        # 视觉处理相关
        self.vision_enabled = False
        self.vision_processor = None
        self.vision_config = None

    def run(self, **kwargs):
        """启动应用程序"""
        print(kwargs)
        mode = kwargs.get('mode', 'gui')
        protocol = kwargs.get('protocol', 'websocket')
        
        # 视觉功能
        vision_enabled = kwargs.get('vision', False)
        camera_id = kwargs.get('camera', 0)
        
        self.set_display_type(mode)
        self.set_protocol_type(protocol)
        
        # 初始化视觉功能
        if vision_enabled:
            self._init_vision(camera_id)
        
        # 创建并启动事件循环线程
        self.loop_thread = threading.Thread(target=self._run_event_loop)
        self.loop_thread.daemon = True
        self.loop_thread.start()

        # 等待事件循环准备就绪
        time.sleep(0.1)

        # 初始化应用程序
        asyncio.run_coroutine_threadsafe(self._initialize(), self.loop)

        # 启动主循环线程
        main_loop_thread = threading.Thread(target=self._main_loop)
        main_loop_thread.daemon = True
        main_loop_thread.start()

        # 启动GUI
        self.display.start()

    def _run_event_loop(self):
        """运行事件循环的线程函数"""
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    async def _initialize(self):
        """初始化应用程序组件"""
        logger.info("正在初始化应用程序...")

        # 设置设备状态为启动中
        self.set_device_state(DeviceState.IDLE)

        # 初始化音频编解码器
        self._initialize_audio()

        # 设置协议回调
        self.protocol.on_network_error = self._on_network_error
        self.protocol.on_incoming_audio = self._on_incoming_audio
        self.protocol.on_incoming_json = self._on_incoming_json
        self.protocol.on_audio_channel_opened = self._on_audio_channel_opened
        self.protocol.on_audio_channel_closed = self._on_audio_channel_closed
        
        # 设置连接状态回调
        self._setup_protocol_callbacks()

        # 连接到服务器
        if not await self.protocol.connect():
            logger.error("连接服务器失败")
            self.alert("错误", "连接服务器失败")
            return

        logger.info("应用程序初始化完成")

    def _initialize_audio(self):
        """初始化音频设备和编解码器"""
        try:
            # 初始化音频输入流
            self.input_stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=AudioConfig.CHANNELS,
                rate=AudioConfig.SAMPLE_RATE,
                input=True,
                frames_per_buffer=AudioConfig.FRAME_SIZE
            )

            # 初始化音频输出流
            self.output_stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=AudioConfig.CHANNELS,
                rate=AudioConfig.SAMPLE_RATE,
                output=True,
                frames_per_buffer=AudioConfig.FRAME_SIZE
            )

            # 初始化Opus编码器
            self.opus_encoder = opuslib.Encoder(
                fs=AudioConfig.SAMPLE_RATE,
                channels=AudioConfig.CHANNELS,
                application=opuslib.APPLICATION_AUDIO
            )

            # 初始化Opus解码器
            self.opus_decoder = opuslib.Decoder(
                fs=AudioConfig.SAMPLE_RATE,
                channels=AudioConfig.CHANNELS
            )

            logger.info("音频设备和编解码器初始化成功")
        except Exception as e:
            logger.error(f"初始化音频设备失败: {e}")
            self.alert("错误", f"初始化音频设备失败: {e}")

    def _initialize_display(self):
        """初始化显示界面"""
        self.display = gui_display.GuiDisplay()

        # 设置回调函数
        self.display.set_callbacks(
            press_callback=self.start_listening,
            release_callback=self.stop_listening,
            status_callback=self._get_status_text,
            text_callback=self._get_current_text,
            emotion_callback=self._get_current_emotion,
            mode_callback=self._on_mode_changed,
            auto_callback=self.toggle_chat_state,
            vision_callback=self._trigger_vision_capture
        )

    def _initialize_cli(self):
        self.display = cli_dispaly.CliDisplay()
        self.display.set_callbacks(
            press_callback=self.toggle_chat_state,
            status_callback=self._get_status_text,
            text_callback=self._get_current_text,
            emotion_callback=self._get_current_emotion
        )

    def set_protocol_type(self, protocol_type: str):
        """设置协议类型"""
        if protocol_type == 'mqtt':
            self.protocol = MqttProtocol(self.loop)
        else:  # websocket
            self.protocol = WebsocketProtocol()

    def set_display_type(self, mode: str):
        if mode == 'gui':
            self._initialize_display()
        else:
            self._initialize_cli()

    def _main_loop(self):
        """应用程序主循环"""
        logger.info("主循环已启动")
        self.running = True

        while self.running:
            # 等待事件
            for event_type, event in self.events.items():
                if event.is_set():
                    event.clear()

                    if event_type == EventType.AUDIO_INPUT_READY_EVENT:
                        self._handle_input_audio()
                    elif event_type == EventType.AUDIO_OUTPUT_READY_EVENT:
                        self._handle_output_audio()
                    elif event_type == EventType.SCHEDULE_EVENT:
                        self._process_scheduled_tasks()

            # 短暂休眠以避免CPU占用过高
            time.sleep(0.01)

    def _process_scheduled_tasks(self):
        """处理调度任务"""
        with self.mutex:
            tasks = self.main_tasks.copy()
            self.main_tasks.clear()

        for task in tasks:
            try:
                task()
            except Exception as e:
                logger.error(f"执行调度任务时出错: {e}")

    def schedule(self, callback):
        """调度任务到主循环"""
        with self.mutex:
            self.main_tasks.append(callback)
        self.events[EventType.SCHEDULE_EVENT].set()

    def _handle_input_audio(self):
        """处理音频输入"""
        if self.device_state != DeviceState.LISTENING or not self.input_stream.is_active():
            return

        try:
            data = self.input_stream.read(AudioConfig.FRAME_SIZE, exception_on_overflow=False)
            if not data:
                return

            encoded_data = self.opus_encoder.encode(data, AudioConfig.FRAME_SIZE)
            if self.protocol and self.protocol.is_audio_channel_opened():
                asyncio.run_coroutine_threadsafe(
                    self.protocol.send_audio(encoded_data),
                    self.loop
                )
        except Exception as e:
            logger.error(f"处理音频输入时出错: {e}")

    def _handle_output_audio(self):
        """处理音频输出"""
        if self.device_state != DeviceState.SPEAKING:
            return
        
        try:
            # 检查输出流状态
            if not self.output_stream or not self.output_stream.is_active():
                # 如果流不活跃，尝试重新启动
                if self.output_stream:
                    try:
                        self.output_stream.start_stream()
                        logger.info("已重新启动音频输出流")
                    except Exception as e:
                        logger.error(f"重新启动音频输出流失败: {e}")
                        return
            
            # 批量处理多个音频包以减少处理延迟
            batch_size = min(10, self.audio_decode_queue.qsize())
            if batch_size == 0:
                return

            # 创建一个足够大的缓冲区来存储解码后的数据
            buffer = bytearray()

            for _ in range(batch_size):
                if self.audio_decode_queue.empty():
                    break

                opus_data = self.audio_decode_queue.get_nowait()

                if self.aborted:
                    # 清空队列
                    while not self.audio_decode_queue.empty():
                        self.audio_decode_queue.get_nowait()
                    return

                try:
                    pcm_data = self.opus_decoder.decode(opus_data, AudioConfig.FRAME_SIZE, decode_fec=False)
                    buffer.extend(pcm_data)
                except Exception as e:
                    logger.error(f"解码音频数据时出错: {e}")

            # 只有在有数据时才处理和播放
            if len(buffer) > 0:
                # 转换为numpy数组
                pcm_array = np.frombuffer(buffer, dtype=np.int16)

                # 调试信息
                logging.debug(f"[DEBUG] PCM数据: 大小={len(pcm_array)}, "
                              f"最大值={np.max(np.abs(pcm_array))}, "
                              f"均值={np.mean(np.abs(pcm_array))}")

                # 播放音频
                try:
                    self.output_stream.write(pcm_array.tobytes())
                except OSError as e:
                    logger.error(f"播放音频时出错: {e}")
                    # 如果是"Stream not open"错误，尝试重新初始化输出流
                    if "Stream not open" in str(e):
                        self._reinitialize_output_stream()
        except queue.Empty:
            pass
        except Exception as e:
            logger.error(f"处理音频输出时出错: {e}")

    def _reinitialize_output_stream(self):
        """重新初始化音频输出流"""
        logger.info("正在重新初始化音频输出流...")
        try:
            # 关闭现有流
            if self.output_stream:
                try:
                    if self.output_stream.is_active():
                        self.output_stream.stop_stream()
                    self.output_stream.close()
                except Exception as e:
                    logger.warning(f"关闭现有输出流时出错: {e}")
            
            # 创建新的输出流
            self.output_stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=AudioConfig.CHANNELS,
                rate=AudioConfig.SAMPLE_RATE,
                output=True,
                frames_per_buffer=AudioConfig.FRAME_SIZE
            )
            
            logger.info("音频输出流重新初始化成功")
        except Exception as e:
            logger.error(f"重新初始化音频输出流失败: {e}")
            self.alert("错误", f"重新初始化音频设备失败: {e}")

    def _on_network_error(self, message):
        """网络错误回调"""
        logger.error(f"网络错误: {message}")
        self.schedule(lambda: self.alert("网络错误", message))

        # 添加重连逻辑
        self.schedule(self._attempt_reconnect)

    def _attempt_reconnect(self):
        """尝试重新连接服务器"""
        if self.device_state != DeviceState.CONNECTING:
            logger.info("检测到连接断开，尝试重新连接...")
            self.set_device_state(DeviceState.CONNECTING)

            # 关闭现有连接
            if self.protocol:
                asyncio.run_coroutine_threadsafe(
                    self.protocol.close_audio_channel(),
                    self.loop
                )

            # 延迟一秒后尝试重新连接
            def delayed_reconnect():
                time.sleep(1)
                asyncio.run_coroutine_threadsafe(self._reconnect(), self.loop)

            threading.Thread(target=delayed_reconnect, daemon=True).start()

    async def _reconnect(self):
        """重新连接到服务器"""

        # 设置协议回调
        self.protocol.on_network_error = self._on_network_error
        self.protocol.on_incoming_audio = self._on_incoming_audio
        self.protocol.on_incoming_json = self._on_incoming_json
        self.protocol.on_audio_channel_opened = self._on_audio_channel_opened
        self.protocol.on_audio_channel_closed = self._on_audio_channel_closed

        # 连接到服务器
        retry_count = 0
        max_retries = 3

        while retry_count < max_retries:
            logger.info(f"尝试重新连接 (尝试 {retry_count + 1}/{max_retries})...")
            if await self.protocol.connect():
                logger.info("重新连接成功")
                self.set_device_state(DeviceState.IDLE)
                return True

            retry_count += 1
            await asyncio.sleep(2)  # 等待2秒后重试

        logger.error(f"重新连接失败，已尝试 {max_retries} 次")
        self.schedule(lambda: self.alert("连接错误", "无法重新连接到服务器"))
        self.set_device_state(DeviceState.IDLE)
        return False

    def _on_incoming_audio(self, data):
        """接收音频数据回调"""
        if self.device_state == DeviceState.SPEAKING:
            # 直接添加到队列，不要设置事件 - 减少事件触发频率
            self.audio_decode_queue.put(data)
            # 确保立即触发事件以减少延迟
            self.events[EventType.AUDIO_OUTPUT_READY_EVENT].set()

    def _on_incoming_json(self, json_data):
        """接收JSON数据回调"""
        try:
            if not json_data:
                return

            # 解析JSON数据
            if isinstance(json_data, str):
                data = json.loads(json_data)
            else:
                data = json_data

            # 处理不同类型的消息
            msg_type = data.get("type", "")
            if msg_type == "tts":
                self._handle_tts_message(data)
            elif msg_type == "stt":
                self._handle_stt_message(data)
            elif msg_type == "llm":
                self._handle_llm_message(data)
            else:
                logger.warning(f"收到未知类型的消息: {msg_type}")
        except Exception as e:
            logger.error(f"处理JSON消息时出错: {e}")

    def _handle_tts_message(self, data):
        """处理TTS消息"""
        state = data.get("state", "")
        if state == "start":
            self.schedule(lambda: self._handle_tts_start())
        elif state == "stop":
            self.schedule(lambda: self._handle_tts_stop())
        elif state == "sentence_start":
            text = data.get("text", "")
            if text:
                logger.info(f"<< {text}")
                self.schedule(lambda: self.set_chat_message("assistant", text))

                # 检查是否包含验证码信息
                if "请登录到控制面板添加设备，输入验证码" in text:
                    self.schedule(lambda: self._handle_verification_code(text))

    def _handle_tts_start(self):
        """处理TTS开始事件"""
        self.aborted = False

        # 清空可能存在的旧音频数据
        while not self.audio_decode_queue.empty():
            try:
                self.audio_decode_queue.get_nowait()
            except queue.Empty:
                break

        if self.device_state == DeviceState.IDLE or self.device_state == DeviceState.LISTENING:
            self.set_device_state(DeviceState.SPEAKING)

    def _handle_tts_stop(self):
        """处理TTS停止事件"""
        if self.device_state == DeviceState.SPEAKING:
            # 给音频播放一个缓冲时间，确保所有音频都播放完毕
            def delayed_state_change():
                # 等待音频队列清空
                attempt = 0
                max_attempts = 10  # 最多等待5秒
                while not self.audio_decode_queue.empty() and attempt < max_attempts:
                    time.sleep(0.1)
                    attempt += 1

                # 在关闭前清空任何剩余数据
                while not self.audio_decode_queue.empty():
                    try:
                        self.audio_decode_queue.get_nowait()
                    except queue.Empty:
                        break

                # 状态转换
                if self.keep_listening:
                    asyncio.run_coroutine_threadsafe(
                        self.protocol.send_start_listening(ListeningMode.AUTO_STOP),
                        self.loop
                    )
                    self.set_device_state(DeviceState.LISTENING)
                else:
                    self.set_device_state(DeviceState.IDLE)

            # 安排延迟执行
            threading.Thread(target=delayed_state_change, daemon=True).start()

    def _handle_stt_message(self, data):
        """处理STT消息"""
        text = data.get("text", "")
        if text:
            logger.info(f">> {text}")
            self.schedule(lambda: self.set_chat_message("user", text))

    def _handle_llm_message(self, data):
        """处理LLM消息"""
        emotion = data.get("emotion", "")
        if emotion:
            self.schedule(lambda: self.set_emotion(emotion))

    async def _on_audio_channel_opened(self):
        """音频通道打开回调"""
        logger.info("音频通道已打开")
        self.schedule(lambda: self._start_audio_streams())

    def _start_audio_streams(self):
        """启动音频流"""
        try:
            # 确保流已关闭后再重新打开
            if self.input_stream:
                if self.input_stream.is_active():
                    self.input_stream.stop_stream()

                # 重新打开流
                self.input_stream.start_stream()

            if self.output_stream:
                if self.output_stream.is_active():
                    self.output_stream.stop_stream()

                # 重新打开流
                self.output_stream.start_stream()

            # 设置事件触发器
            threading.Thread(target=self._audio_input_event_trigger, daemon=True).start()
            threading.Thread(target=self._audio_output_event_trigger, daemon=True).start()

            logger.info("音频流已启动")
        except Exception as e:
            logger.error(f"启动音频流失败: {e}")

    def _audio_input_event_trigger(self):
        """音频输入事件触发器"""
        while self.running:
            try:
                if self.input_stream and self.input_stream.is_active():
                    self.events[EventType.AUDIO_INPUT_READY_EVENT].set()
            except OSError as e:
                logger.error(f"音频输入流错误: {e}")
                # 如果流已关闭，尝试重新打开或者退出循环
                if "Stream not open" in str(e):
                    break
            except Exception as e:
                logger.error(f"音频输入事件触发器错误: {e}")

            time.sleep(AudioConfig.FRAME_DURATION / 1000)  # 按帧时长触发

    def _audio_output_event_trigger(self):
        """音频输出事件触发器"""
        while self.running and self.output_stream and self.output_stream.is_active():
            # 当队列中有足够的数据时才触发事件
            if self.audio_decode_queue.qsize() >= 5:  # 与上面保持一致
                self.events[EventType.AUDIO_OUTPUT_READY_EVENT].set()
            time.sleep(0.02)  # 稍微延长检查间隔

    async def _on_audio_channel_closed(self):
        """音频通道关闭回调"""
        logger.info("音频通道已关闭")
        self.schedule(lambda: self._stop_audio_streams())

    def _stop_audio_streams(self):
        """停止音频流"""
        try:
            if self.input_stream and self.input_stream.is_active():
                self.input_stream.stop_stream()

            if self.output_stream and self.output_stream.is_active():
                self.output_stream.stop_stream()

            logger.info("音频流已停止")
        except Exception as e:
            logger.error(f"停止音频流失败: {e}")

    def set_device_state(self, state):
        """设置设备状态"""
        if self.device_state == state:
            return

        old_state = self.device_state
        self.device_state = state
        logger.info(f"状态变更: {old_state} -> {state}")

        # 根据状态执行相应操作
        if state == DeviceState.IDLE:
            self.display.update_status("待命")
            self.display.update_emotion("😶")
            # 停止输出流但不关闭它
            if self.output_stream and self.output_stream.is_active():
                try:
                    self.output_stream.stop_stream()
                except Exception as e:
                    logger.warning(f"停止输出流时出错: {e}")
        elif state == DeviceState.CONNECTING:
            self.display.update_status("连接中...")
        elif state == DeviceState.LISTENING:
            self.display.update_status("聆听中...")
            self.display.update_emotion("🙂")
            if self.input_stream and not self.input_stream.is_active():
                try:
                    self.input_stream.start_stream()
                except Exception as e:
                    logger.warning(f"启动输入流时出错: {e}")
                    self._reinitialize_input_stream()
        elif state == DeviceState.SPEAKING:
            self.display.update_status("说话中...")
            # 确保输出流处于活跃状态
            if self.output_stream:
                if not self.output_stream.is_active():
                    try:
                        self.output_stream.start_stream()
                    except Exception as e:
                        logger.warning(f"启动输出流时出错: {e}")
                        self._reinitialize_output_stream()
            # 停止输入流
            if self.input_stream and self.input_stream.is_active():
                try:
                    self.input_stream.stop_stream()
                except Exception as e:
                    logger.warning(f"停止输入流时出错: {e}")

        # 通知状态变化
        for callback in self.on_state_changed_callbacks:
            try:
                callback(state)
            except Exception as e:
                logger.error(f"执行状态变化回调时出错: {e}")

    def _get_status_text(self):
        """获取当前状态文本"""
        states = {
            DeviceState.IDLE: "待命",
            DeviceState.CONNECTING: "连接中...",
            DeviceState.LISTENING: "聆听中...",
            DeviceState.SPEAKING: "说话中..."
        }
        return states.get(self.device_state, "未知")

    def _get_current_text(self):
        """获取当前显示文本"""
        return self.current_text

    def _get_current_emotion(self):
        """获取当前表情"""
        emotions = {
            "neutral": "😶",
            "happy": "🙂",
            "laughing": "😆",
            "funny": "😂",
            "sad": "😔",
            "angry": "😠",
            "crying": "😭",
            "loving": "😍",
            "embarrassed": "😳",
            "surprised": "😲",
            "shocked": "😱",
            "thinking": "🤔",
            "winking": "😉",
            "cool": "😎",
            "relaxed": "😌",
            "delicious": "🤤",
            "kissy": "😘",
            "confident": "😏",
            "sleepy": "😴",
            "silly": "😜",
            "confused": "🙄"
        }
        return emotions.get(self.current_emotion, "😶")

    def set_chat_message(self, role, message):
        """设置聊天消息"""
        self.current_text = message
        # 更新显示
        if self.display:
            self.display.update_text(message)

    def set_emotion(self, emotion):
        """设置表情"""
        self.current_emotion = emotion
        # 更新显示
        if self.display:
            self.display.update_emotion(self._get_current_emotion())

    def start_listening(self):
        """开始监听"""
        self.schedule(self._start_listening_impl)

    def _start_listening_impl(self):
        """开始监听的实现"""
        if not self.protocol:
            logger.error("协议未初始化")
            return

        self.keep_listening = False

        if self.device_state == DeviceState.IDLE:
            if not self.protocol.is_audio_channel_opened():
                self.set_device_state(DeviceState.CONNECTING)

                asyncio.run_coroutine_threadsafe(
                    self._open_audio_channel_and_start_manual_listening(),
                    self.loop
                )
            else:
                asyncio.run_coroutine_threadsafe(
                    self.protocol.send_start_listening(ListeningMode.MANUAL),
                    self.loop
                )
                self.set_device_state(DeviceState.LISTENING)
        elif self.device_state == DeviceState.SPEAKING:
            self.abort_speaking(AbortReason.WAKE_WORD_DETECTED)

    async def _open_audio_channel_and_start_manual_listening(self):
        """打开音频通道并开始手动监听"""
        if not await self.protocol.open_audio_channel():
            self.set_device_state(DeviceState.IDLE)
            self.alert("错误", "打开音频通道失败")
            return

        await self.protocol.send_start_listening(ListeningMode.MANUAL)
        self.set_device_state(DeviceState.LISTENING)

    def toggle_chat_state(self):
        """切换聊天状态"""
        self.schedule(self._toggle_chat_state_impl)

    def _toggle_chat_state_impl(self):
        """切换聊天状态的具体实现"""
        # 检查协议是否已初始化
        if not self.protocol:
            logger.error("协议未初始化")
            return

        # 如果设备当前处于空闲状态，尝试连接并开始监听
        if self.device_state == DeviceState.IDLE:
            self.set_device_state(DeviceState.CONNECTING)  # 设置设备状态为连接中

            # 尝试打开音频通道
            if not self.protocol.is_audio_channel_opened():
                asyncio.run_coroutine_threadsafe(
                    self.protocol.open_audio_channel(),
                    self.loop
                )
                if not self.protocol.is_audio_channel_opened():
                    self.alert("错误", "打开音频通道失败")  # 弹出错误提示
                    self.set_device_state(DeviceState.IDLE)  # 设置设备状态为空闲
                    return

            self.keep_listening = True  # 开始监听
            # 启动自动停止的监听模式
            asyncio.run_coroutine_threadsafe(
                self.protocol.send_start_listening(ListeningMode.AUTO_STOP),
                self.loop
            )
            self.set_device_state(DeviceState.LISTENING)  # 设置设备状态为监听中

        # 如果设备正在说话，停止当前说话
        elif self.device_state == DeviceState.SPEAKING:
            self.abort_speaking(AbortReason.NONE)  # 中止说话

        # 如果设备正在监听，关闭音频通道
        elif self.device_state == DeviceState.LISTENING:
            asyncio.run_coroutine_threadsafe(
                self.protocol.close_audio_channel(),
                self.loop
            )

    def stop_listening(self):
        """停止监听"""
        self.schedule(self._stop_listening_impl)

    def _stop_listening_impl(self):
        """停止监听的实现"""
        if self.device_state == DeviceState.LISTENING:
            asyncio.run_coroutine_threadsafe(
                self.protocol.send_stop_listening(),
                self.loop
            )
            self.set_device_state(DeviceState.IDLE)

    def abort_speaking(self, reason):
        """中止语音输出"""
        logger.info(f"中止语音输出，原因: {reason}")
        self.aborted = True
        asyncio.run_coroutine_threadsafe(
            self.protocol.send_abort_speaking(reason),
            self.loop
        )

        # 添加此代码：当用户主动打断时自动进入录音模式
        if reason == AbortReason.WAKE_WORD_DETECTED:
            # 短暂延迟确保abort命令被处理
            def start_listening_after_abort():
                time.sleep(0.2)  # 短暂延迟
                self.schedule(lambda: self._start_listening_impl())

            threading.Thread(target=start_listening_after_abort, daemon=True).start()

    def alert(self, title, message):
        """显示警告信息"""
        logger.warning(f"警告: {title}, {message}")
        # 在GUI上显示警告
        if self.display:
            self.display.update_text(f"{title}: {message}")

    def on_state_changed(self, callback):
        """注册状态变化回调"""
        self.on_state_changed_callbacks.append(callback)

    def shutdown(self):
        """关闭应用程序"""
        logger.info("正在关闭应用程序...")
        self.running = False

        # 关闭音频流
        if self.input_stream:
            if self.input_stream.is_active():
                self.input_stream.stop_stream()
            self.input_stream.close()

        if self.output_stream:
            if self.output_stream.is_active():
                self.output_stream.stop_stream()
            self.output_stream.close()

        if self.audio:
            self.audio.terminate()

        # 关闭协议
        if self.protocol:
            asyncio.run_coroutine_threadsafe(
                self.protocol.close_audio_channel(),
                self.loop
            )

        # 停止事件循环
        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)

        # 等待事件循环线程结束
        if self.loop_thread and self.loop_thread.is_alive():
            self.loop_thread.join(timeout=1.0)

        # 关闭视觉处理
        if self.vision_processor:
            self.vision_processor.stop()
            self.vision_enabled = False

        logger.info("应用程序已关闭")

    def _handle_verification_code(self, text):
        """处理验证码信息"""
        try:
            # 提取验证码
            import re
            verification_code = re.search(r'验证码：(\d+)', text)
            if verification_code:
                code = verification_code.group(1)

                # 尝试复制到剪贴板
                try:
                    import pyperclip
                    pyperclip.copy(code)
                    logger.info(f"验证码 {code} 已复制到剪贴板")
                except Exception as e:
                    logger.warning(f"无法复制验证码到剪贴板: {e}")

                # 尝试打开浏览器
                try:
                    import webbrowser
                    if webbrowser.open("https://xiaozhi.me/login"):
                        logger.info("已打开登录页面")
                    else:
                        logger.warning("无法打开浏览器")
                except Exception as e:
                    logger.warning(f"打开浏览器时出错: {e}")

                # 无论如何都显示验证码
                self.alert("验证码", f"您的验证码是: {code}")

        except Exception as e:
            logger.error(f"处理验证码时出错: {e}")

    def _on_mode_changed(self, auto_mode):
        """处理对话模式变更"""
        # 只有在IDLE状态下才允许切换模式
        if self.device_state != DeviceState.IDLE:
            self.alert("提示", "只有在待命状态下才能切换对话模式")
            return False

        self.keep_listening = auto_mode
        logger.info(f"对话模式已切换为: {'自动' if auto_mode else '手动'}")
        return True

    def _reinitialize_input_stream(self):
        """重新初始化音频输入流"""
        logger.info("正在重新初始化音频输入流...")
        try:
            # 关闭现有流
            if self.input_stream:
                try:
                    if self.input_stream.is_active():
                        self.input_stream.stop_stream()
                    self.input_stream.close()
                except Exception as e:
                    logger.warning(f"关闭现有输入流时出错: {e}")
            
            # 创建新的输入流
            self.input_stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=AudioConfig.CHANNELS,
                rate=AudioConfig.SAMPLE_RATE,
                input=True,
                frames_per_buffer=AudioConfig.FRAME_SIZE
            )
            
            logger.info("音频输入流重新初始化成功")
        except Exception as e:
            logger.error(f"重新初始化音频输入流失败: {e}")
            self.alert("错误", f"重新初始化音频设备失败: {e}")

    async def _on_connection_state_changed(self, connected):
        """处理连接状态变化"""
        if self.display:
            self.display.update_connection_status(connected)

    def _setup_protocol_callbacks(self):
        """设置协议回调函数"""
        # 添加连接状态回调
        if isinstance(self.protocol, WebsocketProtocol):
            self.protocol.on_connection_state_changed = lambda connected: asyncio.run_coroutine_threadsafe(
                self._on_connection_state_changed(connected), self.loop
            )

    def _init_vision(self, camera_id):
        """初始化视觉功能"""
        try:
            # 加载视觉配置
            logger.info("开始加载视觉配置...")
            self.vision_config = VisionConfig.load_config()
            logger.info(f"视觉配置加载完成: {self.vision_config}")
            
            # 检查API密钥
            if not self.vision_config['api_key']:
                logger.error("API密钥为空，请在config/vision_config.json中配置有效的API密钥")
                self.alert("错误", "API密钥为空，请配置有效的API密钥")
                return
            
            # 更新摄像头ID
            if camera_id != self.vision_config['camera_id']:
                self.vision_config['camera_id'] = camera_id
                VisionConfig.save_config(self.vision_config)
            
            # 创建视觉处理器
            logger.info(f"创建视觉处理器，摄像头ID: {self.vision_config['camera_id']}")
            self.vision_processor = VisionProcessor(
                camera_id=self.vision_config['camera_id'],
                api_key=self.vision_config['api_key']
            )
            
            # 设置处理间隔 - 这个设置在基于关键词触发模式下不再使用
            self.vision_processor.set_process_interval(self.vision_config['process_interval'])
            
            # 设置视觉结果回调
            self.vision_processor.on_vision_result = self._on_vision_result
            
            # 启动视觉处理
            logger.info("尝试启动视觉处理器...")
            if self.vision_processor.start():
                self.vision_enabled = True
                logger.info("视觉功能已启用")
                
                # 不再启动自动捕获，改为基于关键词触发
                # if self.vision_config['auto_capture']:
                #     logger.info("启动自动视觉捕获...")
                #     self._start_auto_vision_capture()
            else:
                logger.error("视觉功能启动失败")
                self.alert("错误", "视觉功能启动失败，请检查摄像头连接")
        except Exception as e:
            logger.error(f"初始化视觉功能失败: {e}", exc_info=True)
            self.alert("错误", f"初始化视觉功能失败: {str(e)}")

    def _on_vision_result(self, vision_text):
        """处理视觉识别结果"""
        logger.info(f"收到视觉识别结果: {vision_text[:50]}...")
        
        # 更新当前文本
        self.current_text = f"[视觉识别] {vision_text}"
        
        # 如果显示界面存在，更新界面
        if self.display:
            self.display.update_text(self.current_text)
        
        # 可以在这里添加更多处理逻辑，例如将视觉结果发送到对话系统

    def _start_auto_vision_capture(self):
        """启动自动视觉捕获"""
        if not self.vision_enabled or not self.vision_processor:
            return
        
        def auto_capture():
            while self.running and self.vision_enabled:
                # 只在IDLE状态下自动捕获
                if self.device_state == DeviceState.IDLE:
                    # 获取当前帧并处理
                    frame = self.vision_processor.get_current_frame()
                    if frame is not None:
                        self.vision_processor._process_image(frame.copy())
                
                # 等待下一次捕获
                time.sleep(self.vision_config['process_interval'])
        
        # 启动自动捕获线程
        threading.Thread(target=auto_capture, daemon=True).start()
        logger.info("自动视觉捕获已启动")

    def _trigger_vision_capture(self):
        """触发视觉捕获"""
        if not self.vision_enabled or not self.vision_processor:
            self.alert("提示", "视觉功能未启用")
            return
        
        try:
            # 获取当前帧
            frame = self.vision_processor.get_current_frame()
            if frame is None:
                self.alert("错误", "无法获取摄像头画面")
                return
            
            # 处理图像
            self.vision_processor._process_image(frame.copy())
            self.alert("提示", "正在处理图像...")
        except Exception as e:
            logger.error(f"触发视觉捕获失败: {e}")
            self.alert("错误", f"视觉捕获失败: {e}")

    def _on_text_received(self, text):
        """处理接收到的文本"""
        logger.info(f"收到文本: {text}")
        
        # 检查是否包含视觉相关关键词
        vision_keywords = ["屏幕", "画面", "图片", "看到", "看见", "照片", "摄像头"]
        should_trigger_vision = False
        
        for keyword in vision_keywords:
            if keyword in text:
                should_trigger_vision = True
                break
        
        # 如果包含视觉关键词且视觉功能已启用，触发图像分析
        vision_result = ""
        if should_trigger_vision and self.vision_enabled and self.vision_processor:
            logger.info(f"检测到视觉关键词: '{text}'，触发图像分析")
            
            # 获取当前帧
            frame = self.vision_processor.get_current_frame()
            if frame is not None:
                # 处理图像并等待结果
                vision_result = self._process_image_and_wait(frame.copy())
                
                if vision_result:
                    # 将视觉结果添加到用户文本中
                    text = f"{text}（图像分析：{vision_result}）"
                    logger.info(f"合并后的文本: {text[:100]}...")
        
        # 如果显示界面存在，更新界面
        if self.display:
            self.display.update_text(text)
        
        # 发送文本到协议处理器
        if self.protocol and self.protocol.connected:
            asyncio.run_coroutine_threadsafe(
                self.protocol.send_text(text), self.loop
            )
        else:
            logger.warning("协议处理器未连接，无法发送文本")
            self.alert("错误", "未连接到服务器，无法发送文本")

    def _process_image_and_wait(self, frame, timeout=5):
        """处理图像并等待结果
        
        Args:
            frame: 图像帧
            timeout: 超时时间（秒）
            
        Returns:
            str: 视觉识别结果，超时或失败返回空字符串
        """
        result_event = threading.Event()
        result_container = {"text": ""}
        
        def vision_callback(text):
            result_container["text"] = text
            result_event.set()
        
        # 保存原始回调
        original_callback = self.vision_processor.on_vision_result
        
        try:
            # 设置临时回调
            self.vision_processor.on_vision_result = vision_callback
            
            # 处理图像
            self.vision_processor._process_image(frame)
            
            # 等待结果或超时
            if result_event.wait(timeout=timeout):
                return result_container["text"]
            else:
                logger.warning(f"视觉识别超时（{timeout}秒）")
                return ""
        finally:
            # 恢复原始回调
            self.vision_processor.on_vision_result = original_callback

    def _on_speech_recognized(self, text):
        """处理语音识别结果"""
        logger.info(f">> {text}")
        logger.info("开始检查视觉关键词...")
        
        # 检查是否包含视觉相关关键词
        vision_keywords = ["屏幕", "画面", "图片", "看到", "看见", "照片", "摄像头"]
        should_trigger_vision = False
        
        for keyword in vision_keywords:
            if keyword in text:
                should_trigger_vision = True
                logger.info(f"检测到视觉关键词: '{keyword}'")
                break
        
        # 如果包含视觉关键词且视觉功能已启用，触发图像分析
        vision_result = ""
        if should_trigger_vision:
            logger.info("准备触发视觉分析...")
            if self.vision_enabled and self.vision_processor:
                logger.info(f"视觉功能已启用，开始分析图像")
                
                # 获取当前帧
                frame = self.vision_processor.get_current_frame()
                if frame is not None:
                    logger.info(f"成功获取图像帧，尺寸: {frame.shape}")
                    # 处理图像并等待结果
                    vision_result = self._process_image_and_wait(frame.copy())
                    
                    if vision_result:
                        logger.info(f"获取到视觉分析结果: {vision_result[:50]}...")
                        # 将视觉结果添加到用户文本中
                        text = f"{text}（图像分析：{vision_result}）"
                        logger.info(f"合并后的文本: {text[:100]}...")
                    else:
                        logger.warning("视觉分析未返回结果")
                else:
                    logger.warning("无法获取摄像头画面")
            else:
                logger.warning(f"视觉功能未启用或处理器未初始化: enabled={self.vision_enabled}, processor={self.vision_processor is not None}")
        
        # 更新当前文本
        self.current_text = text
        
        # 如果显示界面存在，更新界面
        if self.display:
            self.display.update_text(text)
        
        # 发送文本到协议处理器
        if self.protocol and self.protocol.connected:
            asyncio.run_coroutine_threadsafe(
                self.protocol.send_text(text), self.loop
            )
        else:
            logger.warning("协议处理器未连接，无法发送文本")
            self.alert("错误", "未连接到服务器，无法发送文本")
        
        # 更新状态
        self.set_device_state(DeviceState.SPEAKING)

    def _on_asr_result(self, text, is_final=False):
        """处理ASR结果"""
        if not is_final:
            # 非最终结果，更新界面显示
            if self.display:
                self.display.update_text(text)
            return
        
        # 最终结果，处理语音识别
        if text:
            # 调用语音识别处理方法
            self._on_speech_recognized(text)