"""هسته برنامه: آرشیو چت‌ها، پروژه‌ها و فایل‌ها + کدهای جداشده."""
import datetime
import html
import json
import os
import re
import shutil
import tempfile
import zipfile

KINDS = ('chat', 'project', 'file')


# ---------- ابزارهای پایه ----------
def safe(name, n=60):
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', ' ', str(name or '')).strip(' .')
    return (name[:n].strip(' .') or 'untitled')


def ts(v):
    try:
        if isinstance(v, (int, float)):
            return datetime.datetime.fromtimestamp(v)
        if isinstance(v, str) and v:
            return datetime.datetime.fromisoformat(v.replace('Z', '+00:00'))
    except Exception:
        pass
    return None


def fmt(d, f='%Y-%m-%d %H:%M'):
    return d.strftime(f) if d else ''


def load_json(p):
    with open(p, 'r', encoding='utf-8') as f:
        return json.load(f)


def posix(p):
    return p.replace('\\', '/')


# ---------- تبدیل پیام‌ها ----------
def chatgpt_messages(conv):
    mapping = conv.get('mapping') or {}
    node, chain, seen = conv.get('current_node'), [], set()
    while node and node in mapping and node not in seen:
        seen.add(node)
        chain.append(mapping[node])
        node = mapping[node].get('parent')
    chain.reverse()
    if not chain:
        chain = sorted([n for n in mapping.values() if n.get('message')],
                       key=lambda n: n['message'].get('create_time') or 0)
    msgs = []
    for n in chain:
        m = n.get('message')
        if not m:
            continue
        role = (m.get('author') or {}).get('role')
        if role == 'system':
            continue
        c = m.get('content') or {}
        out = []
        for p in c.get('parts') or []:
            if isinstance(p, str):
                out.append(p)
            elif isinstance(p, dict):
                if p.get('text'):
                    out.append(p['text'])
                elif 'asset_pointer' in p:
                    out.append('[تصویر/فایل: %s]' % p.get('asset_pointer', ''))
        if not out and c.get('text'):
            out.append(c['text'])
        text = '\n'.join(x for x in out if x).strip()
        if text:
            msgs.append((role or 'unknown', text, ts(m.get('create_time'))))
    return msgs


def claude_messages(conv):
    msgs = []
    for m in conv.get('chat_messages') or []:
        role = 'user' if m.get('sender') == 'human' else 'assistant'
        text = m.get('text') or ''
        if not text and isinstance(m.get('content'), list):
            text = '\n'.join(b.get('text', '') for b in m['content']
                             if isinstance(b, dict) and b.get('type') == 'text')
        for a in m.get('attachments') or []:
            text += '\n\n📎 %s\n```\n%s\n```' % (a.get('file_name', ''), a.get('extracted_content', ''))
        for f in m.get('files') or []:
            text += '\n\n📎 ' + str(f.get('file_name', ''))
        if text.strip():
            msgs.append((role, text.strip(), ts(m.get('created_at'))))
    return msgs


