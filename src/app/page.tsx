"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import Webcam from "react-webcam";
import { Search, LogOut, LogIn, X, Check, Car, Sun, Moon, Trash2, Activity, ListOrdered, Clock } from "lucide-react";
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
      const [c, s, h] = await Promise.all([
        fetch(`${api}/cars`),
        fetch(`${api}/stats`),
        fetch(`${api}/history`)
      ]);
      if (c.ok) setCars(await c.json());
      if (s.ok) setStats(await s.json());
      if (h.ok) setHistory(await h.json());
    } catch (e) {
      console.warn("Sync failed");
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
        if (cars[p]) { alert("Ya en estacionamiento"); return; }
        await fetch(`${api}/entry`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ plate: p, isEvent: selectedEvent.amount !== null, eventFee: selectedEvent.amount })
        });
        setActionResult({ plate: p, action: "entrada" });
      } else {
        const car = cars[p];
        if (!car) { alert("Auto no encontrado"); return; }
        const fee = calculateFee(car.entryTime, Date.now(), car.isEvent, car.eventFee);
        await fetch(`${api}/exit/${p}?fee=${fee}`, { method: "POST" });
        setActionResult({ plate: p, action: "salida", fee });
      }
      fetchData();
    } catch (e) {
      alert("Error conexión");
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
      else alert("No se pudo leer la patente");
    } catch (e) {
      alert("AI offline");
    } finally {
      setIsAnalyzing(false);
    }
  }, [webcamRef, cameraMode, processPlate]);

  const deletePlate = async (p: string) => {
    if (!confirm(`Anular ${p}?`)) return;
    try {
      const api = process.env.NEXT_PUBLIC_API_URL || "/api";
      await fetch(`${api}/cars/${p}`, { method: "DELETE" });
      fetchData();
    } catch (e) {}
  };

  return (
    <div className={`min-h-screen font-sans antialiased text-base ${isDarkMode ? 'bg-slate-950 text-slate-200' : 'bg-slate-50 text-slate-900'}`}>
      
      {/* Header - Mas grande y claro */}
      <header className={`px-6 py-5 flex items-center justify-between border-b ${isDarkMode ? 'bg-slate-900/90 border-white/5' : 'bg-white border-slate-200 shadow-sm'}`}>
        <div className="flex items-center gap-3">
           <div className="p-2.5 rounded-xl bg-indigo-600 text-white shadow-lg shadow-indigo-600/20"><Car size={20}/></div>
           <span className="font-extrabold tracking-tight text-xl">Parking Central</span>
        </div>
        <div className="flex bg-slate-800/10 p-1.5 rounded-xl border border-white/5">
           {["actions", "monitor", "stats"].map(t => (
             <button key={t} onClick={() => setActiveTab(t as any)} className={`px-4 py-2 rounded-lg text-xs font-bold uppercase transition-all ${activeTab === t ? 'bg-indigo-600 text-white shadow-md' : 'opacity-50 hover:opacity-100'}`}>
               {t === 'actions' ? 'Acciones' : t === 'monitor' ? 'Mapa' : 'Cierre'}
             </button>
           ))}
        </div>
        <button onClick={toggleTheme} className="p-2.5 rounded-xl hover:bg-white/5 transition-all">{isDarkMode ? <Sun size={20}/> : <Moon size={20}/>}</button>
      </header>

      <main className="max-w-2xl mx-auto p-4 space-y-8 pt-8">
        
        {activeTab === "actions" && (
          <div className="space-y-8 animate-in fade-in duration-300">
            
            {/* Action Cards - Mas legibles */}
            <div className="grid grid-cols-2 gap-5">
               <button onClick={() => { setCameraMode("entry"); setIsCameraOpen(true); }} className={`p-8 rounded-3xl border-2 flex flex-col items-center gap-5 active:scale-95 transition-all shadow-xl ${isDarkMode ? 'bg-emerald-500/5 border-emerald-500/10 shadow-emerald-500/5' : 'bg-emerald-50 border-emerald-100 shadow-emerald-900/5'}`}>
                 <div className="p-4 rounded-2xl bg-emerald-500 text-white shadow-lg shadow-emerald-500/30"><LogIn size={32} /></div>
                 <span className="font-black text-sm uppercase tracking-widest text-emerald-500">Registrar Entrada</span>
               </button>
               <button onClick={() => { setCameraMode("exit"); setIsCameraOpen(true); }} className={`p-8 rounded-3xl border-2 flex flex-col items-center gap-5 active:scale-95 transition-all shadow-xl ${isDarkMode ? 'bg-indigo-500/5 border-indigo-500/10 shadow-indigo-500/5' : 'bg-indigo-50 border-indigo-100 shadow-indigo-900/5'}`}>
                 <div className="p-4 rounded-2xl bg-indigo-600 text-white shadow-lg shadow-indigo-600/30"><LogOut size={32} /></div>
                 <span className="font-black text-sm uppercase tracking-widest text-indigo-500">Cobrar Salida</span>
               </button>
            </div>

            {/* Select Event - Ahora aqui abajo asociado al ingreso */}
            <div className={`p-6 rounded-3xl border bg-gradient-to-br ${isDarkMode ? 'from-slate-900 to-slate-950 border-white/5' : 'from-white to-slate-50 border-slate-200 shadow-sm'}`}>
               <h3 className="text-xs font-bold uppercase opacity-40 mb-4 px-1 tracking-[0.2em]">Tipo de Tarifa para ingreso</h3>
               <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  {EVENT_FEES.map(f => (
                    <button key={f.id} onClick={() => setSelectedEvent(f)} className={`py-4 px-2 rounded-2xl text-[10px] font-black uppercase border-2 transition-all ${selectedEvent.id === f.id ? 'bg-indigo-600 border-indigo-500 text-white shadow-lg' : 'border-transparent bg-slate-500/5 opacity-50 hover:opacity-100'}`}>
                      {f.name} {f.amount ? `($${f.amount/1000}k)` : ''}
                    </button>
                  ))}
               </div>
            </div>

            {actionResult && (
              <div className={`p-6 rounded-[2rem] border-2 flex items-center justify-between shadow-2xl animate-in zoom-in-95 ${actionResult.action === 'entrada' ? 'bg-emerald-500/10 border-emerald-500/40' : 'bg-indigo-500/10 border-indigo-500/40'}`}>
                <div className="flex items-center gap-5">
                  <span className="text-3xl font-mono font-bold tracking-[0.1em]">{actionResult.plate}</span>
                  <span className="text-xs uppercase font-extrabold bg-black/20 px-3 py-1 rounded-full">{actionResult.action}</span>
                </div>
                {actionResult.fee !== undefined && <span className="text-3xl font-black">${actionResult.fee.toLocaleString()}</span>}
              </div>
            )}

            {/* Core Stats Bar */}
            <div className="grid grid-cols-3 gap-4">
               <div className={`p-5 rounded-2xl border ${isDarkMode ? 'bg-slate-900 border-white/5' : 'bg-white border-slate-100 shadow-sm'}`}>
                  <div className="text-2xl font-black text-indigo-500">${stats.today_income.toLocaleString()}</div>
                  <div className="text-[10px] uppercase font-bold opacity-30 mt-1">Caja Hoy</div>
               </div>
               <div className={`p-5 rounded-2xl border ${isDarkMode ? 'bg-slate-900 border-white/5' : 'bg-white border-slate-100 shadow-sm'}`}>
                  <div className="text-2xl font-black">{stats.parked_now}</div>
                  <div className="text-[10px] uppercase font-bold opacity-30 mt-1">Vigilados</div>
               </div>
               <div className={`p-5 rounded-2xl border ${isDarkMode ? 'bg-slate-900 border-white/5' : 'bg-white border-slate-100 shadow-sm'}`}>
                  <div className="text-2xl font-black">{stats.today_entries}</div>
                  <div className="text-[10px] uppercase font-bold opacity-30 mt-1">Ingresos</div>
               </div>
            </div>

          </div>
        )}

        {activeTab === "monitor" && (
           <div className="grid grid-cols-1 gap-5 animate-in slide-in-from-right-4 pb-20">
              {Object.values(cars).map(c => {
                const f = calculateFee(c.entryTime, Date.now(), c.isEvent, c.eventFee);
                const elapsedMins = Math.floor((Date.now() - c.entryTime) / 60000);
                const progress = Math.min(100, (elapsedMins / 240) * 100); // Progress towards 4 hours
                
                return (
                  <div key={c.plate} className={`p-6 rounded-[2rem] border transition-all ${isDarkMode ? 'bg-slate-900/50 border-white/5 hover:border-indigo-500/40' : 'bg-white border-slate-200 shadow-md'}`}>
                    <div className="flex justify-between items-center mb-5">
                       <span className="font-bold text-3xl font-mono tracking-tight underline decoration-indigo-500/40 underline-offset-8">{c.plate}</span>
                       <div className="flex items-center gap-2">
                          <span className={`text-[9px] font-black uppercase px-3 py-1 rounded-full ${c.isEvent ? 'bg-purple-600 shadow-lg shadow-purple-600/20' : 'bg-indigo-600 shadow-lg shadow-indigo-600/20'} text-white`}>{c.isEvent ? 'Evento' : 'Normal'}</span>
                          <button onClick={() => deletePlate(c.plate)} className="p-2 hover:bg-red-500/10 text-red-500/40 hover:text-red-500 rounded-lg"><Trash2 size={16}/></button>
                       </div>
                    </div>
                    
                    <div className="grid grid-cols-2 gap-4 mb-6">
                       <div className="flex items-center gap-3">
                          <Clock className="text-indigo-500 opacity-50" size={16}/>
                          <div><p className="text-[10px] uppercase font-bold opacity-30">Ingreso</p><p className="font-bold">{format(c.entryTime, 'HH:mm')}</p></div>
                       </div>
                       <div className="text-right">
                          <p className="text-[10px] uppercase font-bold opacity-30">Monto Actual</p>
                          <p className="font-black text-2xl text-indigo-500">${f.toLocaleString()}</p>
                       </div>
                    </div>

                    {!c.isEvent && (
                      <div className="space-y-2 mb-6">
                        <div className="flex justify-between text-[10px] font-bold uppercase opacity-40">
                           <span>Tiempo Estancia</span>
                           <span>{elapsedMins}m / 4h</span>
                        </div>
                        <div className="h-3 bg-slate-800/10 rounded-full overflow-hidden border border-white/5">
                           <div className={`h-full transition-all duration-1000 ${progress > 90 ? 'bg-red-500 animate-pulse' : progress > 70 ? 'bg-yellow-500' : 'bg-emerald-500'}`} style={{ width: `${progress}%` }} />
                        </div>
                      </div>
                    )}

                    <button onClick={() => processPlate(c.plate, 'exit')} className="w-full py-4 rounded-2xl bg-indigo-600 text-white font-black text-sm uppercase tracking-widest shadow-xl shadow-indigo-600/30 hover:bg-indigo-500 active:scale-95 transition-all">TERMINAR Y COBRAR</button>
                  </div>
                );
              })}
           </div>
        )}

        {activeTab === "stats" && (
           <div className="space-y-8 animate-in zoom-in-95 pt-4 pb-20">
              <div className={`p-14 rounded-[3rem] border-2 text-center relative overflow-hidden ${isDarkMode ? 'bg-slate-900 border-indigo-500/10 shadow-2xl' : 'bg-white border-slate-100'}`}>
                 <div className="absolute top-0 right-0 w-48 h-48 bg-indigo-600/5 blur-[100px] rounded-full" />
                 <h2 className="text-xs font-black uppercase opacity-30 mb-6 tracking-[0.4em]">Balance General Diario</h2>
                 <div className="text-7xl font-black text-indigo-500 tracking-tighter shadow-none">${stats.today_income.toLocaleString()}</div>
                 <div className="flex justify-center gap-10 mt-10 border-t border-white/5 pt-10">
                    <div><p className="text-2xl font-black">{stats.today_entries}</p><p className="text-[10px] font-bold opacity-30 uppercase">Entradas</p></div>
                    <div><p className="text-2xl font-black">{stats.today_exits}</p><p className="text-[10px] font-bold opacity-30 uppercase">Salidas</p></div>
                 </div>
              </div>

              <div className="space-y-4">
                 <div className="flex items-center gap-3 px-2">
                   <div className="p-2 rounded-lg bg-indigo-500/10 text-indigo-500"><ListOrdered size={16}/></div>
                   <span className="text-xs font-black uppercase tracking-widest opacity-40 italic">Log Histórico Reciente</span>
                 </div>
                 <div className={`rounded-3xl border overflow-hidden ${isDarkMode ? 'bg-slate-900 border-white/5' : 'bg-white border-slate-200 shadow-sm'}`}>
                    <table className="w-full text-left text-xs border-collapse">
                       <thead className={`font-black border-b ${isDarkMode ? 'bg-white/5 border-white/5' : 'bg-slate-50 border-slate-100 uppercase'}`}>
                          <tr><th className="px-6 py-4">Hora</th><th className="px-6 py-4">Patente</th><th className="px-6 py-4">Tipo</th><th className="px-6 py-4 text-right">Monto</th></tr>
                       </thead>
                       <tbody className="font-medium">
                          {history.slice(0, 20).map((r, i) => (
                             <tr key={i} className={`border-b border-transparent hover:bg-indigo-500/5 transition-colors ${isDarkMode ? 'text-slate-400' : 'text-slate-600'}`}>
                                <td className="px-6 py-4 opacity-40">{r[0]?.split(' ')[1]}</td>
                                <td className="px-6 py-4 font-bold text-slate-100 tracking-wider tabular-nums">{r[1]}</td>
                                <td className="px-6 py-4"><span className={`px-2 py-0.5 rounded text-[10px] font-bold ${r[2]==='ENTRY'?'bg-emerald-500/10 text-emerald-500':'bg-indigo-500/10 text-indigo-500'}`}>{r[2]}</span></td>
                                <td className="px-6 py-4 font-black text-right text-indigo-400 opacity-60">${parseFloat(r[4]||0).toLocaleString()}</td>
                             </tr>
                          ))}
                       </tbody>
                    </table>
                 </div>
              </div>
           </div>
        )}
      </main>

      {/* Cam con Viewfinder Centrado */}
      {isCameraOpen && (
        <div className="fixed inset-0 z-[100] bg-black flex flex-col items-center justify-center p-6 bg-slate-950">
          <div className="w-full max-w-xl aspect-square relative rounded-[2.5rem] overflow-hidden shadow-[0_0_100px_rgba(0,0,0,0.5)] border-4 border-white/10">
             <Webcam audio={false} ref={webcamRef} screenshotFormat="image/jpeg" videoConstraints={{ facingMode: "environment" }} className="h-full w-full object-cover" />
             <div className="absolute inset-0 flex items-center justify-center">
                {/* Viewfinder Area */}
                <div className="w-[85%] aspect-[3/1.1] border-4 border-emerald-400 rounded-3xl relative animate-pulse shadow-[0_0_30px_rgba(52,211,153,0.3)]">
                   <div className="absolute top-1/2 left-0 w-full h-[1px] bg-emerald-400" />
                   <div className="absolute -top-12 left-1/2 -translate-x-1/2 bg-emerald-500 text-black px-4 py-1.5 rounded-full text-[10px] font-black uppercase tracking-widest">Enfoca Patente</div>
                   {/* Corners */}
                   <div className="absolute -top-1 -left-1 w-8 h-8 border-t-4 border-l-4 border-white rounded-tl-xl" />
                   <div className="absolute -bottom-1 -right-1 w-8 h-8 border-b-4 border-r-4 border-white rounded-br-xl" />
                </div>
             </div>
             {isAnalyzing && (
                <div className="absolute inset-0 bg-black/60 flex flex-col items-center justify-center gap-4">
                   <Activity className="text-white animate-spin" size={64}/>
                   <span className="text-white font-black text-xs uppercase tracking-[0.4em]">Analizando...</span>
                </div>
             )}
          </div>
          
          <div className="mt-12 flex gap-8 items-center">
             <button onClick={() => setIsCameraOpen(false)} className="w-16 h-16 rounded-3xl bg-white/5 text-white flex items-center justify-center active:scale-95 border border-white/10"><X size={32}/></button>
             <button onClick={capture} disabled={isAnalyzing} className="w-28 h-28 rounded-full border-8 border-indigo-600 flex items-center justify-center transition-all bg-white active:scale-90 shadow-[0_0_50px_rgba(99,102,241,0.3)]">
                <div className="w-18 h-18 rounded-full bg-indigo-600 flex items-center justify-center text-white"><Check size={48}/></div>
             </button>
             <button onClick={() => setShowManualInput(!showManualInput)} className={`w-16 h-16 rounded-3xl flex items-center justify-center transition-all border border-white/10 ${showManualInput ? 'bg-indigo-600 border-indigo-500' : 'bg-white/5'} text-white active:scale-95`}><Search size={32}/></button>
          </div>
          
          {showManualInput && (
             <div className="mt-10 w-full max-w-sm animate-in slide-in-from-bottom-5">
                <form onSubmit={(e) => { e.preventDefault(); processPlate(manualPlate.toUpperCase().trim(), cameraMode); setShowManualInput(false); setManualPlate(""); }} className="flex gap-2">
                   <input autoFocus type="text" value={manualPlate} onChange={e => setManualPlate(e.target.value)} placeholder="ABC-123" className="flex-1 bg-white p-6 rounded-2xl font-mono font-black text-2xl text-black outline-none uppercase tracking-widest shadow-2xl" />
                   <button type="submit" className="bg-indigo-600 text-white w-20 rounded-2xl flex items-center justify-center shadow-lg"><Check size={32}/></button>
                </form>
             </div>
          )}
        </div>
      )}

      <style jsx global>{`
        input::placeholder { color: #ccc; }
        .scrollbar-none::-webkit-scrollbar { display: none; }
      `}</style>
    </div>
  );
}
