# -*- coding: utf-8 -*-
"""
STM32 동아리 블루투스 로그 — 보드가 보낸 글자를 줄마다 보고, 글자를 보내는 프로그램

실행 방법
  1) 이 파일(btlog.py)을 더블클릭
  2) 안 되면: 시작 메뉴 › IDLE 실행 › File › Open 으로 이 파일 열기 › F5

같은 폴더의 serial 폴더(pyserial)를 그대로 쓰므로 pip 설치가 필요 없습니다.
"""
import os
import sys
import time
import queue
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)                       # 옆에 있는 serial 폴더를 먼저 찾게

import tkinter as tk
from tkinter import ttk, font as tkfont, filedialog

import serial
import serial.tools.list_ports

VERSION = "1.0"
NAVY, GRAY = "#1F497D", "#7F7F7F"
BG, PANEL = "#F4F6F9", "#FFFFFF"


# ====================================================================== 시리얼
class Link:
    def __init__(self):
        self.ser = None
        self.q = queue.Queue()
        self._run = False

    def open(self, port, baud):
        self.ser = serial.serial_for_url(port, baudrate=baud, timeout=0.1, write_timeout=2)
        self._run = True
        threading.Thread(target=self._reader, daemon=True).start()

    def close(self):
        self._run = False
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass
        self.ser = None

    @property
    def is_open(self):
        return self.ser is not None and self.ser.is_open

    def send(self, text):
        self.ser.write(text.encode("ascii", errors="replace"))

    def _reader(self):
        buf = b""
        last = time.time()
        while self._run:
            try:
                data = self.ser.read(self.ser.in_waiting or 1)
            except Exception as e:
                self.q.put(("error", str(e)))
                return
            if data:
                buf += data
                last = time.time()
                while b"\n" in buf:                    # '\n' 이 오면 한 줄
                    line, buf = buf.split(b"\n", 1)
                    self.q.put(("line", line.decode("ascii", errors="replace").rstrip("\r")))
            elif buf and time.time() - last > 0.5:     # 줄바꿈 없이 끝난 글자도 0.5초 뒤 보여 준다
                self.q.put(("line", buf.decode("ascii", errors="replace").rstrip("\r")))
                buf = b""


def list_ports():
    return [(p.device, p.description or "") for p in sorted(serial.tools.list_ports.comports(), key=lambda p: p.device)]


def guess_baud(desc):
    d = desc.lower()
    if "bluetooth" in d or "블루투스" in d:
        return 9600
    if "stlink" in d or "st-link" in d:
        return 115200
    return None


