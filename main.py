import datetime
import json
import math
import os
import pathlib
import random
import shutil
import tempfile
import threading
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk
import archiver

SETTINGS = os.path.join(os.path.expanduser('~'), '.chatarchiver_settings.json')
NIGHT = {'شب', 'نئون'}
HH = 64  # ارتفاع هدر جمع‌وجور

THEMES = {
    'بنفش': dict(bg='#f4f2f8', card='#ffffff', fg='#241a3a', border='#e2d9f0', accent='#7b22cc', accent2='#5f19a3',
                 grad=('#6a14b8', '#a855f7'), deco=('✦', '#f3e8ff'),
                 fx=dict(sym='✦', mode='twinkle', colors=['#ffffff', '#e9d5ff', '#d8b4fe'], n=16, size=(7, 13))),
    'روز': dict(bg='#f3f8ff', card='#ffffff', fg='#1d2b4a', border='#c9d8f5', accent='#3b82f6', accent2='#1d63d6',
                grad=('#3a9bf5', '#8fd3f4'), deco=('☀', '#ffd54a'),
                fx=dict(sym='☁', mode='drift', colors=['#ffffff', '#eaf5ff'], n=6, size=(24, 40))),
    'شب': dict(bg='#12162b', card='#1d2240', fg='#e8ecff', border='#2e3566', accent='#7c5cff', accent2='#5a3de0',
               grad=('#0b1030', '#4a2a8a'), deco=('☾', '#ffe9a8'),
               fx=dict(sym='★', mode='twinkle', colors=['#ffffff', '#ffe9a8', '#9fb4ff', '#6b78c9'], n=22, size=(7, 14))),
    'اقیانوس': dict(bg='#eafaff', card='#ffffff', fg='#07344a', border='#b7e3ee', accent='#0fa3b1', accent2='#0b7f8a',
                    grad=('#0072ff', '#00c6ff'), deco=('≋', '#d6f6ff'),
                    fx=dict(sym='○', mode='rise', colors=['#ffffff', '#c8f1ff'], n=14, size=(10, 24))),
    'جنگل': dict(bg='#eef7ee', card='#ffffff', fg='#1e3a26', border='#bfe0c4', accent='#2e9e5b', accent2='#207a44',
                 grad=('#2e8b3a', '#a8e063'), deco=('❦', '#e9ffd0'),
                 fx=dict(sym='✿', mode='fall', colors=['#f5ffd6', '#d8f5a0', '#ffffff'], n=12, size=(12, 22))),
    'شکوفه': dict(bg='#fff0f6', card='#ffffff', fg='#4a1d35', border='#f6c8dc', accent='#e8559a', accent2='#c23a7e',
                  grad=('#ff6f91', '#ffb4cf'), deco=('❀', '#fff0f6'),
                  fx=dict(sym='♥', mode='rise', colors=['#ffffff', '#ffe0ec', '#ffc2d9'], n=12, size=(10, 22))),
    'نئون': dict(bg='#0b0b12', card='#161622', fg='#e9fff6', border='#2a2a40', accent='#00c896', accent2='#00a07a',
                 grad=('#12002b', '#00c896'), deco=('✦', '#aaffee'),
                 fx=dict(sym='✦', mode='twinkle', colors=['#00ffc6', '#ff4fd8', '#7a5cff', '#ffffff'], n=20, size=(8, 16))),
}

NAV = [('home', '⌂   خانه'), ('import', '⇩   ورود از Export'), ('manual', '✎   ورود دستی'),
       ('archive', '☰   آرشیو'), ('code', '‹›   کدها'), ('export', '⇪   خروجی'), ('backup', '⟳   پشتیبان‌گیری'),
       ('settings', '⚙   تنظیمات'), ('help', '?   راهنما')]

TREE_HEADS = {'date': 'تاریخ', 'source': 'منبع', 'kind': 'نوع', 'title': 'عنوان'}
KIND_FA = {'chat': 'چت', 'project': 'پروژه', 'file': 'فایل'}
SORTS = {'جدیدترین': ('date', True), 'قدیمی‌ترین': ('date', False), 'عنوان (الف تا ی)': ('title', False),
         'منبع': ('source', False), 'نوع': ('kind', False)}


def human(n):
    return '%.1f KB' % (n / 1024) if n >= 1024 else '%d B' % n


HELP = """۱) ChatGPT: Settings ← Data controls ← Export data  (لینک دانلود به ایمیل می‌آید)
۲) Claude: Settings ← Privacy ← Export data  (لینک دانلود به ایمیل می‌آید)
۳) در صفحه‌ی «ورود از Export» فایل ZIP را انتخاب و «شروع» را بزنید.
۴) چت یا پروژه‌ای که Export ندارد را از «ورود دستی» وارد کنید.
۵) در «آرشیو» می‌توانید همه‌چیز را جستجو و باز کنید.
۶) «خروجی» یک فایل Markdown واحد می‌سازد؛ «پشتیبان‌گیری» یک ZIP کامل از آرشیو."""


def lerp(a, b, t):
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return '#%02x%02x%02x' % tuple(int(ca[i] + (cb[i] - ca[i]) * t) for i in range(3))