# ---------- متن → HTML (حفظ ساختار و راست‌به‌چپ) ----------
CSS = (
    "body{font-family:Tahoma,Segoe UI,sans-serif;max-width:860px;margin:2em auto;padding:0 1em;background:#f5f5f7}"
    ".m{padding:.8em 1em;margin:.6em 0;border-radius:10px;line-height:1.9;overflow-wrap:anywhere}"
    ".user{background:#dbeafe}.assistant{background:#fff}.r{font-size:.75em;color:#666;margin-bottom:.3em}"
    ".m p,.m h1,.m h2,.m h3,.m h4,.m ul,.m ol,.m blockquote{margin:.45em 0;text-align:start;unicode-bidi:plaintext}"
    ".codebox{position:relative;margin:.6em 0}"
    ".m pre{direction:ltr;text-align:left;background:#0f172a;color:#e2e8f0;padding:2em .8em .8em;border-radius:8px;"
    "overflow-x:auto;white-space:pre;margin:0}"
    ".cp{position:absolute;top:6px;left:8px;border:0;border-radius:6px;padding:.2em .8em;background:#7b22cc;"
    "color:#fff;cursor:pointer;font-size:.8em}"
    ".m code{direction:ltr;unicode-bidi:isolate;background:rgba(127,127,127,.18);padding:0 .25em;border-radius:4px;"
    "font-family:Consolas,monospace}.m pre code{background:none;padding:0}"
    ".m table{border-collapse:collapse;margin:.5em 0}.m td,.m th{border:1px solid #aaa;padding:.3em .6em}"
    ".m blockquote{border-inline-start:4px solid #8aa;padding-inline-start:.8em;color:#555}bdi{unicode-bidi:isolate}"
    "input{width:100%;padding:.6em;font-size:1em;margin-bottom:1em}a{display:block;padding:.35em 0}"
)
COPY_JS = ("<script>function cp(b){var t=b.parentNode.querySelector('code').innerText;"
           "function ok(){b.textContent='کپی شد ✓';setTimeout(function(){b.textContent='کپی'},1400)}"
           "if(navigator.clipboard&&window.isSecureContext){navigator.clipboard.writeText(t).then(ok)}"
           "else{var a=document.createElement('textarea');a.value=t;document.body.appendChild(a);a.select();"
           "document.execCommand('copy');a.remove();ok()}}</script>")

_W = r'[A-Za-z0-9](?:[A-Za-z0-9_\-./:@#=%\\]*[A-Za-z0-9])?[+#]*'
LATIN = re.compile(r'<[^>]+>|&#?\w+;|(' + _W + r'(?: ' + _W + r')*)')
BLOCK = re.compile(r'^\s*(```|#{1,6}\s|[-*•]\s|\d+[.)]\s|\||>)')


def inline(s):
    out = []
    for p in re.split(r'(`[^`\n]+`)', s):
        if len(p) > 2 and p.startswith('`') and p.endswith('`'):
            out.append('<code>%s</code>' % html.escape(p[1:-1]))
            continue
        e = html.escape(p, quote=False)
        e = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', e)
        e = re.sub(r'(?<![*\w])\*(?!\s)(.+?)(?<!\s)\*(?![*\w])', r'<i>\1</i>', e)
        e = re.sub(r'\[([^\]]+)\]\((https?://[^)\s]+)\)', r'<a href="\2">\1</a>', e)
        e = LATIN.sub(lambda m: '<bdi dir="ltr">%s</bdi>' % m.group(1) if m.group(1) else m.group(0), e)
        out.append(e)
    return ''.join(out)


def md_to_html(text):
    lines = str(text).replace('\r\n', '\n').replace('\r', '\n').split('\n')
    out, i = [], 0
    while i < len(lines):
        ln = lines[i]
        st = ln.strip()
        if st.startswith('```'):
            i += 1
            buf = []
            while i < len(lines) and not lines[i].strip().startswith('```'):
                buf.append(lines[i])
                i += 1
            i += 1
            out.append('<div class="codebox"><button class="cp" onclick="cp(this)">کپی</button>'
                       '<pre dir="ltr"><code>%s</code></pre></div>' % html.escape('\n'.join(buf)))
            continue
        if not st:
            i += 1
            continue
        m = re.match(r'^(#{1,6})\s+(.*)', st)
        if m:
            lv = min(len(m.group(1)) + 1, 6)
            out.append('<h%d dir="auto">%s</h%d>' % (lv, inline(m.group(2)), lv))
            i += 1
            continue
        if re.match(r'^\s*([-*•]|\d+[.)])\s+', ln):
            ordered = bool(re.match(r'^\s*\d+[.)]\s+', ln))
            pat = r'^\s*\d+[.)]\s+' if ordered else r'^\s*[-*•]\s+'
            items = []
            while i < len(lines) and re.match(pat, lines[i]):
                items.append(re.sub(pat, '', lines[i]))
                i += 1
            tag = 'ol' if ordered else 'ul'
            out.append('<%s dir="auto">%s</%s>' % (tag, ''.join('<li dir="auto">%s</li>' % inline(x) for x in items), tag))
            continue
        if st.startswith('|'):
            rows = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                cells = [c.strip() for c in lines[i].strip().strip('|').split('|')]
                if not all(re.fullmatch(r':?-{2,}:?', c) for c in cells if c):
                    rows.append(cells)
                i += 1
            out.append('<table>%s</table>' % ''.join(
                '<tr>%s</tr>' % ''.join('<td dir="auto">%s</td>' % inline(c) for c in r) for r in rows))
            continue
        if st.startswith('>'):
            buf = []
            while i < len(lines) and lines[i].strip().startswith('>'):
                buf.append(lines[i].strip().lstrip('>').strip())
                i += 1
            out.append('<blockquote dir="auto">%s</blockquote>' % '<br>'.join(inline(x) for x in buf))
            continue
        buf = [ln.strip()]
        i += 1
        while i < len(lines) and lines[i].strip() and not BLOCK.match(lines[i]):
            buf.append(lines[i].strip())
            i += 1
        out.append('<p dir="auto">%s</p>' % '<br>'.join(inline(x) for x in buf))
    return '\n'.join(out)


