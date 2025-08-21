# Naver Shopping Connect Lite (Windows EXE friendly)
# 최소 의존성 · 간단 GUI(Tkinter) + CLI 겸용 · Streamlit 제외 버전

import io, os, re, sys, zipfile, textwrap, tempfile, argparse
from datetime import datetime
from urllib.parse import urljoin, urlparse, quote_plus
from typing import List, Optional, Tuple, Dict, Any
import importlib

import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageOps

try:
    _trafilatura = importlib.import_module('trafilatura')
except Exception:
    _trafilatura = None
try:
    from readability import Document as _ReadabilityDocument
except Exception:
    _ReadabilityDocument = None

APP_VERSION = 'L1.0.0'
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36'}
try:
    import lxml  # noqa: F401
    DEFAULT_PARSER = 'lxml'
except Exception:
    DEFAULT_PARSER = 'html.parser'

IMG_MIN_WIDTH, IMG_MIN_HEIGHT = 400, 250
KOREAN_RE = re.compile(r"[\uAC00-\uD7A3]{2,}")
STOP = {"그리고","하지만","그러나","그래서","또한","이것","저것","그것","하면","하며","하는","했다","합니다",
        "및","등","때문","위해","대한","에서","으로","에게","이다","있다","된다","같은","그","더","수","하다","했다",
        "것","입니다","합니다","이번","오늘","지난","통해","이미","최근","많은","모든","사진","이미지","정보","소개"}

def soup(html: str) -> BeautifulSoup:
    try: return BeautifulSoup(html, DEFAULT_PARSER)
    except Exception: return BeautifulSoup(html, 'html.parser')

def fetch_html(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status(); r.encoding = r.apparent_encoding
    return r.text

def _extract_traf(html: str) -> Optional[str]:
    if not _trafilatura: return None
    try:
        t = _trafilatura.extract(html, include_comments=False, include_tables=False)
        return t.strip() if t and len(t.strip()) > 200 else None
    except Exception: return None

def _extract_readability(html: str) -> Optional[str]:
    if not _ReadabilityDocument: return None
    try:
        doc = _ReadabilityDocument(html)
        c = doc.summary(html_partial=True)
        s = soup(c)
        for tag in s(["script","style","noscript","svg"]): tag.decompose()
        parts = [p.get_text("\n", strip=True) for p in s.find_all(["p","li","h2","h3"]) if p.get_text(strip=True)]
        t = "\n\n".join(parts)
        return t.strip() if len(t.strip()) > 50 else None
    except Exception: return None

def _extract_bs(html: str) -> Optional[str]:
    try:
        s = soup(html)
        c = s.find(["article","main","section"]) or s
        blocks = c.find_all(["p","li","h2","h3"]) or c.find_all(["p","li"]) or []
        parts = [b.get_text("\n", strip=True) for b in blocks if b.get_text(strip=True)]
        t = "\n\n".join(parts)
        return t.strip() if len(t.strip()) > 20 else None
    except Exception: return None

def extract_main(html: str, base_url: str) -> tuple[str, str, str]:
    s = soup(html)
    title = (s.find('meta', property='og:title') or {}).get('content') if s else None
    if not title and s.title: title = s.title.get_text(strip=True)
    desc = (s.find('meta', property='og:description') or s.find('meta', attrs={'name':'description'}) or {})
    summary = desc.get('content').strip() if hasattr(desc, 'get') and desc.get('content') else None
    text = _extract_traf(html) or _extract_readability(html) or _extract_bs(html) or ''
    if not title: title = urlparse(base_url).netloc
    if not summary and text: summary = textwrap.shorten(text.replace('\n',' '), width=120, placeholder='…')
    if not text: text = '(본문 추출 실패)'
    return title, (summary or ''), text

def resolve(u: str, base: str) -> str: return urljoin(base, u)

def collect_images(html: str, base_url: str, limit: int) -> list[str]:
    s = soup(html); urls: list[str] = []
    for m in s.find_all('meta', property='og:image'):
        c = m.get('content');  urls.append(resolve(c, base_url)) if c else None
    for img in s.find_all('img'):
        src = img.get('src') or img.get('data-src') or img.get('data-original') or img.get('data-lazy')
        if not src:
            ss = img.get('srcset')
            if ss: src = ss.split(',')[0].strip().split(' ')[0]
        if src: urls.append(resolve(src, base_url))
    seen, outs = set(), []
    for u in urls:
        try:
            pu = urlparse(u); key = pu._replace(query='', fragment='').geturl()
            if key not in seen:
                seen.add(key); outs.append(u)
        except Exception: pass
    return outs[:max(1, limit)] if limit else outs

def dl_image(url: str) -> Optional[Image.Image]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=15); r.raise_for_status()
        return Image.open(io.BytesIO(r.content)).convert('RGB')
    except Exception: return None

