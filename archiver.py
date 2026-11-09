"""هسته برنامه: تبدیل خروجی رسمی (Export) ChatGPT و Claude به آرشیو محلی."""
import datetime
import html
import json
import os
import re
import shutil
import tempfile
import zipfile


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


# ---------- parsers ----------
def chatgpt_messages(conv):
    mapping = conv.get('mapping') or {}
    node, chain, seen = conv.get('current_node'), [], set()
    while node and node in mapping and node not in seen:
        seen.add(node)
        chain.append(mapping[node])
        node = mapping[node].get('parent')
    chain.reverse()
    if not chain:
        chain = sorted(
            [n for n in mapping.values() if n.get('message')],
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


# ---------- renderers ----------
CSS = ("body{font-family:Tahoma,Segoe UI,sans-serif;max-width:860px;margin:2em auto;padding:0 1em;background:#f5f5f7}"
       ".m{padding:.8em 1em;margin:.6em 0;border-radius:10px;white-space:pre-wrap;line-height:1.7}"
       ".user{background:#dbeafe}.assistant{background:#fff}.r{font-size:.75em;color:#666;margin-bottom:.3em}"
       "input{width:100%;padding:.6em;font-size:1em;margin-bottom:1em}a{display:block;padding:.35em 0}")


def write_chat(folder, title, created, msgs, source):
    base = '%s_%s' % (fmt(created, '%Y-%m-%d') or 'nodate', safe(title))
    path, i = os.path.join(folder, base), 2
    while os.path.exists(path + '.md'):
        path = os.path.join(folder, '%s_%d' % (base, i))
        i += 1
    md = ['# %s' % title, '', '%s — %s' % (source, fmt(created)), '']
    body = []
    for role, text, t in msgs:
        who = 'من' if role == 'user' else ('هوش مصنوعی' if role == 'assistant' else role)
        md += ['## %s  %s' % (who, fmt(t)), '', text, '']
        body.append('<div class="m %s" dir="auto"><div class="r">%s %s</div>%s</div>' % (
            'user' if role == 'user' else 'assistant', html.escape(who), fmt(t), html.escape(text)))
    with open(path + '.md', 'w', encoding='utf-8') as f:
        f.write('\n'.join(md))
    with open(path + '.html', 'w', encoding='utf-8') as f:
        f.write('<!doctype html><meta charset="utf-8"><title>%s</title><style>%s</style><h2 dir="auto">%s</h2>%s'
                % (html.escape(title), CSS, html.escape(title), '\n'.join(body)))
    return path + '.html'


def write_index(out, entries):
    store = os.path.join(out, '.index.json')
    old = []
    try:
        old = [tuple(e) for e in load_json(store)]
    except Exception:
        pass
    rel = [(s, t, d, os.path.relpath(p, out)) for s, t, d, p in entries]
    merged = {e[3]: e for e in old}
    merged.update({e[3]: e for e in rel})
    with open(store, 'w', encoding='utf-8') as f:
        json.dump(list(merged.values()), f, ensure_ascii=False)
    entries = [(s, t, d, os.path.join(out, p)) for s, t, d, p in merged.values()]
    entries.sort(key=lambda e: e[2], reverse=True)
    links = '\n'.join('<a dir="auto" href="%s">%s — %s — %s</a>' % (
        html.escape(os.path.relpath(p, out).replace('\\', '/')), html.escape(s), e_date, html.escape(t))
        for s, t, e_date, p in entries)
    js = ("<script>document.getElementById('q').oninput=function(){var v=this.value.toLowerCase();"
          "document.querySelectorAll('a').forEach(function(a){a.style.display="
          "a.textContent.toLowerCase().includes(v)?'':'none'})}</script>")
    with open(os.path.join(out, 'index.html'), 'w', encoding='utf-8') as f:
        f.write('<!doctype html><meta charset="utf-8"><title>آرشیو چت‌ها</title><style>%s</style>'
                '<h2>آرشیو چت‌ها (%d)</h2><input id="q" placeholder="جستجو در عنوان‌ها...">%s%s'
                % (CSS, len(entries), links, js))


# ---------- main ----------
def load_json(p):
    with open(p, 'r', encoding='utf-8') as f:
        return json.load(f)


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
                    if isinstance(data, list) and data and isinstance(data[0], dict) and 'mapping' in data[0]:
                        src_name, parse = 'ChatGPT', chatgpt_messages
                        tf = lambda c: c.get('title') or 'بدون عنوان'
                        cf = lambda c: ts(c.get('create_time'))
                    elif isinstance(data, list) and data and isinstance(data[0], dict) and 'chat_messages' in data[0]:
                        src_name, parse = 'Claude', claude_messages
                        tf = lambda c: c.get('name') or 'بدون عنوان'
                        cf = lambda c: ts(c.get('created_at'))
                    elif low == 'projects.json' and isinstance(data, list):
                        n = save_projects(data, out)
                        log('پروژه‌های Claude: %d' % n)
                        counts['projects'] = counts.get('projects', 0) + n
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
                            entries.append((src_name, title, fmt(created, '%Y-%m-%d'), hp))
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
    n = 0
    for pr in projects:
        if not isinstance(pr, dict):
            continue
        d = os.path.join(out, 'Claude_Projects', safe(pr.get('name')))
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, 'README.md'), 'w', encoding='utf-8') as f:
            f.write('# %s\n\n%s\n\n## Instructions\n\n%s\n' % (
                pr.get('name', ''), pr.get('description', ''), pr.get('prompt_template', '')))
        for doc in pr.get('docs') or []:
            with open(os.path.join(d, safe(doc.get('filename'), 100)), 'w', encoding='utf-8') as f:
                f.write(doc.get('content') or '')
        n += 1
    return n