def is_rtl_line(line):
    for ch in line:
        if '\u0590' <= ch <= '\u08ff' or '\ufb1d' <= ch <= '\ufdff' or '\ufe70' <= ch <= '\ufeff':
            return True
        if ch.isalpha():
            return False
    return False


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('آرشیو چت‌ها - ChatArchiver')
        self.geometry('1060x740')
        self.minsize(920, 660)
        self.option_add('*Font', 'Tahoma 10')
        self.settings = self.load_settings()
        st = self.settings
        self.theme_name = st.get('theme') if st.get('theme') in THEMES else 'بنفش'
        home = os.path.expanduser('~')
        self.out = tk.StringVar(value=st.get('out') or os.path.join(home, 'ChatArchive'))
        self.backup_dir = tk.StringVar(value=st.get('backup_dir') or os.path.join(home, 'ChatArchive_Backups'))
        self.anim = tk.BooleanVar(value=st.get('anim', True))
        self.src = tk.StringVar()
        self.busy, self.busy_pos, self.hw, self.parts = False, 0, 0, []
        self.pages, self.nav, self.stat_labels, self.tree_rows = {}, {}, {}, {}
        self.sort_col, self.sort_rev = 'date', True
        self.item_files, self.code_items = [], []
        self.cur = 'home'
        self.log_visible = False
        self.m_files, self.m_idx = [], 0
        self.style = ttk.Style(self)
        self.style.theme_use('clam')

        self.header = tk.Canvas(self, height=HH, highlightthickness=0, bd=0)
        self.header.pack(fill='x')
        self.header.bind('<Configure>', self.on_resize)
        self.busy_bar = tk.Canvas(self, height=4, highlightthickness=0, bd=0)
        self.busy_bar.pack(fill='x')

        self.footer = tk.Frame(self)
        self.footer.pack(side='bottom', fill='x', padx=12, pady=(0, 8))
        log_row = tk.Frame(self.footer)
        log_row.pack(fill='x')
        self.log_btn = self.make_btn(log_row, '▸ گزارش عملیات', self.toggle_log, ghost=True)
        self.log_btn.pack(side='right')
        self.logbox = scrolledtext.ScrolledText(self.footer, height=7, bd=0, relief='flat')

        body = tk.Frame(self)
        body.pack(fill='both', expand=True)
        self.side = tk.Frame(body, width=200)
        self.side.role = 'side'
        self.side.pack(side='right', fill='y')
        self.side.pack_propagate(False)
        tk.Label(self.side, text='منو', font=('Tahoma', 9, 'bold')).pack(anchor='e', padx=16, pady=(16, 6))
        self.side.winfo_children()[0].role = 'muted'
        for key, label in NAV:
            b = tk.Label(self.side, text=label, anchor='e', padx=16, pady=10, cursor='hand2', font=('Tahoma', 10, 'bold'))
            b.role = 'nav'
            b.pack(fill='x', padx=10, pady=2)
            b.bind('<Button-1>', lambda e, k=key: self.show_page(k))
            b.bind('<Enter>', lambda e, k=key: self.nav_hover(k, True))
            b.bind('<Leave>', lambda e, k=key: self.nav_hover(k, False))
            self.nav[key] = b

        content = tk.Frame(body)
        content.pack(side='left', fill='both', expand=True, padx=12)
        bar = self.card(content)
        bar.pack(fill='x', pady=(10, 6))
        lbl = tk.Label(bar, text='پوشه آرشیو:')
        lbl.pack(side='right', padx=(6, 10), pady=8)
        self.make_btn(bar, 'باز کردن پوشه', self.open_folder, ghost=True).pack(side='left', padx=(10, 4), pady=6)
        self.make_btn(bar, 'تغییر', self.pick_out).pack(side='left', padx=4, pady=6)
        tk.Entry(bar, textvariable=self.out).pack(side='left', fill='x', expand=True, padx=6, pady=8, ipady=3)

        host = tk.Frame(content)
        host.pack(fill='both', expand=True)
        for key, _ in NAV:
            f = tk.Frame(host)
            self.pages[key] = f
            getattr(self, 'build_' + key)(f)

        self.setup_clipboard()
        self.set_theme(self.theme_name)
        self.show_page('home')
        self.protocol('WM_DELETE_WINDOW', self.on_close)
        self.log('آماده است. ابتدا از «ورود از Export» یا «ورود دستی» شروع کنید.')
        self.tick()

    # ---------- تنظیمات ----------
    def load_settings(self):
        try:
            with open(SETTINGS, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}

    def save_settings(self):
        self.settings.update(theme=self.theme_name, out=self.out.get(), backup_dir=self.backup_dir.get(),
                             anim=bool(self.anim.get()))
        try:
            with open(SETTINGS, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, ensure_ascii=False)
        except Exception:
            pass

    def on_close(self):
        self.save_settings()
        self.destroy()

    # ---------- سازنده‌های ظاهر ----------
    def card(self, parent):
        f = tk.Frame(parent)
        f.role = 'card'
        return f

    def card_title(self, parent, text):
        l = tk.Label(parent, text=text, anchor='e', font=('Tahoma', 12, 'bold'))
        l.pack(fill='x', padx=14, pady=(12, 4))
        return l

    def note(self, parent, text, wrap=700):
        l = tk.Label(parent, text=text, anchor='e', justify='right', wraplength=wrap)
        l.role = 'muted'
        l.pack(fill='x', padx=14, pady=2)
        return l

    def make_btn(self, parent, text, cmd, big=False, ghost=False):
        b = tk.Button(parent, text=text, command=cmd, relief='flat', bd=0, cursor='hand2',
                      font=('Tahoma', 11 if big else 10, 'bold'), padx=18 if big else 12, pady=8 if big else 4)
        b.role = 'ghost' if ghost else 'primary'

        def on(_):
            t = self.colors()
            b.config(bg=t['soft'] if ghost else t['accent2'])

        def off(_):
            t = self.colors()
            b.config(bg=t['card'] if ghost else t['accent'])

        b.bind('<Enter>', on)
        b.bind('<Leave>', off)
        return b

    def colors(self):
        t = dict(THEMES[self.theme_name])
        t['muted'] = lerp(t['fg'], t['card'], 0.45)
        t['soft'] = lerp(t['card'], t['accent'], 0.12)
        return t

    # ---------- صفحه‌ها ----------
    def show_page(self, key):
        for k, f in self.pages.items():
            f.pack_forget()
        self.cur = key
        self.pages[key].pack(fill='both', expand=True)
        self.refresh_nav()
        if key == 'home':
            self.refresh_home()
        elif key == 'archive':
            self.refresh_archive()
        elif key == 'code':
            self.refresh_code()

    def nav_hover(self, key, on):
        if key != self.cur:
            t = self.colors()
            self.nav[key].config(bg=t['soft'] if on else t['card'])

    def refresh_nav(self):
        t = self.colors()
        for k, b in self.nav.items():
            if k == self.cur:
                b.config(bg=t['accent'], fg='#ffffff')
            else:
                b.config(bg=t['card'], fg=t['fg'])

    # خانه
    def build_home(self, p):
        row = tk.Frame(p)
        row.pack(fill='x', pady=4)
        for key, cap in (('total', 'کل مورد‌ها'), ('ChatGPT', 'چت‌های ChatGPT'), ('Claude', 'چت‌های Claude'),
                         ('other', 'دستی / پروژه / سایر')):
            c = self.card(row)
            c.pack(side='right', expand=True, fill='x', padx=4)
            n = tk.Label(c, text='0', font=('Tahoma', 24, 'bold'))
            n.role = 'accent'
            n.pack(pady=(10, 0))
            k = tk.Label(c, text=cap)
            k.role = 'muted'
            k.pack(pady=(0, 10))
            self.stat_labels[key] = n
        row2 = tk.Frame(p)
        row2.pack(fill='both', expand=True, pady=4)
        ins = self.card(row2)
        ins.pack(side='right', fill='y', padx=(4, 0))
        ins.config(width=270)
        self.card_title(ins, 'نکته‌ها')
        self.ins_host = tk.Frame(ins)
        self.ins_host.pack(fill='both', expand=True, padx=8, pady=(0, 10))
        rec = self.card(row2)
        rec.pack(side='left', fill='both', expand=True, padx=(0, 4))
        self.card_title(rec, 'اخیراً اضافه‌شده')
        self.recent = self.make_tree(rec, 7)

    def make_tree(self, parent, height, sortable=False):
        fr = tk.Frame(parent)
        fr.pack(fill='both', expand=True, padx=10, pady=(0, 10))
        tree = ttk.Treeview(fr, columns=('date', 'source', 'kind', 'title'), show='headings', height=height,
                            selectmode='extended' if sortable else 'browse')
        for c, w in (('date', 100), ('source', 100), ('kind', 70), ('title', 360)):
            kw = {'command': (lambda cc=c: self.sort_by(cc))} if sortable else {}
            tree.heading(c, text=TREE_HEADS[c], anchor='e', **kw)
            tree.column(c, width=w, anchor='e', stretch=(c == 'title'))
        sb = ttk.Scrollbar(fr, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        sb.pack(side='left', fill='y')
        tree.pack(side='right', fill='both', expand=True)
        tree.bind('<Double-1>', lambda e, t=tree: self.open_selected(t))
        self.tree_rows[tree] = []
        return tree

    def fill_tree(self, tree, rows):
        tree.delete(*tree.get_children())
        self.tree_rows[tree] = rows
        for i, r in enumerate(rows):
            tree.insert('', 'end', iid=str(i),
                        values=(r['date'], r['source'], KIND_FA.get(r['kind'], ''), r['title']))

    def selected_rows(self, tree):
        rows = self.tree_rows.get(tree, [])
        return [rows[int(i)] for i in tree.selection() if int(i) < len(rows)]

    def open_selected(self, tree):
        rows = self.selected_rows(tree)
        if rows:
            self.open_item(rows[0])

    def open_item(self, e):
        self.open_path(os.path.join(self.out.get(), e['rel']))

    def refresh_all(self):
        self.refresh_home()
        self.refresh_archive()
        self.refresh_code()

    def refresh_home(self):
        rows = archiver.load_index(self.out.get())
        n_g = sum(1 for r in rows if r['source'] == 'ChatGPT')
        n_c = sum(1 for r in rows if r['source'] == 'Claude')
        for k, v in (('total', len(rows)), ('ChatGPT', n_g), ('Claude', n_c), ('other', len(rows) - n_g - n_c)):
            self.stat_labels[k].config(text=str(v))
        self.fill_tree(self.recent, rows[:30])
        for w in self.ins_host.winfo_children():
            w.destroy()
        msgs = []
        if not rows:
            msgs.append('آرشیو هنوز خالی است. از «ورود از Export» یا «ورود دستی» شروع کنید.')
        else:
            msgs.append('%d مورد در آرشیو ذخیره شده است.' % len(rows))
        last = self.settings.get('last_backup')
        if not last:
            msgs.append('هنوز پشتیبان‌گیری نکرده‌اید. از صفحه‌ی «پشتیبان‌گیری» یک نسخه‌ی ZIP بسازید.')
        else:
            try:
                days = (datetime.datetime.now() - datetime.datetime.fromisoformat(last)).days
            except Exception:
                days = 0
            msgs.append('آخرین پشتیبان: %s' % last.replace('T', ' ') + ('\nبیش از ۷ روز گذشته است؛ پشتیبان تازه بگیرید.' if days > 7 else ''))
        msgs.append('کدهای داخل چت‌ها جدا ذخیره می‌شوند؛ از صفحه‌ی «کدها» می‌توانید با یک کلیک کپی کنید.')
        for msg in msgs:
            l = tk.Label(self.ins_host, text=msg, anchor='e', justify='right', wraplength=230, padx=10, pady=8)
            l.role = 'insight'
            l.pack(fill='x', pady=3)
        self.walk(self.ins_host, self.colors())

    # ورود از Export
    def build_import(self, p):
        c = self.card(p)
        c.pack(fill='x', pady=6)
        self.card_title(c, 'ورود از فایل Export')
        self.note(c, 'فایل ZIP خروجی رسمی ChatGPT یا Claude را انتخاب کنید. نوع فایل خودکار تشخیص داده می‌شود و '
                     'برای هر چت یک فایل Markdown و HTML ساخته می‌شود.')
        r = tk.Frame(c)
        r.pack(fill='x', padx=14, pady=10)
        self.make_btn(r, 'انتخاب فایل...', self.pick_src).pack(side='left')
        tk.Entry(r, textvariable=self.src).pack(side='left', fill='x', expand=True, padx=8, ipady=4)
        self.btn = self.make_btn(c, 'شروع ورود', self.start, big=True)
        self.btn.pack(pady=(4, 14))
        g = self.card(p)
        g.pack(fill='x', pady=6)
        self.card_title(g, 'Export را از کجا بگیرم؟')
        self.note(g, 'ChatGPT: Settings ← Data controls ← Export data\n'
                     'Claude: Settings ← Privacy ← Export data\n'
                     'لینک دانلود ZIP به ایمیل شما ارسال می‌شود.')
        tk.Frame(g, height=10).pack()

    # ورود دستی (فرم مرحله‌ای)
    def build_manual(self, p):
        self.m_kind = tk.StringVar(value='chat')
        self.m_title = tk.StringVar()
        self.m_source = tk.StringVar(value='Claude')
        c = self.card(p)
        c.pack(fill='both', expand=True, pady=6)
        self.card_title(c, 'ورود دستی چت، پروژه و فایل')
        ind = tk.Frame(c)
        ind.pack(fill='x', padx=14, pady=(0, 6))
        self.step_lbls = []
        for txt in ('① مشخصات', '② محتوا', '③ پیش‌نمایش و ذخیره'):
            l = tk.Label(ind, text=txt)
            l.role = 'static'
            l.pack(side='right', padx=10)
            self.step_lbls.append(l)
        self.m_host = tk.Frame(c)
        self.m_host.pack(fill='both', expand=True, padx=14)
        s1, s2, s3 = tk.Frame(self.m_host), tk.Frame(self.m_host), tk.Frame(self.m_host)
        self.m_steps = [s1, s2, s3]
        # مرحله ۱
        r = tk.Frame(s1)
        r.pack(fill='x', pady=8)
        tk.Radiobutton(r, text='چت', variable=self.m_kind, value='chat').pack(side='right')
        tk.Radiobutton(r, text='پروژه', variable=self.m_kind, value='project').pack(side='right', padx=14)
        tk.Label(r, text='نوع:').pack(side='right', padx=6)
        for label, var, hint in (('عنوان:', self.m_title, 'اگر خالی بماند، خودکار از متن ساخته می‌شود'),
                                 ('منبع:', self.m_source, 'مثلاً Claude / ChatGPT / Gemini')):
            f = tk.Frame(s1)
            f.pack(fill='x', pady=4)
            tk.Label(f, text=label, width=8, anchor='e').pack(side='right')
            e = tk.Entry(f, textvariable=var)
            e.pack(side='right', fill='x', expand=True, padx=6, ipady=4)
            h = tk.Label(s1, text=hint, anchor='e')
            h.role = 'muted'
            h.pack(fill='x')
        # مرحله ۲
        tk.Label(s2, text='متن چت (یا توضیحات/دستورالعمل پروژه) را اینجا Paste کنید:', anchor='e').pack(fill='x')
        self.text = scrolledtext.ScrolledText(s2, height=12, bd=0, relief='flat')
        self.text.pack(fill='both', expand=True, pady=4)
        self.text.tag_configure('rtl', justify='right')
        self.text.bind('<KeyRelease>', lambda e: self.refresh_rtl())
        self.text.bind('<<Paste>>', lambda e: self.after(80, self.refresh_rtl), add='+')
        f = tk.Frame(s2)
        f.pack(fill='x', pady=4)
        self.make_btn(f, 'افزودن فایل‌ها...', self.pick_files).pack(side='right')
        self.make_btn(f, 'چسباندن از کلیپ‌بورد', self.paste_clip, ghost=True).pack(side='right', padx=6)
        self.make_btn(f, 'پاک کردن فایل‌ها', self.clear_files, ghost=True).pack(side='left')
        self.files_lbl = tk.Label(f, text='بدون فایل')
        self.files_lbl.pack(side='right', padx=8)
        # مرحله ۳
        self.sum_lbl = tk.Label(s3, text='', anchor='e', justify='right', wraplength=760)
        self.sum_lbl.pack(fill='x', pady=6)
        self.prev_box = scrolledtext.ScrolledText(s3, height=10, bd=0, relief='flat')
        self.prev_box.pack(fill='both', expand=True)
        f = tk.Frame(s3)
        f.pack(fill='x', pady=6)
        self.make_btn(f, 'ذخیره در آرشیو', self.save_manual, big=True).pack(side='right')
        self.make_btn(f, 'پیش‌نمایش در مرورگر', self.preview_browser, ghost=True).pack(side='right', padx=8)
        nav = tk.Frame(c)
        nav.pack(fill='x', padx=14, pady=10)
        self.next_btn = self.make_btn(nav, 'بعدی ‹', lambda: self.m_go(self.m_idx + 1))
        self.next_btn.pack(side='right')
        self.back_btn = self.make_btn(nav, '› قبلی', lambda: self.m_go(self.m_idx - 1), ghost=True)
        self.back_btn.pack(side='right', padx=8)
        self.m_go(0)

    def m_go(self, idx):
        idx = max(0, min(2, idx))
        if idx == 2 and not (self.get_text() or self.m_files):
            messagebox.showinfo('توجه', 'متن را وارد کنید یا فایلی اضافه کنید.')
            idx = 1
        for s in self.m_steps:
            s.pack_forget()
        self.m_idx = idx
        self.m_steps[idx].pack(fill='both', expand=True)
        self.back_btn.config(state='normal' if idx > 0 else 'disabled')
        self.next_btn.config(state='normal' if idx < 2 else 'disabled')
        if idx == 2:
            self.build_preview()
        self.update_stepper()

    def update_stepper(self):
        t = self.colors()
        for i, l in enumerate(self.step_lbls):
            l.config(fg=t['accent'] if i == self.m_idx else (t['fg'] if i < self.m_idx else t['muted']),
                     font=('Tahoma', 10, 'bold' if i == self.m_idx else 'normal'))

    def get_text(self):
        return self.text.get('1.0', 'end-1c').strip('\n')

    def effective_title(self):
        return self.m_title.get().strip() or archiver.auto_title(self.get_text())

    def build_preview(self):
        txt = self.get_text()
        paras = len([x for x in txt.replace('\r', '').split('\n\n') if x.strip()])
        kind = 'چت' if self.m_kind.get() == 'chat' else 'پروژه'
        codes = len(archiver.extract_code(txt))
        extra = ('\n%d قطعه کد جدا هم ذخیره می‌شود (صفحه‌ی «کدها»)' % codes) if codes else ''
        self.sum_lbl.config(text='%s  |  منبع: %s  |  عنوان: %s\n%d پاراگراف، %d کاراکتر، %d فایل%s' % (
            kind, self.m_source.get() or 'Manual', self.effective_title(), paras, len(txt), len(self.m_files), extra))
        self.prev_box.config(state='normal')
        self.prev_box.delete('1.0', 'end')
        self.prev_box.insert('1.0', txt[:1500] + ('\n…' if len(txt) > 1500 else ''))
        self.prev_box.config(state='disabled')

    def preview_browser(self):
        html_text = archiver.preview_html(self.effective_title(), self.get_text())
        fd, path = tempfile.mkstemp(suffix='.html')
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(html_text)
        self.open_path(path)

    def clear_files(self):
        self.m_files = []
        self.files_lbl.config(text='بدون فایل')

    # آرشیو
    def build_archive(self, p):
        self.q = tk.StringVar()
        bar = tk.Frame(p)
        bar.pack(fill='x', pady=(4, 6))
        self.sort_box = ttk.Combobox(bar, values=list(SORTS), state='readonly', width=16, justify='center')
        self.sort_box.set('جدیدترین')
        self.sort_box.pack(side='left')
        tk.Label(bar, text='مرتب‌سازی:').pack(side='left', padx=(6, 4))
        self.src_box = ttk.Combobox(bar, values=['همه'], state='readonly', width=14, justify='center')
        self.src_box.set('همه')
        self.src_box.pack(side='left', padx=(10, 4))
        tk.Label(bar, text='منبع:').pack(side='left')
        tk.Entry(bar, textvariable=self.q).pack(side='right', fill='x', expand=True, padx=(0, 8), ipady=5)
        c = self.card(p)
        c.pack(fill='both', expand=True)
        self.arch_title = self.card_title(c, 'آرشیو')
        self.arch_tree = self.make_tree(c, 8, sortable=True)
        act = tk.Frame(c)
        act.pack(fill='x', padx=14, pady=(0, 6))
        self.make_btn(act, 'باز کردن', lambda: self.open_selected(self.arch_tree)).pack(side='right')
        self.make_btn(act, 'تغییر نام', self.rename_item, ghost=True).pack(side='right', padx=6)
        self.make_btn(act, 'حذف', self.delete_items, ghost=True).pack(side='right')
        tk.Label(act, text='(حذف = انتقال به سطل آرشیو؛ قابل بازگشت)').pack(side='left')
        act.winfo_children()[-1].role = 'muted'
        t2 = tk.Label(c, text='فایل‌ها و کدهای مورد انتخاب‌شده', anchor='e', font=('Tahoma', 10, 'bold'))
        t2.pack(fill='x', padx=14)
        fr = tk.Frame(c)
        fr.pack(fill='x', padx=14, pady=(2, 4))
        self.ftree = ttk.Treeview(fr, columns=('size', 'group', 'name'), show='headings', height=3, selectmode='browse')
        for col, txt, w in (('size', 'حجم', 80), ('group', 'نوع', 70), ('name', 'نام', 420)):
            self.ftree.heading(col, text=txt, anchor='e')
            self.ftree.column(col, width=w, anchor='e', stretch=(col == 'name'))
        self.ftree.pack(fill='x')
        self.ftree.bind('<Double-1>', lambda e: self.open_item_file())
        fb = tk.Frame(c)
        fb.pack(fill='x', padx=14, pady=(0, 10))
        self.make_btn(fb, 'باز کردن فایل', self.open_item_file, ghost=True).pack(side='right')
        self.make_btn(fb, 'حذف فایل', self.delete_item_file, ghost=True).pack(side='right', padx=6)
        self.arch_tree.bind('<<TreeviewSelect>>', lambda e: self.refresh_item_files())
        self.sort_box.bind('<<ComboboxSelected>>', self.on_sort_box)
        self.src_box.bind('<<ComboboxSelected>>', lambda e: self.refresh_archive())
        self.q.trace_add('write', lambda *a: self.refresh_archive())

    def on_sort_box(self, e=None):
        self.sort_col, self.sort_rev = SORTS[self.sort_box.get()]
        self.refresh_archive()

    def sort_by(self, col):
        if self.sort_col == col:
            self.sort_rev = not self.sort_rev
        else:
            self.sort_col, self.sort_rev = col, (col == 'date')
        self.sort_box.set('')
        self.refresh_archive()

    def refresh_archive(self):
        out = self.out.get()
        rows = archiver.load_index(out) + archiver.list_loose_files(out)
        sources = ['همه'] + sorted({r['source'] for r in rows if r['source']})
        self.src_box.config(values=sources)
        if self.src_box.get() not in sources:
            self.src_box.set('همه')
        q, sf = self.q.get().strip().lower(), self.src_box.get()
        rows = [r for r in rows if (sf == 'همه' or r['source'] == sf)
                and (not q or q in (r['title'] + ' ' + r['source']).lower())]
        col = self.sort_col
        rows.sort(key=lambda r: str(r[col]).casefold(), reverse=self.sort_rev)
        self.fill_tree(self.arch_tree, rows)
        for c, txt in TREE_HEADS.items():
            self.arch_tree.heading(c, text=txt + ((' ▼' if self.sort_rev else ' ▲') if c == col else ''))
        self.arch_title.config(text='آرشیو (%d)' % len(rows))
        self.refresh_item_files()

    def refresh_item_files(self):
        rows = self.selected_rows(self.arch_tree)
        self.item_files = archiver.entry_files(self.out.get(), rows[0]) if len(rows) == 1 else []
        self.ftree.delete(*self.ftree.get_children())
        for i, f in enumerate(self.item_files):
            self.ftree.insert('', 'end', iid=str(i), values=(human(f['size']), f['group'], f['name']))

    def rename_item(self):
        rows = self.selected_rows(self.arch_tree)
        if len(rows) != 1:
            messagebox.showinfo('توجه', 'برای تغییر نام، فقط یک مورد را انتخاب کنید.')
            return
        e = rows[0]
        new = simpledialog.askstring('تغییر نام', 'نام جدید:', initialvalue=e['title'], parent=self)
        if not new or new.strip() == e['title']:
            return
        try:
            archiver.rename_entry(self.out.get(), e, new)
            self.log('تغییر نام داده شد: %s ← %s' % (e['title'], new.strip()))
            self.refresh_all()
        except Exception as ex:
            messagebox.showwarning('توجه', str(ex))

    def delete_items(self):
        rows = self.selected_rows(self.arch_tree)
        if not rows:
            messagebox.showinfo('توجه', 'اول یک یا چند مورد را انتخاب کنید.')
            return
        if not messagebox.askyesno('حذف', '%d مورد (همراه فایل‌های Markdown/HTML و کدهای جداشده‌شان) '
                                          'به سطل آرشیو منتقل شود؟' % len(rows)):
            return
        for r in rows:
            try:
                archiver.delete_entry(self.out.get(), r)
            except Exception as ex:
                self.log('خطا در حذف %s: %s' % (r['title'], ex))
        self.log('%d مورد به سطل منتقل شد.' % len(rows))
        self.refresh_all()

    def sel_item_file(self):
        sel = self.ftree.selection()
        return self.item_files[int(sel[0])] if sel else None

    def open_item_file(self):
        f = self.sel_item_file()
        if f:
            self.open_path(f['path'])

    def delete_item_file(self):
        f = self.sel_item_file()
        if not f:
            messagebox.showinfo('توجه', 'یک فایل را از فهرست پایین انتخاب کنید.')
            return
        if messagebox.askyesno('حذف فایل', 'فایل «%s» به سطل آرشیو منتقل شود؟' % f['name']):
            archiver.delete_file(self.out.get(), f['path'])
            self.log('فایل به سطل منتقل شد: ' + f['name'])
            self.refresh_item_files()
            self.refresh_code()

    # کدها
    def build_code(self, p):
        self.cq = tk.StringVar()
        bar = tk.Frame(p)
        bar.pack(fill='x', pady=(4, 6))
        self.make_btn(bar, 'بازخوانی', self.refresh_code, ghost=True).pack(side='left')
        tk.Entry(bar, textvariable=self.cq).pack(side='right', fill='x', expand=True, padx=(0, 8), ipady=5)
        c = self.card(p)
        c.pack(fill='both', expand=True)
        self.code_title = self.card_title(c, 'کدها')
        self.note(c, 'کدهای داخل چت‌ها و پروژه‌ها (بلوک‌های ```) جدا از متن چت ذخیره می‌شوند. '
                     'یک کد را انتخاب کنید و «کپی کد» را بزنید.')
        body = tk.Frame(c)
        body.pack(fill='both', expand=True, padx=10, pady=(6, 4))
        left = tk.Frame(body)
        left.pack(side='right', fill='y')
        self.code_tree = ttk.Treeview(left, columns=('ext', 'name', 'title'), show='headings', height=14,
                                      selectmode='browse')
        for col, txt, w in (('ext', 'زبان', 50), ('name', 'فایل', 130), ('title', 'چت / پروژه', 190)):
            self.code_tree.heading(col, text=txt, anchor='e')
            self.code_tree.column(col, width=w, anchor='e', stretch=(col == 'title'))
        sb = ttk.Scrollbar(left, orient='vertical', command=self.code_tree.yview)
        self.code_tree.configure(yscrollcommand=sb.set)
        sb.pack(side='left', fill='y')
        self.code_tree.pack(side='right', fill='y')
        right = tk.Frame(body)
        right.pack(side='left', fill='both', expand=True, padx=(0, 8))
        self.code_view = tk.Text(right, wrap='none', height=14, bd=0, relief='flat', font=('Consolas', 10))
        xs = ttk.Scrollbar(right, orient='horizontal', command=self.code_view.xview)
        ys = ttk.Scrollbar(right, orient='vertical', command=self.code_view.yview)
        self.code_view.configure(xscrollcommand=xs.set, yscrollcommand=ys.set)
        xs.pack(side='bottom', fill='x')
        ys.pack(side='right', fill='y')
        self.code_view.pack(side='left', fill='both', expand=True)
        row = tk.Frame(c)
        row.pack(fill='x', padx=14, pady=(2, 12))
        self.copy_btn = self.make_btn(row, 'کپی کد', self.copy_code, big=True)
        self.copy_btn.pack(side='right')
        self.make_btn(row, 'ذخیره به‌عنوان...', self.save_code_as, ghost=True).pack(side='right', padx=8)
        self.make_btn(row, 'باز کردن', self.open_code_file, ghost=True).pack(side='right')
        self.make_btn(row, 'حذف', self.delete_code, ghost=True).pack(side='left')
        self.code_tree.bind('<<TreeviewSelect>>', lambda e: self.show_code())
        self.cq.trace_add('write', lambda *a: self.refresh_code())

    def refresh_code(self):
        q = self.cq.get().strip().lower()
        items = [x for x in archiver.list_code(self.out.get())
                 if not q or q in (x['title'] + ' ' + x['name'] + ' ' + x['ext']).lower()]
        self.code_items = items
        self.code_tree.delete(*self.code_tree.get_children())
        for i, x in enumerate(items):
            self.code_tree.insert('', 'end', iid=str(i), values=(x['ext'], x['name'], x['title']))
        self.code_title.config(text='کدها (%d)' % len(items))
        self.set_code_view('')

    def set_code_view(self, text):
        self.code_view.config(state='normal')
        self.code_view.delete('1.0', 'end')
        self.code_view.insert('1.0', text)
        self.code_view.config(state='disabled')

    def sel_code(self):
        sel = self.code_tree.selection()
        return self.code_items[int(sel[0])] if sel else None

    def read_code(self, item):
        with open(item['path'], 'r', encoding='utf-8', errors='replace') as f:
            return f.read()

    def show_code(self):
        item = self.sel_code()
        self.set_code_view(self.read_code(item)[:300000] if item else '')

    def copy_code(self):
        item = self.sel_code()
        if not item:
            messagebox.showinfo('توجه', 'اول یک کد را از فهرست انتخاب کنید.')
            return
        self.clipboard_clear()
        self.clipboard_append(self.read_code(item))
        self.update()
        self.copy_btn.config(text='کپی شد ✓')
        self.after(1400, lambda: self.copy_btn.config(text='کپی کد'))

    def save_code_as(self):
        item = self.sel_code()
        if not item:
            return
        dest = filedialog.asksaveasfilename(initialfile=item['name'])
        if dest:
            shutil.copy2(item['path'], dest)
            self.log('کد ذخیره شد: ' + dest)

    def open_code_file(self):
        item = self.sel_code()
        if item:
            self.open_path(item['path'])

    def delete_code(self):
        item = self.sel_code()
        if item and messagebox.askyesno('حذف کد', 'فایل «%s» به سطل آرشیو منتقل شود؟' % item['name']):
            archiver.delete_file(self.out.get(), item['path'])
            self.refresh_code()

    # خروجی
    def build_export(self, p):
        c = self.card(p)
        c.pack(fill='x', pady=6)
        self.card_title(c, 'خروجی: یک فایل واحد')
        self.note(c, 'همه‌ی چت‌ها و پروژه‌های آرشیو را در یک فایل Markdown پشت سر هم جمع می‌کند؛ '
                     'مناسب برای خواندن پیوسته، جستجو یا دادن به یک ابزار دیگر.')
        self.make_btn(c, 'ساخت فایل Markdown واحد', self.do_export, big=True).pack(pady=14)

    def do_export(self):
        dest = filedialog.asksaveasfilename(defaultextension='.md', initialfile='AllChats.md',
                                            filetypes=[('Markdown', '*.md')])
        if not dest:
            return
        try:
            n = archiver.export_combined(self.out.get(), dest)
            self.log('خروجی ساخته شد: %s (%d فایل)' % (dest, n))
            messagebox.showinfo('انجام شد', '%d مورد در یک فایل جمع شد.' % n)
        except Exception as e:
            self.log('خطا: %s' % e)

    # پشتیبان‌گیری
    def build_backup(self, p):
        c = self.card(p)
        c.pack(fill='x', pady=6)
        self.card_title(c, 'پشتیبان‌گیری کامل')
        self.note(c, 'یک نسخه‌ی ZIP از کل آرشیو (چت‌ها، فایل‌ها، پروژه‌ها و JSON خام) با تاریخ و ساعت می‌سازد. '
                     'پوشه‌ی پشتیبان باید بیرون از پوشه‌ی آرشیو باشد (ترجیحاً روی درایو دیگر).')
        r = tk.Frame(c)
        r.pack(fill='x', padx=14, pady=10)
        self.make_btn(r, 'باز کردن', lambda: self.open_dir(self.backup_dir.get()), ghost=True).pack(side='left')
        self.make_btn(r, 'تغییر', self.pick_backup).pack(side='left', padx=6)
        tk.Entry(r, textvariable=self.backup_dir).pack(side='left', fill='x', expand=True, padx=6, ipady=4)
        self.make_btn(c, 'ساخت پشتیبان ZIP', self.do_backup, big=True).pack(pady=(4, 14))

    def do_backup(self):
        out, dest = self.out.get(), self.backup_dir.get()
        self.busy = True

        def work():
            try:
                path = archiver.backup_zip(out, dest)
                self.after(0, lambda: self.backup_done(path))
            except Exception as e:
                err = str(e)
                self.after(0, lambda: (self.log('خطا: ' + err), self.toggle_log(True)))
            self.busy = False

        threading.Thread(target=work, daemon=True).start()

    def backup_done(self, path):
        self.settings['last_backup'] = datetime.datetime.now().isoformat(timespec='minutes')
        self.save_settings()
        self.log('پشتیبان ساخته شد: ' + path)
        self.toggle_log(True)
        self.refresh_home()

    # تنظیمات
    def build_settings(self, p):
        c = self.card(p)
        c.pack(fill='x', pady=6)
        self.card_title(c, 'ظاهر برنامه')
        r = tk.Frame(c)
        r.pack(fill='x', padx=14, pady=10)
        self.toggle_btn = self.make_btn(r, '', self.toggle_daynight)
        self.toggle_btn.pack(side='left')
        self.theme_box = ttk.Combobox(r, values=list(THEMES), state='readonly', width=14, justify='center')
        self.theme_box.pack(side='right', padx=8)
        self.theme_box.bind('<<ComboboxSelected>>', lambda e: self.set_theme(self.theme_box.get()))
        tk.Label(r, text='تم:').pack(side='right')
        tk.Checkbutton(c, text='انیمیشن هدر', variable=self.anim, anchor='e').pack(fill='x', padx=14, pady=(0, 12))
        c2 = self.card(p)
        c2.pack(fill='x', pady=6)
        self.card_title(c2, 'سطل آرشیو')
        self.note(c2, 'موردهایی که حذف می‌کنید به پوشه‌ی .trash داخل آرشیو منتقل می‌شوند و تا وقتی سطل را خالی '
                      'نکنید، قابل بازگرداندن‌اند (فایل‌ها را از آن پوشه به جای اولشان برگردانید).')
        r2 = tk.Frame(c2)
        r2.pack(fill='x', padx=14, pady=10)
        self.make_btn(r2, 'خالی کردن سطل', self.do_empty_trash).pack(side='right')
        self.make_btn(r2, 'باز کردن سطل', lambda: self.open_dir(os.path.join(self.out.get(), '.trash')),
                      ghost=True).pack(side='right', padx=8)

    def do_empty_trash(self):
        if messagebox.askyesno('خالی کردن سطل', 'همه‌ی موردهای سطل برای همیشه پاک شوند؟'):
            n = archiver.empty_trash(self.out.get())
            self.log('سطل خالی شد (%d فایل).' % n)

    def toggle_daynight(self):
        self.set_theme('روز' if self.theme_name in NIGHT else 'شب')

    # راهنما
    def build_help(self, p):
        c = self.card(p)
        c.pack(fill='x', pady=6)
        self.card_title(c, 'راهنما')
        self.note(c, HELP, wrap=760)
        tk.Frame(c, height=10).pack()

    # ---------- تم ----------
    def set_theme(self, name):
        self.theme_name = name
        t = self.colors()
        self.configure(bg=t['bg'])
        self.theme_box.set(name)
        self.toggle_btn.config(text='☀ حالت روز' if name in NIGHT else '☾ حالت شب')
        s = self.style
        s.configure('TCombobox', fieldbackground=t['card'], background=t['card'], foreground=t['fg'],
                    arrowcolor=t['accent'], bordercolor=t['border'])
        s.map('TCombobox', fieldbackground=[('readonly', t['card'])], foreground=[('readonly', t['fg'])])
        s.configure('Treeview', background=t['card'], fieldbackground=t['card'], foreground=t['fg'], rowheight=28,
                    borderwidth=0)
        s.configure('Treeview.Heading', background=t['soft'], foreground=t['muted'], relief='flat',
                    font=('Tahoma', 9, 'bold'))
        s.map('Treeview', background=[('selected', t['accent'])], foreground=[('selected', '#ffffff')])
        s.configure('Vertical.TScrollbar', background=t['border'], troughcolor=t['card'], bordercolor=t['card'],
                    arrowcolor=t['muted'])
        self.option_add('*TCombobox*Listbox.background', t['card'])
        self.option_add('*TCombobox*Listbox.foreground', t['fg'])
        self.option_add('*TCombobox*Listbox.selectBackground', t['accent'])
        self.walk(self, t)
        self.refresh_nav()
        self.update_stepper()
        self.build_header()
        self.save_settings()

    def walk(self, widget, t):
        for w in widget.winfo_children():
            c, role = w.winfo_class(), getattr(w, 'role', None)
            try:
                pbg = w.master.cget('bg')
            except Exception:
                pbg = t['bg']
            try:
                if c == 'Frame':
                    if role == 'card':
                        w.config(bg=t['card'], highlightthickness=1, highlightbackground=t['border'])
                    elif role == 'side':
                        w.config(bg=t['card'], highlightthickness=1, highlightbackground=t['border'])
                    else:
                        w.config(bg=pbg)
                elif c == 'Label':
                    if role == 'nav':
                        pass
                    elif role == 'insight':
                        w.config(bg=t['soft'], fg=t['fg'])
                    elif role == 'static':
                        w.config(bg=pbg)
                    else:
                        w.config(bg=pbg, fg={'muted': t['muted'], 'accent': t['accent']}.get(role, t['fg']))
                elif c in ('Radiobutton', 'Checkbutton'):
                    w.config(bg=pbg, fg=t['fg'], selectcolor=t['card'], activebackground=pbg,
                             activeforeground=t['fg'])
                elif c == 'Entry':
                    w.config(bg=t['card'], fg=t['fg'], insertbackground=t['fg'], relief='flat',
                             highlightthickness=1, highlightbackground=t['border'], highlightcolor=t['accent'])
                elif c == 'Text':
                    w.config(bg=t['card'], fg=t['fg'], insertbackground=t['fg'], highlightthickness=1,
                             highlightbackground=t['border'], highlightcolor=t['accent'])
                elif c == 'Button':
                    if role == 'ghost':
                        w.config(bg=t['card'], fg=t['accent'], activebackground=t['soft'], activeforeground=t['accent'])
                    else:
                        w.config(bg=t['accent'], fg='#ffffff', activebackground=t['accent2'], activeforeground='#ffffff')
                elif c == 'Canvas' and w not in (self.header, self.busy_bar):
                    w.config(bg=pbg)
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
        w = max(c.winfo_width(), 900)
        self.hw = w
        steps = 70
        for i in range(steps):
            c.create_rectangle(i * w / steps, 0, (i + 1) * w / steps + 1, HH, outline='',
                               fill=lerp(t['grad'][0], t['grad'][1], i / (steps - 1)))
        sym, col = t['deco']
        c.create_text(46, HH / 2, text=sym, fill=col, font=('Tahoma', 26))
        fx = t['fx']
        self.parts = []
        for _ in range(fx['n']):
            size = max(7, int(random.randint(*fx['size']) * 0.6))
            x, y = random.uniform(0, w), random.uniform(0, HH)
            item = c.create_text(x, y, text=fx['sym'], fill=random.choice(fx['colors']), font=('Tahoma', size))
            self.parts.append(dict(id=item, x=x, y=y, s=random.uniform(0.3, 0.9), ph=random.uniform(0, 6.28)))
        shadow = lerp(t['grad'][0], '#000000', 0.55)
        c.create_text(w / 2 + 1, 24, text='آرشیو چت‌ها', fill=shadow, font=('Tahoma', 17, 'bold'))
        c.create_text(w / 2, 23, text='آرشیو چت‌ها', fill='#ffffff', font=('Tahoma', 17, 'bold'))
        c.create_text(w / 2, 47, text='ChatArchiver', fill='#ffffff', font=('Tahoma', 9))

    def tick(self):
        try:
            t = self.colors()
            mode, w = t['fx']['mode'], max(self.hw, 900)
            now = self.tk.call('clock', 'milliseconds') / 1000.0
            if self.anim.get():
                for p in self.parts:
                    if mode == 'drift':
                        p['x'] += p['s']
                        if p['x'] > w + 50:
                            p['x'] = -50
                    elif mode == 'rise':
                        p['y'] -= p['s']
                        p['x'] += math.sin(now * 1.5 + p['ph']) * 0.5
                        if p['y'] < -15:
                            p['y'], p['x'] = HH + 15, random.uniform(0, w)
                    elif mode == 'fall':
                        p['y'] += p['s']
                        p['x'] += math.sin(now * 1.2 + p['ph']) * 0.8
                        if p['y'] > HH + 15:
                            p['y'], p['x'] = -15, random.uniform(0, w)
                    elif mode == 'twinkle':
                        p['x'] += p['s'] * 0.08
                        if p['x'] > w + 10:
                            p['x'] = -10
                        if random.random() < 0.02:
                            self.header.itemconfig(p['id'], fill=random.choice(t['fx']['colors']))
                    self.header.coords(p['id'], p['x'], p['y'])
            b = self.busy_bar
            b.config(bg=t['bg'])
            b.delete('all')
            bw = max(b.winfo_width(), 10)
            b.create_rectangle(0, 0, bw, 4, fill=t['border'], outline='')
            if self.busy:
                self.busy_pos = (self.busy_pos + 14) % (bw + 160)
                b.create_rectangle(self.busy_pos - 160, 0, self.busy_pos, 4, fill=t['accent'], outline='')
        except tk.TclError:
            return
        self.after(40, self.tick)

    # ---------- کلیپ‌بورد (Ctrl+V با کیبورد فارسی) ----------
    def setup_clipboard(self):
        def on_key(e):
            w = e.widget
            if w.winfo_class() not in ('Text', 'Entry', 'TCombobox'):
                return None
            k = e.keycode
            if k == 65:
                if w.winfo_class() == 'Text':
                    w.tag_add('sel', '1.0', 'end-1c')
                else:
                    w.select_range(0, 'end')
                    w.icursor('end')
                return 'break'
            if e.keysym.lower() in ('v', 'c', 'x'):
                return None
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

    def refresh_rtl(self):
        t = self.text
        t.tag_remove('rtl', '1.0', 'end')
        n = int(t.index('end-1c').split('.')[0])
        if n > 5000:
            return
        for i in range(1, n + 1):
            if is_rtl_line(t.get('%d.0' % i, '%d.end' % i)):
                t.tag_add('rtl', '%d.0' % i, '%d.end' % i)

    def paste_clip(self):
        try:
            data = self.clipboard_get()
        except tk.TclError:
            messagebox.showinfo('توجه', 'کلیپ‌بورد خالی است. اول متن را کپی کنید.')
            return
        self.text.insert('insert', data)
        self.text.focus_set()
        self.refresh_rtl()

    # ---------- عملیات ----------
    def toggle_log(self, show=None):
        show = (not self.log_visible) if show is None else show
        if show:
            self.logbox.pack(fill='x', pady=(4, 0))
        else:
            self.logbox.pack_forget()
        self.log_btn.config(text='▾ گزارش عملیات' if show else '▸ گزارش عملیات')
        self.log_visible = show

    def log(self, msg):
        self.after(0, lambda: (self.logbox.insert('end', msg + '\n'), self.logbox.see('end')))

    def open_path(self, path):
        path = os.path.normpath(path)
        if not os.path.exists(path):
            return
        if path.lower().endswith(('.html', '.htm')):
            try:
                if webbrowser.open(pathlib.Path(path).as_uri()):
                    return
            except Exception:
                pass
        for target in (path, os.path.dirname(path)):
            try:
                os.startfile(target)
                return
            except Exception:
                continue
        self.log('مسیر: ' + path)

    def open_dir(self, d):
        os.makedirs(d, exist_ok=True)
        self.open_path(d)

    def open_folder(self):
        self.open_dir(self.out.get())

    def pick_src(self):
        p = filedialog.askopenfilename(filetypes=[('ZIP', '*.zip'), ('All', '*.*')]) or filedialog.askdirectory()
        if p:
            self.src.set(p)

    def pick_out(self):
        p = filedialog.askdirectory()
        if p:
            self.out.set(p)
            self.save_settings()
            self.refresh_all()

    def pick_backup(self):
        p = filedialog.askdirectory()
        if p:
            self.backup_dir.set(p)
            self.save_settings()

    def pick_files(self):
        fs = filedialog.askopenfilenames()
        if fs:
            self.m_files = list(fs)
            self.files_lbl.config(text='%d فایل انتخاب شد' % len(fs))

    def start(self):
        if not self.src.get():
            messagebox.showwarning('توجه', 'اول فایل ZIP را انتخاب کنید.')
            return
        src, out = self.src.get(), self.out.get()
        self.btn.config(state='disabled')
        self.busy = True
        self.toggle_log(True)
        threading.Thread(target=self.work, args=(src, out), daemon=True).start()

    def work(self, src, out):
        try:
            archiver.run(src, out, self.log)
        except Exception as e:
            self.log('خطا: %s' % e)
        self.busy = False
        self.after(0, lambda: (self.btn.config(state='normal'), self.show_page('archive')))

    def save_manual(self):
        try:
            archiver.add_manual(self.out.get(), self.m_kind.get(), self.m_title.get(), self.m_source.get(),
                                self.get_text(), self.m_files, self.log)
            self.text.delete('1.0', 'end')
            self.m_title.set('')
            self.clear_files()
            self.m_go(0)
            self.show_page('archive')
        except Exception as e:
            messagebox.showwarning('توجه', str(e))


if __name__ == '__main__':
    App().mainloop()