def page_html(title, body):
    return ('<!doctype html><html lang="fa"><meta charset="utf-8"><title>%s</title><style>%s</style>'
            '<h2 dir="auto">%s</h2>%s%s' % (html.escape(title), CSS, html.escape(title), body, COPY_JS))


# ---------- جداسازی کد ----------
LANG_EXT = {
    'python': 'py', 'py': 'py', 'javascript': 'js', 'js': 'js', 'typescript': 'ts', 'ts': 'ts', 'html': 'html',
    'css': 'css', 'json': 'json', 'bash': 'sh', 'sh': 'sh', 'shell': 'sh', 'powershell': 'ps1', 'ps1': 'ps1',
    'mql5': 'mq5', 'mq5': 'mq5', 'mql4': 'mq4', 'cpp': 'cpp', 'c++': 'cpp', 'c': 'c', 'csharp': 'cs', 'cs': 'cs',
    'java': 'java', 'kotlin': 'kt', 'sql': 'sql', 'yaml': 'yml', 'yml': 'yml', 'xml': 'xml', 'markdown': 'md',
    'md': 'md', 'gdscript': 'gd', 'gd': 'gd', 'swift': 'swift', 'go': 'go', 'rust': 'rs', 'php': 'php',
    'ruby': 'rb', 'dart': 'dart', 'lua': 'lua', 'bat': 'bat', 'batch': 'bat', 'cmd': 'bat', 'gradle': 'gradle',
    'toml': 'toml', 'ini': 'ini', 'csv': 'csv', 'text': 'txt', 'txt': 'txt'}
FENCE = re.compile(r'^[ \t]*```[ \t]*([\w+#.\-]*)[^\n]*\n(.*?)^[ \t]*```[ \t]*$', re.S | re.M)


def extract_code(text):
    """[(زبان, کد)] از بلوک‌های ``` داخل متن."""
    t = str(text or '').replace('\r\n', '\n')
    return [(m.group(1).lower(), m.group(2).rstrip('\n')) for m in FENCE.finditer(t) if m.group(2).strip()]


def save_code(dest_dir, title, source, texts):
    blocks = []
    for t in texts:
        blocks += extract_code(t)
    if not blocks:
        return 0
    os.makedirs(dest_dir, exist_ok=True)
    for i, (lang, code) in enumerate(blocks, 1):
        ext = LANG_EXT.get(lang) or (lang if lang.isalnum() and len(lang) <= 5 else 'txt')
        name = '%02d_%s.%s' % (i, safe(lang or 'code', 20), ext)
        with open(os.path.join(dest_dir, name), 'w', encoding='utf-8', newline='\n') as f:
            f.write(code + '\n')
    with open(os.path.join(dest_dir, 'code_meta.json'), 'w', encoding='utf-8') as f:
        json.dump({'title': title, 'source': source}, f, ensure_ascii=False)
    return len(blocks)