def clean_image(im: Image.Image, w: int) -> Optional[Image.Image]:
    iw, ih = im.size
    if iw < 400 or ih < 250: return None
    if iw != w:
        r = w/float(iw); im = im.resize((w, int(ih*r)))
    return ImageOps.expand(im, border=30, fill='white')

def keywords(text: str, k: int = 12) -> list[str]:
    toks = [t for t in KOREAN_RE.findall(text) if t not in STOP]
    freq = {}
    for t in toks: freq[t] = freq.get(t,0)+1
    return [w for w,_ in sorted(freq.items(), key=lambda x: -x[1])][:k]

def hashtags(ks: list[str], commas=True) -> str:
    tags = [f"#{k}" for k in ks]
    return ", ".join(tags) if commas else " ".join(tags)

def compose_post(title: str, summary: str, body: str, url: str, imgs: list[str], interval: int) -> tuple[str,str,list[str]]:
    ks = keywords(title + "\n" + body); ht = hashtags(ks)
    paras = [p.strip() for p in body.split('\n') if p.strip()]
    header = [f"[정보정리] {title}"]
    if summary: header.append(f"\n한줄 요약: {summary}")
    header += ["\n본문","-"*40]
    lines, idx = [], 0
    for i,p in enumerate(paras,1):
        lines.append(p)
        if imgs and (i % interval == 0) and idx < len(imgs):
            lines.append(f"[이미지 삽입: {os.path.basename(imgs[idx])}]"); idx += 1
    footer = ["\n정리 및 참고 링크","-"*40,f"원문 링크: {url}","\n해시태그",ht]
    return "\n".join(header+["\n"]+lines+["\n"]+footer), ht, ks

def pack_zip(text_name: str, text: bytes, image_paths: list[str]) -> bytes:
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr(text_name, text)
        for p in image_paths:
            try: z.write(p, f"images/{os.path.basename(p)}")
            except Exception: pass
    mem.seek(0); return mem.read()

def run_gui():
    try:
        import tkinter as tk
        from tkinter import ttk, filedialog, messagebox
    except Exception:
        print('[INFO] Tkinter 불가 → CLI로 전환');  return run_cli()

    def go():
        url = ent_url.get().strip()
        if not url:
            messagebox.showwarning('확인', 'URL을 입력하세요.'); return
        outdir = filedialog.askdirectory(title='저장 폴더 선택')
        if not outdir: return
        try:
            btn.config(state='disabled'); root.update()
            html = fetch_html(url)
            t,s,b = extract_main(html, url)
            max_img = int(spin_img.get()); width = int(cmb_w.get()); interval = int(spin_int.get())
            cand = collect_images(html, url, limit=max_img*3 if max_img else 0)
            saved = []
            if max_img>0:
                tmp = tempfile.mkdtemp(prefix='nblog_')
                for cu in cand:
                    if len(saved) >= max_img: break
                    im = dl_image(cu)
                    if not im: continue
                    im = clean_image(im, width)
                    if not im: continue
                    fp = os.path.join(tmp, f"image_{len(saved)+1:02d}.jpg")
                    im.save(fp, 'JPEG', quality=90); saved.append(fp)
            post, ht, ks = compose_post(t, s, b, url, saved, int(spin_int.get()))
            if not var_commas.get(): post = post.replace(', ', ' ')
            slug = re.sub(r'[^a-zA-Z0-9\-_.]+','-', t.lower()).strip('-') or 'naver-post'
            zip_bytes = pack_zip(f"{slug}.txt", post.encode('utf-8'), saved)
            out = os.path.join(outdir, f"{slug}_{datetime.now().strftime('%Y%m%d_%H%M')}.zip")
            with open(out,'wb') as f: f.write(zip_bytes)
            messagebox.showinfo('완료', f'ZIP 저장:\n{out}')
        except Exception as e:
            messagebox.showerror('오류', str(e))
        finally:
            btn.config(state='normal')

    root = tk.Tk(); root.title(f"Naver Shopping Connect Lite v{APP_VERSION}")
    root.geometry('620x220')

    frm = ttk.Frame(root, padding=10); frm.pack(fill='both', expand=True)
    ttk.Label(frm, text='상품/글 URL').grid(row=0, column=0, sticky='w');
    ent_url = ttk.Entry(frm, width=70); ent_url.grid(row=0, column=1, columnspan=4, sticky='we', padx=6)
    ttk.Label(frm, text='최대 이미지').grid(row=1, column=0, sticky='w');
    spin_img = ttk.Spinbox(frm, from_=0, to=20, width=5); spin_img.set(8); spin_img.grid(row=1, column=1, sticky='w')
    ttk.Label(frm, text='가로폭').grid(row=1, column=2, sticky='w');
    cmb_w = ttk.Combobox(frm, values=[960,1200,1280,1440], width=8, state='readonly'); cmb_w.set(1280); cmb_w.grid(row=1, column=3, sticky='w')
    ttk.Label(frm, text='이미지 간격').grid(row=2, column=0, sticky='w');
    spin_int = ttk.Spinbox(frm, from_=2, to=8, width=5); spin_int.set(3); spin_int.grid(row=2, column=1, sticky='w')
    var_commas = tk.BooleanVar(value=True)
    ttk.Checkbutton(frm, text='해시태그 쉼표 포함', variable=var_commas).grid(row=2, column=2, sticky='w')
    btn = ttk.Button(frm, text='분석하고 저장 (ZIP)', command=go); btn.grid(row=3, column=0, columnspan=5, pady=12, sticky='we')
    for i in range(5): frm.columnconfigure(i, weight=1)
    root.mainloop()

