"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import Webcam from "react-webcam";
import { Camera, Search, LogOut, LogIn, CalendarDays, X, Check, Car, History, Sun, Moon, MapPin, MousePointer2, Clock, DollarSign, Activity, Trash2, TrendingUp, Users, ZoomIn, ZoomOut, AlertCircle } from "lucide-react";
import { format } from "date-fns";
import { type ParkedCar, calculateFee } from "../lib/parking";

const EVENT_FEES = [
  { id: "normal", name: "Tarifa Normal", amount: null },
  { id: "event_5k", name: "Matucana 100", amount: 5000 },
  { id: "event_8k", name: "Evento Premium", amount: 8000 },
  { id: "event_10k", name: "Evento VIP", amount: 10000 },
];

export default function ParkingMVP() {
  const [cars, setCars] = useState<Record<string, ParkedCar>>({});
  const [stats, setStats] = useState({ today_income: 0, today_entries: 0, today_exits: 0, parked_now: 0 });
  const [selectedEvent, setSelectedEvent] = useState(EVENT_FEES[0]);
  const [isCameraOpen, setIsCameraOpen] = useState(false);
  const [cameraMode, setCameraMode] = useState<"entry" | "exit">("entry");
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [manualPlate, setManualPlate] = useState("");
  const [showManualInput, setShowManualInput] = useState(false);
  const [isDarkMode, setIsDarkMode] = useState(true);
  const [activeTab, setActiveTab] = useState<"actions" | "monitor" | "stats">("actions");
  
  const [zoomLevel, setZoomLevel] = useState(1);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [actionResult, setActionResult] = useState<{
    plate: string;
    action: "entered" | "exited" | "deleted";
    fee?: number;
    time?: string;
  } | null>(null);

  const webcamRef = useRef<Webcam>(null);

  const fetchData = async () => {
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "/api";
      const [carsRes, statsRes] = await Promise.all([
        fetch(`${apiUrl}/cars`),
        fetch(`${apiUrl}/stats`)
      ]);
      if (carsRes.ok) setCars(await carsRes.json());
      if (statsRes.ok) setStats(await statsRes.json());
    } catch (err) {
      console.warn("Sync failed");
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000);
    const savedTheme = localStorage.getItem("theme");
    if (savedTheme === "light") setIsDarkMode(false);
    return () => clearInterval(interval);
  }, []);

  const toggleTheme = () => {
    const newTheme = !isDarkMode;
    setIsDarkMode(newTheme);
    localStorage.setItem("theme", newTheme ? "dark" : "light");
  };

  const handleManualEntry = (e: React.FormEvent) => {
    e.preventDefault();
    if (!manualPlate) return;
    const cleanPlate = manualPlate.toUpperCase().trim();
    processPlate(cleanPlate, cameraMode);
    setShowManualInput(false);
    setManualPlate("");
  };

  const deleteCar = async (plate: string) => {
    if (!confirm(`¿Eliminar ${plate}?`)) return;
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "/api";
    try {
      const res = await fetch(`${apiUrl}/cars/${plate}`, { method: "DELETE" });
      if (res.ok) {
        setActionResult({ plate, action: "deleted" });
        setTimeout(() => setActionResult(null), 3000);
        fetchData();
      }
    } catch (err) {
      alert("Error");
    }
  };

  const processPlate = async (plateNumber: string, mode: "entry" | "exit") => {
    const now = Date.now();
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "/api";
    try {
      if (mode === "entry") {
        if (cars[plateNumber]) {
          alert("¡Ese auto ya está registrado!");
          setIsCameraOpen(false);
          return;
        }
        await fetch(`${apiUrl}/entry`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ plate: plateNumber, isEvent: selectedEvent.amount !== null, eventFee: selectedEvent.amount })
        });
        setActionResult({ plate: plateNumber, action: "entered", time: format(now, "HH:mm") });
      } else {
        const existingCar = cars[plateNumber];
        if (!existingCar) {
          alert("Auto no encontrado.");
          setIsCameraOpen(false);
          return;
        }
        const fee = calculateFee(existingCar.entryTime, now, existingCar.isEvent, existingCar.eventFee);
        await fetch(`${apiUrl}/exit/${plateNumber}?fee=${fee}`, { method: "POST" });
        setActionResult({ plate: plateNumber, action: "exited", fee, time: format(now - existingCar.entryTime, "HH:mm") });
      }
      fetchData();
    } catch (err) {
      alert("Error de conexión local.");
    } finally {
      setIsCameraOpen(false);
      setTimeout(() => setActionResult(null), 8000);
    }
  };

  const captureAndAnalyze = useCallback(async () => {
    if (!webcamRef.current) return;
    setIsAnalyzing(true);
    const video = webcamRef.current.video;
    if (!video) return;

    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const sw = video.videoWidth / zoomLevel;
    const sh = video.videoHeight / zoomLevel;
    const sx = (video.videoWidth - sw) / 2;
    const sy = (video.videoHeight - sh) / 2;
    ctx.drawImage(video, sx, sy, sw, sh, 0, 0, canvas.width, canvas.height);
    canvas.toBlob(async (blob) => {
      if (!blob) return;
      const formData = new FormData();
      formData.append("image", blob, "capture.jpg");
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || "/api";
        const response = await fetch(`${apiUrl}/detect`, { method: "POST", body: formData });
        const data = await response.json();
        if (data.plate && data.plate !== "None") processPlate(data.plate, cameraMode);
        else alert("No se detectó patente con este zoom.");
      } catch (err) {
        alert("Error de motor AI.");
      } finally {
        setIsAnalyzing(false);
      }
    }, "image/jpeg", 0.95);
  }, [webcamRef, cameraMode, zoomLevel, processPlate]);

  const getStayProgress = (entryTime: number) => {
    const mins = (Date.now() - entryTime) / 60000;
    return Math.min((mins / 240) * 100, 100);
  };

  return (
    <div className={`min-h-screen transition-colors duration-500 font-sans pb-20 ${isDarkMode ? 'bg-slate-950 text-slate-200' : 'bg-slate-50 text-slate-900'}`}>
      <header className={`sticky top-0 z-30 px-6 py-4 flex items-center justify-between border-b backdrop-blur-md ${isDarkMode ? 'bg-slate-900/80 border-indigo-500/30' : 'bg-white/80 border-slate-200 shadow-sm'}`}>
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-indigo-600 flex items-center justify-center text-white"><Car size={20} /></div>
          <h1 className="text-xl font-black bg-clip-text text-transparent bg-gradient-to-r from-indigo-500 to-purple-500">CParking</h1>
        </div>
        <nav className="flex bg-slate-800/10 p-1 rounded-xl gap-0.5 border border-white/5">
          {["actions", "monitor", "stats"].map(tab => (
            <button key={tab} onClick={() => setActiveTab(tab as any)} className={`px-4 py-1.5 rounded-lg font-bold text-[10px] uppercase transition-all ${activeTab === tab ? 'bg-indigo-600 text-white' : 'opacity-40 hover:opacity-100'}`}>
              {tab === 'actions' ? 'Control' : tab === 'monitor' ? 'Monitor' : 'Cierre'}
            </button>
          ))}
        </nav>
        <button onClick={toggleTheme} className="p-2 transition-transform hover:scale-110">{isDarkMode ? <Sun size={20} className="text-yellow-400" /> : <Moon size={20} className="text-slate-600" />}</button>
      </header>

      <main className="max-w-6xl mx-auto p-4 mt-6">
        {activeTab === "actions" && (
          <div className="lg:grid lg:grid-cols-12 lg:gap-8 space-y-6 lg:space-y-0 animate-in fade-in duration-500">
            
            {/* ENTRADA / SALIDA - THE MAIN THING (Layout top) */}
            <div className="lg:col-span-7 space-y-6">
               <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <button onClick={() => { setCameraMode("entry"); setIsCameraOpen(true); }} className={`p-10 rounded-[2.5rem] border-2 flex flex-col items-center gap-6 transition-all active:scale-95 ${isDarkMode ? 'bg-emerald-500/10 border-emerald-500/30 shadow-2xl shadow-emerald-500/10' : 'bg-emerald-50 border-emerald-200 shadow-md'}`}>
                    <div className="p-6 rounded-full bg-emerald-500 text-white shadow-lg"><LogIn size={36} /></div>
                    <span className="font-black text-2xl tracking-tighter">ENTRADA</span>
                  </button>
                  <button onClick={() => { setCameraMode("exit"); setIsCameraOpen(true); }} className={`p-10 rounded-[2.5rem] border-2 flex flex-col items-center gap-6 transition-all active:scale-95 ${isDarkMode ? 'bg-indigo-500/10 border-indigo-500/30 shadow-2xl shadow-indigo-500/10' : 'bg-indigo-50 border-indigo-200 shadow-md'}`}>
                    <div className="p-6 rounded-full bg-indigo-500 text-white shadow-lg"><LogOut size={36} /></div>
                    <span className="font-black text-2xl tracking-tighter">SALIDA</span>
                  </button>
               </div>

               {/* Results & Actions Feedback */}
               {actionResult && (
                 <div className={`p-6 rounded-[2rem] border-2 shadow-2xl flex items-center gap-5 ${actionResult.action === 'entered' ? 'bg-emerald-500/10 border-emerald-500/30' : 'bg-indigo-500/10 border-indigo-500/30'}`}>
                    <div className={`p-4 rounded-2xl ${actionResult.action === 'entered' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-indigo-500/20 text-indigo-400'}`}>
                      {actionResult.action === 'entered' ? <LogIn size={28} /> : <LogOut size={28} />}
                    </div>
                    <div className="flex-1">
                      <h3 className="font-black text-3xl tracking-tight leading-none">{actionResult.plate}</h3>
                      <p className="text-xs font-bold opacity-40 mt-1 uppercase tracking-widest">{actionResult.action === 'entered' ? 'Ingreso registrado' : 'Salida registrada'}</p>
                    </div>
                    {actionResult.fee !== undefined && <div className="text-right font-black text-3xl">${actionResult.fee.toLocaleString("es-CL")}</div>}
                 </div>
               )}

               {/* Current Stats below buttons */}
               <div className="grid grid-cols-2 gap-4">
                  <div className={`p-6 rounded-3xl border ${isDarkMode ? 'bg-slate-900 border-slate-800' : 'bg-white border-slate-100 shadow-sm'}`}>
                    <TrendingUp className="text-emerald-500 mb-2" size={18} />
                    <div className="text-2xl font-black">${stats.today_income.toLocaleString("es-CL")}</div>
                    <div className="text-[10px] uppercase font-black opacity-30 mt-1">Hoy</div>
                  </div>
                  <div className={`p-6 rounded-3xl border ${isDarkMode ? 'bg-slate-900 border-slate-800' : 'bg-white border-slate-100 shadow-sm'}`}>
                    <Users className="text-indigo-500 mb-2" size={18} />
                    <div className="text-2xl font-black">{stats.parked_now}</div>
                    <div className="text-[10px] uppercase font-black opacity-30 mt-1">En Recinto</div>
                  </div>
               </div>

               {/* Configuration / Event Mode */}
               <section className={`p-8 rounded-[2rem] border ${isDarkMode ? 'bg-slate-900 border-slate-800' : 'bg-white border-slate-100 shadow-sm'}`}>
                  <h2 className="text-xs font-black uppercase tracking-[0.3em] opacity-40 mb-6">Tarifado Activo / Eventos</h2>
                  <div className="grid grid-cols-2 gap-3">
                    {EVENT_FEES.map(fee => (
                      <button key={fee.id} onClick={() => setSelectedEvent(fee)} className={`p-4 rounded-2xl text-left border-2 transition-all ${selectedEvent.id === fee.id ? 'bg-indigo-600 border-indigo-500 text-white' : isDarkMode ? 'bg-slate-800/50 border-transparent hover:border-slate-700' : 'bg-slate-50 border-transparent'}`}>
                        <div className="font-bold text-sm">{fee.name}</div>
                        <div className="text-[10px] opacity-70 mt-0.5">{fee.amount ? `$${fee.amount.toLocaleString("es-CL")}` : "Por minuto"}</div>
                      </button>
                    ))}
                  </div>
               </section>
            </div>

            {/* Recent History Sidebar */}
            <div className={`lg:col-span-12 xl:col-span-5 h-full p-8 rounded-[2.5rem] border shadow-2xl overflow-hidden ${isDarkMode ? 'bg-slate-900 border-slate-800' : 'bg-white border-slate-100 shadow-sm'}`}>
               <div className="flex items-center justify-between mb-8 pb-4 border-b border-dashed border-slate-800">
                  <h2 className="text-xs font-black uppercase tracking-[0.3em] opacity-40">Monitor de Acceso</h2>
                  <Activity className="text-emerald-500 animate-pulse" size={16} />
               </div>
               <div className="space-y-3 max-h-[600px] overflow-y-auto pr-2 custom-scrollbar">
                  {Object.values(cars).length === 0 ? (
                    <div className="text-center py-20 opacity-20 italic">No hay registros</div>
                  ) : (
                    Object.values(cars).reverse().map(car => (
                      <div key={car.plate} className={`group p-4 rounded-2xl flex justify-between items-center ${isDarkMode ? 'bg-slate-800/40 hover:bg-slate-800' : 'bg-slate-100 hover:bg-white border border-transparent hover:border-slate-200'}`}>
                        <div className="flex items-center gap-4">
                           <div className="font-bold font-mono tracking-widest text-lg">{car.plate}</div>
                           <span className="text-[10px] font-bold opacity-30">{format(car.entryTime, "HH:mm")}</span>
                        </div>
                        <button onClick={() => deleteCar(car.plate)} className="p-2 text-red-500/20 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-all"><Trash2 size={16} /></button>
                      </div>
                    ))
                  )}
               </div>
            </div>
          </div>
        )}

        {activeTab === "monitor" && (
           <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6 animate-in slide-in-from-right-10 pt-4">
              {Object.values(cars).map((car) => {
                const progress = getStayProgress(car.entryTime);
                const mins = Math.floor((Date.now() - car.entryTime) / 60000);
                const fee = calculateFee(car.entryTime, Date.now(), car.isEvent, car.eventFee);
                return (
                  <div key={car.plate} className={`p-8 rounded-[2.5rem] border-2 transition-all hover:-translate-y-2 shadow-2xl ${isDarkMode ? 'bg-slate-900 border-slate-800' : 'bg-white border-slate-100 shadow-xl'}`}>
                    <div className="flex justify-between items-start mb-6">
                      <div className="font-black text-3xl font-mono tracking-tighter">{car.plate}</div>
                      <div className={`px-2 py-0.5 rounded text-[8px] font-black uppercase ${car.isEvent ? 'bg-purple-600' : 'bg-indigo-600'} text-white`}>{car.isEvent ? "Evento" : "Normal"}</div>
                    </div>
                    <div className="space-y-4">
                      <div className="flex justify-between items-center">
                         <div><p className="text-[9px] uppercase font-bold opacity-40 mb-1">Entrada</p><p className="font-black text-xl">{format(car.entryTime, "HH:mm")}</p></div>
                         <div className="text-right"><p className="text-[9px] uppercase font-bold opacity-40 mb-1">Monto Actual</p><p className="font-black text-2xl text-indigo-500">${fee.toLocaleString("es-CL")}</p></div>
                      </div>
                      {!car.isEvent && (
                        <div className="h-2 bg-slate-800/10 rounded-full overflow-hidden">
                           <div className={`h-full transition-all duration-1000 ${progress > 80 ? 'bg-red-500' : 'bg-emerald-500'}`} style={{ width: `${progress}%` }} />
                        </div>
                      )}
                      <button onClick={() => processPlate(car.plate, "exit")} className="w-full py-4 rounded-2xl bg-indigo-600 text-white font-black text-xs uppercase tracking-[0.2em] shadow-lg shadow-indigo-600/30 active:scale-95 transition-all">TERMINAR</button>
                    </div>
                  </div>
                );
              })}
           </div>
        )}

        {activeTab === "stats" && (
           <div className="animate-in zoom-in-95 duration-500 space-y-10 max-w-4xl mx-auto py-10">
              <div className={`p-20 rounded-[4rem] border-2 shadow-2xl text-center ${isDarkMode ? 'bg-slate-900 border-indigo-500/30 shadow-[0_0_100px_rgba(79,70,229,0.1)]' : 'bg-white border-slate-200'}`}>
                 <h2 className="text-xs font-black uppercase tracking-[0.5em] opacity-40 mb-10">Total Recaudado Hoy</h2>
                 <div className="text-9xl font-black italic tracking-tighter text-indigo-500 mb-10 tabular-nums">${stats.today_income.toLocaleString("es-CL")}</div>
                 <div className="flex justify-center gap-16 border-t border-dashed border-slate-800 pt-10">
                    <div className="text-center group"><p className="text-4xl font-black group-hover:scale-125 transition-transform">{stats.today_entries}</p><p className="text-[10px] font-bold uppercase opacity-30 mt-2">Ingresos</p></div>
                    <div className="text-center group"><p className="text-4xl font-black group-hover:scale-125 transition-transform">{stats.today_exits}</p><p className="text-[10px] font-bold uppercase opacity-30 mt-2">Salidas</p></div>
                 </div>
              </div>
           </div>
        )}
      </main>

      {isCameraOpen && (
        <div className="fixed inset-0 z-[100] bg-black flex flex-col font-sans">
          <div className="p-8 flex justify-between items-center absolute top-0 inset-x-0 z-20 bg-gradient-to-b from-black to-transparent">
            <h2 className="text-white font-black text-2xl tracking-tighter uppercase">{cameraMode === "entry" ? "ESCANEANDO ENTRADA" : "ESCANEANDO SALIDA"}</h2>
            <button onClick={() => setIsCameraOpen(false)} className="w-14 h-14 bg-white/10 rounded-2xl flex items-center justify-center text-white backdrop-blur-xl active:scale-90"><X size={32} /></button>
          </div>
          <div className="flex-1 relative flex items-center justify-center">
            {cameraError ? (
               <div className="text-center text-white px-10 space-y-4"><AlertCircle size={48} className="mx-auto text-red-500" /><p className="font-bold text-lg">{cameraError}</p><button onClick={() => setIsCameraOpen(false)} className="bg-white text-black px-6 py-2 rounded-xl font-black">CERRAR</button></div>
            ) : (
              <Webcam audio={false} ref={webcamRef} screenshotFormat="image/jpeg" videoConstraints={{ facingMode: "environment", width: 1920, height: 1080 }} className="h-full w-full object-cover transition-transform" style={{ transform: `scale(${zoomLevel})` }} />
            )}
            <div className="absolute inset-x-0 bottom-44 px-10 flex justify-between items-center z-20">
               <div className="flex bg-black/60 p-2 rounded-2xl border border-white/20 items-center gap-4">
                  <button onClick={() => setZoomLevel(prev => Math.max(1, prev - 1))} className="w-10 h-10 bg-white/10 rounded-xl text-white"><ZoomOut size={18} /></button>
                  <span className="text-white font-black text-xs tabular-nums">{zoomLevel}x</span>
                  <button onClick={() => setZoomLevel(prev => Math.min(3, prev + 1))} className="w-10 h-10 bg-white/10 rounded-xl text-white"><ZoomIn size={18} /></button>
               </div>
               <button onClick={() => setShowManualInput(!showManualInput)} className={`w-14 h-14 rounded-2xl flex items-center justify-center transition-all ${showManualInput ? 'bg-indigo-600 text-white' : 'bg-black/60 text-white border border-white/20'}`}><Search /></button>
            </div>
            {showManualInput && (
              <div className="absolute bottom-60 inset-x-10 px-4 z-30 animate-in slide-in-from-bottom-5">
                <form onSubmit={handleManualEntry} className="bg-white p-2.5 rounded-[2.5rem] flex shadow-2xl">
                  <input autoFocus type="text" value={manualPlate} onChange={e => setManualPlate(e.target.value)} placeholder="PATENTE" className="flex-1 bg-slate-100 rounded-[2rem] px-8 py-5 font-mono font-black text-2xl uppercase tracking-widest text-slate-900 outline-none" />
                  <button type="submit" className="bg-slate-900 text-white px-8 rounded-[2rem]"><Check size={28} /></button>
                </form>
              </div>
            )}
          </div>
          <div className="h-48 bg-black flex items-center justify-center pb-12">
            <button onClick={captureAndAnalyze} disabled={isAnalyzing} className="w-32 h-32 rounded-full border-4 border-emerald-400 p-2 flex items-center justify-center">
               {isAnalyzing ? <div className="w-10 h-10 border-4 border-white/20 border-t-white rounded-full animate-spin" /> : <div className="w-24 h-24 bg-white rounded-full shadow-2xl active:scale-90 transition-all" />}
            </button>
          </div>
        </div>
      )}

      <style jsx global>{`
        .custom-scrollbar::-webkit-scrollbar { width: 4px; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(99, 102, 241, 0.4); border-radius: 10px; }
      `}</style>
    </div>
  );
}