def list_code(out):
    """همه‌ی تکه‌کدهای جداشده‌ی آرشیو."""
    res = []
    for dp, dn, files in os.walk(out):
        dn[:] = [d for d in dn if d not in ('.trash', 'raw_json')]
        if 'code_meta.json' not in files:
            continue
        try:
            meta = load_json(os.path.join(dp, 'code_meta.json'))
        except Exception:
            meta = {}
        for n in sorted(files):
            if n == 'code_meta.json':
                continue
            p = os.path.join(dp, n)
            res.append(dict(title=meta.get('title', ''), source=meta.get('source', ''), name=n, path=p,
                            ext=os.path.splitext(n)[1].lstrip('.'), size=os.path.getsize(p)))
    res.sort(key=lambda r: (r['title'].casefold(), r['name']))
    return res


# ---------- نوشتن چت و پروژه ----------
def entry(out, source, title, date, page, kind):
    return dict(source=source, title=title, date=date, rel=posix(os.path.relpath(page, out)), kind=kind)


def write_chat(folder, title, created, msgs, source, files=None):
    base = '%s_%s' % (fmt(created, '%Y-%m-%d') or 'nodate', safe(title))
    path, i = os.path.join(folder, base), 2
    while os.path.exists(path + '.md'):
        path = os.path.join(folder, '%s_%d' % (base, i))
        i += 1
    if files:
        fdir = path + '_files'
        os.makedirs(fdir, exist_ok=True)
        names = []
        for fp in files:
            if os.path.isfile(fp):
                shutil.copy2(fp, os.path.join(fdir, os.path.basename(fp)))
                names.append(os.path.basename(fp))
        if names:
            extra = '\n'.join('📎 ' + n for n in names)
            if msgs:
                role, text, t = msgs[-1]
                msgs = msgs[:-1] + [(role, text + '\n\n' + extra, t)]
            else:
                msgs = [('متن/یادداشت', extra, created)]
    md = ['# %s' % title, '', '%s — %s' % (source, fmt(created)), '']
    body = []
    for role, text, t in msgs:
        who = 'من' if role == 'user' else ('هوش مصنوعی' if role == 'assistant' else role)
        md += ['## %s  %s' % (who, fmt(t)), '', text, '']
        body.append('<div class="m %s"><div class="r" dir="rtl">%s %s</div>%s</div>' % (
            'user' if role == 'user' else 'assistant', html.escape(who), fmt(t), md_to_html(text)))
    with open(path + '.md', 'w', encoding='utf-8') as f:
        f.write('\n'.join(md))
    with open(path + '.html', 'w', encoding='utf-8') as f:
        f.write(page_html(title, '\n'.join(body)))
    save_code(path + '_code', title, source, [m[1] for m in msgs])
    return path + '.html'


def write_project(pdir, title, source, text, files, date):
    os.makedirs(pdir, exist_ok=True)
    names = []
    for fp in files or []:
        if os.path.isfile(fp):
            shutil.copy2(fp, os.path.join(pdir, os.path.basename(fp)))
            names.append(os.path.basename(fp))
    with open(os.path.join(pdir, 'README.md'), 'w', encoding='utf-8') as f:
        f.write('# %s\n\n%s\n' % (title, text or ''))
    links = ''.join('<a href="%s">%s</a>' % (html.escape(n), html.escape(n)) for n in names)
    page = os.path.join(pdir, 'index.html')
    with open(page, 'w', encoding='utf-8') as f:
        f.write(page_html(title, '<div class="m assistant">%s</div>%s' % (md_to_html(text or ''), links)))
    save_code(os.path.join(pdir, 'code'), title, source, [text or ''])
    return page