def run_cli() -> int:
    import argparse, os
    p = argparse.ArgumentParser(description='Naver Shopping Connect Lite')
    p.add_argument('--url', type=str)
    p.add_argument('--max-img', type=int, default=8)
    p.add_argument('--width', type=int, default=1280)
    p.add_argument('--interval', type=int, default=3)
    p.add_argument('--no-commas', action='store_true')
    p.add_argument('--outdir', type=str, default='./output')
    p.add_argument('--run-tests', action='store_true')
    a = p.parse_args()
    if a.run_tests:
        for r in self_tests(): print(r);  return 0
    if not a.url:
        try: u = input('URL을 입력하세요: ').strip()
        except Exception: u = ''
        if not u: print('종료'); return 0
        a.url = u
    os.makedirs(a.outdir, exist_ok=True)
    try:
        html = fetch_html(a.url)
        t,s,b = extract_main(html, a.url)
        cand = collect_images(html, a.url, limit=a.max_img*3 if a.max_img else 0)
        saved = []
        if a.max_img>0:
            tmp = os.path.join(a.outdir, 'images_tmp'); os.makedirs(tmp, exist_ok=True)
            for cu in cand:
                if len(saved) >= a.max_img: break
                im = dl_image(cu)
                if not im: continue
                im = clean_image(im, a.width)
                if not im: continue
                fp = os.path.join(tmp, f'image_{len(saved)+1:02d}.jpg')
                im.save(fp, 'JPEG', quality=90); saved.append(fp)
        post, ht, ks = compose_post(t,s,b,a.url,saved,a.interval)
        if a.no_commas: post = post.replace(', ', ' ')
        slug = re.sub(r'[^a-zA-Z0-9\-_.]+','-', t.lower()).strip('-') or 'naver-post'
        with open(os.path.join(a.outdir, f'{slug}.txt'), 'w', encoding='utf-8') as f: f.write(post)
        z = pack_zip(f'{slug}.txt', post.encode('utf-8'), saved)
        zp = os.path.join(a.outdir, f'{slug}_{datetime.now().strftime('%Y%m%d_%H%M')}.zip')
        with open(zp,'wb') as f: f.write(z)
        print('완료:', zp);  return 0
    except Exception as e:
        print('오류:', e); return 1

def _ok(name, cond, detail=''):
    return f"✅ {name}" if cond else f"❌ {name} → {detail}"

def self_tests():
    res = []
    h = """
    <html><head><title>샘플</title><meta name='description' content='요약'></head>
    <body><article><p>문단1 테스트</p><p>문단2 테스트</p><img src='/a.jpg'></article></body></html>
    """
    t,s,b = extract_main(h,'https://ex.com')
    res.append(_ok('본문/제목', t=='샘플' and '문단1' in b))
    imgs = collect_images(h,'https://ex.com',limit=5)
    res.append(_ok('이미지 수집', len(imgs)>=1))
    post, ht, ks = compose_post(t,s,b,'https://ex.com',[],3)
    res.append(_ok('해시태그', ht.startswith('#') and len(ks)>=1))
    z = pack_zip('t.txt', post.encode('utf-8'), [])
    res.append(_ok('ZIP', len(z)>50))
    return res

if __name__ == '__main__':
    try: run_gui()
    except Exception: run_cli()
