"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import Webcam from "react-webcam";
import { Search, LogOut, LogIn, X, Check, Car, Sun, Moon, Trash2, TrendingUp, Users, Activity, ListOrdered } from "lucide-react";
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
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "/api";
      const [c, s, h] = await Promise.all([
        fetch(`${apiUrl}/cars`),
        fetch(`${apiUrl}/stats`),
        fetch(`${apiUrl}/history`)
      ]);
      if (c.ok) setCars(await c.json());
      if (s.ok) setStats(await s.json());
      if (h.ok) setHistory(await h.json());
    } catch (e) {
      console.warn("Offline sync");
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
        if (cars[p]) { alert("Ya registrado"); return; }
        await fetch(`${api}/entry`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ plate: p, isEvent: selectedEvent.amount !== null, eventFee: selectedEvent.amount })
        });
        setActionResult({ plate: p, action: "entrada" });
      } else {
        const car = cars[p];
        if (!car) { alert("No encontrado"); return; }
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
      else alert("Patente no detectada");
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
    <div className={`min-h-screen font-sans antialiased ${isDarkMode ? 'bg-slate-950 text-slate-200' : 'bg-slate-50 text-slate-900'}`}>
      
      {/* Header Compacto */}
      <header className={`px-6 py-4 flex items-center justify-between border-b ${isDarkMode ? 'bg-slate-900/80 border-white/5' : 'bg-white border-slate-200 shadow-sm'}`}>
        <div className="flex items-center gap-2">
           <div className="p-2 rounded-lg bg-indigo-600 text-white"><Car size={16}/></div>
           <span className="font-bold tracking-tight text-lg underline decoration-indigo-500 decoration-2 underline-offset-4">PARKING</span>
        </div>
        <div className="flex bg-slate-800/10 p-1 rounded-lg border border-white/5">
           {["actions", "monitor", "stats"].map(t => (
             <button key={t} onClick={() => setActiveTab(t as any)} className={`px-3 py-1 rounded-md text-[10px] font-bold uppercase ${activeTab === t ? 'bg-indigo-600 text-white' : 'opacity-40'}`}>
               {t === 'actions' ? 'Control' : t === 'monitor' ? 'Monitor' : 'Cierre'}
             </button>
           ))}
        </div>
        <button onClick={toggleTheme} className="p-2 opacity-60 hover:opacity-100">{isDarkMode ? <Sun size={18}/> : <Moon size={18}/>}</button>
      </header>

      <main className="max-w-2xl mx-auto p-4 space-y-6">
        
        {activeTab === "actions" && (
          <div className="space-y-6 animate-in fade-in duration-300">
            
            {/* Buttons Row - Clean & Grid */}
            <div className="grid grid-cols-2 gap-4">
               <button onClick={() => { setCameraMode("entry"); setIsCameraOpen(true); }} className={`p-6 rounded-2xl border-2 flex flex-col items-center gap-4 active:scale-95 transition-all ${isDarkMode ? 'bg-emerald-500/5 border-emerald-500/20' : 'bg-emerald-50 border-emerald-100'}`}>
                 <div className="p-3 uppercase font-black text-emerald-500 tracking-widest text-[10px]">Entrada</div>
                 <LogIn size={24} className="text-emerald-500" />
               </button>
               <button onClick={() => { setCameraMode("exit"); setIsCameraOpen(true); }} className={`p-6 rounded-2xl border-2 flex flex-col items-center gap-4 active:scale-95 transition-all ${isDarkMode ? 'bg-indigo-500/5 border-indigo-500/20' : 'bg-indigo-50 border-indigo-100'}`}>
                 <div className="p-3 uppercase font-black text-indigo-500 tracking-widest text-[10px]">Salida</div>
                 <LogOut size={24} className="text-indigo-500" />
               </button>
            </div>

            {actionResult && (
              <div className={`p-5 rounded-xl border flex items-center justify-between font-bold ${actionResult.action === 'entrada' ? 'bg-emerald-500/10 border-emerald-500/30' : 'bg-indigo-500/10 border-indigo-500/30'}`}>
                <div className="flex items-center gap-3">
                  <span className="text-2xl font-mono tracking-widest">{actionResult.plate}</span>
                  <span className="text-[10px] uppercase opacity-40">{actionResult.action} OK</span>
                </div>
                {actionResult.fee !== undefined && <span className="text-2xl font-black">${actionResult.fee.toLocaleString()}</span>}
              </div>
            )}

            {/* Quick Stats Grid */}
            <div className="grid grid-cols-3 gap-3">
               <div className={`p-4 rounded-xl border ${isDarkMode ? 'bg-slate-900 border-white/5' : 'bg-white border-slate-100 shadow-sm'}`}>
                  <div className="text-lg font-black">${stats.today_income.toLocaleString()}</div>
                  <div className="text-[8px] uppercase font-bold opacity-30">Hoy</div>
               </div>
               <div className={`p-4 rounded-xl border ${isDarkMode ? 'bg-slate-900 border-white/5' : 'bg-white border-slate-100 shadow-sm'}`}>
                  <div className="text-lg font-black">{stats.parked_now}</div>
                  <div className="text-[8px] uppercase font-bold opacity-30">Total</div>
               </div>
               <div className={`p-4 rounded-xl border ${isDarkMode ? 'bg-slate-900 border-white/5' : 'bg-white border-slate-100 shadow-sm'}`}>
                 <div className="text-lg font-black">{stats.today_entries}</div>
                 <div className="text-[8px] uppercase font-bold opacity-30">Ingresos</div>
               </div>
            </div>

            {/* Config Minimal */}
            <div className={`p-4 rounded-xl border ${isDarkMode ? 'bg-slate-900 border-white/5' : 'bg-white border-slate-200'}`}>
               <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-none">
                  {EVENT_FEES.map(f => (
                    <button key={f.id} onClick={() => setSelectedEvent(f)} className={`whitespace-nowrap px-4 py-2 rounded-lg text-[9px] font-black uppercase border-2 transition-all ${selectedEvent.id === f.id ? 'bg-indigo-600 border-indigo-500 text-white' : 'border-transparent opacity-40 hover:opacity-100'}`}>
                      {f.name} {f.amount ? `($${f.amount/1000}k)` : ''}
                    </button>
                  ))}
               </div>
            </div>

            {/* Simple Small Recent */}
            <div className="space-y-2">
               <div className="flex items-center justify-between px-1">
                  <h3 className="text-[9px] font-black uppercase opacity-30 tracking-widest">En Vigilancia</h3>
                  <Activity size={12} className="text-emerald-500"/>
               </div>
               <div className="grid grid-cols-2 gap-2">
                  {Object.values(cars).reverse().slice(0, 4).map(c => (
                    <div key={c.plate} className={`p-3 rounded-xl border flex justify-between items-center group ${isDarkMode ? 'bg-slate-900/50 border-white/5' : 'bg-white border-slate-100 shadow-sm'}`}>
                       <span className="font-mono font-bold text-sm tracking-widest tabular-nums">{c.plate}</span>
                       <button onClick={() => deletePlate(c.plate)} className="p-1 opacity-0 group-hover:opacity-100 text-red-500/40 hover:text-red-500"><Trash2 size={12}/></button>
                    </div>
                  ))}
               </div>
            </div>

          </div>
        )}

        {activeTab === "monitor" && (
           <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 animate-in slide-in-from-right-4 pt-2 pb-10">
              {Object.values(cars).map(c => {
                const f = calculateFee(c.entryTime, Date.now(), c.isEvent, c.eventFee);
                return (
                  <div key={c.plate} className={`p-5 rounded-2xl border ${isDarkMode ? 'bg-slate-900 border-white/10' : 'bg-white border-slate-200 shadow-md'}`}>
                    <div className="flex justify-between items-center mb-4">
                       <span className="font-black text-2xl font-mono tracking-tight tabular-nums">{c.plate}</span>
                       <span className={`text-[8px] font-black uppercase px-2 py-0.5 rounded ${c.isEvent ? 'bg-purple-600' : 'bg-indigo-600'} text-white`}>{c.isEvent ? 'E' : 'N'}</span>
                    </div>
                    <div className="flex justify-between items-center mb-6">
                       <div><p className="text-[8px] font-bold opacity-30 uppercase tracking-tighter">Entrada {format(c.entryTime, 'HH:mm')}</p></div>
                       <div className="text-right text-indigo-500 font-bold tracking-tight">${f.toLocaleString()}</div>
                    </div>
                    <button onClick={() => processPlate(c.plate, 'exit')} className="w-full py-3 rounded-xl bg-indigo-600 text-white font-black text-[10px] uppercase hover:bg-indigo-500 active:scale-95">Cobrar</button>
                  </div>
                );
              })}
           </div>
        )}

        {activeTab === "stats" && (
           <div className="space-y-6 animate-in zoom-in-95 pt-4 pb-20">
              <div className={`p-10 rounded-3xl border-2 text-center ${isDarkMode ? 'bg-slate-900 border-indigo-500/10 shadow-2xl' : 'bg-white border-slate-100'}`}>
                 <h2 className="text-[9px] font-black uppercase opacity-30 mb-4 tracking-widest">Caja de Hoy</h2>
                 <div className="text-6xl font-black text-indigo-500 tracking-tighter tabular-nums">${stats.today_income.toLocaleString()}</div>
              </div>

              <div className="space-y-3">
                 <div className="flex items-center gap-2 px-1">
                   <ListOrdered size={14} className="text-indigo-500"/>
                   <span className="text-[9px] font-black uppercase opacity-30 tracking-widest">Historial CSV</span>
                 </div>
                 <div className={`rounded-2xl border overflow-hidden ${isDarkMode ? 'bg-slate-900 border-white/5' : 'bg-white border-slate-200 shadow-sm'}`}>
                    <table className="w-full text-left text-[10px] border-collapse">
                       <thead className={`font-bold border-b ${isDarkMode ? 'bg-white/5 border-white/5' : 'bg-slate-50 border-slate-100 uppercase'}`}>
                          <tr><th className="px-5 py-3">Hora</th><th className="px-5 py-3">Patente</th><th className="px-5 py-3">Evento</th><th className="px-5 py-3">Cobro</th></tr>
                       </thead>
                       <tbody className="font-mono">
                          {history.slice(0, 15).map((r, i) => (
                             <tr key={i} className={`border-b border-transparent hover:bg-indigo-500/5 ${isDarkMode ? 'text-slate-400' : 'text-slate-600'}`}>
                                <td className="px-5 py-2.5 opacity-50 tabular-nums">{r[0]?.split(' ')[1]}</td>
                                <td className="px-5 py-2.5 font-bold text-slate-200 tracking-tighter tabular-nums">{r[1]}</td>
                                <td className="px-5 py-2.5"><span className={r[2]==='ENTRY'?'text-emerald-500':'text-indigo-500'}>{r[2]}</span></td>
                                <td className="px-5 py-2.5 font-bold text-indigo-400">${parseFloat(r[4]||0).toLocaleString()}</td>
                             </tr>
                          ))}
                       </tbody>
                    </table>
                 </div>
              </div>
           </div>
        )}
      </main>

      {/* Cam Simple */}
      {isCameraOpen && (
        <div className="fixed inset-0 z-[100] bg-black flex flex-col items-center justify-center p-6 sm:p-10">
          <div className="w-full max-w-lg aspect-square relative rounded-3xl overflow-hidden shadow-2xl">
             <Webcam audio={false} ref={webcamRef} screenshotFormat="image/jpeg" videoConstraints={{ facingMode: "environment" }} className="h-full w-full object-cover" />
             <div className="absolute inset-0 border-[1.5rem] border-black/70 flex items-center justify-center">
                <div className="w-full aspect-[3/1.2] border-4 border-emerald-400 rounded-2xl relative shadow-[0_0_20px_emerald]">
                   <div className="absolute -top-10 left-1/2 -translate-x-1/2 bg-emerald-400 text-black px-3 py-1 rounded-full text-[8px] font-black uppercase tracking-widest">Encuadra aquí</div>
                </div>
             </div>
             {isAnalyzing && <div className="absolute inset-0 bg-black/40 flex items-center justify-center"><Activity className="text-white animate-pulse" size={48}/></div>}
          </div>
          <div className="mt-8 flex gap-6 items-center">
             <button onClick={() => setIsCameraOpen(false)} className="w-14 h-14 rounded-2xl bg-white/10 text-white flex items-center justify-center active:scale-90"><X size={28}/></button>
             <button onClick={capture} disabled={isAnalyzing} className="w-24 h-24 rounded-full border-4 border-white flex items-center justify-center transition-all bg-white active:scale-95 shadow-xl"><Check size={48} className="text-black"/></button>
             <button onClick={() => setShowManualInput(!showManualInput)} className={`w-14 h-14 rounded-2xl flex items-center justify-center transition-all ${showManualInput ? 'bg-indigo-600' : 'bg-white/10'} text-white active:scale-90`}><Search size={28}/></button>
          </div>
          {showManualInput && (
             <div className="mt-8 w-full max-w-sm flex gap-2">
                <input autoFocus type="text" value={manualPlate} onChange={e => setManualPlate(e.target.value)} placeholder="ABCD-12" className="flex-1 bg-white p-4 rounded-xl font-mono font-black text-xl text-black outline-none uppercase tracking-widest" />
                <button onClick={() => { processPlate(manualPlate.toUpperCase().trim(), cameraMode); setShowManualInput(false); setManualPlate(""); }} className="bg-indigo-600 text-white px-6 rounded-xl border-none"><Check size={32}/></button>
             </div>
          )}
        </div>
      )}

      <style jsx global>{`
        input::placeholder { color: #999; }
        .scrollbar-none::-webkit-scrollbar { display: none; }
      `}</style>
    </div>
  );
}