def write_index(out, new=(), remove=()):
    merged = {e['rel']: e for e in load_index(out)}
    for r in remove:
        merged.pop(r, None)
    for e in new:
        merged[e['rel']] = e
    rows = sorted(merged.values(), key=lambda e: e['date'], reverse=True)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, '.index.json'), 'w', encoding='utf-8') as f:
        json.dump(rows, f, ensure_ascii=False)
    links = '\n'.join('<a dir="auto" href="%s">%s — %s — %s</a>' % (
        html.escape(quote_rel(e['rel'])), html.escape(e['source']), e['date'], html.escape(e['title'])) for e in rows)
    js = ("<script>document.getElementById('q').oninput=function(){var v=this.value.toLowerCase();"
          "document.querySelectorAll('a').forEach(function(a){a.style.display="
          "a.textContent.toLowerCase().includes(v)?'':'none'})}</script>")
    with open(os.path.join(out, 'index.html'), 'w', encoding='utf-8') as f:
        f.write('<!doctype html><meta charset="utf-8"><title>آرشیو چت‌ها</title><style>%s</style>'
                '<h2>آرشیو چت‌ها (%d)</h2><input id="q" placeholder="جستجو در عنوان‌ها...">%s%s'
                % (CSS, len(rows), links, js))


def quote_rel(rel):
    from urllib.parse import quote
    return quote(rel)


def load_index(out):
    """فهرست آرشیو: لیست دیکشنری‌ها (جدیدترین اول). فرمت قدیمی هم خوانده می‌شود."""
    try:
        raw = load_json(os.path.join(out, '.index.json'))
    except Exception:
        raw = []
    rows = []
    for e in raw:
        if isinstance(e, (list, tuple)) and len(e) >= 4:
            e = dict(source=e[0], title=e[1], date=e[2], rel=e[3])
        if not isinstance(e, dict) or 'rel' not in e:
            continue
        e['rel'] = posix(e['rel'])
        if e.get('kind') not in KINDS:
            e['kind'] = 'project' if e['rel'].endswith('/index.html') and 'Projects' in e['rel'] else 'chat'
        e.setdefault('source', '')
        e.setdefault('title', '')
        e.setdefault('date', '')
        rows.append(e)
    rows.sort(key=lambda e: e['date'], reverse=True)
    return rows


def list_loose_files(out):
    """فایل‌های آزاد Export (پوشه‌ی Files) به‌صورت ردیف‌های آرشیو."""
    d = os.path.join(out, 'Files')
    rows = []
    if os.path.isdir(d):
        for n in sorted(os.listdir(d)):
            p = os.path.join(d, n)
            if os.path.isfile(p):
                rows.append(dict(source='فایل', title=n, kind='file', rel='Files/' + n,
                                 date=datetime.datetime.fromtimestamp(os.path.getmtime(p)).strftime('%Y-%m-%d')))
    return rows


def entry_files(out, e):
    """فایل‌ها و کدهای وابسته به یک مورد آرشیو."""
    res = []
    page = os.path.join(out, e['rel'])
    if e['kind'] == 'chat':
        base = page[:-5]
        for suf, group in (('_code', 'کد'), ('_files', 'پیوست')):
            d = base + suf
            if os.path.isdir(d):
                for n in sorted(os.listdir(d)):
                    if n != 'code_meta.json':
                        res.append(dict(name=n, path=os.path.join(d, n), group=group))
    elif e['kind'] == 'project':
        d = os.path.dirname(page)
        for dp, _, fs in os.walk(d):
            for n in sorted(fs):
                if n in ('README.md', 'index.html', 'code_meta.json'):
                    continue
                p = os.path.join(dp, n)
                res.append(dict(name=os.path.relpath(p, d), path=p,
                                group='کد' if os.path.basename(dp) == 'code' else 'فایل'))
    for r in res:
        try:
            r['size'] = os.path.getsize(r['path'])
        except OSError:
            r['size'] = 0
    return res


# ---------- سطل آرشیو، حذف و تغییر نام ----------
def trash_move(out, path):
    if not os.path.exists(path):
        return False
    rel = os.path.relpath(path, out)
    dest = os.path.join(out, '.trash', datetime.datetime.now().strftime('%Y%m%d_%H%M%S'), rel)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.move(path, dest)
    return True


def empty_trash(out):
    d = os.path.join(out, '.trash')
    n = sum(len(f) for _, _, f in os.walk(d)) if os.path.isdir(d) else 0
    shutil.rmtree(d, ignore_errors=True)
    return n


