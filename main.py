import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import sqlite3
import hashlib
from datetime import datetime
import cv2
from PIL import Image, ImageTk
import threading
import numpy as np
import time
import winsound  # 用于播放报警声音
import smtplib  # 用于邮件报警
from email.mime.text import MIMEText

# 颜色主题
THEME = {
    "primary": "#2c3e50",
    "secondary": "#34495e",
    "accent": "#e74c3c",
    "text": "#ecf0f1",
    "success": "#27ae60",
    "warning": "#f39c12",
    "danger": "#e74c3c",
    "background": "#bdc3c7"
}

# 报警配置
ALARM_CONFIG = {
    "sound_alarm": True,  # 启用声音报警
    "email_alarm": False,  # 启用邮件报警
    "email_sender": "your_email@example.com",
    "email_password": "your_password",
    "email_receiver": "receiver@example.com",
    "smtp_server": "smtp.example.com",
    "smtp_port": 587
}


# 初始化数据库
def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
              (id INTEGER PRIMARY KEY AUTOINCREMENT,
               username TEXT UNIQUE NOT NULL,
               password TEXT NOT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS alarm_logs
              (id INTEGER PRIMARY KEY AUTOINCREMENT,
               alarm_time TEXT NOT NULL,
               alarm_type TEXT NOT NULL,
               location TEXT,
               description TEXT)''')
    # 添加一个测试用户
    try:
        hashed_pwd = hashlib.sha256("123456".encode()).hexdigest()
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)",
                  ("admin", hashed_pwd))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()


# 登录验证
def login():
    username = username_entry.get()
    password = password_entry.get()

    if not username or not password:
        messagebox.showerror("错误", "用户名和密码不能为空")
        return

    hashed_pwd = hashlib.sha256(password.encode()).hexdigest()

    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username=? AND password=?",
              (username, hashed_pwd))
    user = c.fetchone()
    conn.close()

    if user:
        login_window.destroy()
        show_video_analysis_system(username)
    else:
        messagebox.showerror("登录失败", "用户名或密码错误")


# 火灾检测函数 - 基于颜色和运动特征
def detect_fire(frame):
    # 转换到HSV色彩空间
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    # 定义火灾颜色范围（红色和橙色）
    lower_fire = np.array([0, 120, 70])
    upper_fire = np.array([20, 255, 255])
    lower_fire2 = np.array([160, 120, 70])
    upper_fire2 = np.array([180, 255, 255])

    # 创建火灾颜色掩膜
    mask1 = cv2.inRange(hsv, lower_fire, upper_fire)
    mask2 = cv2.inRange(hsv, lower_fire2, upper_fire2)
    fire_mask = cv2.bitwise_or(mask1, mask2)

    # 形态学操作去除噪声
    kernel = np.ones((5, 5), np.uint8)
    fire_mask = cv2.morphologyEx(fire_mask, cv2.MORPH_OPEN, kernel)
    fire_mask = cv2.morphologyEx(fire_mask, cv2.MORPH_CLOSE, kernel)

    # 计算火灾区域面积
    fire_area = cv2.countNonZero(fire_mask)
    total_area = frame.shape[0] * frame.shape[1]
    fire_ratio = fire_area / total_area

    # 如果火灾区域超过一定比例，则认为检测到火灾
    return fire_ratio > 0.01, fire_mask  # 1%的面积阈值


# 报警处理类
class AlarmHandler:
    @staticmethod
    def trigger_alarm(alarm_type, location=None, description=None):
        # 记录报警日志
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("INSERT INTO alarm_logs (alarm_time, alarm_type, location, description) VALUES (?, ?, ?, ?)",
                  (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), alarm_type, location or "未知", description or "无"))
        conn.commit()
        conn.close()

        # 播放报警声音
        if ALARM_CONFIG["sound_alarm"]:
            try:
                winsound.Beep(1000, 1000)  # 频率1000Hz，持续1秒
            except:
                pass

        # 发送邮件报警
        if ALARM_CONFIG["email_alarm"] and ALARM_CONFIG["email_sender"] and ALARM_CONFIG["email_receiver"]:
            try:
                msg = MIMEText(
                    f"火灾报警触发\n类型: {alarm_type}\n时间: {datetime.now()}\n位置: {location}\n描述: {description}")
                msg['Subject'] = f"火灾报警 - {alarm_type}"
                msg['From'] = ALARM_CONFIG["email_sender"]
                msg['To'] = ALARM_CONFIG["email_receiver"]

                with smtplib.SMTP(ALARM_CONFIG["smtp_server"], ALARM_CONFIG["smtp_port"]) as server:
                    server.starttls()
                    server.login(ALARM_CONFIG["email_sender"], ALARM_CONFIG["email_password"])
                    server.send_message(msg)
            except Exception as e:
                print(f"邮件发送失败: {e}")


# 视频分析系统界面
class VideoAnalysisSystem:
    def __init__(self, username):
        self.username = username
        self.video_source = None
        self.cap = None
        self.analyze = False
        self.fire_detected = False
        self.video_thread = None
        self.prev_frame = None
        self.fps = 0
        self.frame_count = 0
        self.start_time = time.time()
        self.alarm_triggered = False
        self.alarm_handler = AlarmHandler()

        # 创建主窗口
        self.main_window = tk.Tk()
        self.main_window.title(f"智能火灾预警监控系统 - 用户: {username}")
        self.main_window.geometry("1200x800")
        self.main_window.configure(bg=THEME["background"])

        # 窗口居中
        self.center_window(self.main_window, 1200, 800)

        # 设置窗口关闭事件
        self.main_window.protocol("WM_DELETE_WINDOW", self.on_closing)

        # 创建界面
        self.create_ui()

        # 启动主循环
        self.main_window.mainloop()

        # 在VideoAnalysisSystem类中添加以下修改
        class VideoAnalysisSystem:
            DEFAULT_VIDEO_PATH = "fire_demo.mp4"  # 预设视频路径，放在项目根目录下

            def __init__(self, username):
                def create_ui(self, control_panel=None):
                    # 修改视频源选择区域的按钮
                    source_frame = tk.LabelFrame(control_panel, text="视频源设置",
                                                 font=("微软雅黑", 12), bg=THEME["secondary"],
                                                 fg=THEME["text"], padx=10, pady=10)
                    source_frame.pack(fill="x", padx=5, pady=5)

                    # 修改按钮文字和命令
                    tk.Button(source_frame, text="加载测试视频", command=self.load_demo_video,
                              font=("微软雅黑", 10), bg=THEME["primary"], fg=THEME["text"],
                              activebackground=THEME["accent"], activeforeground=THEME["text"]).pack(fill="x", pady=5)

                    tk.Button(source_frame, text="使用真实摄像头", command=self.use_real_camera,
                              font=("微软雅黑", 10), bg=THEME["primary"], fg=THEME["text"],
                              activebackground=THEME["accent"], activeforeground=THEME["text"]).pack(fill="x", pady=5)

                    tk.Button(source_frame, text="选择其他视频", command=self.select_video_file,
                              font=("微软雅黑", 10), bg=THEME["primary"], fg=THEME["text"],
                              activebackground=THEME["accent"], activeforeground=THEME["text"]).pack(fill="x", pady=5)

                    # ... 其余UI代码不变 ...

            def load_demo_video(self):
                """加载预设测试视频"""
                if self.cap is not None:
                    self.cap.release()
                    self.cap = None

                if not os.path.exists(self.DEFAULT_VIDEO_PATH):
                    messagebox.showerror("错误",
                                         f"预设视频文件不存在：\n{self.DEFAULT_VIDEO_PATH}\n"
                                         "请确保文件位于程序目录")
                    return

                self.video_source = self.DEFAULT_VIDEO_PATH
                self.source_label.config(text=f"当前视频源: 测试视频\n{os.path.basename(self.DEFAULT_VIDEO_PATH)}")
                self.start_btn.config(state="normal")
                self.update_status("已加载预设火灾测试视频")

            def use_real_camera(self):
                """使用真实摄像头"""
                if self.cap is not None:
                    self.cap.release()
                    self.cap = None

                # 尝试自动检测可用摄像头
                detected = False
                for index in range(3):  # 尝试0-2号摄像头
                    cap = cv2.VideoCapture(index)
                    if cap.isOpened():
                        detected = True
                        self.video_source = index
                        cap.release()
                        break

                if not detected:
                    messagebox.showerror("错误", "未检测到可用摄像头\n请检查设备连接")
                    return

                self.source_label.config(text=f"当前视频源: 摄像头({self.video_source})")
                self.start_btn.config(state="normal")
                self.update_status(f"已选择摄像头({self.video_source})")

            def start_analysis(self):
                if self.video_source is None:
                    messagebox.showerror("错误", "请先选择视频源")
                    return

                # 添加文件存在检查（如果是文件路径）
                if isinstance(self.video_source, str):
                    if not os.path.exists(self.video_source):
                        messagebox.showerror("错误",
                                             f"视频文件不存在：\n{self.video_source}\n"
                                             "请检查文件路径")
                        return

                try:
                    self.cap = cv2.VideoCapture(self.video_source)
                    if not self.cap.isOpened():
                        raise Exception("无法打开视频源")

                    # 获取视频实际属性
                    width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    self.original_fps = self.cap.get(cv2.CAP_PROP_FPS)

                    # 显示视频参数
                    self.update_status(f"视频参数: {width}x{height} @ {self.original_fps:.1f}FPS")

                    # ... 其余原有代码不变 ...

                except Exception as e:
                    messagebox.showerror("错误", f"无法启动视频分析: {str(e)}")

            # ... 其余方法保持不变 ...

    def center_window(self, window, width, height):
        screen_width = window.winfo_screenwidth()
        screen_height = window.winfo_screenheight()
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        window.geometry(f"{width}x{height}+{x}+{y}")

    def create_ui(self):
        # 主容器
        main_container = tk.Frame(self.main_window, bg=THEME["background"])
        main_container.pack(fill="both", expand=True, padx=10, pady=10)

        # 标题栏
        title_frame = tk.Frame(main_container, bg=THEME["primary"])
        title_frame.pack(fill="x", pady=(0, 10))

        tk.Label(title_frame, text="智能火灾预警监控系统",
                 font=("微软雅黑", 20, "bold"),
                 bg=THEME["primary"], fg=THEME["text"]).pack(pady=10)

        # 用户信息栏
        user_frame = tk.Frame(title_frame, bg=THEME["primary"])
        user_frame.pack(fill="x", pady=(0, 10))

        tk.Label(user_frame,
                 text=f"用户: {self.username} | 登录时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                 font=("微软雅黑", 10),
                 bg=THEME["primary"], fg=THEME["text"]).pack(side="left", padx=10)

        # 报警状态指示灯
        self.alarm_indicator = tk.Label(user_frame, text="■", font=("Arial", 16),
                                        fg="green", bg=THEME["primary"])
        self.alarm_indicator.pack(side="right", padx=10)

        # 主内容区域
        content_frame = tk.Frame(main_container, bg=THEME["background"])
        content_frame.pack(fill="both", expand=True)

        # 左侧控制面板
        control_panel = tk.Frame(content_frame, bg=THEME["secondary"], width=250,
                                 relief=tk.RAISED, borderwidth=2)
        control_panel.pack(side="left", fill="y", padx=(0, 10))
        control_panel.pack_propagate(False)

        # 视频源选择区域
        source_frame = tk.LabelFrame(control_panel, text="视频源设置",
                                     font=("微软雅黑", 12), bg=THEME["secondary"],
                                     fg=THEME["text"], padx=10, pady=10)
        source_frame.pack(fill="x", padx=5, pady=5)

        tk.Button(source_frame, text="选择视频文件", command=self.select_video_file,
                  font=("微软雅黑", 10), bg=THEME["primary"], fg=THEME["text"],
                  activebackground=THEME["accent"], activeforeground=THEME["text"]).pack(fill="x", pady=5)

        tk.Button(source_frame, text="使用摄像头", command=self.use_camera,
                  font=("微软雅黑", 10), bg=THEME["primary"], fg=THEME["text"],
                  activebackground=THEME["accent"], activeforeground=THEME["text"]).pack(fill="x", pady=5)

        self.source_label = tk.Label(source_frame, text="当前视频源: 未选择",
                                     font=("微软雅黑", 10), bg=THEME["secondary"], fg=THEME["text"])
        self.source_label.pack(fill="x", pady=5)

        # 分析控制区域
        analysis_frame = tk.LabelFrame(control_panel, text="分析控制",
                                       font=("微软雅黑", 12), bg=THEME["secondary"],
                                       fg=THEME["text"], padx=10, pady=10)
        analysis_frame.pack(fill="x", padx=5, pady=5)

        self.start_btn = tk.Button(analysis_frame, text="开始分析",
                                   command=self.start_analysis,
                                   state="disabled", font=("微软雅黑", 12),
                                   bg=THEME["success"], fg=THEME["text"],
                                   activebackground="#2ecc71", activeforeground=THEME["text"])
        self.start_btn.pack(fill="x", pady=5)

        self.stop_btn = tk.Button(analysis_frame, text="停止分析",
                                  command=self.stop_analysis,
                                  state="disabled", font=("微软雅黑", 12),
                                  bg=THEME["danger"], fg=THEME["text"],
                                  activebackground="#c0392b", activeforeground=THEME["text"])
        self.stop_btn.pack(fill="x", pady=5)

        tk.Button(analysis_frame, text="手动报警", command=self.manual_alert,
                  font=("微软雅黑", 12), bg=THEME["danger"], fg=THEME["text"],
                  activebackground="#c0392b", activeforeground=THEME["text"]).pack(fill="x", pady=5)

        # 报警设置区域
        settings_frame = tk.LabelFrame(control_panel, text="报警设置",
                                       font=("微软雅黑", 12), bg=THEME["secondary"],
                                       fg=THEME["text"], padx=10, pady=10)
        settings_frame.pack(fill="x", padx=5, pady=5)

        self.sound_var = tk.BooleanVar(value=ALARM_CONFIG["sound_alarm"])
        sound_cb = tk.Checkbutton(settings_frame, text="声音报警",
                                  variable=self.sound_var, font=("微软雅黑", 10),
                                  bg=THEME["secondary"], fg=THEME["text"],
                                  selectcolor=THEME["secondary"])
        sound_cb.pack(anchor="w", pady=2)

        self.email_var = tk.BooleanVar(value=ALARM_CONFIG["email_alarm"])
        email_cb = tk.Checkbutton(settings_frame, text="邮件报警",
                                  variable=self.email_var, font=("微软雅黑", 10),
                                  bg=THEME["secondary"], fg=THEME["text"],
                                  selectcolor=THEME["secondary"])
        email_cb.pack(anchor="w", pady=2)

        # 系统信息区域
        info_frame = tk.LabelFrame(control_panel, text="系统信息",
                                   font=("微软雅黑", 12), bg=THEME["secondary"],
                                   fg=THEME["text"], padx=10, pady=10)
        info_frame.pack(fill="x", padx=5, pady=5)

        self.fps_label = tk.Label(info_frame, text="FPS: 0.0",
                                  font=("微软雅黑", 10), bg=THEME["secondary"], fg=THEME["text"])
        self.fps_label.pack(anchor="w", pady=2)

        self.status_label = tk.Label(info_frame, text="状态: 待机",
                                     font=("微软雅黑", 10), bg=THEME["secondary"], fg=THEME["text"])
        self.status_label.pack(anchor="w", pady=2)

        self.fire_status = tk.Label(info_frame, text="火情: 未检测到",
                                    font=("微软雅黑", 10), bg=THEME["secondary"], fg=THEME["success"])
        self.fire_status.pack(anchor="w", pady=2)

        # 右侧显示区域
        display_panel = tk.Frame(content_frame, bg="black", relief=tk.SUNKEN, borderwidth=2)
        display_panel.pack(side="right", fill="both", expand=True)

        # 视频显示区域
        self.video_panel = tk.Label(display_panel, bg="black")
        self.video_panel.pack(fill="both", expand=True, padx=5, pady=5)

        # 分析结果显示区域
        result_frame = tk.LabelFrame(display_panel, text="分析结果",
                                     font=("微软雅黑", 12), bg=THEME["secondary"],
                                     fg=THEME["text"], padx=10, pady=10)
        result_frame.pack(fill="x", padx=5, pady=(0, 5))

        self.result_text = tk.Text(result_frame, height=8, font=("Consolas", 10),
                                   bg="#2c3e50", fg="white", insertbackground="white")
        self.result_text.pack(fill="both", expand=True)

        scrollbar = ttk.Scrollbar(result_frame, orient="vertical", command=self.result_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.result_text.configure(yscrollcommand=scrollbar.set)

        # 状态栏
        status_bar = tk.Frame(self.main_window, bg=THEME["primary"], height=25)
        status_bar.pack(fill="x", side="bottom")

        self.status_message = tk.Label(status_bar, text="系统就绪",
                                       font=("微软雅黑", 9), bg=THEME["primary"], fg=THEME["text"])
        self.status_message.pack(side="left", padx=10)

        tk.Label(status_bar, text="© 2023 智能火灾预警系统",
                 font=("微软雅黑", 9), bg=THEME["primary"], fg=THEME["text"]).pack(side="right", padx=10)

    def select_video_file(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None

        file_path = filedialog.askopenfilename(
            title="选择视频文件",
            filetypes=[("视频文件", "*.mp4 *.avi *.mov"), ("所有文件", "*.*")]
        )

        if file_path:
            self.video_source = file_path
            self.source_label.config(text=f"当前视频源: 文件\n{file_path[-30:]}" if len(
                file_path) > 30 else f"当前视频源: 文件\n{file_path}")
            self.start_btn.config(state="normal")
            self.update_status(f"已选择视频文件: {file_path}")

    def use_camera(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None

        self.video_source = 0  # 默认摄像头
        self.source_label.config(text="当前视频源: 摄像头(0)")
        self.start_btn.config(state="normal")
        self.update_status("已选择摄像头作为视频源")

    def start_analysis(self):
        if self.video_source is None:
            messagebox.showerror("错误", "请先选择视频源")
            return

        try:
            self.cap = cv2.VideoCapture(self.video_source)
            if not self.cap.isOpened():
                raise Exception("无法打开视频源")

            # 获取视频的原始帧率
            self.original_fps = self.cap.get(cv2.CAP_PROP_FPS)
            if self.original_fps <= 0:
                self.original_fps = 30  # 默认值

            self.frame_delay = int(1000 / self.original_fps)  # 每帧之间的毫秒延迟

            self.analyze = True
            self.start_btn.config(state="disabled")
            self.stop_btn.config(state="normal")
            self.frame_count = 0
            self.start_time = time.time()
            self.alarm_triggered = False
            self.alarm_indicator.config(fg="green")

            # 更新报警配置
            ALARM_CONFIG["sound_alarm"] = self.sound_var.get()
            ALARM_CONFIG["email_alarm"] = self.email_var.get()

            # 启动视频处理线程
            self.video_thread = threading.Thread(target=self.process_video, daemon=True)
            self.video_thread.start()

            self.update_status(f"视频分析已启动 - 原始FPS: {self.original_fps:.1f}")
            self.status_label.config(text=f"状态: 分析中 (FPS: {self.original_fps:.1f})")
        except Exception as e:
            messagebox.showerror("错误", f"无法启动视频分析: {str(e)}")

    def stop_analysis(self):
        self.analyze = False
        if self.cap is not None:
            self.cap.release()
            self.cap = None

        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.update_status("视频分析已停止")
        self.status_label.config(text="状态: 待机")
        self.fire_status.config(text="火情: 未检测到", fg=THEME["success"])
        self.alarm_indicator.config(fg="green")

    def process_video(self):
        while self.analyze and self.cap is not None:
            start_time = time.time()

            ret, frame = self.cap.read()
            if not ret:
                self.analyze = False
                self.main_window.after(0, lambda: messagebox.showinfo(
                    "提示", "视频播放结束"))
                break

            # 火灾检测
            fire_detected, fire_mask = detect_fire(frame)

            # 计算实际FPS
            self.frame_count += 1
            elapsed_time = time.time() - self.start_time
            current_fps = self.frame_count / elapsed_time

            # 更新FPS显示
            self.main_window.after(0, self.fps_label.config,
                                   {"text": f"FPS: {current_fps:.1f}"})

            # 如果检测到火灾，在图像上标记
            if fire_detected:
                if not self.alarm_triggered:
                    self.alarm_triggered = True
                    self.main_window.after(0, self.fire_status.config,
                                           {"text": "火情: 检测到!", "fg": THEME["danger"]})
                    self.main_window.after(0, self.alarm_indicator.config, {"fg": "red"})

                    # 触发报警
                    location = "摄像头画面" if self.video_source == 0 else f"视频文件: {self.video_source}"
                    self.alarm_handler.trigger_alarm("自动检测", location, "系统自动检测到可能的火灾")

                    # 在主线程中更新警告信息
                    self.main_window.after(0, self.add_warning,
                                           f"[{datetime.now().strftime('%H:%M:%S')}] "
                                           f"警告: 检测到可能的火灾! FPS: {current_fps:.1f}")

                # 在图像上标记火灾区域
                contours, _ = cv2.findContours(fire_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                for cnt in contours:
                    if cv2.contourArea(cnt) > 100:  # 只显示面积大于100的区域
                        x, y, w, h = cv2.boundingRect(cnt)
                        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 0, 255), 2)

                cv2.putText(frame, "FIRE DETECTED!", (50, 50),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                cv2.rectangle(frame, (30, 30), (frame.shape[1] - 30, frame.shape[0] - 30),
                              (0, 0, 255), 3)
            else:
                if self.alarm_triggered:
                    self.alarm_triggered = False
                    self.main_window.after(0, self.fire_status.config,
                                           {"text": "火情: 未检测到", "fg": THEME["success"]})
                    self.main_window.after(0, self.alarm_indicator.config, {"fg": "green"})

            # 显示FPS信息
            cv2.putText(frame, f"FPS: {current_fps:.1f}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

            # 转换图像格式用于Tkinter显示
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame)
            img = ImageTk.PhotoImage(image=img)

            # 在主线程中更新图像
            self.main_window.after(0, self.update_video_panel, img)

            # 计算处理时间并添加适当延迟以保持原始帧率
            processing_time = (time.time() - start_time) * 1000  # 转换为毫秒
            remaining_delay = max(1, self.frame_delay - processing_time)
            time.sleep(remaining_delay / 1000)

        # 分析结束后更新UI状态
        self.main_window.after(0, lambda: self.stop_btn.config(state="disabled"))
        self.main_window.after(0, lambda: self.start_btn.config(state="normal"))

    def update_video_panel(self, img):
        self.video_panel.configure(image=img)
        self.video_panel.image = img

    def add_warning(self, message):
        self.result_text.insert(tk.END, message + "\n", "warning")
        self.result_text.see(tk.END)
        self.result_text.tag_config("warning", foreground="red",
                                    font=("Consolas", 10, "bold"))

        # 触发警报声音或通知
        self.main_window.bell()

    def manual_alert(self):
        alert_window = tk.Toplevel(self.main_window)
        alert_window.title("手动报警")
        alert_window.geometry("400x300")
        alert_window.resizable(False, False)
        self.center_window(alert_window, 400, 300)
        alert_window.configure(bg=THEME["background"])

        tk.Label(alert_window, text="手动触发火灾警报",
                 font=("微软雅黑", 16), bg=THEME["background"]).pack(pady=20)

        tk.Label(alert_window, text="位置描述:",
                 font=("微软雅黑", 10), bg=THEME["background"]).pack()
        location_entry = tk.Entry(alert_window, width=40, font=("微软雅黑", 10))
        location_entry.pack(pady=5)

        tk.Label(alert_window, text="报警原因:",
                 font=("微软雅黑", 10), bg=THEME["background"]).pack()
        reason_text = tk.Text(alert_window, height=5, width=40, font=("微软雅黑", 10))
        reason_text.pack(pady=5)

        def confirm_alert():
            location = location_entry.get()
            reason = reason_text.get(1.0, tk.END).strip()

            if not location:
                messagebox.showerror("错误", "请输入位置描述")
                return

            # 触发手动报警
            self.alarm_handler.trigger_alarm("手动报警", location, reason)

            # 更新界面
            self.add_warning(
                f"[{datetime.now().strftime('%H:%M:%S')}] 手动报警: {location} | 原因: {reason if reason else '未说明原因'}"
            )
            self.alarm_indicator.config(fg="red")
            self.fire_status.config(text="火情: 手动报警!", fg=THEME["danger"])

            # 3秒后恢复状态
            self.main_window.after(3000, lambda: self.fire_status.config(
                text="火情: 未检测到", fg=THEME["success"]))
            self.main_window.after(3000, lambda: self.alarm_indicator.config(fg="green"))

            alert_window.destroy()

        tk.Button(alert_window, text="确认报警", command=confirm_alert,
                  bg=THEME["danger"], fg=THEME["text"], font=("微软雅黑", 12),
                  activebackground="#c0392b", activeforeground=THEME["text"]).pack(pady=10)

    def update_status(self, message):
        self.status_message.config(text=message)

    def on_closing(self):
        if messagebox.askokcancel("退出", "确定要退出系统吗?"):
            self.analyze = False
            if self.cap is not None:
                self.cap.release()
            self.main_window.destroy()


def show_video_analysis_system(username):
    VideoAnalysisSystem(username)


# 创建登录窗口
login_window = tk.Tk()
login_window.title("火灾预警系统 - 用户登录")
login_window.geometry("400x300")
login_window.resizable(False, False)
login_window.configure(bg=THEME["background"])

# 窗口居中
window_width = 400
window_height = 300
screen_width = login_window.winfo_screenwidth()
screen_height = login_window.winfo_screenheight()
x = (screen_width // 2) - (window_width // 2)
y = (screen_height // 2) - (window_height // 2)
login_window.geometry(f"{window_width}x{window_height}+{x}+{y}")

# 创建标题标签
title_label = tk.Label(login_window, text="火灾预警系统登录",
                       font=("微软雅黑", 20), bg=THEME["background"])
title_label.pack(pady=20)

# 用户名输入框
input_frame = tk.Frame(login_window, bg=THEME["background"])
input_frame.pack(pady=10)

tk.Label(input_frame, text="用户名:", font=("微软雅黑", 12),
         bg=THEME["background"]).grid(row=0, column=0, padx=5, pady=5, sticky="e")
username_entry = tk.Entry(input_frame, font=("微软雅黑", 12), width=20)
username_entry.grid(row=0, column=1, padx=5, pady=5)

# 密码输入框
tk.Label(input_frame, text="密  码:", font=("微软雅黑", 12),
         bg=THEME["background"]).grid(row=1, column=0, padx=5, pady=5, sticky="e")
password_entry = tk.Entry(input_frame, show="*", font=("微软雅黑", 12), width=20)
password_entry.grid(row=1, column=1, padx=5, pady=5)

# 登录按钮
login_button = tk.Button(login_window, text="登录", command=login,
                         bg=THEME["primary"], fg=THEME["text"],
                         font=("微软雅黑", 12), width=15,
                         activebackground=THEME["accent"], activeforeground=THEME["text"])
login_button.pack(pady=20)

# 初始化数据库
init_db()

# 运行登录窗口
login_window.mainloop()