# ---------- ورود دستی ----------
def add_manual(out, kind, title, source, text, files, log=print):
    """kind: 'chat' یا 'project'. text: متن چسبانده‌شده. files: لیست مسیر فایل‌ها."""
    title = (title or '').strip() or 'بدون عنوان'
    source = (source or '').strip() or 'Manual'
    now = datetime.datetime.now()
    base = os.path.join(out, 'Manual')
    os.makedirs(base, exist_ok=True)
    copied = []
    if files and kind == 'chat':
        fdir = os.path.join(base, 'Files', safe(title))
        os.makedirs(fdir, exist_ok=True)
        for fp in files:
            if os.path.isfile(fp):
                shutil.copy2(fp, os.path.join(fdir, os.path.basename(fp)))
                copied.append('Files/%s/%s' % (safe(title), os.path.basename(fp)))
    if kind == 'chat':
        body = text or ''
        if copied:
            body += '\n\n' + '\n'.join('📎 ' + c for c in copied)
        if not body.strip():
            raise ValueError('متن چت یا فایل را وارد کنید.')
        page = write_chat(base, title, now, [('متن/یادداشت', body.strip(), now)], source)
    else:
        pdir = os.path.join(base, 'Projects', safe(title))
        os.makedirs(pdir, exist_ok=True)
        for fp in files or []:
            if os.path.isfile(fp):
                shutil.copy2(fp, os.path.join(pdir, os.path.basename(fp)))
        with open(os.path.join(pdir, 'README.md'), 'w', encoding='utf-8') as f:
            f.write('# %s\n\n%s\n' % (title, text or ''))
        links = '\n'.join('<a href="%s">%s</a>' % (html.escape(os.path.basename(fp)), html.escape(os.path.basename(fp)))
                          for fp in files or [])
        page = os.path.join(pdir, 'index.html')
        with open(page, 'w', encoding='utf-8') as f:
            f.write('<!doctype html><meta charset="utf-8"><title>%s</title><style>%s</style><h2 dir="auto">%s</h2>'
                    '<div class="m assistant" dir="auto">%s</div>%s'
                    % (html.escape(title), CSS, html.escape(title), html.escape(text or ''), links))
    write_index(out, [(source if kind == 'chat' else 'Project', title, fmt(now, '%Y-%m-%d'), page)])
    log('ذخیره شد: %s (%d فایل)' % (title, len(copied) if kind == 'chat' else len(files or [])))