def delete_entry(out, e):
    """مورد را به سطل آرشیو می‌برد (قابل بازگشت از پوشه‌ی .trash)."""
    page = os.path.join(out, e['rel'])
    n = 0
    if e['kind'] == 'chat':
        base = page[:-5]
        paths = [base + '.html', base + '.md', base + '_code', base + '_files',
                 os.path.join(out, 'Manual', 'Files', safe(e['title']))]
    elif e['kind'] == 'project':
        paths = [os.path.dirname(page)]
    else:
        paths = [page]
    for p in paths:
        n += 1 if trash_move(out, p) else 0
    if e['kind'] != 'file':
        write_index(out, remove=[e['rel']])
    return n


def delete_file(out, path):
    return trash_move(out, path)


def _replace_in(path, pairs):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            s = f.read()
    except OSError:
        return
    for a, b in pairs:
        s = s.replace(a, b, 1)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(s)


def _set_meta_title(d, title):
    p = os.path.join(d, 'code_meta.json')
    try:
        meta = load_json(p)
        meta['title'] = title
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False)
    except Exception:
        pass


def rename_entry(out, e, new_title):
    """تغییر نام یک چت/پروژه/فایل؛ فایل‌های همراه و فهرست هم به‌روز می‌شوند."""
    new_title = (new_title or '').strip()
    if not new_title:
        raise ValueError('نام جدید خالی است.')
    old_title = e['title']
    page = os.path.join(out, e['rel'])
    if e['kind'] == 'file':
        new_name = safe(new_title, 120)
        if '.' not in new_name and '.' in old_title:
            new_name += os.path.splitext(old_title)[1]
        dst = os.path.join(os.path.dirname(page), new_name)
        if os.path.exists(dst) and os.path.normcase(dst) != os.path.normcase(page):
            raise ValueError('فایلی با این نام وجود دارد.')
        os.rename(page, dst)
        return dict(e, title=new_name, rel=posix(os.path.relpath(dst, out)))
    esc_o, esc_n = html.escape(old_title), html.escape(new_title)
    pairs_html = [('<title>%s</title>' % esc_o, '<title>%s</title>' % esc_n),
                  ('<h2 dir="auto">%s</h2>' % esc_o, '<h2 dir="auto">%s</h2>' % esc_n)]
    if e['kind'] == 'chat':
        folder = os.path.dirname(page)
        base_old = page[:-5]
        prefix = os.path.basename(base_old).split('_', 1)[0]
        base_new, i = os.path.join(folder, '%s_%s' % (prefix, safe(new_title))), 2
        cand = base_new
        while os.path.normcase(cand) != os.path.normcase(base_old) and os.path.exists(cand + '.html'):
            cand = '%s_%d' % (base_new, i)
            i += 1
        base_new = cand
        if os.path.normcase(base_new) != os.path.normcase(base_old):
            for suf in ('.html', '.md', '_code', '_files'):
                if os.path.exists(base_old + suf):
                    os.rename(base_old + suf, base_new + suf)
        _replace_in(base_new + '.html', pairs_html)
        _replace_in(base_new + '.md', [('# %s\n' % old_title, '# %s\n' % new_title)])
        _set_meta_title(base_new + '_code', new_title)
        new_page = base_new + '.html'
    else:
        pdir = os.path.dirname(page)
        parent = os.path.dirname(pdir)
        dst, i = os.path.join(parent, safe(new_title)), 2
        cand = dst
        while os.path.normcase(cand) != os.path.normcase(pdir) and os.path.exists(cand):
            cand = '%s_%d' % (dst, i)
            i += 1
        if os.path.normcase(cand) != os.path.normcase(pdir):
            os.rename(pdir, cand)
        pdir = cand
        _replace_in(os.path.join(pdir, 'index.html'), pairs_html)
        _replace_in(os.path.join(pdir, 'README.md'), [('# %s\n' % old_title, '# %s\n' % new_title)])
        _set_meta_title(os.path.join(pdir, 'code'), new_title)
        new_page = os.path.join(pdir, 'index.html')
    ne = dict(e, title=new_title, rel=posix(os.path.relpath(new_page, out)))
    write_index(out, [ne], remove=[e['rel']] if ne['rel'] != e['rel'] else [])
    return ne


