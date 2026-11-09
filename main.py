import json
import math
import os
import pathlib
import random
import threading
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
import archiver

SETTINGS = os.path.join(os.path.expanduser('~'), '.chatarchiver_settings.json')
NIGHT = {'شب', 'نئون'}

# تم‌ها: رنگ‌ها + افکت متحرک هدر
THEMES = {
    'روز': dict(bg='#f3f8ff', card='#ffffff', fg='#1d2b4a', border='#c9d8f5', accent='#3b82f6', accent2='#1d63d6',
                grad=('#3a9bf5', '#8fd3f4'), deco=('☀', '#ffd54a'),
                fx=dict(sym='☁', mode='drift', colors=['#ffffff', '#eaf5ff'], n=7, size=(24, 40))),
    'شب': dict(bg='#12162b', card='#1d2240', fg='#e8ecff', border='#2e3566', accent='#7c5cff', accent2='#5a3de0',
               grad=('#0b1030', '#4a2a8a'), deco=('☾', '#ffe9a8'),
               fx=dict(sym='★', mode='twinkle', colors=['#ffffff', '#ffe9a8', '#9fb4ff', '#6b78c9'], n=26, size=(7, 14))),
    'اقیانوس': dict(bg='#eafaff', card='#ffffff', fg='#07344a', border='#b7e3ee', accent='#0fa3b1', accent2='#0b7f8a',
                    grad=('#0072ff', '#00c6ff'), deco=('≋', '#d6f6ff'),
                    fx=dict(sym='○', mode='rise', colors=['#ffffff', '#c8f1ff'], n=18, size=(10, 24))),
    'جنگل': dict(bg='#eef7ee', card='#ffffff', fg='#1e3a26', border='#bfe0c4', accent='#2e9e5b', accent2='#207a44',
                 grad=('#2e8b3a', '#a8e063'), deco=('❦', '#e9ffd0'),
                 fx=dict(sym='✿', mode='fall', colors=['#f5ffd6', '#d8f5a0', '#ffffff'], n=14, size=(12, 22))),
    'شکوفه': dict(bg='#fff0f6', card='#ffffff', fg='#4a1d35', border='#f6c8dc', accent='#e8559a', accent2='#c23a7e',
                  grad=('#ff6f91', '#ffb4cf'), deco=('❀', '#fff0f6'),
                  fx=dict(sym='♥', mode='rise', colors=['#ffffff', '#ffe0ec', '#ffc2d9'], n=16, size=(10, 22))),
    'نئون': dict(bg='#0b0b12', card='#161622', fg='#e9fff6', border='#2a2a40', accent='#00c896', accent2='#00a07a',
                 grad=('#12002b', '#00c896'), deco=('✦', '#aaffee'),
                 fx=dict(sym='✦', mode='twinkle', colors=['#00ffc6', '#ff4fd8', '#7a5cff', '#ffffff'], n=24, size=(8, 16))),
}

HELP = """راهنما:
۱) ChatGPT: Settings ← Data controls ← Export data  (لینک دانلود به ایمیل می‌آید)
۲) Claude: Settings ← Privacy ← Export data  (لینک دانلود به ایمیل می‌آید)
۳) فایل ZIP دریافتی را انتخاب کنید، پوشه مقصد را انتخاب کنید و «شروع» را بزنید.
خروجی: فایل‌های Markdown و HTML برای هر چت + index.html با جستجو."""


