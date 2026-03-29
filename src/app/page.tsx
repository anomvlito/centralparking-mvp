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
      const timestamp = Date.now();
      const [c, s, h] = await Promise.all([
        fetch(`${api}/cars?t=${timestamp}`),
        fetch(`${api}/stats?t=${timestamp}`),
        fetch(`${api}/history?t=${timestamp}`)
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
    try {
      if (mode === "entry") {
        if (cars[p]) { alert("Registrado ya"); return; }
        await fetch(`${api}/entry`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ plate: p, isEvent: selectedEvent.amount !== null, eventFee: selectedEvent.amount })
        });
        setActionResult({ plate: p, action: "entrada" });
      } else {
        const car = cars[p];
        if (!car) { alert("Auto no detectado en monitor"); return; }
        const fee = calculateFee(car.entryTime, Date.now(), car.isEvent, car.eventFee);
        await fetch(`${api}/exit/${p}?fee=${fee}`, { method: "POST" });
        setActionResult({ plate: p, action: "salida", fee });
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
    if (!confirm("¿Borrar historial CSV de hoy?")) return;
    try {
      const api = process.env.NEXT_PUBLIC_API_URL || "/api";
      await fetch(`${api}/clear-history`, { method: "POST" });
      setHistory([]);
      fetchData();
    } catch (e) {}
  };

  const deleteActive = async (p: string) => {
    if (!confirm(`Anular ${p}?`)) return;
    try {
      const api = process.env.NEXT_PUBLIC_API_URL || "/api";
      await fetch(`${api}/cars/${p}`, { method: "DELETE" });
      fetchData();
    } catch (e) {}
  };

  return (
    <div className={`min-h-screen font-sans antialiased text-base pb-32 transition-all duration-500 ${isDarkMode ? 'bg-slate-950 text-slate-200' : 'bg-slate-50 text-slate-900'}`}>
      
      {/* Header Fijo para Navegación */}
      <header className={`sticky top-0 z-50 px-6 py-5 flex items-center justify-between border-b backdrop-blur-xl ${isDarkMode ? 'bg-slate-900/80 border-white/5' : 'bg-white/80 border-slate-200 shadow-sm'}`}>
        <div className="flex items-center gap-3">
           <div className="p-2.5 rounded-xl bg-indigo-600 text-white shadow-lg shadow-indigo-600/30"><Car size={20}/></div>
           <span className="font-extrabold tracking-tight text-xl">Parking Central</span>
        </div>
        <div className="flex bg-slate-800/10 p-1.5 rounded-xl border border-white/5">
           {["actions", "monitor", "stats"].map(t => (
             <button key={t} onClick={() => setActiveTab(t as any)} className={`px-4 py-2 rounded-lg text-xs font-bold uppercase transition-all ${activeTab === t ? 'bg-indigo-600 text-white shadow-md' : 'opacity-50 hover:opacity-100'}`}>
               {t === 'actions' ? 'Acciones' : t === 'monitor' ? 'Mapa' : 'Cierre'}
             </button>
           ))}
        </div>
        <button onClick={toggleTheme} className="p-2.5 rounded-xl transition-all border border-transparent hover:border-white/10">{isDarkMode ? <Sun size={20}/> : <Moon size={20}/>}</button>
      </header>

      <main className="max-w-2xl mx-auto p-4 space-y-8 pt-10">
        
        {activeTab === "actions" && (
          <div className="space-y-10 animate-in fade-in slide-in-from-bottom-5 duration-500">
            
            {/* Action Cards */}
            <div className="grid grid-cols-2 gap-5">
               <button onClick={() => { setCameraMode("entry"); setIsCameraOpen(true); }} className={`p-10 rounded-[2.5rem] border-2 flex flex-col items-center gap-6 active:scale-95 transition-all shadow-2xl ${isDarkMode ? 'bg-emerald-500/5 border-emerald-500/10 shadow-emerald-500/5' : 'bg-emerald-50 border-emerald-100 shadow-emerald-900/5'}`}>
                 <div className="p-5 rounded-full bg-emerald-500 text-white shadow-lg shadow-emerald-500/40"><LogIn size={36} /></div>
                 <span className="font-black text-xs uppercase tracking-[0.2em] text-emerald-500">Registrar Entrada</span>
               </button>
               <button onClick={() => { setCameraMode("exit"); setIsCameraOpen(true); }} className={`p-10 rounded-[2.5rem] border-2 flex flex-col items-center gap-6 active:scale-95 transition-all shadow-2xl ${isDarkMode ? 'bg-indigo-500/5 border-indigo-500/10 shadow-indigo-500/5' : 'bg-indigo-50 border-indigo-100 shadow-indigo-900/5'}`}>
                 <div className="p-5 rounded-full bg-indigo-600 text-white shadow-lg shadow-indigo-600/40"><LogOut size={36} /></div>
                 <span className="font-black text-xs uppercase tracking-[0.2em] text-indigo-500">Cobrar Salida</span>
               </button>
            </div>

            {/* Event Setup - Estilo Contenido */}
            <div className={`p-8 rounded-[2.5rem] border overflow-hidden ${isDarkMode ? 'bg-slate-900 border-white/5' : 'bg-white border-slate-200'}`}>
               <div className="flex items-center gap-2 mb-6 px-1">
                  <Activity size={16} className="text-indigo-500" />
                  <h3 className="text-xs font-black uppercase tracking-[0.3em] opacity-40">Tarifa para nuevo ingreso</h3>
               </div>
               <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  {EVENT_FEES.map(f => (
                    <button key={f.id} onClick={() => setSelectedEvent(f)} className={`py-4 px-2 rounded-2xl text-[10px] font-black uppercase border-2 transition-all ${selectedEvent.id === f.id ? 'bg-indigo-600 border-indigo-500 text-white shadow-lg' : 'border-transparent bg-slate-500/5 opacity-50 hover:opacity-100'}`}>
                      {f.name} {f.amount ? `($${f.amount/1000}k)` : ''}
                    </button>
                  ))}
               </div>
            </div>

            {actionResult && (
              <div className={`p-8 rounded-[3rem] border-4 flex items-center justify-between shadow-2xl animate-in zoom-in-95 duration-500 ${actionResult.action === 'entrada' ? 'bg-emerald-500/5 border-emerald-500/30' : 'bg-indigo-600/5 border-indigo-600/30'}`}>
                <div className="flex items-center gap-6">
                  <span className="text-4xl font-mono font-black tracking-widest tabular-nums">{actionResult.plate}</span>
                  <div className="bg-white/10 px-4 py-2 rounded-2xl text-xs uppercase font-black">{actionResult.action}</div>
                </div>
                {actionResult.fee !== undefined && <span className="text-4xl font-black italic tracking-tighter">${actionResult.fee.toLocaleString()}</span>}
              </div>
            )}

            {/* Realtime Bar */}
            <div className="grid grid-cols-3 gap-5">
               <div className={`p-6 rounded-3xl border ${isDarkMode ? 'bg-slate-900 border-white/5' : 'bg-white border-slate-100 shadow-sm'}`}>
                  <div className="text-3xl font-black text-indigo-500 tabular-nums">${stats.today_income.toLocaleString()}</div>
                  <div className="text-[10px] font-bold opacity-30 uppercase tracking-widest mt-2">Recargo Hoy</div>
               </div>
               <div className={`p-6 rounded-3xl border ${isDarkMode ? 'bg-slate-900 border-white/5' : 'bg-white border-slate-100 shadow-sm'}`}>
                  <div className="text-3xl font-black tabular-nums">{stats.parked_now}</div>
                  <div className="text-[10px] font-bold opacity-30 uppercase tracking-widest mt-2">En Planta</div>
               </div>
               <div className={`p-6 rounded-3xl border ${isDarkMode ? 'bg-slate-900 border-white/5' : 'bg-white border-slate-100 shadow-sm'}`}>
                  <div className="text-3xl font-black tabular-nums">{stats.today_entries}</div>
                  <div className="text-[10px] font-bold opacity-30 uppercase tracking-widest mt-2">Total Dia</div>
               </div>
            </div>

          </div>
        )}

        {activeTab === "monitor" && (
           <div className="space-y-6 animate-in slide-in-from-right-10 pb-20">
              {Object.values(cars).length === 0 && (
                <div className="py-20 text-center opacity-30 flex flex-col items-center gap-4">
                  <Car size={64} />
                  <p className="font-bold text-sm tracking-widest uppercase">Estacionamiento Vacío</p>
                </div>
              )}
              {Object.values(cars).map(c => {
                const f = calculateFee(c.entryTime, Date.now(), c.isEvent, c.eventFee);
                const elapsedMins = Math.floor((Date.now() - c.entryTime) / 60000);
                const progress = Math.min(100, (elapsedMins / 240) * 100); 
                
                return (
                  <div key={c.plate} className={`p-8 rounded-[3rem] border-2 transition-all ${isDarkMode ? 'bg-slate-900/60 border-white/5 hover:border-indigo-600/30' : 'bg-white border-slate-200 shadow-xl'}`}>
                    <div className="flex justify-between items-center mb-6">
                       <span className="font-black text-4xl font-mono tracking-tighter italic underline decoration-indigo-600 decoration-4 underline-offset-8">{c.plate}</span>
                       <button onClick={() => deleteActive(c.plate)} className="p-3 bg-red-500/5 text-red-500 hover:bg-red-500 text-red-500/50 hover:text-white rounded-2xl transition-all shadow-sm"><Trash2 size={20}/></button>
                    </div>
                    
                    <div className="grid grid-cols-2 gap-8 mb-8">
                       <div className="flex items-center gap-4">
                          <div className="p-3 rounded-2xl bg-indigo-500/10 text-indigo-500"><Clock size={20}/></div>
                          <div><p className="text-[10px] uppercase font-black opacity-30">Desde las</p><p className="font-extrabold text-xl">{format(c.entryTime, 'HH:mm')}</p></div>
                       </div>
                       <div className="text-right">
                          <p className="text-[10px] uppercase font-black opacity-30 mb-1">Monto Actual</p>
                          <p className="font-black text-4xl text-indigo-500 italic tabular-nums">${f.toLocaleString()}</p>
                       </div>
                    </div>

                    {!c.isEvent && (
                      <div className="space-y-4 mb-8">
                        <div className="flex justify-between text-xs font-black uppercase tracking-widest opacity-40">
                           <span className="flex items-center gap-2"><div className={`w-2 h-2 rounded-full ${progress > 90 ? 'bg-red-500' : 'bg-emerald-500'}`} /> Tiempo Estancia</span>
                           <span className="tabular-nums">{elapsedMins}m de 240m</span>
                        </div>
                        <div className="h-4 bg-black/10 rounded-full overflow-hidden border border-white/5 shadow-inner">
                           <div className={`h-full transition-all duration-1000 ${progress > 90 ? 'bg-red-500 animate-pulse' : progress > 70 ? 'bg-yellow-500' : 'bg-emerald-500'}`} style={{ width: `${progress}%` }} />
                        </div>
                      </div>
                    )}

                    <button onClick={() => processPlate(c.plate, 'exit')} className="w-full py-5 rounded-[2rem] bg-indigo-600 text-white font-black text-sm uppercase tracking-[0.2em] shadow-2xl shadow-indigo-600/20 hover:bg-indigo-500 active:scale-95 transition-all">COBRAR Y LIBERAR</button>
                  </div>
                );
              })}
           </div>
        )}

        {activeTab === "stats" && (
           <div className="space-y-10 animate-in zoom-in-95 pt-4 pb-20">
              {/* Daily Hero */}
              <div className={`p-16 rounded-[4rem] border-4 text-center relative overflow-hidden ${isDarkMode ? 'bg-slate-900 border-indigo-600/20 shadow-[0_0_80px_rgba(79,70,229,0.1)]' : 'bg-white border-slate-100 shadow-2xl'}`}>
                 <h2 className="text-xs font-black uppercase opacity-20 mb-10 tracking-[0.6em] italic">Cierre de Caja</h2>
                 <div className="text-8xl font-black text-indigo-500 tracking-tighter tabular-nums italic">${stats.today_income.toLocaleString()}</div>
                 <div className="flex justify-center gap-16 mt-16 border-t border-white/5 pt-16">
                    <div><p className="text-4xl font-black">{stats.today_entries}</p><p className="text-xs font-bold opacity-30 mt-2 uppercase tracking-widest">Ingresos</p></div>
                    <div><p className="text-4xl font-black">{stats.today_exits}</p><p className="text-xs font-bold opacity-30 mt-2 uppercase tracking-widest">Salidas</p></div>
                 </div>
              </div>

              {/* History List - Mejorado y Navegable */}
              <div className="space-y-4">
                 <div className="flex items-center justify-between px-3">
                    <div className="flex items-center gap-3">
                       <ListOrdered size={20} className="text-indigo-500 opacity-50"/>
                       <h3 className="text-xs font-black uppercase tracking-[0.4em] opacity-30 italic">Registros Recientes</h3>
                    </div>
                    <button onClick={clearRecords} className="flex items-center gap-2 px-4 py-2 rounded-xl bg-red-500/10 text-red-500 text-[10px] font-black uppercase hover:bg-red-500 hover:text-white transition-all">
                       <Eraser size={14}/> Limpiar
                    </button>
                 </div>
                 
                 <div className="space-y-3 max-h-[500px] overflow-y-auto pr-2 scrollbar-none">
                    {history.length === 0 && <p className="text-center py-10 opacity-20 italic font-bold">Sin registros</p>}
                    {history.map((r, i) => (
                      <div key={i} className={`p-5 rounded-3xl border flex items-center justify-between transition-all ${isDarkMode ? 'bg-slate-900 border-white/5 hover:border-white/10' : 'bg-white border-slate-100 shadow-sm'}`}>
                         <div className="flex items-center gap-5">
                            <span className="text-[10px] font-bold opacity-30 tabular-nums">{r[0]?.split(' ')[1]}</span>
                            <span className="text-2xl font-mono font-black tracking-tighter tabular-nums">{r[1]}</span>
                            <span className={`px-3 py-1 rounded-full text-[9px] font-black uppercase tracking-widest ${r[2]==='ENTRY'?'bg-emerald-500/10 text-emerald-500':'bg-indigo-500/10 text-indigo-500'}`}>{r[2]}</span>
                         </div>
                         <div className="text-right">
                            <span className="text-xl font-black tabular-nums text-indigo-500">${parseFloat(r[4]||0).toLocaleString()}</span>
                         </div>
                      </div>
                    ))}
                 </div>
              </div>
           </div>
        )}
      </main>

      {/* Cam Full Screen Feel */}
      {isCameraOpen && (
        <div className="fixed inset-0 z-[100] bg-black flex flex-col items-center justify-center p-8 bg-slate-950">
          <div className="w-full max-w-2xl aspect-square relative rounded-[3rem] overflow-hidden border-8 border-white/5 shadow-2xl">
             <Webcam audio={false} ref={webcamRef} screenshotFormat="image/jpeg" videoConstraints={{ facingMode: "environment" }} className="h-full w-full object-cover grayscale opacity-80" />
             <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                <div className="w-[85%] aspect-[3/1.1] border-4 border-emerald-400 rounded-3xl relative shadow-[0_0_100px_rgba(16,185,129,0.2)]">
                   <div className="absolute top-1/2 left-0 w-full h-[1px] bg-emerald-400" />
                   <div className="absolute -top-14 left-1/2 -translate-x-1/2 bg-emerald-500 text-black px-6 py-2 rounded-full text-xs font-black uppercase tracking-widest">Encuadra la Patente</div>
                   {/* Corner Visuals */}
                   <div className="absolute -top-2 -left-2 w-12 h-12 border-t-8 border-l-8 border-emerald-400 rounded-tl-2xl" />
                   <div className="absolute -bottom-2 -right-2 w-12 h-12 border-b-8 border-r-8 border-emerald-400 rounded-br-2xl" />
                </div>
             </div>
             {isAnalyzing && (
                <div className="absolute inset-0 bg-black/80 flex flex-col items-center justify-center gap-6">
                   <RefreshCw className="text-white animate-spin" size={64}/>
                   <span className="text-white font-black text-xs uppercase tracking-[0.5em]">Escaneando Placa...</span>
                </div>
             )}
          </div>
          
          <div className="mt-14 flex gap-10 items-center">
             <button onClick={() => setIsCameraOpen(false)} className="w-18 h-18 rounded-3xl bg-white/5 text-white flex items-center justify-center active:scale-90 border border-white/10"><X size={36}/></button>
             <button onClick={capture} disabled={isAnalyzing} className="w-32 h-32 rounded-full border-4 border-indigo-600/50 p-2 flex items-center justify-center transition-all bg-white active:scale-90 shadow-2xl">
                <div className="w-24 h-24 rounded-full bg-indigo-600 flex items-center justify-center text-white scale-110"><Check size={54}/></div>
             </button>
             <button onClick={() => setShowManualInput(!showManualInput)} className={`w-18 h-18 rounded-3xl flex items-center justify-center transition-all border border-white/10 ${showManualInput ? 'bg-indigo-600 border-indigo-500' : 'bg-white/5'} text-white active:scale-90`}><Search size={36}/></button>
          </div>
          
          {showManualInput && (
             <div className="mt-12 w-full max-w-sm animate-in slide-in-from-bottom-10">
                <form onSubmit={(e) => { e.preventDefault(); processPlate(manualPlate.toUpperCase().trim(), cameraMode); setShowManualInput(false); setManualPlate(""); }} className="bg-white p-3 rounded-[2rem] flex shadow-2xl">
                   <input autoFocus type="text" value={manualPlate} onChange={e => setManualPlate(e.target.value)} placeholder="ABC-123" className="flex-1 bg-slate-100 p-6 rounded-2xl font-mono font-black text-3xl text-black outline-none uppercase tracking-[0.2em]" />
                   <button type="submit" className="bg-slate-900 text-white w-24 rounded-2xl flex items-center justify-center ml-2"><Check size={40}/></button>
                </form>
             </div>
          )}
        </div>
      )}

      <style jsx global>{`
        input::placeholder { color: #aaa; }
        .scrollbar-none::-webkit-scrollbar { display: none; }
        .italic { font-style: normal !important; } /* Hard override to ensure NO italics */
      `}</style>
    </div>
  );
}