# ---------- ورود از Export ----------
def run(src, out, log=print):
    tmp = None
    if os.path.isfile(src) and src.lower().endswith('.zip'):
        tmp = tempfile.mkdtemp()
        log('در حال باز کردن فایل ZIP ...')
        with zipfile.ZipFile(src) as z:
            z.extractall(tmp)
        root = tmp
    elif os.path.isdir(src):
        root = src
    else:
        raise ValueError('ورودی باید فایل ZIP یا پوشه باشد.')
    os.makedirs(out, exist_ok=True)
    entries, counts = [], {}
    try:
        for dp, _, files in os.walk(root):
            for fn in files:
                p = os.path.join(dp, fn)
                low = fn.lower()
                if low.endswith('.json'):
                    try:
                        data = load_json(p)
                    except Exception:
                        continue
                    first = data[0] if isinstance(data, list) and data and isinstance(data[0], dict) else None
                    if first is not None and 'mapping' in first:
                        src_name, parse = 'ChatGPT', chatgpt_messages
                        tf = lambda c: c.get('title') or 'بدون عنوان'
                        cf = lambda c: ts(c.get('create_time'))
                    elif first is not None and 'chat_messages' in first:
                        src_name, parse = 'Claude', claude_messages
                        tf = lambda c: c.get('name') or 'بدون عنوان'
                        cf = lambda c: ts(c.get('created_at'))
                    elif low == 'projects.json' and isinstance(data, list):
                        new = save_projects(data, out)
                        entries += new
                        log('پروژه‌های Claude: %d' % len(new))
                        counts['projects'] = counts.get('projects', 0) + len(new)
                        continue
                    else:
                        raw = os.path.join(out, 'raw_json')
                        os.makedirs(raw, exist_ok=True)
                        shutil.copy2(p, os.path.join(raw, fn))
                        continue
                    folder = os.path.join(out, src_name)
                    os.makedirs(folder, exist_ok=True)
                    raw = os.path.join(out, 'raw_json')
                    os.makedirs(raw, exist_ok=True)
                    shutil.copy2(p, os.path.join(raw, '%s_%s' % (src_name, fn)))
                    for c in data:
                        try:
                            msgs = parse(c)
                            if not msgs:
                                continue
                            title, created = tf(c), cf(c)
                            hp = write_chat(folder, title, created, msgs, src_name)
                            entries.append(entry(out, src_name, title, fmt(created, '%Y-%m-%d'), hp, 'chat'))
                            counts[src_name] = counts.get(src_name, 0) + 1
                        except Exception as e:
                            log('خطا در یک چت: %s' % e)
                    log('%s: %d چت' % (src_name, counts.get(src_name, 0)))
                elif not low.endswith(('.html', '.txt', '.md')) or 'attach' in dp.lower():
                    dst = os.path.join(out, 'Files')
                    os.makedirs(dst, exist_ok=True)
                    d = os.path.join(dst, fn)
                    if os.path.exists(d):
                        d = os.path.join(dst, '%d_%s' % (len(os.listdir(dst)), fn))
                    shutil.copy2(p, d)
                    counts['files'] = counts.get('files', 0) + 1
        write_index(out, entries)
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
    log('تمام شد. چت‌ها: %d | فایل‌ها: %d | پروژه‌ها: %d' % (
        sum(v for k, v in counts.items() if k in ('ChatGPT', 'Claude')),
        counts.get('files', 0), counts.get('projects', 0)))
    return counts


