import tkinter as tk
from tkinter import messagebox
from PIL import ImageGrab
import numpy as np
import re
import os
import sys

# 抑制 PaddleOCR 烦人的启动日志
os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'

class ScreenSnip:
    def __init__(self, parent, callback):
        self.parent = parent
        self.callback = callback
        self.snip_window = tk.Toplevel(parent)
        self.snip_window.attributes('-fullscreen', True)
        self.snip_window.attributes('-alpha', 0.3) # 设置半透明遮罩
        self.snip_window.config(cursor="cross")
        
        self.canvas = tk.Canvas(self.snip_window, cursor="cross", bg="gray")
        self.canvas.pack(fill="both", expand=True)

        self.start_x = None
        self.start_y = None
        self.rect = None

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)

    def on_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        self.rect = self.canvas.create_rectangle(self.start_x, self.start_y, 1, 1, outline='red', width=2, fill="black")

    def on_drag(self, event):
        self.canvas.coords(self.rect, self.start_x, self.start_y, event.x, event.y)

    def on_release(self, event):
        x1 = min(self.start_x, event.x)
        y1 = min(self.start_y, event.y)
        x2 = max(self.start_x, event.x)
        y2 = max(self.start_y, event.y)
        self.snip_window.destroy()
        # 传递框选坐标
        self.callback((x1, y1, x2, y2))

class OCRApp:
    def __init__(self, root):
        self.root = root
        root.title("屏幕数字识别工具")
        root.geometry("320x350")
        root.attributes('-topmost', True) # 窗口置顶

        self.bbox = None
        self.img = None
        
        # 延迟加载 PaddleOCR（避免刚打开软件时卡顿）
        self.ocr = None 

        tk.Label(root, text="第一步：点击下方按钮框选屏幕区域", pady=5).pack()
        tk.Button(root, text="1. 手动框选区域", command=self.start_snip, width=20, bg="#e0f7fa").pack(pady=5)
        
        tk.Label(root, text="第二步：确认框选后点击识别", pady=5).pack()
        tk.Button(root, text="2. 识别数字", command=self.recognize, width=20, bg="#fff9c4").pack(pady=5)

        tk.Label(root, text="识别结果：", pady=5).pack()
        self.result_text = tk.Text(root, height=8, width=35, font=("Arial", 12))
        self.result_text.pack(pady=5)

    def init_ocr(self):
        if self.ocr is None:
            self.result_text.delete(1.0, tk.END)
            self.result_text.insert(tk.END, "首次运行正在加载 AI 模型，请稍候...\n(这可能需要几秒钟)")
            self.root.update()
            from paddleocr import PaddleOCR
            # 使用 en 模型，体积小，对数字识别极准
            self.ocr = PaddleOCR(use_angle_cls=False, lang='en', show_log=False)

    def start_snip(self):
        self.root.iconify() # 截图时隐藏主窗口
        self.root.after(200, lambda: ScreenSnip(self.root, self.on_snip_complete))

    def on_snip_complete(self, bbox):
        self.bbox = bbox
        self.root.deiconify() # 恢复主窗口
        
        # 防止用户仅仅点了一下没有拖动
        if bbox[2] - bbox[0] > 5 and bbox[3] - bbox[1] > 5:
            self.img = ImageGrab.grab(bbox)
            self.result_text.delete(1.0, tk.END)
            self.result_text.insert(tk.END, "区域已锁定。准备就绪，请点击识别。")
        else:
            self.img = None
            messagebox.showwarning("警告", "框选区域太小，请重新框选！")

    def recognize(self):
        if not self.img:
            messagebox.showwarning("提示", "请先点击【手动框选区域】")
            return

        self.init_ocr()

        self.result_text.delete(1.0, tk.END)
        self.result_text.insert(tk.END, "识别中，请稍候...\n")
        self.root.update()

        try:
            # 将 PIL 图像转换为 PaddleOCR 需要的 OpenCV 格式 (BGR numpy array)
            img_cv = np.array(self.img)
            if len(img_cv.shape) == 3:
                img_cv = img_cv[:, :, ::-1] 

            results = self.ocr.ocr(img_cv, cls=False)
            extracted_numbers = []

            if results and results[0]:
                for line in results[0]:
                    text = line[1][0]
                    # 正则表达式：只提取纯数字或带小数点的数字
                    nums = re.findall(r'\d+\.?\d*', text)
                    extracted_numbers.extend(nums)

            self.result_text.delete(1.0, tk.END)
            if extracted_numbers:
                self.result_text.insert(tk.END, "\n".join(extracted_numbers))
            else:
                self.result_text.insert(tk.END, "该区域未发现数字。")
                
        except Exception as e:
            self.result_text.delete(1.0, tk.END)
            self.result_text.insert(tk.END, f"识别出错: {str(e)}")

if __name__ == "__main__":
    root = tk.Tk()
    app = OCRApp(root)
    root.mainloop()