# ====================================================================== 화면
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("STM32 동아리 블루투스 로그  v" + VERSION)
        self.geometry("900x620")
        self.minsize(760, 520)
        self.configure(bg=BG)
        self.link = Link()
        self.lines = 0
        self.port_desc = {}
        self._fonts()
        self._style()
        self._build()
        self.refresh_ports()
        self.after(50, self._poll)
        self.protocol("WM_DELETE_WINDOW", self._quit)

    def _fonts(self):
        fams = set(tkfont.families())
        ui = next((f for f in ("맑은 고딕", "Malgun Gothic", "Noto Sans CJK KR", "Apple SD Gothic Neo") if f in fams), "TkDefaultFont")
        mono = next((f for f in ("Consolas", "D2Coding", "DejaVu Sans Mono", "Menlo") if f in fams), "TkFixedFont")
        self.f_ui, self.f_bold = (ui, 10), (ui, 10, "bold")
        self.f_title, self.f_big = (ui, 15, "bold"), (ui, 13)
        self.f_mono = (mono, 12)

    def _style(self):
        st = ttk.Style(self)
        st.theme_use("vista" if "vista" in st.theme_names() else "clam")
        st.configure(".", font=self.f_ui)
        st.configure("TFrame", background=BG)
        st.configure("TLabel", background=BG)
        st.configure("Hint.TLabel", background=BG, foreground=GRAY)
        st.configure("TCheckbutton", background=BG)
        st.configure("Big.TButton", font=self.f_bold, padding=(14, 6))
        st.configure("Cmd.TButton", padding=(8, 4))

    def _build(self):
        top = tk.Frame(self, bg=NAVY, height=48)
        top.pack(fill="x")
        self.top = top
        self.lbl_title = tk.Label(top, text="블루투스 로그", bg=NAVY, fg="white", font=self.f_title)
        self.lbl_title.pack(side="left", padx=16, pady=8)
        self.lbl_state = tk.Label(top, text="●  연결 안 됨", bg=NAVY, fg="#C9D3E0", font=self.f_bold)
        self.lbl_state.pack(side="right", padx=16)

        con = ttk.Frame(self, padding=(14, 12, 14, 4))
        con.pack(fill="x")
        ttk.Label(con, text="포트").pack(side="left")
        self.cb_port = ttk.Combobox(con, width=44)
        self.cb_port.pack(side="left", padx=(6, 4))
        self.cb_port.bind("<<ComboboxSelected>>", self._on_port)
        ttk.Button(con, text="새로고침", command=self.refresh_ports).pack(side="left", padx=(0, 14))
        ttk.Label(con, text="속도").pack(side="left")
        self.cb_baud = ttk.Combobox(con, width=8, values=["9600", "115200"], state="readonly")
        self.cb_baud.set("9600")
        self.cb_baud.pack(side="left", padx=(6, 14))
        self.btn_con = ttk.Button(con, text="연결", style="Big.TButton", command=self.toggle)
        self.btn_con.pack(side="left")
        ttk.Label(self, text="블루투스(HC-06)는 '표준 직렬 Bluetooth 링크' 중 '나가는' 포트 · 9600 (위 띠 파랑),   USB 선은 STLink · 115200 (위 띠 초록)",
                  style="Hint.TLabel", padding=(14, 0, 14, 6)).pack(fill="x")

        # 로그
        bar = ttk.Frame(self, padding=(14, 4, 14, 2))
        bar.pack(fill="x")
        ttk.Label(bar, text="받은 글자", font=self.f_bold).pack(side="left")
        ttk.Button(bar, text="파일로 저장", command=self.save_log).pack(side="right")
        ttk.Button(bar, text="지우기", command=self.clear_log).pack(side="right", padx=6)
        self.var_pause = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="잠깐 멈춤", variable=self.var_pause).pack(side="right", padx=8)
        self.var_time = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="시각 붙이기", variable=self.var_time).pack(side="right", padx=8)

        box = ttk.Frame(self, padding=(14, 0, 14, 6))
        box.pack(fill="both", expand=True)
        self.log = tk.Text(box, font=self.f_mono, bg="#1E1E1E", fg="#E6E6E6", relief="flat", wrap="none", padx=10, pady=8, height=12)
        sb = ttk.Scrollbar(box, command=self.log.yview)
        self.log.configure(yscrollcommand=sb.set, state="disabled")
        sb.pack(side="right", fill="y")
        self.log.pack(side="left", fill="both", expand=True)
        self.log.tag_configure("time", foreground="#7F8C8D")
        self.log.tag_configure("tx", foreground="#7EC8FF")
        self.log.tag_configure("sys", foreground="#9E9E9E")

        # 보내기
        snd = ttk.Frame(self, padding=(14, 4, 14, 4))
        snd.pack(fill="x")
        ttk.Label(snd, text="보내기", font=self.f_bold).pack(side="left")
        self.ent = ttk.Entry(snd, width=26, font=self.f_big)
        self.ent.pack(side="left", padx=(8, 4))
        self.ent.bind("<Return>", lambda e: self.send_entry())
        ttk.Button(snd, text="보내기", style="Big.TButton", command=self.send_entry).pack(side="left")
        self.var_nl = tk.BooleanVar(value=False)
        ttk.Checkbutton(snd, text="끝에 줄바꿈(\\n)", variable=self.var_nl).pack(side="left", padx=10)

        cmd = ttk.Frame(self, padding=(14, 0, 14, 4))
        cmd.pack(fill="x")
        ttk.Label(cmd, text="한 글자 바로 보내기").pack(side="left", padx=(0, 8))
        for c in ("1", "2", "3", "0", "a"):
            ttk.Button(cmd, text=c, width=4, style="Cmd.TButton", command=lambda c=c: self.send_text(c, nl=False)).pack(side="left", padx=2)
        ttk.Label(cmd, text="   1 · 2 · 3 : LED 켜기   0 : 끄기   a : adc 한 번 (도전)", style="Hint.TLabel").pack(side="left")

        self.lbl_count = ttk.Label(self, text="", style="Hint.TLabel", padding=(14, 0, 14, 8))
        self.lbl_count.pack(fill="x")
        self._update_count()

    # ------------------------------------------------------------ 포트
    def refresh_ports(self):
        ports = list_ports()
        self.port_desc = dict(ports)
        items = ["%s  —  %s" % (d, s) if s else d for d, s in ports]
        self.cb_port["values"] = items
        if items and not self.cb_port.get():
            self.cb_port.set(items[0])
            self._on_port()
        if not items:
            self._sys("포트가 없습니다 — USB 선 · 블루투스 짝 맺기를 확인하고 '새로고침'")

    def _port_name(self):
        return self.cb_port.get().split("—")[0].strip()

    def _on_port(self, _e=None):
        b = guess_baud(self.port_desc.get(self._port_name(), ""))
        if b:
            self.cb_baud.set(str(b))

    def toggle(self):
        if self.link.is_open:
            self.link.close()
            self._set_state(False)
            self._sys("연결을 끊었습니다")
            return
        port, baud = self._port_name(), int(self.cb_baud.get())
        if not port:
            self._sys("포트를 먼저 고르세요")
            return
        self.btn_con.configure(text="연결 중…", state="disabled")
        self.lbl_state.configure(text="●  연결 중…  (블루투스는 몇 초 걸립니다)", fg="#FFD08A")

        def work():
            try:
                self.link.open(port, baud)
                self.after(0, lambda: (self._set_state(True), self._sys("연결됨 — %s · %d" % (port, baud))))
            except Exception as e:
                msg = self._why(str(e))
                self.after(0, lambda: (self._set_state(False), self._sys("연결 실패 — " + msg)))
        threading.Thread(target=work, daemon=True).start()

    @staticmethod
    def _why(err):
        e = err.lower()
        if "permission" in e or "access is denied" in e or "액세스" in err:
            return "다른 프로그램(크롬 웹 터미널 · 다른 창)이 이 포트를 쓰고 있습니다. 그 창을 닫고 다시 연결하세요."
        if "filenotfound" in e or "could not find" in e or "지정된 파일" in err:
            return "포트를 찾을 수 없습니다. '새로고침' 후 다시 고르세요."
        if "semaphore" in e or "timeout" in e or "세마포" in err or "시간" in err:
            return "블루투스 연결이 안 됩니다. HC-06 전원(LED 깜빡임) · 짝 맺기 · '나가는' 포트인지 확인하세요."
        return err

    def _kind(self):
        d = self.port_desc.get(self._port_name(), "").lower()
        if "bluetooth" in d or "블루투스" in d:
            return "블루투스", NAVY
        if "stlink" in d or "st-link" in d:
            return "USB 선 (STLink)", "#2E7D32"
        return "", "#555555"

    def _paint(self, color, title):
        for w in (self.top, self.lbl_title, self.lbl_state):
            w.configure(bg=color)
        self.lbl_title.configure(text=title)
        self.title(title + "  —  STM32 동아리 블루투스 로그  v" + VERSION)

    def _set_state(self, on):
        if on:
            kind, color = self._kind()
            self._paint(color, "%s  %s" % (kind or "연결", self._port_name()))
            self.btn_con.configure(text="끊기", state="normal")
            self.lbl_state.configure(text="●  연결됨  %s · %s" % (self._port_name(), self.cb_baud.get()), fg="#8EE29A")
            self.ent.focus_set()
        else:
            self._paint(NAVY, "블루투스 로그")
            self.btn_con.configure(text="연결", state="normal")
            self.lbl_state.configure(text="●  연결 안 됨", fg="#C9D3E0")

    # ------------------------------------------------------------ 보내기
    def send_entry(self):
        t = self.ent.get()
        if t and self.send_text(t, nl=self.var_nl.get()):
            self.ent.delete(0, "end")

    def send_text(self, t, nl=False):
        if not self.link.is_open:
            self._sys("먼저 '연결' 을 누르세요")
            return False
        try:
            self.link.send(t + ("\n" if nl else ""))
        except Exception as e:
            self._sys("보내기 실패 — " + self._why(str(e)))
            return False
        self._write("> " + t, "tx")
        return True

    # ------------------------------------------------------------ 받기
    def _poll(self):
        try:
            while True:
                kind, data = self.link.q.get_nowait()
                if kind == "line":
                    self.lines += 1
                    if not self.var_pause.get():
                        self._write(data)
                elif kind == "error":
                    self.link.close()
                    self._set_state(False)
                    self._sys("연결이 끊겼습니다 — " + self._why(data))
        except queue.Empty:
            pass
        self._update_count()
        self.after(50, self._poll)

    def _write(self, text, tag=None):
        self.log.configure(state="normal")
        if self.var_time.get():
            self.log.insert("end", time.strftime("%H:%M:%S  "), "time")
        self.log.insert("end", text + "\n", tag)
        if int(self.log.index("end-1c").split(".")[0]) > 5000:
            self.log.delete("1.0", "1000.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _sys(self, text):
        self._write("[로그] " + text, "sys")

    def clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def save_log(self):
        path = filedialog.asksaveasfilename(defaultextension=".txt", initialfile=time.strftime("log_%m%d_%H%M.txt"),
                                            filetypes=[("텍스트 파일", "*.txt")])
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.log.get("1.0", "end"))
            self._sys("저장했습니다 — " + path)

    def _update_count(self):
        self.lbl_count.configure(text="받은 줄 %d      |      pyserial %s   ·   Python %s"
                                 % (self.lines, serial.__version__, sys.version.split()[0]))

    def _quit(self):
        self.link.close()
        self.destroy()


if __name__ == "__main__":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    App().mainloop()
