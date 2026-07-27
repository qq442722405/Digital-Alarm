import io
import os
import re
import sys
import tkinter as tk
from tkinter import messagebox
from PIL import ImageGrab
import ddddocr
import pyperclip

# ==================== Windows 高分屏 (DPI) 适配 ====================
if sys.platform.startswith('win'):
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDpiAware()
        except Exception:
            pass


def resource_path(relative_path):
    """ 获取静态资源（如图标）绝对路径 """
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


class ScreenOCRApp:
    def __init__(self, root):
        self.root = root
        self.root.title("数字报警")
        self.root.geometry("360x220")
        self.root.attributes("-topmost", True)
        self.root.resizable(False, False)

        # 初始化 ddddocr 引擎（关闭日志/广告输出）
        try:
            self.ocr = ddddocr.DdddOcr(show_ad=False)
        except Exception as e:
            messagebox.showerror("初始化错误", f"OCR引擎加载失败: {e}")

        # 加载图标
        ico_file = resource_path("1.ico")
        if os.path.exists(ico_file):
            try:
                self.root.iconbitmap(ico_file)
            except Exception:
                pass

        # 界面布局
        self.btn_select = tk.Button(
            root, 
            text="🔍 点击框选识别", 
            command=self.start_selection, 
            font=("Microsoft YaHei", 12, "bold"), 
            bg="#007ACC", 
            fg="white", 
            height=2,
            relief="flat",
            cursor="hand2"
        )
        self.btn_select.pack(pady=20, padx=20, fill='x')

        self.label_title = tk.Label(root, text="识别结果：", font=("Microsoft YaHei", 10), fg="#666666")
        self.label_title.pack()

        self.label_result = tk.Label(root, text="等待识别...", font=("Microsoft YaHei", 14, "bold"), fg="#333333")
        self.label_result.pack(pady=5)

        self.label_tip = tk.Label(root, text="（结果已自动复制到剪贴板）", font=("Microsoft YaHei", 8), fg="#999999")
        self.label_tip.pack()

    def start_selection(self):
        """隐藏主窗口并开启透明遮罩"""
        self.root.withdraw()

        self.overlay = tk.Toplevel(self.root)
        self.overlay.attributes("-fullscreen", True)
        self.overlay.attributes("-topmost", True)
        self.overlay.attributes("-alpha", 0.3)
        self.overlay.config(cursor="cross")

        self.canvas = tk.Canvas(self.overlay, cursor="cross", bg="gray")
        self.canvas.pack(fill="both", expand=True)

        self.canvas.bind("<ButtonPress-1>", self.on_button_press)
        self.canvas.bind("<B1-Motion>", self.on_move_press)
        self.canvas.bind("<ButtonRelease-1>", self.on_button_release)

        self.start_x = None
        self.start_y = None
        self.rect = None

    def on_button_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        self.rect = self.canvas.create_rectangle(
            self.start_x, self.start_y, 1, 1, outline='red', width=2
        )

    def on_move_press(self, event):
        cur_x, cur_y = (event.x, event.y)
        self.canvas.coords(self.rect, self.start_x, self.start_y, cur_x, cur_y)

    def on_button_release(self, event):
        end_x, end_y = (event.x, event.y)

        x1 = min(self.start_x, end_x)
        y1 = min(self.start_y, end_y)
        x2 = max(self.start_x, end_x)
        y2 = max(self.start_y, end_y)

        self.overlay.destroy()
        self.root.deiconify()

        if (x2 - x1) > 5 and (y2 - y1) > 5:
            img = ImageGrab.grab(bbox=(x1, y1, x2, y2))
            self.recognize_digits(img)

    def recognize_digits(self, img):
        """内存识别数字"""
        try:
            # 1. 将截图转换为内存字节流，完全绕过磁盘路径，避开中文路径 Bug
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='PNG')
            image_bytes = img_byte_arr.getvalue()

            # 2. 执行神经网络识别
            raw_text = self.ocr.classification(image_bytes)

            # 3. 过滤提炼数字和小数点
            digits_only = "".join(re.findall(r'[\d\.]+', raw_text))

            if digits_only:
                self.label_result.config(text=digits_only, fg="#008000")
                pyperclip.copy(digits_only)
            else:
                self.label_result.config(text="未识别到数字", fg="#FF0000")

        except Exception as e:
            self.label_result.config(text="识别出错", fg="#FF0000")
            messagebox.showerror("识别错误", f"识别过程出错：\n{e}")


if __name__ == "__main__":
    root = tk.Tk()
    app = ScreenOCRApp(root)
    root.mainloop()