def lerp(a, b, t):
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return '#%02x%02x%02x' % tuple(int(ca[i] + (cb[i] - ca[i]) * t) for i in range(3))


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('آرشیو چت‌ها - ChatArchiver')
        self.geometry('820x760')
        self.minsize(720, 640)
        self.option_add('*Font', 'Tahoma 10')
        st = self.load_settings()
        self.theme_name = st.get('theme') if st.get('theme') in THEMES else 'روز'
        self.src = tk.StringVar()
        self.out = tk.StringVar(value=st.get('out') or os.path.join(os.path.expanduser('~'), 'ChatArchive'))
        self.files = []
        self.busy, self.busy_pos, self.hw = False, 0, 0
        self.parts = []
        self.style = ttk.Style(self)
        self.style.theme_use('clam')

        self.header = tk.Canvas(self, height=110, highlightthickness=0, bd=0)
        self.header.pack(fill='x')
        self.header.bind('<Configure>', self.on_resize)

        bar = tk.Frame(self)
        bar.pack(fill='x', padx=10, pady=(8, 0))
        self.toggle_btn = self.make_btn(bar, '', self.toggle_daynight)
        self.toggle_btn.pack(side='left')
        self.make_btn(bar, 'باز کردن آرشیو', self.open_index).pack(side='right')
        self.theme_box = ttk.Combobox(bar, values=list(THEMES), state='readonly', width=12, justify='center')
        self.theme_box.pack(side='left', padx=8)
        self.theme_box.bind('<<ComboboxSelected>>', lambda e: self.set_theme(self.theme_box.get()))
        tk.Label(bar, text='تم:').pack(side='left')

        self.busy_bar = tk.Canvas(self, height=6, highlightthickness=0, bd=0)
        self.busy_bar.pack(fill='x', padx=10, pady=6)

        top = tk.Frame(self)
        top.pack(fill='x', padx=10, pady=4)
        tk.Label(top, text='پوشه ذخیره آرشیو:', width=20, anchor='e').pack(side='right')
        self.make_btn(top, 'انتخاب...', self.pick_out).pack(side='left')
        tk.Entry(top, textvariable=self.out).pack(side='left', fill='x', expand=True, padx=6, ipady=3)

        nb = ttk.Notebook(self)
        nb.pack(fill='both', expand=True, padx=10, pady=6)
        t1, t2 = tk.Frame(nb), tk.Frame(nb)
        nb.add(t1, text='  وارد کردن فایل Export  ')
        nb.add(t2, text='  ورود دستی (کپی/آپلود)  ')

        fr = tk.Frame(t1)
        fr.pack(fill='x', padx=10, pady=14)
        tk.Label(fr, text='فایل ZIP خروجی:', width=16, anchor='e').pack(side='right')
        self.make_btn(fr, 'انتخاب...', self.pick_src).pack(side='left')
        tk.Entry(fr, textvariable=self.src).pack(side='left', fill='x', expand=True, padx=6, ipady=3)
        self.btn = self.make_btn(t1, 'شروع', self.start, big=True)
        self.btn.pack(pady=6)

        self.kind = tk.StringVar(value='chat')
        r = tk.Frame(t2)
        r.pack(fill='x', padx=10, pady=4)
        tk.Radiobutton(r, text='چت', variable=self.kind, value='chat').pack(side='right')
        tk.Radiobutton(r, text='پروژه', variable=self.kind, value='project').pack(side='right', padx=10)
        self.title_var, self.source_var = tk.StringVar(), tk.StringVar(value='Claude')
        for label, var in (('عنوان:', self.title_var), ('منبع (Claude / ChatGPT ...):', self.source_var)):
            f = tk.Frame(t2)
            f.pack(fill='x', padx=10, pady=2)
            tk.Label(f, text=label, width=26, anchor='e').pack(side='right')
            tk.Entry(f, textvariable=var).pack(side='left', fill='x', expand=True, ipady=2)
        tk.Label(t2, text='متن چت (یا توضیحات/دستورالعمل پروژه) را اینجا Paste کنید:', anchor='e').pack(fill='x', padx=10)
        self.text = scrolledtext.ScrolledText(t2, height=9, bd=0, relief='flat')
        self.text.pack(fill='both', expand=True, padx=10, pady=3)
        f = tk.Frame(t2)
        f.pack(fill='x', padx=10, pady=3)
        self.make_btn(f, 'افزودن فایل‌ها...', self.pick_files).pack(side='right')
        self.make_btn(f, 'چسباندن از کلیپ‌بورد', self.paste_clip).pack(side='left')
        self.files_lbl = tk.Label(f, text='بدون فایل', anchor='e')
        self.files_lbl.pack(side='right', padx=8)
        self.make_btn(t2, 'ذخیره در آرشیو', self.save_manual, big=True).pack(pady=6)

        self.logbox = scrolledtext.ScrolledText(self, height=7, bd=0, relief='flat')
        self.logbox.pack(fill='both', padx=10, pady=(0, 10))
        self.log(HELP)

        self.setup_clipboard()
        self.set_theme(self.theme_name)
        self.protocol('WM_DELETE_WINDOW', self.on_close)
        self.tick()

    # ---------- تنظیمات ----------
    def load_settings(self):
        try:
            with open(SETTINGS, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}

    def save_settings(self):
        try:
            with open(SETTINGS, 'w', encoding='utf-8') as f:
                json.dump({'theme': self.theme_name, 'out': self.out.get()}, f, ensure_ascii=False)
        except Exception:
            pass

    def on_close(self):
        self.save_settings()
        self.destroy()

    # ---------- تم ----------
    def make_btn(self, parent, text, cmd, big=False):
        b = tk.Button(parent, text=text, command=cmd, relief='flat', bd=0, cursor='hand2',
                      font=('Tahoma', 12 if big else 10, 'bold'), padx=18 if big else 12, pady=8 if big else 5)
        b.bind('<Enter>', lambda e: b.config(bg=THEMES[self.theme_name]['accent2']))
        b.bind('<Leave>', lambda e: b.config(bg=THEMES[self.theme_name]['accent']))
        return b

    def toggle_daynight(self):
        self.set_theme('روز' if self.theme_name in NIGHT else 'شب')

    def set_theme(self, name):
        self.theme_name = name
        t = THEMES[name]
        self.configure(bg=t['bg'])
        self.theme_box.set(name)
        self.toggle_btn.config(text='☀ حالت روز' if name in NIGHT else '☾ حالت شب')
        s = self.style
        s.configure('TNotebook', background=t['bg'], borderwidth=0)
        s.configure('TNotebook.Tab', background=t['card'], foreground=t['fg'], padding=(16, 7), borderwidth=0,
                    font=('Tahoma', 10, 'bold'))
        s.map('TNotebook.Tab', background=[('selected', t['accent'])], foreground=[('selected', '#ffffff')])
        s.configure('TCombobox', fieldbackground=t['card'], background=t['card'], foreground=t['fg'],
                    arrowcolor=t['accent'], bordercolor=t['border'])
        s.map('TCombobox', fieldbackground=[('readonly', t['card'])], foreground=[('readonly', t['fg'])])
        self.option_add('*TCombobox*Listbox.background', t['card'])
        self.option_add('*TCombobox*Listbox.foreground', t['fg'])
        self.option_add('*TCombobox*Listbox.selectBackground', t['accent'])
        self.walk(self, t)
        self.build_header()
        self.save_settings()

    def walk(self, widget, t):
        for w in widget.winfo_children():
            c = w.winfo_class()
            try:
                if c == 'Frame':
                    w.config(bg=t['bg'])
                elif c == 'Label':
                    w.config(bg=t['bg'], fg=t['fg'])
                elif c == 'Radiobutton':
                    w.config(bg=t['bg'], fg=t['fg'], selectcolor=t['card'], activebackground=t['bg'],
                             activeforeground=t['fg'])
                elif c == 'Entry':
                    w.config(bg=t['card'], fg=t['fg'], insertbackground=t['fg'], relief='flat',
                             highlightthickness=1, highlightbackground=t['border'], highlightcolor=t['accent'])
                elif c == 'Text':
                    w.config(bg=t['card'], fg=t['fg'], insertbackground=t['fg'], highlightthickness=1,
                             highlightbackground=t['border'], highlightcolor=t['accent'])
                elif c == 'Button':
                    w.config(bg=t['accent'], fg='#ffffff', activebackground=t['accent2'], activeforeground='#ffffff')
                elif c == 'Canvas':
                    w.config(bg=t['bg'])
            except tk.TclError:
                pass
            self.walk(w, t)

    # ---------- هدر متحرک ----------
    def on_resize(self, e):
        if abs(e.width - self.hw) > 4:
            self.after(60, self.build_header)

    def build_header(self):
        c, t = self.header, THEMES[self.theme_name]
        c.delete('all')
        w, h = max(c.winfo_width(), 820), 110
        self.hw = w
        steps = 70
        for i in range(steps):
            c.create_rectangle(i * w / steps, 0, (i + 1) * w / steps + 1, h, outline='',
                               fill=lerp(t['grad'][0], t['grad'][1], i / (steps - 1)))
        sym, col = t['deco']
        c.create_text(70, 56, text=sym, fill=col, font=('Tahoma', 44))
        fx = t['fx']
        self.parts = []
        for _ in range(fx['n']):
            size = random.randint(*fx['size'])
            x, y = random.uniform(0, w), random.uniform(0, h)
            item = c.create_text(x, y, text=fx['sym'], fill=random.choice(fx['colors']), font=('Tahoma', size))
            self.parts.append(dict(id=item, x=x, y=y, s=random.uniform(0.4, 1.2), ph=random.uniform(0, 6.28)))
        shadow = lerp(t['grad'][0], '#000000', 0.55)
        c.create_text(w / 2 + 2, 44, text='آرشیو چت‌ها', fill=shadow, font=('Tahoma', 26, 'bold'))
        c.create_text(w / 2, 42, text='آرشیو چت‌ها', fill='#ffffff', font=('Tahoma', 26, 'bold'))
        c.create_text(w / 2 + 1, 82, text='ChatArchiver — آرشیو شخصی چت‌ها، پروژه‌ها و فایل‌ها', fill=shadow,
                      font=('Tahoma', 10))
        c.create_text(w / 2, 81, text='ChatArchiver — آرشیو شخصی چت‌ها، پروژه‌ها و فایل‌ها', fill='#ffffff',
                      font=('Tahoma', 10))

    def tick(self):
        try:
            t = THEMES[self.theme_name]
            mode, w, h = t['fx']['mode'], max(self.hw, 820), 110
            now = self.tk.call('clock', 'milliseconds') / 1000.0
            for p in self.parts:
                if mode == 'drift':
                    p['x'] += p['s']
                    if p['x'] > w + 50:
                        p['x'] = -50
                elif mode == 'rise':
                    p['y'] -= p['s']
                    p['x'] += math.sin(now * 1.5 + p['ph']) * 0.6
                    if p['y'] < -20:
                        p['y'], p['x'] = h + 20, random.uniform(0, w)
                elif mode == 'fall':
                    p['y'] += p['s']
                    p['x'] += math.sin(now * 1.2 + p['ph']) * 0.9
                    if p['y'] > h + 20:
                        p['y'], p['x'] = -20, random.uniform(0, w)
                elif mode == 'twinkle':
                    p['x'] += p['s'] * 0.08
                    if p['x'] > w + 10:
                        p['x'] = -10
                    if random.random() < 0.02:
                        self.header.itemconfig(p['id'], fill=random.choice(t['fx']['colors']))
                self.header.coords(p['id'], p['x'], p['y'])
            b = self.busy_bar
            b.delete('all')
            bw = max(b.winfo_width(), 10)
            b.create_rectangle(0, 0, bw, 6, fill=t['border'], outline='')
            if self.busy:
                self.busy_pos = (self.busy_pos + 14) % (bw + 160)
                b.create_rectangle(self.busy_pos - 160, 0, self.busy_pos, 6, fill=t['accent'], outline='')
        except tk.TclError:
            return
        self.after(40, self.tick)

    # ---------- کلیپ‌بورد (کار کردن Ctrl+V با کیبورد فارسی) ----------
    def setup_clipboard(self):
        def on_key(e):
            w = e.widget
            if w.winfo_class() not in ('Text', 'Entry', 'TCombobox'):
                return None
            k = e.keycode
            if k == 65:  # A
                if w.winfo_class() == 'Text':
                    w.tag_add('sel', '1.0', 'end-1c')
                else:
                    w.select_range(0, 'end')
                    w.icursor('end')
                return 'break'
            if e.keysym.lower() in ('v', 'c', 'x'):
                return None  # با کیبورد انگلیسی، خود Tk کار را انجام می‌دهد
            ev = {86: '<<Paste>>', 67: '<<Copy>>', 88: '<<Cut>>'}.get(k)
            if ev:
                w.event_generate(ev)
                return 'break'
            return None

        self.bind_all('<Control-KeyPress>', on_key)

        menu = tk.Menu(self, tearoff=0)

        def show(e):
            w = e.widget
            if w.winfo_class() not in ('Text', 'Entry'):
                return
            w.focus_set()
            menu.delete(0, 'end')
            menu.add_command(label='برش', command=lambda: w.event_generate('<<Cut>>'))
            menu.add_command(label='کپی', command=lambda: w.event_generate('<<Copy>>'))
            menu.add_command(label='چسباندن', command=lambda: w.event_generate('<<Paste>>'))
            menu.tk_popup(e.x_root, e.y_root)

        self.bind_all('<Button-3>', show)

    def paste_clip(self):
        try:
            data = self.clipboard_get()
        except tk.TclError:
            messagebox.showinfo('توجه', 'کلیپ‌بورد خالی است. اول متن را کپی کنید.')
            return
        self.text.insert('insert', data)
        self.text.focus_set()

    # ---------- عملیات ----------
    def pick_src(self):
        p = filedialog.askopenfilename(filetypes=[('ZIP', '*.zip'), ('All', '*.*')]) or filedialog.askdirectory()
        if p:
            self.src.set(p)

    def pick_out(self):
        p = filedialog.askdirectory()
        if p:
            self.out.set(p)

    def pick_files(self):
        fs = filedialog.askopenfilenames()
        if fs:
            self.files = list(fs)
            self.files_lbl.config(text='%d فایل انتخاب شد' % len(fs))

    def log(self, msg):
        self.after(0, lambda: (self.logbox.insert('end', msg + '\n'), self.logbox.see('end')))

    def open_index(self):
        idx = os.path.normpath(os.path.join(self.out.get(), 'index.html'))
        if not os.path.exists(idx):
            return
        try:
            if webbrowser.open(pathlib.Path(idx).as_uri()):
                return
        except Exception:
            pass
        for target in (idx, os.path.dirname(idx)):
            try:
                os.startfile(target)
                return
            except Exception:
                continue
        self.log('آرشیو ذخیره شد: ' + idx)

    def start(self):
        if not self.src.get():
            messagebox.showwarning('توجه', 'اول فایل ZIP را انتخاب کنید.')
            return
        self.btn.config(state='disabled')
        self.busy = True
        threading.Thread(target=self.work, daemon=True).start()

    def work(self):
        try:
            archiver.run(self.src.get(), self.out.get(), self.log)
            self.open_index()
        except Exception as e:
            self.log('خطا: %s' % e)
        self.busy = False
        self.after(0, lambda: self.btn.config(state='normal'))

    def save_manual(self):
        try:
            archiver.add_manual(self.out.get(), self.kind.get(), self.title_var.get(),
                                self.source_var.get(), self.text.get('1.0', 'end').strip(),
                                self.files, self.log)
            self.text.delete('1.0', 'end')
            self.title_var.set('')
            self.files = []
            self.files_lbl.config(text='بدون فایل')
            self.open_index()
        except Exception as e:
            messagebox.showwarning('توجه', str(e))


if __name__ == '__main__':
    App().mainloop()
