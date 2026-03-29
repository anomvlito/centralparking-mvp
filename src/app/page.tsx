"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import Webcam from "react-webcam";
import { Search, LogOut, LogIn, X, Check, Car, Sun, Moon, Trash2, TrendingUp, Users, Activity, FileText } from "lucide-react";
import { format } from "date-fns";
import { type ParkedCar, calculateFee } from "../lib/parking";

const EVENT_FEES = [
  { id: "normal", name: "Tarifa Normal", amount: null },
  { id: "event_5k", name: "Matucana 100", amount: 5000 },
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
  
  const [actionResult, setActionResult] = useState<{
    plate: string;
    action: "entered" | "exited" | "deleted";
    fee?: number;
  } | null>(null);

  const webcamRef = useRef<Webcam>(null);

  const fetchData = async () => {
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "/api";
      const [carsRes, statsRes, historyRes] = await Promise.all([
        fetch(`${apiUrl}/cars`),
        fetch(`${apiUrl}/stats`),
        fetch(`${apiUrl}/history`)
      ]);
      if (carsRes.ok) setCars(await carsRes.json());
      if (statsRes.ok) setStats(await statsRes.json());
      if (historyRes.ok) setHistory(await historyRes.json());
    } catch (err) {
      console.warn("API Sync failed");
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 2000);
    const theme = localStorage.getItem("theme");
    if (theme === "light") setIsDarkMode(false);
    return () => clearInterval(interval);
  }, []);

  const toggleTheme = () => {
    const next = !isDarkMode;
    setIsDarkMode(next);
    localStorage.setItem("theme", next ? "dark" : "light");
  };

  const processPlate = async (p: string, mode: "entry" | "exit") => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "/api";
    try {
      if (mode === "entry") {
        if (cars[p]) { alert("El auto ya está dentro"); return; }
        await fetch(`${apiUrl}/entry`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ plate: p, isEvent: selectedEvent.amount !== null, eventFee: selectedEvent.amount })
        });
        setActionResult({ plate: p, action: "entered" });
      } else {
        const car = cars[p];
        if (!car) { alert("Patente no encontrada"); return; }
        const fee = calculateFee(car.entryTime, Date.now(), car.isEvent, car.eventFee);
        await fetch(`${apiUrl}/exit/${p}?fee=${fee}`, { method: "POST" });
        setActionResult({ plate: p, action: "exited", fee });
      }
      fetchData();
    } catch (err) {
      alert("Error de conexión");
    } finally {
      setIsCameraOpen(false);
      setTimeout(() => setActionResult(null), 5000);
    }
  };

  const captureCapture = useCallback(async () => {
    if (!webcamRef.current) return;
    setIsAnalyzing(true);
    const img = webcamRef.current.getScreenshot();
    if (!img) { setIsAnalyzing(false); return; }
    try {
      const blob = await (await fetch(img)).blob();
      const fd = new FormData();
      fd.append("image", blob, 'cap.jpg');
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "/api";
      const res = await fetch(`${apiUrl}/detect`, { method: "POST", body: fd });
      const data = await res.json();
      if (data.plate && data.plate !== "None") processPlate(data.plate, cameraMode);
      else alert("No se pudo leer la patente. Intenta centrarla mejor.");
    } catch (err) {
      alert("Error servidor AI");
    } finally {
      setIsAnalyzing(false);
    }
  }, [webcamRef, cameraMode, processPlate]);

  const deleteCar = async (p: string) => {
    if (!confirm(`¿Eliminar ${p}?`)) return;
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "/api";
      await fetch(`${apiUrl}/cars/${p}`, { method: "DELETE" });
      fetchData();
    } catch (err) {}
  };

  return (
    <div className={`min-h-screen font-sans ${isDarkMode ? 'bg-slate-950 text-white' : 'bg-slate-50 text-slate-800'}`}>
      
      {/* Header */}
      <header className={`px-6 py-4 flex items-center justify-between border-b ${isDarkMode ? 'bg-slate-900 border-white/5' : 'bg-white border-slate-200'}`}>
        <div className="flex items-center gap-2">
           <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center text-white"><Car size={18} /></div>
           <h1 className="font-black text-lg">CParking MVP</h1>
        </div>
        <div className="flex bg-slate-800/20 p-1 rounded-xl gap-0.5 border border-white/5">
           {["actions", "monitor", "stats"].map(t => (
             <button key={t} onClick={() => setActiveTab(t as any)} className={`px-4 py-1.5 rounded-lg font-black text-[10px] uppercase transition-all ${activeTab === t ? 'bg-indigo-600 text-white shadow-xl' : 'opacity-40 hover:opacity-80'}`}>
               {t === 'actions' ? 'Control' : t === 'monitor' ? 'Monitor' : 'Cierre'}
             </button>
           ))}
        </div>
        <button onClick={toggleTheme} className="p-2.5 rounded-xl transition-all border border-transparent hover:border-white/10 active:scale-90">
           {isDarkMode ? <Sun size={20} className="text-yellow-400" /> : <Moon size={20} className="text-slate-500" />}
        </button>
      </header>

      <main className="max-w-4xl mx-auto p-4 pt-8">
        
        {activeTab === "actions" && (
          <div className="space-y-6 animate-in fade-in duration-500">
            
            {/* Main Action Buttons */}
            <div className="grid grid-cols-2 gap-4">
               <button onClick={() => { setCameraMode("entry"); setIsCameraOpen(true); }} className={`p-10 rounded-[2rem] border-2 flex flex-col items-center gap-6 transition-all active:scale-95 ${isDarkMode ? 'bg-emerald-500/10 border-emerald-500/20 shadow-emerald-500/5 shadow-2xl' : 'bg-emerald-50 border-emerald-100'}`}>
                 <div className="p-5 rounded-full bg-emerald-500 text-white"><LogIn size={32} /></div>
                 <span className="font-black text-xl tracking-tight">ENTRADA</span>
               </button>
               <button onClick={() => { setCameraMode("exit"); setIsCameraOpen(true); }} className={`p-10 rounded-[2rem] border-2 flex flex-col items-center gap-6 transition-all active:scale-95 ${isDarkMode ? 'bg-indigo-500/10 border-indigo-500/20 shadow-indigo-500/5 shadow-2xl' : 'bg-indigo-50 border-indigo-100'}`}>
                 <div className="p-5 rounded-full bg-indigo-500 text-white"><LogOut size={32} /></div>
                 <span className="font-black text-xl tracking-tight">SALIDA</span>
               </button>
            </div>

            {/* Visual Feedback for operations */}
            {actionResult && (
              <div className={`p-6 rounded-3xl border-2 flex items-center justify-between scale-in-center ${actionResult.action === 'entered' ? 'bg-emerald-500/5 border-emerald-500/40' : 'bg-indigo-500/5 border-indigo-500/40'}`}>
                <div className="flex items-center gap-4">
                  <div className="text-4xl font-black font-mono tracking-tighter italic">{actionResult.plate}</div>
                  <div className="text-[10px] uppercase font-bold tracking-widest bg-white/10 px-2 py-1 rounded">{actionResult.action === 'entered' ? 'Ingreso Registrado' : 'Cobro Finalizado'}</div>
                </div>
                {actionResult.fee !== undefined && <div className="text-4xl font-black">${actionResult.fee.toLocaleString("es-CL")}</div>}
              </div>
            )}

            {/* Quick Stats & Config */}
            <div className="grid grid-cols-1 md:grid-cols-12 gap-6">
                <div className={`md:col-span-8 p-8 rounded-[2rem] border ${isDarkMode ? 'bg-slate-900 border-white/5' : 'bg-white border-slate-200'}`}>
                  <h3 className="text-[10px] font-black uppercase tracking-widest opacity-40 mb-6">Tarifa Seleccionada</h3>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                    {EVENT_FEES.map(f => (
                      <button key={f.id} onClick={() => setSelectedEvent(f)} className={`py-4 px-3 rounded-2xl text-[10px] font-bold border-2 transition-all ${selectedEvent.id === f.id ? 'bg-indigo-600 border-indigo-500 text-white shadow-xl' : 'opacity-40 hover:opacity-100 border-transparent'}`}>
                        {f.name} {f.amount ? `($${f.amount/1000}k)` : ''}
                      </button>
                    ))}
                  </div>
                </div>
                <div className={`md:col-span-4 p-8 rounded-[2rem] border flex flex-col justify-center text-center ${isDarkMode ? 'bg-slate-900 border-white/5' : 'bg-white border-slate-200 shadow-sm'}`}>
                  <p className="text-4xl font-black mb-1 italic text-indigo-500">{stats.parked_now}</p>
                  <p className="text-[10px] font-bold uppercase opacity-40 tracking-widest">Vehículos Hoy</p>
                </div>
            </div>
            
            {/* Simple Monitor List */}
            <div className="space-y-4">
               <h3 className="text-[10px] font-black uppercase tracking-[0.4em] opacity-30 px-2">Actividad Reciente</h3>
               <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                  {Object.values(cars).reverse().slice(0, 6).map(car => (
                    <div key={car.plate} className={`p-4 rounded-2xl flex justify-between items-center group ${isDarkMode ? 'bg-slate-900/50 border border-white/5' : 'bg-white border border-slate-100 shadow-sm'}`}>
                       <span className="font-mono font-bold tracking-widest">{car.plate}</span>
                       <button onClick={() => deleteCar(car.plate)} className="p-1.5 rounded-lg opacity-0 group-hover:opacity-100 text-red-500/40 hover:bg-red-500/10 hover:text-red-500 transition-all"><Trash2 size={14}/></button>
                    </div>
                  ))}
               </div>
            </div>
          </div>
        )}

        {activeTab === "monitor" && (
           <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 animate-in slide-in-from-right-10 pt-4 pb-20">
              {Object.values(cars).map((car) => {
                const mins = Math.floor((Date.now() - car.entryTime) / 60000);
                const fee = calculateFee(car.entryTime, Date.now(), car.isEvent, car.eventFee);
                return (
                  <div key={car.plate} className={`p-8 rounded-[2rem] border-2 ${isDarkMode ? 'bg-slate-900 border-white/5 shadow-2xl shadow-indigo-500/5' : 'bg-white border-slate-200'}`}>
                    <div className="flex justify-between items-center mb-6">
                      <div className="font-black text-3xl font-mono tracking-tighter italic">{car.plate}</div>
                      <div className={`px-2 py-0.5 rounded text-[8px] font-black uppercase ${car.isEvent ? 'bg-purple-600' : 'bg-indigo-600'} text-white`}>{car.isEvent ? "Evento" : "Normal"}</div>
                    </div>
                    <div className="space-y-6">
                      <div className="flex justify-between">
                         <div><p className="text-[9px] uppercase font-bold opacity-30 mb-1">Entrada</p><p className="font-black text-xl">{format(car.entryTime, "HH:mm")}</p></div>
                         <div className="text-right"><p className="text-[9px] uppercase font-bold opacity-30 mb-1">Monto Hoy</p><p className="font-black text-2xl text-indigo-500 tabular-nums">${fee.toLocaleString("es-CL")}</p></div>
                      </div>
                      <button onClick={() => processPlate(car.plate, "exit")} className="w-full py-4 rounded-2xl bg-indigo-600 text-white font-black text-xs tracking-widest uppercase shadow-xl shadow-indigo-500/20 active:scale-95 transition-all">TERMINAR ESTADÍA</button>
                    </div>
                  </div>
                );
              })}
           </div>
        )}

        {activeTab === "stats" && (
           <div className="animate-in zoom-in-95 duration-500 space-y-12 pb-20">
              {/* Daily Revenue Hero */}
              <div className={`p-16 rounded-[4rem] text-center border-2 border-indigo-500/20 shadow-2xl relative overflow-hidden ${isDarkMode ? 'bg-slate-900' : 'bg-white'}`}>
                 <div className="absolute top-0 right-10 text-[10rem] font-black opacity-5 italic select-none">$</div>
                 <h2 className="text-[10px] font-black uppercase tracking-[0.5em] opacity-30 mb-8 relative z-10">Balance de la Jornada</h2>
                 <div className="text-8xl font-black italic tracking-tighter text-indigo-500 mb-10 tabular-nums relative z-10">${stats.today_income.toLocaleString("es-CL")}</div>
                 <div className="grid grid-cols-2 gap-8 border-t border-dashed border-white/10 pt-10 relative z-10">
                    <div><p className="text-3xl font-black">{stats.today_entries}</p><p className="text-[10px] font-bold opacity-30 uppercase mt-1 tracking-widest">Ingresos Totales</p></div>
                    <div><p className="text-3xl font-black">{stats.today_exits}</p><p className="text-[10px] font-bold opacity-30 uppercase mt-1 tracking-widest">Salidas Cimentadas</p></div>
                 </div>
              </div>

              {/* CSV Records Table */}
              <div className="space-y-4">
                 <div className="flex items-center gap-3 px-2">
                    <FileText className="text-indigo-500" size={18} />
                    <h3 className="text-xs font-black uppercase tracking-[0.3em] opacity-40 italic">Registros en history.csv (Últimos 50)</h3>
                 </div>
                 <div className={`rounded-3xl border overflow-hidden ${isDarkMode ? 'bg-slate-900 border-white/5' : 'bg-white border-slate-200 shadow-sm'}`}>
                    <div className="overflow-x-auto">
                       <table className="w-full text-left text-[11px] border-collapse">
                          <thead className={`font-black uppercase tracking-tighter border-b ${isDarkMode ? 'bg-white/5 border-white/5' : 'bg-slate-50 border-slate-100'}`}>
                             <tr>
                                <th className="px-6 py-4">Hora</th>
                                <th className="px-6 py-4">Patente</th>
                                <th className="px-6 py-4">Acción</th>
                                <th className="px-6 py-4">Cobro</th>
                                <th className="px-6 py-4">AI %</th>
                             </tr>
                          </thead>
                          <tbody className="font-mono">
                             {history.map((row, i) => (
                               <tr key={i} className={`border-b ${isDarkMode ? 'border-white/5 hover:bg-white/5' : 'border-slate-100 hover:bg-slate-50'}`}>
                                  <td className="px-6 py-3 opacity-40">{row[0]?.split(' ')[1]}</td>
                                  <td className="px-6 py-3 font-black text-sm tracking-tighter">{row[1]}</td>
                                  <td className="px-6 py-3">
                                     <span className={`px-2 py-0.5 rounded-[4px] font-black text-[9px] ${row[2] === 'ENTRY' ? 'bg-emerald-500/20 text-emerald-400' : row[2] === 'EXIT' ? 'bg-indigo-500/20 text-indigo-400' : 'bg-red-500/20 text-red-400'}`}>
                                        {row[2]}
                                     </span>
                                  </td>
                                  <td className="px-6 py-3 font-bold">${parseFloat(row[4] || 0).toLocaleString("es-CL")}</td>
                                  <td className="px-6 py-3 opacity-60 italic">{row[5] ? `${(row[5])}` : '-'}</td>
                               </tr>
                             ))}
                          </tbody>
                       </table>
                    </div>
                 </div>
              </div>
           </div>
        )}
      </main>

      {/* Camera Interface */}
      {isCameraOpen && (
        <div className="fixed inset-0 z-[100] bg-black flex flex-col select-none overflow-hidden">
          <div className="p-8 pb-12 flex justify-between items-start absolute top-0 inset-x-0 z-20 bg-gradient-to-b from-black via-black/80 to-transparent">
             <div className="flex flex-col gap-1">
                <h2 className="text-white font-black text-2xl tracking-tighter uppercase italic">{cameraMode === "entry" ? "Ingresa Vehículo" : "Cobra Salida"}</h2>
                <div className="flex items-center gap-2 opacity-50">
                   <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                   <p className="text-white text-[8px] font-black uppercase tracking-widest">Escaneando...</p>
                </div>
             </div>
             <button onClick={() => setIsCameraOpen(false)} className="w-14 h-14 bg-white/10 rounded-2xl flex items-center justify-center text-white border border-white/20 active:scale-90 transition-all"><X size={32} /></button>
          </div>
          
          <div className="flex-1 relative flex items-center justify-center bg-slate-950">
             <Webcam audio={false} ref={webcamRef} screenshotFormat="image/jpeg" videoConstraints={{ facingMode: "environment" }} className="h-full w-full object-cover" />
             
             {/* Center Frame */}
             <div className="absolute inset-0 flex items-center justify-center p-12 pointer-events-none">
                <div className="w-full max-w-sm aspect-[3/1.2] border-4 border-emerald-400 rounded-3xl shadow-[0_0_0_2000px_rgba(0,0,0,0.7)] relative">
                   <div className="absolute top-1/2 left-0 w-full h-[1px] bg-emerald-400 animate-pulse" />
                   <div className="absolute -top-[1.2rem] left-1/2 -translate-x-1/2 px-4 py-1 rounded-full bg-emerald-400 text-black text-[9px] font-black uppercase tracking-widest whitespace-nowrap">Cuadrar Patente</div>
                   
                   {/* Corner Accents */}
                   <div className="absolute -top-1 -left-1 w-8 h-8 border-t-4 border-l-4 border-white rounded-tl-xl" />
                   <div className="absolute -bottom-1 -right-1 w-8 h-8 border-b-4 border-r-4 border-white rounded-br-xl" />
                </div>
             </div>
             
             <button onClick={() => setShowManualInput(!showManualInput)} className={`absolute bottom-32 right-10 w-14 h-14 rounded-2xl flex items-center justify-center border border-white/20 ${showManualInput ? 'bg-indigo-600' : 'bg-black/60'} text-white shadow-2xl transition-all`}><Search size={24} /></button>

             {showManualInput && (
              <div className="absolute bottom-52 inset-x-10 px-4 z-30 animate-in slide-in-from-bottom-10">
                <form onSubmit={(e) => { e.preventDefault(); processPlate(manualPlate.toUpperCase().trim(), cameraMode); setShowManualInput(false); setManualPlate(""); }} className="bg-white p-2 rounded-[2rem] flex shadow-2xl scale-110">
                  <input autoFocus type="text" value={manualPlate} onChange={e => setManualPlate(e.target.value)} placeholder="PATENTE" className="flex-1 bg-slate-100 rounded-[1.5rem] px-6 py-4 font-mono font-black text-xl uppercase tracking-[0.2em] text-slate-900 outline-none" />
                  <button type="submit" className="bg-slate-900 text-white w-20 rounded-[1.5rem] flex items-center justify-center shadow-lg"><Check size={32} /></button>
                </form>
              </div>
            )}
          </div>

          <div className="h-44 bg-slate-950 flex flex-col items-center justify-center pb-12">
            <button onClick={captureCapture} disabled={isAnalyzing} className="group relative w-24 h-24 rounded-full border-4 border-white p-1 flex items-center justify-center active:scale-95 transition-all outline-none">
               <div className={`w-20 h-20 rounded-full flex items-center justify-center transition-all ${isAnalyzing ? 'bg-indigo-900 border-indigo-400' : 'bg-white shadow-[0_0_50px_rgba(255,255,255,0.4)]'}`}>
                  {isAnalyzing ? <Activity className="text-indigo-300 animate-pulse" size={28} /> : <div className="w-18 h-18 rounded-full border border-slate-200" />}
               </div>
            </button>
          </div>
        </div>
      )}

      <style jsx global>{`
        .scale-in-center { animation: scale-in-center 0.6s cubic-bezier(0.25, 0.46, 0.45, 0.94) both; }
        @keyframes scale-in-center { 0% { transform: scale(0.5); opacity: 0; } 100% { transform: scale(1); opacity: 1; } }
      `}</style>
    </div>
  );
}
