"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { Minus, Plus, RotateCcw, Scan } from "lucide-react";

type Props = { children: ReactNode; width: number; height: number; nativeWidth?: number;
  resetKey: string | null; split: number; onSplit: (value: number) => void; compare: boolean; brush: boolean };

export default function ZoomViewport({children,width,height,nativeWidth,resetKey,split,onSplit,compare,brush}: Props) {
  const viewport=useRef<HTMLDivElement>(null);
  const [view,setView]=useState({zoom:1,x:0,y:0});
  const value=useRef(view); value.current=view;
  const pointers=useRef(new Map<number,{x:number;y:number}>());
  const gesture=useRef<{x:number;y:number;distance:number;view:typeof view}|null>(null);
  const space=useRef(false);
  const compareDrag=useRef(false);
  function moveDivider(clientX:number) {
    const frame=viewport.current?.querySelector(".image-frame")?.getBoundingClientRect();
    if(frame)onSplit(Math.max(0,Math.min(100,(clientX-frame.left)/frame.width*100)));
  }
  function bounded(next: typeof view) {
    const el=viewport.current;
    const maxX=Math.max(0,(width*next.zoom-(el?.clientWidth||width))/2);
    const maxY=Math.max(0,(height*next.zoom-(el?.clientHeight||height))/2);
    return {...next,x:Math.max(-maxX,Math.min(maxX,next.x)),y:Math.max(-maxY,Math.min(maxY,next.y))};
  }
  function zoomTo(zoom:number,clientX?:number,clientY?:number) {
    const old=value.current;const nextZoom=Math.min(32,Math.max(1,zoom));
    const rect=viewport.current?.getBoundingClientRect();
    const px=rect&&clientX!==undefined?clientX-rect.left-rect.width/2:0;
    const py=rect&&clientY!==undefined?clientY-rect.top-rect.height/2:0;
    const ratio=nextZoom/old.zoom;
    setView(bounded({zoom:nextZoom,x:px-(px-old.x)*ratio,y:py-(py-old.y)*ratio}));
  }
  useEffect(()=>{setView({zoom:1,x:0,y:0});pointers.current.clear();gesture.current=null;},[resetKey]);
  useEffect(()=>{setView(current=>bounded(current));},[width,height]); // Resize without losing the viewed area.
  useEffect(()=>{
    const el=viewport.current;if(!el)return;
    const wheel=(event:WheelEvent)=>{event.preventDefault();zoomTo(value.current.zoom*Math.exp(-event.deltaY*.0018),event.clientX,event.clientY);};
    el.addEventListener("wheel",wheel,{passive:false});
    return()=>el.removeEventListener("wheel",wheel);
  },[width,height]);
  function start(event:React.PointerEvent<HTMLDivElement>) {
    if((event.target as HTMLElement).closest("input,button"))return;
    if(!brush&&(event.target as HTMLElement).closest(".split-line")) {
      event.preventDefault();event.currentTarget.setPointerCapture(event.pointerId);
      compareDrag.current=true;moveDivider(event.clientX);return;
    }
    if(brush&&!event.altKey&&event.button!==1)return;
    if(event.button!==0&&event.button!==1)return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    pointers.current.set(event.pointerId,{x:event.clientX,y:event.clientY});
    const points=[...pointers.current.values()];
    gesture.current={x:points.reduce((n,p)=>n+p.x,0)/points.length,y:points.reduce((n,p)=>n+p.y,0)/points.length,
      distance:points.length>1?Math.hypot(points[0].x-points[1].x,points[0].y-points[1].y):0,view:value.current};
  }
  function move(event:React.PointerEvent<HTMLDivElement>) {
    if(compareDrag.current){moveDivider(event.clientX);return;}
    if(!pointers.current.has(event.pointerId)||!gesture.current)return;
    pointers.current.set(event.pointerId,{x:event.clientX,y:event.clientY});
    const points=[...pointers.current.values()];const old=gesture.current;
    const x=points.reduce((n,p)=>n+p.x,0)/points.length,y=points.reduce((n,p)=>n+p.y,0)/points.length;
    if(points.length>1&&old.distance) {
      const distance=Math.hypot(points[0].x-points[1].x,points[0].y-points[1].y);
      const zoom=Math.max(1,Math.min(32,old.view.zoom*distance/old.distance));
      const rect=viewport.current?.getBoundingClientRect();if(!rect)return;
      const px=old.x-rect.left-rect.width/2,py=old.y-rect.top-rect.height/2,ratio=zoom/old.view.zoom;
      setView(bounded({zoom,x:px-(px-old.view.x)*ratio+x-old.x,y:py-(py-old.view.y)*ratio+y-old.y}));
    } else setView(bounded({...old.view,x:old.view.x+x-old.x,y:old.view.y+y-old.y}));
  }
  function end(event:React.PointerEvent<HTMLDivElement>) {
    compareDrag.current=false;
    pointers.current.delete(event.pointerId);gesture.current=null;
  }
  return <>
    <div ref={viewport} className={`zoom-viewport ${view.zoom>1?"is-zoomed":""}`} data-testid="zoom-viewport"
      tabIndex={0} role="region" aria-label="Yakınlaştırılabilir fotoğraf alanı"
      onPointerDown={start} onPointerMove={move} onPointerUp={end} onPointerCancel={end}
      onDoubleClick={event=>{if(!brush)zoomTo(view.zoom===1?Math.min(4,nativeWidth?nativeWidth/width:4):1,event.clientX,event.clientY);}}
      onKeyDown={event=>{
        if(event.key===" "){space.current=true;event.preventDefault();}
        if(event.key==="+"||event.key==="="){event.preventDefault();zoomTo(view.zoom*1.25);}
        if(event.key==="-"){event.preventDefault();zoomTo(view.zoom/1.25);}
        if(event.key==="0")setView({zoom:1,x:0,y:0});
        const arrows:Record<string,[number,number]>={ArrowLeft:[30,0],ArrowRight:[-30,0],ArrowUp:[0,30],ArrowDown:[0,-30]};
        if(arrows[event.key]){event.preventDefault();const [x,y]=arrows[event.key];setView(bounded({...view,x:view.x+x,y:view.y+y}));}
      }} onKeyUp={event=>{if(event.key===" ")space.current=false;}} onBlur={()=>{space.current=false;}}>
      <div className="zoom-content" style={{width,height,transform:`translate(${view.x}px,${view.y}px) scale(${view.zoom})`,imageRendering:nativeWidth && view.zoom*width>=nativeWidth-.5?"pixelated":"auto","--view-zoom":view.zoom} as React.CSSProperties}>{children}</div>
    </div>
    <div className="zoom-controls" aria-label="Yakınlaştırma kontrolleri">
      <button aria-label="Uzaklaştır" disabled={view.zoom<=1} onClick={()=>zoomTo(view.zoom/1.25)}><Minus size={15}/></button>
      <output aria-label="Görünüm yakınlaştırması">%{Math.round(view.zoom*100)}</output>
      <button aria-label="Yakınlaştır" disabled={view.zoom>=32} onClick={()=>zoomTo(view.zoom*1.25)}><Plus size={15}/></button>
      <button aria-label="Orijinal piksel boyutu" title="1:1 piksel" onClick={()=>zoomTo(nativeWidth?nativeWidth/width:1)}><Scan size={15}/><span>1:1</span></button>
      <button aria-label="Ekrana sığdır" title="Sığdır" onClick={()=>setView({zoom:1,x:0,y:0})}><RotateCcw size={15}/></button>
    </div>
    {compare&&<label className="zoom-compare-control">Önce / sonra<input aria-label="Yakınlaştırılmış karşılaştırma konumu" type="range" min="0" max="100" value={split} onChange={event=>onSplit(Number(event.target.value))}/></label>}
    <span className="zoom-hint">{brush?"Tekerlek: büyüt · Alt + sürükle: gezin":"Tekerlek veya iki parmak: büyüt · Sürükle: gezin"}</span>
  </>;
}