def save_projects(projects, out):
    res = []
    for pr in projects:
        if not isinstance(pr, dict):
            continue
        name = pr.get('name') or 'بدون نام'
        d = os.path.join(out, 'Claude_Projects', safe(name))
        os.makedirs(d, exist_ok=True)
        text = '%s\n\n## Instructions\n\n%s' % (pr.get('description', ''), pr.get('prompt_template', ''))
        for doc in pr.get('docs') or []:
            with open(os.path.join(d, safe(doc.get('filename'), 100)), 'w', encoding='utf-8') as f:
                f.write(doc.get('content') or '')
        names = [n for n in os.listdir(d) if n not in ('README.md', 'index.html', 'code')]
        page = write_project(d, name, 'Claude', text, [], fmt(ts(pr.get('created_at')), '%Y-%m-%d'))
        links = ''.join('<a href="%s">%s</a>' % (html.escape(n), html.escape(n)) for n in names)
        if links:
            _replace_in(page, [('</div>' , '</div>' + links)])
        date = fmt(ts(pr.get('created_at')), '%Y-%m-%d') or fmt(datetime.datetime.now(), '%Y-%m-%d')
        res.append(entry(out, 'Claude', name, date, page, 'project'))
    return res


# ---------- ورود دستی ----------
def auto_title(text):
    """عنوان خودکار: اولین خط معنادار متن، یا تاریخ و ساعت."""
    for ln in str(text or '').splitlines():
        t = re.sub(r'^[#>*\-\s•`|]+', '', ln.strip()).strip()
        if t:
            return t[:45].rstrip() + ('…' if len(t) > 45 else '')
    return 'یادداشت ' + fmt(datetime.datetime.now())


def add_manual(out, kind, title, source, text, files, log=print):
    """kind: 'chat' یا 'project'. متن چت و کدها جدا ذخیره می‌شوند."""
    title = (title or '').strip() or auto_title(text)
    source = (source or '').strip() or 'Manual'
    now = datetime.datetime.now()
    base = os.path.join(out, 'Manual')
    os.makedirs(base, exist_ok=True)
    date = fmt(now, '%Y-%m-%d')
    if kind == 'chat':
        if not (text or '').strip() and not files:
            raise ValueError('متن چت یا فایل را وارد کنید.')
        msgs = [('متن/یادداشت', (text or '').strip(), now)] if (text or '').strip() else []
        page = write_chat(base, title, now, msgs, source, files)
        e = entry(out, source, title, date, page, 'chat')
    else:
        pdir, i = os.path.join(base, 'Projects', safe(title)), 2
        while os.path.exists(pdir):
            pdir = os.path.join(base, 'Projects', '%s_%d' % (safe(title), i))
            i += 1
        page = write_project(pdir, title, source, text, files, date)
        e = entry(out, source, title, date, page, 'project')
    write_index(out, [e])
    codes = len(extract_code(text))
    log('ذخیره شد: %s (%d فایل، %d قطعه کد جدا)' % (title, len(files or []), codes))
    return e


def preview_html(title, text):
    return page_html(title, '<div class="m assistant">%s</div>' % md_to_html(text or ''))


# ---------- خروجی و پشتیبان ----------
def export_combined(out, dest):
    """همه‌ی فایل‌های Markdown آرشیو را در یک فایل واحد جمع می‌کند."""
    paths = []
    for dp, dn, files in os.walk(out):
        dn[:] = [d for d in dn if d not in ('Files', 'raw_json', '.trash') and not d.endswith('_files')]
        paths += [os.path.join(dp, f) for f in files if f.lower().endswith('.md')]
    paths.sort()
    with open(dest, 'w', encoding='utf-8') as w:
        for p in paths:
            with open(p, 'r', encoding='utf-8') as r:
                w.write(r.read().rstrip() + '\n\n---\n\n')
    return len(paths)


def backup_zip(out, dest_dir):
    """نسخه‌ی پشتیبان کامل از آرشیو (ZIP با تاریخ و ساعت)."""
    out_abs, dest_abs = os.path.abspath(out), os.path.abspath(dest_dir)
    if dest_abs == out_abs or dest_abs.startswith(out_abs + os.sep):
        raise ValueError('پوشه‌ی پشتیبان نباید داخل پوشه‌ی آرشیو باشد.')
    if not os.path.isdir(out_abs):
        raise ValueError('پوشه‌ی آرشیو هنوز ساخته نشده است.')
    os.makedirs(dest_abs, exist_ok=True)
    base = os.path.join(dest_abs, 'ChatArchive_backup_' + datetime.datetime.now().strftime('%Y-%m-%d_%H%M'))
    return shutil.make_archive(base, 'zip', out_abs)
