import multiprocessing
import shutil
import uuid
import io
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

from fastapi import FastAPI, File, UploadFile, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import fitz
from ebooklib import epub
from PIL import Image

app = FastAPI(title="Manga to Kindle (Max 50MB)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMP_DIR = Path("temp_files")
TEMP_DIR.mkdir(exist_ok=True)
jobs = {}

def add_log(job_id: str, message: str):
    if job_id in jobs:
        jobs[job_id]["logs"].append(message)

def render_and_compress_page(pdf_path: Path, temp_img_dir: Path, page_num: int) -> tuple[int, Path]:
    """Renderização focada em atingir o limite de 50MB por volume."""
    doc = fitz.open(pdf_path)
    page = doc.load_page(page_num)
    
    # 1. Rasteriza com Zoom moderado (1.2x) para manter nitidez sem explodir o arquivo
    mat = fitz.Matrix(1.2, 1.2)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY)
    
    img = Image.frombytes("L", [pix.width, pix.height], pix.samples)
    
    # 2. Redimensiona para o padrão Kindle (1448px de altura)
    # Isso garante que cada página tenha aprox. 150kb a 200kb
    target_height = 1448
    if img.height > target_height:
        ratio = target_height / img.height
        new_size = (int(img.width * ratio), target_height)
        img = img.resize(new_size, Image.Resampling.LANCZOS)
        
    # 3. Compressão Otimizada: Quality 60 é o "sweet spot" para Kindle
    img_path = temp_img_dir / f"img_{page_num}.jpg"
    img.save(img_path, format="JPEG", quality=60, optimize=True, progressive=False)
    
    doc.close()
    return page_num, img_path

def process_kindle_manga_task(pdf_path: Path, epub_path: Path, job_id: str, title: str, author: str):
    job_img_dir = TEMP_DIR / f"images_{job_id}"
    job_img_dir.mkdir(exist_ok=True)

    try:
        jobs[job_id] = {"status": "processing", "progress": 0, "logs": []}
        add_log(job_id, "Iniciando compressão para limite de 50MB...")
        
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        add_log(job_id, f"Processando {total_pages} páginas. Alvo: < 200KB por página.")
        
        book = epub.EpubBook()
        book.set_identifier(job_id)
        book.set_title(title)
        book.set_language('pt-BR')
        book.add_author(author)

        # Metadados Kindle
        book.add_metadata('DC', 'type', 'comic')
        book.add_metadata('meta', '', {'name': 'fixed-layout', 'content': 'true'})
        book.add_metadata('meta', '', {'name': 'book-type', 'content': 'comic'})

        # Capa Otimizada
        first_page = doc.load_page(0)
        cover_pix = first_page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), colorspace=fitz.csRGB)
        cover_img = Image.frombytes("RGB", [cover_pix.width, cover_pix.height], cover_pix.samples)
        cover_io = io.BytesIO()
        cover_img.save(cover_io, format="JPEG", quality=70)
        book.set_cover("cover.jpg", cover_io.getvalue())
        doc.close()

        # CSS Minimalista
        css = 'body { margin: 0; padding: 0; background: #000; text-align: center; } img { max-width: 100%; height: auto; }'
        css_item = epub.EpubItem(uid="style", file_name="style/k.css", media_type="text/css", content=css)
        book.add_item(css_item)

        cores = multiprocessing.cpu_count()
        img_paths_ordered = {}

        with ProcessPoolExecutor(max_workers=cores) as executor:
            futures = {executor.submit(render_and_compress_page, pdf_path, job_img_dir, i): i for i in range(total_pages)}
            
            for future in as_completed(futures):
                if jobs[job_id]["status"] == "cancelling":
                    break
                page_num, img_path = future.result()
                img_paths_ordered[page_num] = img_path
                jobs[job_id]["progress"] = int((len(img_paths_ordered) / total_pages) * 100)
                
        if jobs[job_id]["status"] == "cancelling":
            jobs[job_id]["status"] = "cancelled"
            return

        add_log(job_id, "Encapsulando imagens no EPUB...")
        chapters = []
        for i in range(total_pages):
            img_path = img_paths_ordered[i]
            with open(img_path, "rb") as f:
                img_item = epub.EpubItem(uid=f"i{i}", file_name=f"i/{i}.jpg", media_type="image/jpeg", content=f.read())
                book.add_item(img_item)
            
            chapter = epub.EpubHtml(title=f"P{i}", file_name=f"p{i}.xhtml")
            chapter.content = f'<html><head><link rel="stylesheet" href="style/k.css"/></head><body><img src="i/{i}.jpg"/></body></html>'
            chapter.add_item(css_item)
            book.add_item(chapter)
            chapters.append(chapter)

        book.spine = chapters
        epub.write_epub(str(epub_path), book, {})
        
        final_size_mb = epub_path.stat().st_size / (1024 * 1024)
        add_log(job_id, f"Concluído! Tamanho final: {final_size_mb:.2f} MB")
        
        if final_size_mb > 50:
            add_log(job_id, "AVISO: O arquivo ainda excede 50MB. Considere dividir o PDF em partes.")
            
        jobs[job_id]["status"] = "completed"
        
    except Exception as e:
        jobs[job_id]["status"] = "failed"
        add_log(job_id, f"Erro: {str(e)}")
    finally:
        if pdf_path.exists(): pdf_path.unlink()
        if job_img_dir.exists(): shutil.rmtree(job_img_dir)

@app.get("/")
def serve_ui():
    return HTMLResponse(content=Path("index.html").read_text(encoding="utf-8"))

@app.post("/convert")
async def start_conversion(background_tasks: BackgroundTasks, file: UploadFile = File(...), title: str = Form(...), author: str = Form(...)):
    job_id = str(uuid.uuid4())
    pdf_path = TEMP_DIR / f"{job_id}.pdf"
    with open(pdf_path, "wb") as buffer: shutil.copyfileobj(file.file, buffer)
    background_tasks.add_task(process_kindle_manga_task, pdf_path, TEMP_DIR / f"{job_id}.epub", job_id, title, author)
    return {"job_id": job_id}

@app.get("/status/{job_id}")
async def get_status(job_id: str): return jobs.get(job_id, {"status": "not_found"})

@app.post("/cancel/{job_id}")
async def cancel_job(job_id: str):
    if job_id in jobs: jobs[job_id]["status"] = "cancelling"
    return {"ok": True}

@app.get("/download/{job_id}")
async def download(job_id: str):
    return FileResponse(path=TEMP_DIR / f"{job_id}.epub", filename=f"manga_kindle.epub", media_type='application/epub+zip')