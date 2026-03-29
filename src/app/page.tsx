"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import Webcam from "react-webcam";
import { Search, LogOut, LogIn, X, Check, Car, Sun, Moon, Trash2, Activity, ListOrdered, Clock, RefreshCw, Eraser } from "lucide-react";
import { format } from "date-fns";
import { type ParkedCar, calculateFee } from "../lib/parking";

const EVENT_FEES = [
  { id: "normal", name: "Normal", amount: null },
  { id: "event_5k", name: "Matucana", amount: 5000 },
  { id: "event_8k", name: "Premium", amount: 8000 },
  { id: "event_10k", name: "VIP", amount: 10000 },
];

export default function ParkingMVP() {
  const [cars, setCars] = useState<Record<string, ParkedCar>>({});
  const [history, setHistory] = useState<any[]>([]);
  const [stats, setStats] = useState({ today_income: 0, today_entries: 0, today_exits: 0, parked_now: 0 });
  const [selectedEvent, setSelectedEvent] = useState(EVENT_FEES[0]);
  const [activeTab, setActiveTab] = useState<"actions" | "monitor" | "stats">("actions");
  
  const [isCameraOpen, setIsCameraOpen] = useState(false);
  const [cameraMode, setCameraMode] = useState<"entry" | "exit">("entry");
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [manualPlate, setManualPlate] = useState("");
  const [showManualInput, setShowManualInput] = useState(false);
  const [isDarkMode, setIsDarkMode] = useState(true);
  
  const [actionResult, setActionResult] = useState<{ plate: string; action: string; fee?: number } | null>(null);

  const webcamRef = useRef<Webcam>(null);

  const fetchData = async () => {
    try {
      const api = process.env.NEXT_PUBLIC_API_URL || "/api";
      const ts = Date.now();
      const [c, s, h] = await Promise.all([
        fetch(`${api}/cars?t=${ts}`),
        fetch(`${api}/stats?t=${ts}`),
        fetch(`${api}/history?t=${ts}`)
      ]);
      if (c.ok) setCars(await c.json());
      if (s.ok) setStats(await s.json());
      if (h.ok) setHistory(await h.json());
    } catch (e) {
      console.warn("API Error");
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 2000);
    if (localStorage.getItem("theme") === "light") setIsDarkMode(false);
    return () => clearInterval(interval);
  }, []);

  const toggleTheme = () => {
    const next = !isDarkMode;
    setIsDarkMode(next);
    localStorage.setItem("theme", next ? "dark" : "light");
  };

  const processPlate = async (p: string, mode: "entry" | "exit") => {
    const api = process.env.NEXT_PUBLIC_API_URL || "/api";
    const cleaned = p.toUpperCase().replace(/[^A-Z0-9]/g, '');
    try {
      if (mode === "entry") {
        if (cars[cleaned]) { alert("Ya registrado"); return; }
        await fetch(`${api}/entry`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ plate: cleaned, isEvent: selectedEvent.amount !== null, eventFee: selectedEvent.amount })
        });
        setActionResult({ plate: cleaned, action: "entrada" });
      } else {
        const car = cars[cleaned];
        if (!car) { alert("Auto no encontrado"); return; }
        const fee = calculateFee(car.entryTime, Date.now(), car.isEvent, car.eventFee);
        await fetch(`${api}/exit/${cleaned}?fee=${fee}`, { method: "POST" });
        setActionResult({ plate: cleaned, action: "salida", fee });
      }
      fetchData();
    } catch (e) {
      alert("Error local");
    } finally {
      setIsCameraOpen(false);
      setTimeout(() => setActionResult(null), 4000);
    }
  };

  const capture = useCallback(async () => {
    if (!webcamRef.current) return;
    setIsAnalyzing(true);
    const img = webcamRef.current.getScreenshot();
    if (!img) { setIsAnalyzing(false); return; }
    try {
      const blob = await (await fetch(img)).blob();
      const fd = new FormData();
      fd.append("image", blob, 'p.jpg');
      const api = process.env.NEXT_PUBLIC_API_URL || "/api";
      const res = await fetch(`${api}/detect`, { method: "POST", body: fd });
      const data = await res.json();
      if (data.plate && data.plate !== "None") processPlate(data.plate, cameraMode);
      else alert("No detectado");
    } catch (e) {
      alert("AI offline");
    } finally {
      setIsAnalyzing(false);
    }
  }, [webcamRef, cameraMode, processPlate]);

  const clearRecords = async () => {
    if (!confirm("Borrar historial?")) return;
    const api = process.env.NEXT_PUBLIC_API_URL || "/api";
    await fetch(`${api}/clear-history`, { method: "POST" });
    fetchData();
  };

  return (
    <div className={`min-h-screen selection:bg-indigo-500 selection:text-white transition-colors duration-300 font-sans ${isDarkMode ? 'bg-slate-950 text-slate-100' : 'bg-slate-50 text-slate-900'}`}>
      
      {/* Header - Fixed & Self Contained */}
      <header className={`sticky top-0 z-50 w-full border-b backdrop-blur-md px-6 py-4 flex items-center justify-between overflow-hidden shadow-sm ${isDarkMode ? 'bg-slate-900/90 border-white/5' : 'bg-white/90 border-slate-200 text-slate-950'}`}>
        <div className="flex items-center gap-2 truncate max-w-[40%]">
           <div className="shrink-0 p-2 rounded-lg bg-indigo-600 text-white"><Car size={18}/></div>
           <span className="font-bold whitespace-nowrap hidden sm:block">CParking</span>
        </div>
        
        <nav className="flex bg-black/10 dark:bg-white/5 p-1 rounded-xl border border-white/5 shrink-0 overflow-hidden">
           {["actions", "monitor", "stats"].map(t => (
             <button key={t} onClick={() => setActiveTab(t as any)} className={`px-3 py-1.5 rounded-lg text-[10px] font-black uppercase transition-all whitespace-nowrap ${activeTab === t ? 'bg-indigo-600 text-white shadow-md' : 'opacity-40 hover:opacity-100'}`}>
               {t === 'actions' ? 'Control' : t === 'monitor' ? 'Mapa' : 'Cierre'}
             </button>
           ))}
        </nav>

        <button onClick={toggleTheme} className="shrink-0 p-2 opacity-60 hover:opacity-100 transition-transform active:scale-90">
          {isDarkMode ? <Sun size={18}/> : <Moon size={18}/>}
        </button>
      </header>

      <main className="w-full max-w-2xl mx-auto px-4 py-8 space-y-8 overflow-x-hidden">
        
        {activeTab === "actions" && (
          <div className="space-y-8 animate-in fade-in slide-in-from-top-4 duration-500">
            
            {/* Primary Action Buttons - Flexible Grid */}
            <div className="grid grid-cols-2 gap-4">
               <button onClick={() => { setCameraMode("entry"); setIsCameraOpen(true); }} className={`p-6 sm:p-10 rounded-[2.5rem] border-2 flex flex-col items-center gap-4 transition-all shadow-xl hover:shadow-2xl active:scale-95 ${isDarkMode ? 'bg-emerald-500/5 border-emerald-500/10' : 'bg-emerald-50 border-emerald-100'}`}>
                 <div className="p-4 sm:p-5 rounded-full bg-emerald-500 text-white shadow-lg"><LogIn size={24} className="sm:w-8 sm:h-8" /></div>
                 <span className="font-bold text-[10px] sm:text-xs uppercase tracking-widest text-emerald-500">ENTRADA</span>
               </button>
               <button onClick={() => { setCameraMode("exit"); setIsCameraOpen(true); }} className={`p-6 sm:p-10 rounded-[2.5rem] border-2 flex flex-col items-center gap-4 transition-all shadow-xl hover:shadow-2xl active:scale-95 ${isDarkMode ? 'bg-indigo-500/5 border-indigo-500/10' : 'bg-indigo-50 border-indigo-100'}`}>
                 <div className="p-4 sm:p-5 rounded-full bg-indigo-600 text-white shadow-lg"><LogOut size={24} className="sm:w-8 sm:h-8" /></div>
                 <span className="font-bold text-[10px] sm:text-xs uppercase tracking-widest text-indigo-500">SALIDA</span>
               </button>
            </div>

            {/* Event Setup Card */}
            <div className={`p-6 rounded-[2.5rem] border overflow-hidden ${isDarkMode ? 'bg-slate-900 border-white/5' : 'bg-white border-slate-200'}`}>
               <div className="flex items-center gap-2 mb-4 opacity-40">
                  <Activity size={14} />
                  <h3 className="text-[10px] font-bold uppercase tracking-[0.2em]">Tarifa de Ingreso</h3>
               </div>
               <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  {EVENT_FEES.map(f => (
                    <button key={f.id} onClick={() => setSelectedEvent(f)} className={`py-3 px-1 rounded-xl text-[9px] font-bold uppercase border-2 transition-all truncate ${selectedEvent.id === f.id ? 'bg-indigo-600 border-indigo-500 text-white shadow-lg' : 'border-transparent bg-slate-500/5 opacity-40'}`}>
                      {f.name} {f.amount ? `(${f.amount/1000}k)` : ''}
                    </button>
                  ))}
               </div>
            </div>

            {/* Results Banner */}
            {actionResult && (
              <div className={`p-8 rounded-[3rem] border-4 flex flex-col sm:flex-row items-center justify-between gap-4 shadow-2xl animate-in zoom-in-95 duration-500 ${actionResult.action === 'entrada' ? 'bg-emerald-500/5 border-emerald-500/30' : 'bg-indigo-600/5 border-indigo-600/30'}`}>
                <div className="flex items-center gap-4">
                  <span className="text-3xl sm:text-4xl font-mono font-black tracking-widest break-all">{actionResult.plate}</span>
                  <div className="bg-white/10 px-3 py-1 rounded-xl text-[10px] uppercase font-black">{actionResult.action}</div>
                </div>
                {actionResult.fee !== undefined && <span className="text-4xl font-black tabular-nums font-mono">${actionResult.fee.toLocaleString()}</span>}
              </div>
            )}

            {/* Minimal Dashboard */}
            <div className="grid grid-cols-3 gap-3">
               {[
                 { label: 'Ingresos', val: `$${stats.today_income.toLocaleString()}`, color: 'text-indigo-500' },
                 { label: 'Plantel', val: stats.parked_now, color: 'text-slate-100' },
                 { label: 'Movimientos', val: stats.today_entries, color: 'text-slate-100' }
               ].map((item, idx) => (
                 <div key={idx} className={`p-4 rounded-3xl border text-center ${isDarkMode ? 'bg-slate-900 border-white/5' : 'bg-white border-slate-100 shadow-sm'}`}>
                    <div className={`text-xl sm:text-2xl font-black tabular-nums ${item.color.replace('text-slate-100', isDarkMode ? 'text-slate-100' : 'text-slate-900')}`}>{item.val}</div>
                    <div className="text-[8px] font-bold opacity-30 uppercase tracking-widest mt-1">{item.label}</div>
                 </div>
               ))}
            </div>

          </div>
        )}

        {activeTab === "monitor" && (
           <div className="grid grid-cols-1 gap-4 animate-in slide-in-from-right-10 pb-20 overflow-visible">
              {Object.values(cars).length === 0 && (
                <div className="py-20 text-center opacity-20 flex flex-col items-center gap-4">
                  <Car size={48} />
                  <p className="font-bold text-[10px] uppercase tracking-widest leading-loose text-center">Sin vehículos registrados</p>
                </div>
              )}
              {Object.values(cars).map(c => {
                const fee = calculateFee(c.entryTime, Date.now(), c.isEvent, c.eventFee);
                const elapsedMins = Math.floor((Date.now() - c.entryTime) / 60000);
                const progress = Math.min(100, (elapsedMins / 240) * 100); 
                
                return (
                  <div key={c.plate} className={`p-6 rounded-[2.5rem] border-2 transition-all ${isDarkMode ? 'bg-slate-900/40 border-white/5' : 'bg-white border-slate-200 shadow-xl'}`}>
                    <div className="flex justify-between items-center mb-6 gap-2">
                       <span className="font-black text-2xl sm:text-3xl font-mono tracking-tight underline decoration-indigo-600 decoration-2 underline-offset-8 truncate">{c.plate}</span>
                       <div className="flex items-center gap-1 shrink-0">
                          <span className={`text-[8px] font-black uppercase px-2 py-1 rounded-lg ${c.isEvent ? 'bg-purple-600' : 'bg-indigo-600'} text-white shadow-lg shadow-indigo-500/10`}>{c.isEvent ? 'Ev' : 'Nm'}</span>
                          <button onClick={() => { if(confirm(`Eliminar ${c.plate}?`)) fetch(`${process.env.NEXT_PUBLIC_API_URL || "/api"}/cars/${c.plate}`, {method: 'DELETE'}).then(fetchData) }} className="p-2 text-red-500/30 hover:text-red-500 transition-all"><Trash2 size={16}/></button>
                       </div>
                    </div>
                    
                    <div className="grid grid-cols-2 gap-4 mb-6">
                       <div className="flex items-center gap-3">
                          <Clock size={16} className="text-indigo-500 opacity-40 shrink-0"/>
                          <div className="truncate"><p className="text-[8px] font-bold opacity-30 uppercase">Entrada</p><p className="font-bold text-sm">{format(c.entryTime, 'HH:mm')}</p></div>
                       </div>
                       <div className="text-right truncate">
                          <p className="text-[8px] font-bold opacity-30 uppercase">Actual</p>
                          <p className="font-bold text-2xl text-indigo-500 tabular-nums font-mono">${fee.toLocaleString()}</p>
                       </div>
                    </div>

                    {!c.isEvent && (
                      <div className="space-y-3 mb-6">
                        <div className="flex justify-between text-[9px] font-black uppercase tracking-widest opacity-30">
                           <span className="flex items-center gap-1"><Activity size={10}/> Estancia</span>
                           <span className="tabular-nums font-mono">{elapsedMins} / 240m</span>
                        </div>
                        <div className="h-2.5 bg-black/10 dark:bg-white/5 rounded-full overflow-hidden border border-white/5 shadow-inner">
                           <div className={`h-full transition-all duration-1000 ${progress > 90 ? 'bg-red-500 animate-pulse' : progress > 70 ? 'bg-yellow-500' : 'bg-emerald-500'}`} style={{ width: `${progress}%` }} />
                        </div>
                      </div>
                    )}

                    <button onClick={() => processPlate(c.plate, 'exit')} className="w-full py-4 rounded-2xl bg-indigo-600 text-white font-black text-xs uppercase tracking-[0.2em] shadow-lg shadow-indigo-600/30 active:scale-95 transition-all">TERMINAR</button>
                  </div>
                );
              })}
           </div>
        )}

        {activeTab === "stats" && (
           <div className="space-y-8 animate-in zoom-in-95 pt-4 pb-16 overflow-visible">
              {/* Daily Hero - Fluid sizing */}
              <div className={`p-10 sm:p-14 rounded-[3.5rem] border-4 text-center relative overflow-hidden ${isDarkMode ? 'bg-slate-900 border-indigo-600/10 shadow-2xl' : 'bg-white border-slate-100 shadow-xl'}`}>
                 <div className="absolute top-0 right-0 w-32 h-32 bg-indigo-600/10 blur-[50px] rounded-full -mr-10 -mt-10" />
                 <h2 className="text-[10px] font-black uppercase opacity-20 mb-6 tracking-[0.3em]">Cierre Diario</h2>
                 <div className="text-5xl sm:text-7xl font-black text-indigo-500 tracking-tighter tabular-nums font-mono overflow-hidden truncate px-2">${stats.today_income.toLocaleString()}</div>
                 <div className="flex justify-center gap-8 mt-10 border-t border-white/10 pt-10">
                    <div className="truncate"><p className="text-2xl font-black tabular-nums">{stats.today_entries}</p><p className="text-[8px] font-bold opacity-30 mt-1 uppercase tracking-widest whitespace-nowrap">Ingresos</p></div>
                    <div className="truncate"><p className="text-2xl font-black tabular-nums">{stats.today_exits}</p><p className="text-[8px] font-bold opacity-30 mt-1 uppercase tracking-widest whitespace-nowrap">Salidas</p></div>
                 </div>
              </div>

              {/* Enhanced History - Container Bound */}
              <div className="space-y-4 max-w-full">
                 <div className="flex items-center justify-between px-2 gap-2">
                    <div className="flex items-center gap-2 truncate opacity-30">
                       <ListOrdered size={16} className="text-indigo-500 shrink-0"/>
                       <h3 className="text-[10px] font-black uppercase tracking-[0.2em] truncate">Ultimos Registros</h3>
                    </div>
                    <button onClick={clearRecords} className="shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-500/10 text-red-500 text-[8px] font-black uppercase hover:bg-red-500 hover:text-white transition-all">
                       <Eraser size={12}/> Limpiar
                    </button>
                 </div>
                 
                 <div className="space-y-3 max-h-[400px] overflow-y-auto pr-1 scrollbar-none custom-scroll overflow-x-hidden">
                    {history.length === 0 && <p className="text-center py-10 opacity-20 text-[10px] font-bold uppercase tracking-widest">Lista Vacía</p>}
                    {history.map((r, i) => (
                      <div key={i} className={`p-4 rounded-2xl border flex items-center justify-between transition-all gap-4 overflow-hidden ${isDarkMode ? 'bg-slate-900 border-white/5 hover:bg-white/5' : 'bg-white border-slate-100 shadow-sm'}`}>
                         <div className="flex items-center gap-3 overflow-hidden">
                            <span className="text-[8px] font-bold opacity-20 tabular-nums shrink-0 font-mono hidden sm:block">{r[0]?.split(' ')[1]}</span>
                            <span className="text-base sm:text-lg font-black tracking-tight tabular-nums font-mono truncate">{r[1]}</span>
                            <span className={`px-2 py-0.5 rounded-md text-[7px] font-black uppercase shrink-0 ${r[2]==='ENTRY'?'bg-emerald-500/10 text-emerald-500':'bg-indigo-500/10 text-indigo-500'}`}>{r[2]}</span>
                         </div>
                         <div className="text-right shrink-0">
                            <span className="text-sm font-black tabular-nums font-mono text-indigo-500">${parseFloat(r[4]||0).toLocaleString()}</span>
                         </div>
                      </div>
                    ))}
                 </div>
              </div>
           </div>
        )}
      </main>

      {/* Camera Interface - Bound Viewport */}
      {isCameraOpen && (
        <div className="fixed inset-0 z-[100] bg-black flex flex-col items-center justify-center p-4 sm:p-10 transition-all">
          <div className="w-full max-w-lg aspect-square relative rounded-[2.5rem] overflow-hidden border-4 border-white/10 shadow-2xl">
             <Webcam audio={false} ref={webcamRef} screenshotFormat="image/jpeg" videoConstraints={{ facingMode: "environment" }} className="h-full w-full object-cover" />
             <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                <div className="w-[85%] aspect-[3/1.2] border-2 border-emerald-400 rounded-3xl relative">
                   <div className="absolute top-1/2 left-0 w-full h-[0.5px] bg-emerald-400 animate-pulse" />
                   {/* Corners */}
                   <div className="absolute -top-1 -left-1 w-6 h-6 border-t-4 border-l-4 border-emerald-400 rounded-tl-xl" />
                   <div className="absolute -bottom-1 -right-1 w-6 h-6 border-b-4 border-r-4 border-emerald-400 rounded-br-xl" />
                </div>
             </div>
             {isAnalyzing && (
                <div className="absolute inset-0 bg-black/70 flex flex-col items-center justify-center gap-4">
                   <RefreshCw className="text-white animate-spin" size={48}/>
                   <span className="text-white font-bold text-[10px] uppercase tracking-[0.5em]">AI Analizando</span>
                </div>
             )}
          </div>
          
          <div className="mt-8 flex gap-6 items-center">
             <button onClick={() => setIsCameraOpen(false)} className="w-14 h-14 rounded-2xl bg-white/5 text-white flex items-center justify-center active:scale-90 border border-white/5"><X size={24}/></button>
             <button onClick={capture} disabled={isAnalyzing} className="w-24 h-24 rounded-full border-4 border-indigo-600/20 p-1 flex items-center justify-center transition-all bg-white active:scale-95 shadow-xl">
                <div className="w-18 h-18 rounded-full bg-indigo-600 flex items-center justify-center text-white"><Check size={40}/></div>
             </button>
             <button onClick={() => setShowManualInput(!showManualInput)} className={`w-14 h-14 rounded-2xl flex items-center justify-center transition-all border border-white/5 ${showManualInput ? 'bg-indigo-600 border-indigo-500' : 'bg-white/5'} text-white active:scale-90`}><Search size={24}/></button>
          </div>
          
          {showManualInput && (
             <div className="mt-8 w-full max-w-sm animate-in fade-in zoom-in-95 duration-300">
                <form onSubmit={(e) => { e.preventDefault(); processPlate(manualPlate.toUpperCase().trim(), cameraMode); setShowManualInput(false); setManualPlate(""); }} className="bg-white p-2 rounded-2xl flex shadow-2xl">
                   <input autoFocus type="text" value={manualPlate} onChange={e => setManualPlate(e.target.value)} placeholder="ABC123" className="flex-1 bg-slate-50 p-4 rounded-xl font-mono font-black text-xl text-black outline-none uppercase tracking-[0.1em]" />
                   <button type="submit" className="bg-slate-900 text-white w-16 rounded-xl flex items-center justify-center ml-2 shrink-0"><Check size={28}/></button>
                </form>
             </div>
          )}
        </div>
      )}

      <style jsx global>{`
        input::placeholder { color: #ccc; }
        .scrollbar-none::-webkit-scrollbar { display: none; }
        .custom-scroll { scroll-behavior: smooth; }
        * { -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; }
        /* Prevent overflow globally */
        body { overflow-x: hidden; width: 100vw; }
      `}</style>
    </div>
  );
}
