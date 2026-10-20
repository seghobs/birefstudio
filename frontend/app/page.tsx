"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowDownToLine, ArrowRight, Check, ChevronDown, CircleHelp, Clock3, Printer, Scissors, Eraser, FolderOpen, ImagePlus, Layers3, Leaf, LoaderCircle, Paintbrush, Plus, RefreshCw, ShieldCheck, SlidersHorizontal, Sparkles, Trash2, Upload, WandSparkles, X, Zap } from "lucide-react";
import { api, downloadUrl, type Job, type Health } from "@/lib/api";
import ZoomViewport from "./components/ZoomViewport";
import PrintStudio from "./components/PrintStudio";

const colors = ["transparent", "#ffffff", "#e7e5df", "#183d32", "#e5c9b6", "#c9d8ee"];
const labels = ["Şeffaf", "Beyaz", "Kum", "Orman", "Şeftali", "Gökyüzü"];
const statusLabels = { queued: "Sırada", processing: "İşleniyor", done: "Hazır", failed: "Başarısız" };

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image(); image.onload = () => resolve(image); image.onerror = () => reject(new Error("Görüntü yüklenemedi.")); image.src = url;
  });
}

export default function Studio() {
  const [search, setSearch] = useState("");
  const [galleryFilter, setGalleryFilter] = useState("all");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [online, setOnline] = useState(false);
  const [model, setModel] = useState<"quality" | "fast">("quality");
  const [refine, setRefine] = useState(true);
  const [eyeSharpen,setEyeSharpen]=useState(false);
  const [faceClean,setFaceClean]=useState(false);
  const [faceSharpen,setFaceSharpen]=useState(false);
  const [faceSpots,setFaceSpots]=useState(true);
  const [faceStrength,setFaceStrength]=useState(70);
  const [faceUpdating,setFaceUpdating]=useState(false);
  const [viewKey,setViewKey]=useState<string|null>(null);
  const [hardware, setHardware] = useState<Health | null>(null);
  const [background, setBackground] = useState("transparent");
  const [format, setFormat] = useState("png");
  const [preset, setPreset] = useState("original");
  const [split, setSplit] = useState(50);
  const [compare, setCompare] = useState(true);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [notice, setNotice] = useState<{ text: string; error: boolean } | null>(null);
  const [brush, setBrush] = useState<"erase" | "restore" | "detail" | null>(null);
  const [brushSize, setBrushSize] = useState(32);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editorReady, setEditorReady] = useState(false);
  const [revision, setRevision] = useState(0);
  const [frame, setFrame] = useState({ width: 480, height: 440 });
  const [printOpen,setPrintOpen]=useState(false);
  const [help, setHelp] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const stage = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const detailMask = useRef<HTMLCanvasElement | null>(null);
  const source = useRef<HTMLImageElement | null>(null);
  const drawing = useRef(false);
  const lastPoint = useRef<{x: number; y: number} | null>(null);
  const active = jobs.find(job => job.id === activeId);
  const done = jobs.filter(job => job.status === "done");
  const pending = jobs.filter(job => job.status === "queued" || job.status === "processing");
  const visibleJobs = jobs.filter(job => job.name.toLocaleLowerCase("tr").includes(search.toLocaleLowerCase("tr")) && (galleryFilter === "all" || (galleryFilter === "done" ? job.status === "done" : job.status === "queued" || job.status === "processing")));
  const busy = active?.status === "queued" || active?.status === "processing";
  const ready = active?.status === "done";
  useEffect(()=>{
    if(active&&ready){setEyeSharpen(Boolean(active.eye_sharpen));setFaceClean(Boolean(active.face_clean));setFaceSharpen(Boolean(active.face_sharpen));setFaceSpots(active.face_spots??true);setFaceStrength(active.face_strength??70);}
  },[activeId,ready]);

  const notify = useCallback((text: string, error = false) => setNotice({ text, error }), []);
  const refresh = useCallback(async () => {
    try { const list = await api<Job[]>("/jobs"); setJobs(list); setOnline(true); }
    catch { setOnline(false); }
  }, []);
  useEffect(() => {
    void api<Health>("/health").then(setHardware).catch(() => {});
    void refresh(); const timer = setInterval(() => void refresh(), 1600);
    return () => clearInterval(timer);
  }, [refresh]);
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(null), notice.error ? 10000 : 4500);
    return () => clearTimeout(timer);
  }, [notice]);
  useEffect(() => {
    if (!stage.current) return;
    const observer = new ResizeObserver(([entry]) => {
      const ratio = active ? active.width / active.height : 720 / 660;
      const maxW = Math.max(80, entry.contentRect.width - 48);
      const maxH = Math.max(80, entry.contentRect.height - 40);
      const width = Math.min(maxW, maxH * ratio);
      setFrame({ width, height: width / ratio });
    });
    observer.observe(stage.current);
    return () => observer.disconnect();
  }, [active?.id, active?.width, active?.height]);

  const resultSrc = active?.result_url ? `${active.result_url}?v=${revision}` : "/demo-cutout.svg";
  useEffect(() => {
    setDirty(false); setEditorReady(false); drawing.current = false;
    if (!ready || !active || !brush) return;
    let cancelled = false;
    Promise.all([loadImage(`${active.result_url}?v=${revision}`), loadImage(active.original_url)]).then(([result, original]) => {
      if (cancelled || !canvas.current) return;
      canvas.current.width = original.naturalWidth; canvas.current.height = original.naturalHeight;
      const ctx = canvas.current.getContext("2d");
      if (!ctx) return;
      ctx.clearRect(0, 0, canvas.current.width, canvas.current.height); ctx.drawImage(result, 0, 0);
      const mask = document.createElement("canvas");
      mask.width = original.naturalWidth; mask.height = original.naturalHeight;
      const maskCtx = mask.getContext("2d");
      if (maskCtx) { maskCtx.fillStyle = "black"; maskCtx.fillRect(0, 0, mask.width, mask.height); }
      detailMask.current = mask;
      source.current = original; setEditorReady(true);
    }).catch(error => { if (!cancelled) notify(error.message, true); });
    return () => { cancelled = true; };
    // Changing brush tools must retain the current canvas.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId, ready, revision, Boolean(brush), brush === "detail", notify]);

  async function uploadFiles(files: FileList | File[]) {
    if (uploading) return;
    if (dirty && !window.confirm("Kaydedilmemiş fırça düzenlemesi var. Yeni fotoğrafa geçilsin mi?")) return;
    const batch = Array.from(files).slice(0, 12);
    if (!batch.length) return;
    if (files.length > 12) notify("Bir seferde ilk 12 fotoğraf işleme alınır.");
    setUploading(true); setBrush(null);
    let first = true; let accepted = 0;
    for (const file of batch) {
      if (file.size > 20 * 1024 * 1024) { notify(`${file.name}: 20 MB sınırını aşıyor.`, true); continue; }
      if (!/\.(png|jpe?g|webp|bmp)$/i.test(file.name)) { notify(`${file.name}: JPG, PNG, WEBP veya BMP seçin.`, true); continue; }
      const body = new FormData(); body.append("file", file); body.append("model", model); body.append("refine", String(model === "quality" && refine));
      body.append("eye_sharpen",String(eyeSharpen));body.append("face_clean",String(faceClean));body.append("face_sharpen",String(faceSharpen));body.append("face_spots",String(faceSpots));body.append("face_strength",String(faceStrength));
      try {
        const job = await api<Job>("/jobs", { method: "POST", body });
        setJobs(previous => [job, ...previous.filter(item => item.id !== job.id)]);
        if (first) { setActiveId(job.id);setViewKey(job.id); first = false; }
        accepted++;
      } catch (error) { notify(error instanceof Error ? error.message : "Yükleme tamamlanamadı.", true); }
    }
    setUploading(false); if (input.current) input.current.value = "";
    if (accepted) await refresh();
  }

  function chooseJob(job: Job) {
    if (job.id === activeId) return;
    if (dirty && !window.confirm("Kaydedilmemiş düzenleme var. Fotoğraf değiştirilsin mi?")) return;
    setActiveId(job.id);setViewKey(job.id); setBrush(null); setDirty(false); setCompare(true);
    document.getElementById("studio")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  function selectBrush(next: "erase" | "restore" | "detail") {
    if (saving) return;
    if (dirty && ((brush === "detail") !== (next === "detail")) && !window.confirm("Fırça değişiklikleri kaydedilmedi. Diğer araca geçilsin mi?")) return;
    setBrush(next); setCompare(false);
  }
  async function removeJob(job: Job) {
    if (!window.confirm(`“${job.name}” ve sonucu bilgisayardan silinsin mi?`)) return;
    try {
      await api(`/jobs/${job.id}`, { method: "DELETE" });
      if (activeId === job.id) { setActiveId(null); setBrush(null); setDirty(false); }
      await refresh(); notify("Fotoğraf silindi.");
    } catch (error) { notify((error as Error).message, true); }
  }
  async function retry(job: Job) {
    try {
      const response = await fetch(job.original_url); if (!response.ok) throw new Error("Orijinal görüntü bulunamadı.");
      await uploadFiles([new File([await response.blob()], `${job.name.replace(/\.[^.]+$/, "")}.png`, { type: "image/png" })]);
    } catch (error) { notify((error as Error).message, true); }
  }
  function paint(e: React.PointerEvent<HTMLCanvasElement>) {
    if (!drawing.current || !canvas.current || !editorReady) return;
    const el = canvas.current; const rect = el.getBoundingClientRect(); const ctx = el.getContext("2d");
    if (!ctx || !source.current) return;
    const x = (e.clientX - rect.left) * el.width / rect.width;
    const y = (e.clientY - rect.top) * el.height / rect.height;
    const radius = brushSize / 2 * el.width / rect.width;
    const prev = lastPoint.current || {x, y};
    const distance = Math.hypot(x - prev.x, y - prev.y);
    const steps = Math.max(1, Math.ceil(distance / Math.max(1, radius / 3)));
    ctx.save();
    for (let step = 0; step <= steps; step++) {
      const px = prev.x + (x-prev.x) * step / steps; const py = prev.y + (y-prev.y) * step / steps;
      ctx.beginPath(); ctx.arc(px, py, radius, 0, Math.PI * 2);
      if (brush === "detail") {
        ctx.globalCompositeOperation = "source-over"; ctx.fillStyle = "rgba(192, 228, 107, .25)"; ctx.fill();
        const maskCtx = detailMask.current?.getContext("2d");
        if (maskCtx) { maskCtx.fillStyle = "white"; maskCtx.beginPath(); maskCtx.arc(px, py, radius, 0, Math.PI * 2); maskCtx.fill(); }
      }
      else if (brush === "erase") { ctx.globalCompositeOperation = "destination-out"; ctx.fill(); }
      else { ctx.save(); ctx.clip(); ctx.globalCompositeOperation = "source-over"; ctx.drawImage(source.current, 0, 0); ctx.restore(); }
    }
    ctx.restore(); lastPoint.current = {x,y}; setDirty(true);
  }
  async function saveEdit() {
    if (!active || !canvas.current) return;
    setSaving(true);
    try {
      let exportCanvas = brush === "detail" ? detailMask.current : canvas.current;
      if (!exportCanvas) throw new Error("İşaretleme hazırlanamadı.");
      if (brush !== "detail") {
        // The API only needs alpha. Constant RGB keeps large edits below the
        // upload limit without changing any alpha value or source RGB.
        const alphaCanvas = document.createElement("canvas");
        alphaCanvas.width = exportCanvas.width; alphaCanvas.height = exportCanvas.height;
        const ctx = alphaCanvas.getContext("2d");
        if (!ctx) throw new Error("Maske hazırlanamadı.");
        ctx.drawImage(exportCanvas, 0, 0);
        ctx.globalCompositeOperation = "source-in";
        ctx.fillStyle = "white"; ctx.fillRect(0, 0, alphaCanvas.width, alphaCanvas.height);
        exportCanvas = alphaCanvas;
      }
      const blob = await new Promise<Blob>((resolve, reject) => exportCanvas.toBlob(value => value ? resolve(value) : reject(new Error("Görüntü kaydedilemedi.")), "image/png"));
      const body = new FormData(); body.append("file", blob, "edit.png");
      if (brush === "detail") {
        const job = await api<Job>(`/jobs/${active.id}/refine`, { method: "POST", body });
        setJobs(previous => [job, ...previous]); setActiveId(job.id);
        notify("İşaretlediğiniz saç kenarları yeniden inceleniyor. Önceki sonuç galeride korunur.");
      } else {
        await api(`/jobs/${active.id}/edit`, { method: "POST", body });
        notify("Düzenlemeniz kaydedildi.");
      }
      setDirty(false); setRevision(value => value + 1); setBrush(null);
    } catch (error) { notify((error as Error).message, true); }
    finally { setSaving(false); }
  }
  async function download() {
    if (!active || !ready || dirty) return;
    try {
      const response = await fetch(downloadUrl(active, background, format, preset));
      if (!response.ok) { const data = await response.json(); throw new Error(data.detail || "İndirme başarısız."); }
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a"); link.href = url; link.download = `${active.name.replace(/\.[^.]+$/, "")}-studio.${format}`; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) { notify((error as Error).message, true); }
  }

  async function updateFace(clean:boolean,sharp:boolean,spots:boolean,strength=faceStrength,eyes=eyeSharpen) {
    const previous={eyes:eyeSharpen,clean:faceClean,sharp:faceSharpen,spots:faceSpots,strength:active?.face_strength??faceStrength};
    setEyeSharpen(eyes);setFaceClean(clean);setFaceSharpen(sharp);setFaceSpots(spots);setFaceStrength(strength);
    if(!active||!ready)return;
    setFaceUpdating(true);
    try {
      const body=new FormData();body.append("eye_sharpen",String(eyes));body.append("face_clean",String(clean));body.append("face_sharpen",String(sharp));body.append("face_spots",String(spots));body.append("face_strength",String(strength));
      const job=await api<Job>(`/jobs/${active.id}/retouch`,{method:"POST",body});
      setJobs(old=>[job,...old]);setActiveId(job.id);setBrush(null);setDirty(false);
      notify(clean||sharp||eyes?"Yüz ayarı ayrı bir sonuç olarak uygulanıyor.":"Yüz işlemi kapatıldı; rötuşsuz kesim geri getiriliyor.");
    } catch(error) {
      setEyeSharpen(previous.eyes);setFaceClean(previous.clean);setFaceSharpen(previous.sharp);setFaceSpots(previous.spots);setFaceStrength(previous.strength);
      notify((error as Error).message,true);
    } finally {setFaceUpdating(false);}
  }

  return <>
    <header className="site-header"><div className="header-inner">
      <a className="brand" href="#studio" aria-label="BiRef Studio ana sayfa"><span className="brand-mark">B<span>/</span></span>BiRef<span className="brand-light">studio</span><span className="brand-dot"/></a>
      <nav aria-label="Ana menü"><a href="#studio" className="nav-active">Stüdyo</a><a href="#results">Fotoğraflarım <span className="nav-count">{jobs.length}</span></a><button className="nav-print" disabled={!ready||dirty||saving} onClick={()=>setPrintOpen(true)}>Baskı masası</button></nav>
      <div className="header-right"><button className="header-export" disabled={!ready||dirty||saving} onClick={()=>void download()}><ArrowDownToLine size={15}/>Dışa aktar</button><span className={`connection ${online ? "" : "offline"}`}><i/>{online ? hardware?.device === "cuda" ? "RTX · Yerel GPU" : "Yerel olarak çalışıyor" : "Bağlantı bekleniyor"}</span><button className="icon-button help-button" onClick={() => setHelp(true)} aria-label="Yardım"><CircleHelp size={20}/></button></div>
    </div></header>

    <main>
      <aside className="library-sidebar" aria-label="Fotoğraf kitaplığı">
        <button className="library-import" onClick={()=>input.current?.click()} disabled={uploading}><Plus size={17}/>Fotoğraf ekle</button>
        <label className="library-search"><FolderOpen size={15}/><input aria-label="Fotoğraflarda ara" placeholder="Fotoğraf ara…" value={search} onChange={e=>setSearch(e.target.value)}/></label>
        <h2>Kitaplık</h2>
        <button aria-pressed={galleryFilter==="all"} className={galleryFilter==="all"?"library-active":""} onClick={()=>setGalleryFilter("all")}><Layers3 size={17}/>Tüm fotoğraflar<span>{jobs.length}</span></button>
        <button aria-pressed={galleryFilter==="done"} className={galleryFilter==="done"?"library-active":""} onClick={()=>setGalleryFilter("done")}><Check size={17}/>Tamamlananlar<span>{done.length}</span></button>
        <button aria-pressed={galleryFilter==="pending"} className={galleryFilter==="pending"?"library-active":""} onClick={()=>setGalleryFilter("pending")}><Clock3 size={17}/>İşlem kuyruğu<span>{pending.length}</span></button>
        <h2>Çalışma alanı</h2>
        <button disabled={!ready||dirty||saving} onClick={()=>setPrintOpen(true)}><Printer size={17}/>Vesikalık & baskı</button>
        <div className="library-bottom"><ShieldCheck size={19}/><strong>Yerel çalışma alanınız</strong><p>Fotoğraflar bu cihazda işlenir ve saklanır.</p><span>{online?"● Sistem hazır":"○ Bağlantı bekleniyor"}</span></div>
      </aside>
      <div className="workflow-bar"><a className="workflow-active" href="#studio"><WandSparkles size={17}/> Düzenle</a><button disabled={!ready||dirty||saving} onClick={()=>setPrintOpen(true)}><Printer size={17}/> Baskı masası</button><div className="workflow-meta"><ShieldCheck size={14}/>Cihazınızda işlenir</div></div>

      <section id="studio" className="studio-shell" onDragOver={e => { e.preventDefault(); if (!uploading) setDragging(true); }} onDragLeave={e => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragging(false); }} onDrop={e => { e.preventDefault(); setDragging(false); void uploadFiles(e.dataTransfer.files); }}>
        {dragging && <div className="drop-overlay"><Upload size={44}/><h2>Fotoğraflarınızı buraya bırakın</h2><p>Bir seferde 12 fotoğrafa kadar</p></div>}
        <div className="workspace">
          <div className="workspace-top"><div className="workspace-title"><span className="tiny-mark"><WandSparkles size={16}/></span><strong>{active ? active.name : "Yeni fotoğrafınızı ekleyin"}</strong>{!active && <span className="demo-badge">ÇALIŞMA ALANI</span>}</div><div className="view-switch" aria-label="Önizleme modu"><button className={compare ? "selected" : ""} onClick={() => { if (!dirty) { setCompare(true); setBrush(null); } }} disabled={!!brush && dirty}>Karşılaştır</button><button className={!compare ? "selected" : ""} onClick={() => setCompare(false)}>Sonuç</button></div></div>
          <div className={`preview-stage ${!active?"empty-stage":""} ${background === "transparent" ? "checker" : ""}`} ref={stage} style={{backgroundColor: background === "transparent" ? undefined : background}}>
            {!active&&<div className="studio-empty"><div className="empty-upload-icon"><ImagePlus size={32}/></div><h2>Sıradaki kareniz.</h2><p>Fotoğrafları sürükleyip bırakın veya cihazınızdan seçin.</p><button className="intro-upload" onClick={()=>input.current?.click()}><Upload size={17}/>Fotoğraf seç</button><span>JPG, PNG, WEBP · Toplu yükleme desteklenir</span><div className="empty-features"><span><Sparkles size={14}/>Hassas kesim</span><span><Printer size={14}/>Dörtlü baskı</span></div></div>}
            <ZoomViewport width={frame.width} height={frame.height} nativeWidth={active?.width} resetKey={viewKey} split={split} onSplit={setSplit} compare={compare && !brush && !busy} brush={!!brush}>
            <div className="image-frame" style={{width: frame.width, height: frame.height}}>
              {brush && ready ? <canvas ref={canvas} className="brush-canvas" style={{cursor: editorReady ? "crosshair" : "wait"}} onPointerDown={e => { if (e.button !== 0 || e.altKey || !editorReady || saving) return; drawing.current = true; lastPoint.current = null; e.currentTarget.setPointerCapture(e.pointerId); paint(e); }} onPointerMove={paint} onPointerUp={() => {drawing.current = false; lastPoint.current = null;}} onPointerCancel={() => {drawing.current = false;}}/> : <>
                {/* Local user images preserve their original dimensions; Next image optimization is unnecessary. */}
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img draggable={false} className="main-image" src={active && !ready ? active.original_url : resultSrc} alt={active ? `${active.name} sonucu` : "Arka planı kaldırılmış saksı bitkisi örneği"}/>
                {compare && !busy && active?.status !== "failed" && <div className={`before-layer ${!active ? "demo-before" : ""}`} style={{clipPath: `inset(0 ${100-split}% 0 0)`}}><img draggable={false} src={active?.original_url || "/demo-cutout.svg"} alt="Orijinal fotoğraf"/></div>}
              </>}
              {compare && !brush && !busy && active?.status !== "failed" && <><div className="split-line" style={{left: `${split}%`}}><span><ChevronDown size={17}/><ChevronDown size={17}/></span></div><input aria-label="Önce ve sonra karşılaştırma" className="comparison-slider" type="range" min="0" max="100" value={split} onChange={e => setSplit(Number(e.target.value))}/></>}
            </div>
            </ZoomViewport>
            {compare && !brush && !busy && active?.status !== "failed" && <><span className="preview-label before-label">ÖNCE</span><span className="preview-label after-label">SONRA</span></>}
            {(busy || uploading) && <div className="processing-overlay"><div className="processing-symbol"><LoaderCircle className="spin" size={30}/></div><h3>{uploading ? "Fotoğraflar yükleniyor" : active?.status === "queued" ? "Fotoğrafınız sırada" : "Fotoğraf hazırlanıyor"}</h3><p>{uploading ? "Birazdan işlem başlayacak." : active?.stage || "İlk kullanımda modeller indirilir."}</p>{active?.progress ? <div className="job-progress" role="progressbar" aria-label="Fotoğraf işleme" aria-valuenow={active.progress} aria-valuemin={0} aria-valuemax={100}><span style={{width:`${active.progress}%`}}/><small>%{active.progress}</small></div> : <span className="indeterminate"/>}</div>}
            {active?.status === "failed" && <div className="processing-overlay"><span className="error-symbol"><X size={24}/></span><h3>Bu fotoğraf işlenemedi</h3><p>{active.error}</p><button className="secondary-button" onClick={() => void retry(active)}><RefreshCw size={16}/>Tekrar dene</button></div>}
            {brush && !editorReady && <div className="editor-loading"><LoaderCircle className="spin" size={22}/> Düzenleyici hazırlanıyor</div>}
          </div>
          <div className="workspace-bottom"><span><span className="small-dot"/>{active ? `${active.width} × ${active.height} px` : "Örnek önizleme"}<span className="bottom-divider"/>{brush ? "Fırçayla fotoğrafın üzerine çizin" : "Orijinal çözünürlük korunur"}</span><button className="text-button" onClick={() => input.current?.click()} disabled={uploading}><Plus size={16}/>Yeni fotoğraf</button></div>
          {brush && <><div className="brush-toolbar"><div className="brush-tools"><button className={brush === "erase" ? "active" : ""} onClick={() => selectBrush("erase")} disabled={saving}><Eraser size={16}/>Sil</button><button className={brush === "restore" ? "active" : ""} onClick={() => selectBrush("restore")} disabled={saving}><Paintbrush size={16}/>Geri getir</button><button className={brush === "detail" ? "active" : ""} onClick={() => selectBrush("detail")} disabled={saving}><Sparkles size={16}/>Saç detayı</button></div><label className="brush-size">Boyut <input aria-label="Fırça boyutu" type="range" min="6" max="100" value={brushSize} onChange={e => setBrushSize(Number(e.target.value))}/></label><button className="text-button" disabled={saving} onClick={() => { if (!dirty || window.confirm("Fırça değişiklikleri iptal edilsin mi?")) {setBrush(null); setDirty(false);} }}>İptal</button><button className="small-primary" disabled={!dirty || saving} onClick={() => void saveEdit()}>{saving ? <LoaderCircle className="spin" size={15}/> : brush === "detail" ? <Sparkles size={15}/> : <Check size={15}/>} {brush === "detail" ? "İyileştir" : "Kaydet"}</button></div>{brush === "detail" && <p className="detail-hint">Saç ile arka planın birleştiği kenarı boyayın. ViTMatte-B, işaretlediğiniz alanı orijinal fotoğraftan yeniden hesaplar; önceki sonuç korunur.</p>}</>}
        </div>

        <aside className="settings-panel"><div className="panel-heading"><SlidersHorizontal size={18}/><h2>Stüdyo ayarları</h2></div>
          <button className="upload-button" onClick={() => input.current?.click()} disabled={uploading}>{uploading ? <LoaderCircle className="spin" size={20}/> : <Upload size={20}/>}Fotoğraf yükle<ArrowRight size={18}/></button><p className="upload-caption">veya fotoğraflarınızı buraya sürükleyin</p><input ref={input} type="file" accept=".jpg,.jpeg,.png,.webp,.bmp" multiple hidden onChange={e => {if (e.target.files) void uploadFiles(e.target.files);}}/>
          <div className="settings-group model-settings"><div className="group-heading"><h3>İşleme modu</h3><span>YENİ YÜKLEMELER</span></div><div className="model-options"><button className={model === "quality" ? "active" : ""} onClick={() => setModel("quality")}><Sparkles size={17}/><span><strong>Maksimum detay</strong><small>Saç ve kenarlarda yüksek ayrıntı</small></span><span className="radio-circle">{model === "quality" && <i/>}</span></button><button className={model === "fast" ? "active" : ""} onClick={() => setModel("fast")}><Zap size={17}/><span><strong>Hızlı işlem</strong><small>Önizleme ve günlük işler</small></span><span className="radio-circle">{model === "fast" && <i/>}</span></button></div><label className="toggle-row"><span>Saç detaylarını koru<small>Saç, iç boşluk ve hale temizliği</small></span><input type="checkbox" checked={model === "quality" && refine} disabled={model === "fast"} onChange={e => setRefine(e.target.checked)}/><span className="toggle-track"/></label><p className="pipeline-note">{model === "quality" ? refine ? "İnce teller, doğal şeffaflık ve kenar temizliği" : "Detaylı kesim · Ek saç iyileştirme kapalı" : "Hızlı kesim · Saç detayını sonradan fırçayla iyileştirebilirsiniz."}</p></div>
          <div className="settings-group face-settings"><div className="group-heading"><h3>Doğal yüz rötuşu</h3><span>İSTEĞE BAĞLI</span></div>
            <label className="toggle-row"><span>Leke temizliği<small>Küçük cilt alanlarında yerel onarım</small></span><input aria-label="Yüz leke temizliği" type="checkbox" checked={faceClean} disabled={busy||saving||dirty||faceUpdating} onChange={e=>void updateFace(e.target.checked,faceSharpen,faceSpots)}/><span className="toggle-track"/></label>
            <label className="toggle-row"><span>Doğal netlik<small>Mevcut dokuya sınırlı netlik</small></span><input aria-label="Yüz hafif netlik" type="checkbox" checked={faceSharpen} disabled={busy||saving||dirty||faceUpdating} onChange={e=>void updateFace(faceClean,e.target.checked,faceSpots)}/><span className="toggle-track"/></label>
            {faceSharpen&&<div className="face-strength"><label htmlFor="face-strength">Netlik gücü <strong>%{faceStrength}</strong></label><input id="face-strength" type="range" min="0" max="100" step="5" value={faceStrength} disabled={busy||saving||dirty||faceUpdating} onChange={e=>setFaceStrength(Number(e.target.value))}/><small>Düşük: hafif · Yüksek: cilt kenarı kontrastı. Göz ve ağız korunur.</small>{ready&&<button className="small-primary" disabled={busy||saving||dirty||faceUpdating} onClick={()=>void updateFace(faceClean,faceSharpen,faceSpots,faceStrength)}>Netlik gücünü uygula</button>}</div>}
            <label className="toggle-row"><span>Doğal göz netliği<small>Mevcut iris ve kirpik kenarlarına sınırlı kontrast</small></span><input aria-label="Doğal göz netliği" type="checkbox" checked={eyeSharpen} disabled={busy||saving||dirty||faceUpdating} onChange={e=>void updateFace(faceClean,faceSharpen,faceSpots,faceStrength,e.target.checked)}/><span className="toggle-track"/></label>
            <label className="face-spots"><input type="checkbox" checked={faceSpots} disabled={!faceClean||busy||saving||dirty||faceUpdating} onChange={e=>void updateFace(faceClean,faceSharpen,e.target.checked)}/>Küçük benekleri de hedefle</label>
            <p className="pipeline-note">Yüz yeniden üretilmez. Küçük ben ve çiller değişebilir; kıl ve doku korunması garanti edilemez. Kapatınca rötuşsuz kesime dönülür.</p>
            {active?.face_report?.message&&(active.face_clean||active.face_sharpen||active.eye_sharpen)&&<p className="face-report" role="status">{active.face_report.message}</p>}
          </div>
          <div className="settings-group"><div className="group-heading"><h3>Arka plan</h3><span>{colors.includes(background) ? labels[colors.indexOf(background)] : "Özel"}</span></div><div className="color-options">{colors.map((color, index) => <button key={color} className={`color-swatch ${background === color ? "chosen" : ""} ${color === "transparent" ? "checker" : ""}`} style={{backgroundColor: color === "transparent" ? undefined : color}} onClick={() => setBackground(color)} aria-label={`${labels[index]} arka plan`} title={labels[index]}>{background === color && <Check size={17} color={color === "#183d32" ? "white" : "#183d32"}/>}</button>)}<label className="custom-color" title="Özel renk"><Plus size={18}/><input aria-label="Özel arka plan rengi" type="color" value={background === "transparent" ? "#ffffff" : background} onChange={e => setBackground(e.target.value)}/></label></div></div>
          <div className="settings-group export-settings"><div className="group-heading"><h3>Dışa aktar</h3></div><label className="select-label">Boyut<select value={preset} onChange={e => setPreset(e.target.value)}><option value="original">Orijinal boyut</option><option value="portrait">Portre · 600 × 800</option></select></label><div className="format-row"><span>Dosya biçimi</span><div className="format-switch"><button onClick={() => setFormat("png")} className={format === "png" ? "active" : ""}>PNG</button><button onClick={() => setFormat("jpg")} className={format === "jpg" ? "active" : ""}>JPG</button></div></div>{format === "jpg" && background === "transparent" && <p className="format-note">JPG, beyaz arka planla kaydedilir.</p>}{preset === "portrait" && <p className="format-note">Nesne ortalanır. Resmî biyometrik uygunluk garantisi vermez.</p>}</div>
          <button className="download-button" disabled={!ready || dirty || saving} onClick={() => void download()}><ArrowDownToLine size={18}/>Fotoğrafı indir<span>{format.toUpperCase()}</span></button><button className="refine-button hair-button" disabled={!ready || saving} onClick={() => selectBrush("detail")}><Sparkles size={16}/>Saç detay fırçası</button><button className="refine-button" disabled={!ready || saving} onClick={() => selectBrush("erase")}><Paintbrush size={16}/>Fırçayla düzenle</button>
          <button className="print-entry" disabled={!ready||dirty||saving} onClick={()=>setPrintOpen(true)}><span><Printer size={20}/></span><div><strong>Vesikalık & baskı</strong><small>4’lü yerleşim · Beyaz zemin · PDF</small></div><ArrowRight size={17}/></button>
          <div className="panel-footnote"><ShieldCheck size={14}/><span>JPG, PNG, WEBP, BMP · En fazla 20 MB</span></div>
        </aside>
      </section>

      <div className="benefits"><span><Sparkles size={16}/>Yapay zekâ ile hassas kesim</span><span><ImagePlus size={16}/>Tam çözünürlükte indirme</span><span><ShieldCheck size={16}/>Tamamen yerel ve özel</span></div>

      <section id="results" className="results-section"><div className="results-heading"><div><div className="eyebrow"><span/>FOTOĞRAF ŞERİDİ</div><h2>Fotoğraflar <span>{visibleJobs.length} / {jobs.length}</span></h2></div><div className="results-actions">{pending.length > 0 && <span className="queue-badge"><LoaderCircle className="spin" size={14}/>{pending.length} işlem sırada</span>}<button className="icon-button" onClick={() => void refresh()} aria-label="Sonuçları yenile"><RefreshCw size={17}/></button>{done.length > 0 && <a className="secondary-button" href="/api/export" download><ArrowDownToLine size={16}/>Tümünü indir <span>ZIP</span></a>}</div></div>
        {jobs.length === 0 ? <div className="empty-gallery"><div className="empty-icon"><FolderOpen size={26}/></div><h3>İlk fotoğrafınız için hazır.</h3><p>Yüklediğiniz fotoğraflar ve sonuçları burada sizi bekleyecek.</p><button className="text-button" onClick={() => input.current?.click()}>Bir fotoğrafla başlayın<ArrowRight size={16}/></button></div> : <div className="gallery">{visibleJobs.length===0&&<p className="no-matches">Bu filtrede fotoğraf bulunamadı.</p>}{visibleJobs.map(job => <article className={`photo-card ${activeId === job.id ? "selected-card" : ""}`} key={job.id}><button className="photo-preview checker" onClick={() => chooseJob(job)} aria-label={`${job.name} fotoğrafını aç`}><img src={job.status === "done" ? `${job.result_url}?v=${revision}` : job.original_url} alt={job.name} loading="lazy"/>{job.status !== "done" && <span className={`status-badge ${job.status === "failed" ? "failed" : ""}`}>{job.status === "failed" ? <X size={13}/> : <LoaderCircle size={13} className="spin"/>}{statusLabels[job.status]}</span>}{job.status === "done" && <span className="ready-badge"><Check size={12}/></span>}</button><div className="photo-info"><div><h3 title={job.name}>{job.name}</h3><p>{job.width} × {job.height} <span>·</span> {job.model === "quality" ? "Detaylı kesim" : "Hızlı kesim"}{(job.face_clean||job.face_sharpen||job.eye_sharpen)?" · Rötuşlu":""}</p></div><div className="photo-actions">{job.status === "done" && <a href={downloadUrl(job,"transparent","png","original")} download className="icon-button" aria-label={`${job.name} indir`}><ArrowDownToLine size={17}/></a>}{job.status === "failed" && <button className="icon-button" onClick={() => void retry(job)} aria-label="Tekrar dene"><RefreshCw size={16}/></button>}<button className="icon-button delete-button" disabled={job.status === "processing" || job.status === "queued"} onClick={() => void removeJob(job)} aria-label={`${job.name} sil`}><Trash2 size={16}/></button></div></div></article>)}<button className="add-card" onClick={() => input.current?.click()} disabled={uploading}><span><Plus size={27}/></span><strong>Yeni kare ekle</strong><p>Yeni fotoğraf yükle</p></button></div>}
      </section>
      <footer><a className="footer-brand" href="#studio"><Layers3 size={16}/>BiRef studio</a><p>Fotoğraftan baskıya, tek çalışma alanı.</p><span><Leaf size={14}/>Cihazınızda, sizin için.</span></footer>
    </main>
    {printOpen&&active&&ready&&<PrintStudio job={active} onClose={()=>setPrintOpen(false)}/>}
    {notice && <div className={`toast ${notice.error ? "toast-error" : ""}`} role={notice.error ? "alert" : "status"}>{notice.error ? <CircleHelp size={19}/> : <Check size={19}/>}<span>{notice.text}</span><button aria-label="Bildirimi kapat" onClick={() => setNotice(null)}><X size={17}/></button></div>}
    {help && <div className="modal-backdrop" onClick={() => setHelp(false)}><section className="help-modal" role="dialog" aria-modal="true" aria-labelledby="help-title" onClick={e => e.stopPropagation()}><button className="modal-close icon-button" onClick={() => setHelp(false)} aria-label="Yardımı kapat"><X size={20}/></button><span className="tiny-mark"><Sparkles size={22}/></span><h2 id="help-title">Stüdyonuza hoş geldiniz.</h2><ol><li><strong>Fotoğrafınızı yükleyin.</strong> Birden fazla fotoğraf seçebilir veya sürükleyebilirsiniz.</li><li><strong>Sonucu size göre şekillendirin.</strong> Karşılaştırma çizgisini kaydırın; arka plan rengini değiştirin.</li><li><strong>Son dokunuşu yapın.</strong> Fırçayla silin veya orijinalden geri getirin, ardından kaydedin.</li><li><strong>İndirin.</strong> Şeffaf PNG, renkli JPG veya 600 × 800 portre olarak dışa aktarın.</li></ol><div className="help-note"><Clock3 size={18}/><p>Maksimum detay modu BiRefNet HR ve ViTMatte-B kullanır. Saç detay fırçasıyla zor kenarları işaretleyebilirsiniz. NVIDIA ekran kartı otomatik kullanılır; ilk işlemde modeller indirilir.</p></div><button className="upload-button" onClick={() => setHelp(false)}>Hadi başlayalım<ArrowRight size={18}/></button></section></div>}
  </>;
}
