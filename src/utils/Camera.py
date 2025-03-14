import cv2
import base64
import json
import logging
from pathlib import Path
import threading

logger = logging.getLogger(__name__)

class CameraManager:
    """摄像头管理器 - 单例模式"""

    _instance = None
    _lock = threading.Lock()

    # 配置文件路径
    CONFIG_DIR = Path(__file__).parent.parent.parent / "config"
    CONFIG_FILE = CONFIG_DIR / "camera_config.json"

    # 默认配置
    DEFAULT_CONFIG = {
        "camera_index": 0,  # 默认摄像头索引
        "frame_width": 640,  # 帧宽度
        "frame_height": 480,  # 帧高度
        "fps": 30,  # 帧率
    }

    def __new__(cls):
        """确保单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """初始化摄像头管理器"""
        if hasattr(self, '_initialized'):
            return
        self._initialized = True

        # 加载配置
        self._config = self._load_config()
        self.cap = None
        self.is_running = False
        self.camera_thread = None

    def _load_config(self):
        """加载配置文件，如果不存在则创建"""
        try:
            if self.CONFIG_FILE.exists():
                config = json.loads(self.CONFIG_FILE.read_text(encoding='utf-8'))
                return self._merge_configs(self.DEFAULT_CONFIG, config)
            else:
                # 创建默认配置
                self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
                self._save_config(self.DEFAULT_CONFIG)
                return self.DEFAULT_CONFIG.copy()
        except Exception as e:
            logger.error(f"加载配置出错: {e}")
            return self.DEFAULT_CONFIG.copy()

    def _save_config(self, config):
        """保存配置到文件"""
        try:
            self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            self.CONFIG_FILE.write_text(
                json.dumps(config, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )
            return True
        except Exception as e:
            logger.error(f"保存配置出错: {e}")
            return False

    @staticmethod
    def _merge_configs(default, custom):
        """递归合并配置字典"""
        result = default.copy()
        for key, value in custom.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = CameraManager._merge_configs(result[key], value)
            else:
                result[key] = value
        return result

    def get_config(self, path, default=None):
        """
        通过路径获取配置值
        path: 点分隔的配置路径，如 "camera_index"
        """
        try:
            value = self._config
            for key in path.split('.'):
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default

    def update_config(self, path, value):
        """
        更新特定配置项
        path: 点分隔的配置路径，如 "camera_index"
        """
        try:
            current = self._config
            *parts, last = path.split('.')
            for part in parts:
                current = current.setdefault(part, {})
            current[last] = value
            return self._save_config(self._config)
        except Exception as e:
            logger.error(f"更新配置出错 {path}: {e}")
            return False

    def _camera_loop(self):
        """摄像头线程的主循环"""
        try:
            camera_index = self.get_config("camera_index")
            logger.info(f"正在打开摄像头 (索引: {camera_index})...")
            
            # 先尝试释放可能存在的上一个摄像头对象
            if self.cap is not None:
                self.cap.release()
                self.cap = None
                
            # 尝试打开摄像头
            self.cap = cv2.VideoCapture(camera_index)
            
            # 如果打开失败，尝试其他摄像头索引
            if not self.cap.isOpened():
                logger.warning(f"无法打开摄像头索引 {camera_index}，尝试其他索引...")
                # 尝试索引0和1
                for alt_index in [0, 1]:
                    if alt_index != camera_index:
                        logger.info(f"尝试摄像头索引 {alt_index}")
                        self.cap = cv2.VideoCapture(alt_index)
                        if self.cap.isOpened():
                            # 更新配置
                            self.update_config("camera_index", alt_index)
                            logger.info(f"成功打开摄像头索引 {alt_index}")
                            break
                
            # 如果仍然无法打开，则退出
            if not self.cap.isOpened():
                logger.error("无法打开任何摄像头")
                self.is_running = False
                return

            # 设置摄像头参数
            frame_width = self.get_config("frame_width")
            frame_height = self.get_config("frame_height")
            fps = self.get_config("fps")
            
            logger.info(f"设置摄像头参数: {frame_width}x{frame_height}@{fps}fps")
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, frame_width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, frame_height)
            self.cap.set(cv2.CAP_PROP_FPS, fps)

            # 首次读取一帧测试连接
            ret, _ = self.cap.read()
            if not ret:
                logger.error("摄像头连接成功但无法读取图像")
                self.is_running = False
                return
                
            logger.info("摄像头初始化成功并开始运行")
            self.is_running = True
            
            failed_reads = 0  # 用于跟踪连续读取失败的次数
            max_failed_reads = 5  # 最大连续失败次数
            
            while self.is_running:
                try:
                    ret, frame = self.cap.read()
                    if not ret:
                        failed_reads += 1
                        logger.warning(f"无法读取画面 (连续失败: {failed_reads}/{max_failed_reads})")
                        
                        # 如果连续失败多次，尝试重新初始化摄像头
                        if failed_reads >= max_failed_reads:
                            logger.error("连续多次读取失败，尝试重新初始化摄像头")
                            if self.cap is not None:
                                self.cap.release()
                            self.cap = cv2.VideoCapture(camera_index)
                            
                            if not self.cap.isOpened():
                                logger.error("重新初始化摄像头失败")
                                self.is_running = False
                                break
                                
                            # 重置失败计数
                            failed_reads = 0
                            
                        # 短暂等待后继续
                        import time
                        time.sleep(0.1)
                        continue
                    
                    # 读取成功，重置失败计数
                    failed_reads = 0
                    
                    # 显示画面
                    cv2.imshow('Camera', frame)

                    # 按下 'q' 键退出
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        logger.info("用户按下q键，退出摄像头")
                        self.is_running = False
                        
                except Exception as e:
                    logger.error(f"摄像头处理帧时出错: {e}")
                    failed_reads += 1
                    
                    # 如果错误过多，重置摄像头
                    if failed_reads >= max_failed_reads:
                        logger.error("摄像头错误过多，尝试重置")
                        if self.cap is not None:
                            self.cap.release()
                        self.cap = cv2.VideoCapture(camera_index)
                        failed_reads = 0
        except Exception as e:
            logger.error(f"摄像头线程发生异常: {e}")
        finally:
            # 释放摄像头并关闭窗口
            self.is_running = False
            if self.cap is not None:
                self.cap.release()
                self.cap = None
            cv2.destroyAllWindows()
            logger.info("摄像头线程已结束")

    def start_camera(self):
        """启动摄像头线程"""
        with self._lock:  # 使用锁确保线程安全
            try:
                # 如果线程已存在并且还在运行，不需要重新启动
                if self.camera_thread is not None and self.camera_thread.is_alive():
                    if self.is_running:
                        logger.warning("摄像头线程已在运行")
                        return True
                    else:
                        # 线程存在但可能停止运行，需要重新创建
                        logger.warning("摄像头线程存在但已停止运行，重新创建线程")
                        self.stop_camera()  # 确保彻底停止
                
                # 创建并启动新线程
                self.camera_thread = threading.Thread(target=self._camera_loop, daemon=True, name="CameraThread")
                self.camera_thread.start()
                
                # 等待摄像头初始化完成
                import time
                max_wait = 3.0  # 最多等待3秒
                wait_interval = 0.1
                waited = 0
                
                while waited < max_wait:
                    if self.is_running:
                        logger.info(f"摄像头线程已启动，用时 {waited:.1f} 秒")
                        return True
                    time.sleep(wait_interval)
                    waited += wait_interval
                
                # 如果等待超时仍未启动，记录错误
                if not self.is_running:
                    logger.error("摄像头启动超时")
                    return False
                    
                return True
            except Exception as e:
                logger.error(f"启动摄像头线程时出错: {e}")
                return False

    def capture_frame_to_base64(self):
        """截取当前画面并转换为 Base64 编码"""
        if not self.cap or not self.cap.isOpened():
            logger.error("摄像头未打开")
            return None

        # 尝试多次读取，防止偶发的读取失败
        max_attempts = 3
        for attempt in range(max_attempts):
            ret, frame = self.cap.read()
            if ret:
                break
            logger.warning(f"无法读取画面，尝试重试 {attempt+1}/{max_attempts}")
            import time
            time.sleep(0.1)
            
        if not ret:
            logger.error(f"经过 {max_attempts} 次尝试后仍无法读取画面")
            return None

        try:
            # 将帧转换为 JPEG 格式
            _, buffer = cv2.imencode('.jpg', frame)

            # 将 JPEG 图像转换为 Base64 编码
            frame_base64 = base64.b64encode(buffer).decode('utf-8')
            return frame_base64
        except Exception as e:
            logger.error(f"转换图像为Base64时出错: {e}")
            return None
        
    def stop_camera(self):
        """停止摄像头线程"""
        with self._lock:  # 使用锁确保线程安全
            try:
                # 标记线程应该停止
                self.is_running = False
                
                # 等待线程结束
                if self.camera_thread is not None:
                    if self.camera_thread.is_alive():
                        self.camera_thread.join(timeout=2.0)  # 等待线程结束，最多等待2秒
                        
                    if self.camera_thread.is_alive():
                        logger.warning("摄像头线程无法在超时时间内停止")
                    else:
                        logger.info("摄像头线程已正常停止")
                        
                    self.camera_thread = None
                
                # 释放摄像头资源
                if self.cap is not None:
                    self.cap.release()
                    self.cap = None
                    
                # 关闭所有OpenCV窗口
                cv2.destroyAllWindows()
                
                return True
            except Exception as e:
                logger.error(f"停止摄像头时出错: {e}")
                return False

    @classmethod
    def get_instance(cls):
        """获取摄像头管理器实例（线程安全）"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
        return cls._instance 