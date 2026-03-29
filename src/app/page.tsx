"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import Webcam from "react-webcam";
import { Camera, Search, LogOut, LogIn, CalendarDays, X, Check, Car, History, Sun, Moon, MapPin, MousePointer2, Clock, DollarSign, Activity, Trash2, TrendingUp, Users } from "lucide-react";
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
    if (!confirm(`¿Estás seguro de eliminar el registro de ${plate}? No se registrará cobro.`)) return;
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "/api";
    try {
      const res = await fetch(`${apiUrl}/cars/${plate}`, { method: "DELETE" });
      if (res.ok) {
        setCars(prev => {
          const next = { ...prev };
          delete next[plate];
          return next;
        });
        setActionResult({ plate, action: "deleted" });
        setTimeout(() => setActionResult(null), 3000);
        fetchData();
      }
    } catch (err) {
      alert("Error al eliminar");
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

        const res = await fetch(`${apiUrl}/entry`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            plate: plateNumber,
            isEvent: selectedEvent.amount !== null,
            eventFee: selectedEvent.amount
          })
        });

        if (!res.ok) throw new Error("Entry failed");
        const newCar = await res.json();
        setCars((prev) => ({ ...prev, [plateNumber]: newCar }));
        setActionResult({ plate: plateNumber, action: "entered", time: format(now, "HH:mm") });

      } else {
        const existingCar = cars[plateNumber];
        if (!existingCar) {
          alert("Auto no encontrado.");
          setIsCameraOpen(false);
          return;
        }

        const fee = calculateFee(existingCar.entryTime, now, existingCar.isEvent, existingCar.eventFee);
        
        const res = await fetch(`${apiUrl}/exit/${plateNumber}?fee=${fee}`, { method: "POST" });
        if (!res.ok) throw new Error("Exit failed");

        setCars((prev) => {
          const next = { ...prev };
          delete next[plateNumber];
          return next;
        });

        setActionResult({
          plate: plateNumber,
          action: "exited",
          fee: fee,
          time: format(now - existingCar.entryTime, "HH:mm")
        });
      }
      fetchData();
    } catch (err) {
      console.error(err);
      alert("Error de conexión con el backend.");
    } finally {
      setIsCameraOpen(false);
      setTimeout(() => setActionResult(null), 8000);
    }
  };

  const captureAndAnalyze = useCallback(async () => {
    if (!webcamRef.current) return;
    setIsAnalyzing(true);
    const imageSrc = webcamRef.current.getScreenshot();
    if (!imageSrc) {
      alert("Captura fallida");
      setIsAnalyzing(false);
      return;
    }

    try {
      const res = await fetch(imageSrc);
      const blob = await res.blob();
      const formData = new FormData();
      formData.append("image", blob, "capture.jpg");

      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "/api";
      const response = await fetch(`${apiUrl}/detect`, { method: "POST", body: formData });
      const data = await response.json();
      
      if (data.plate && data.plate !== "None") {
        processPlate(data.plate, cameraMode);
      } else {
        alert("No se detectó la patente. Intenta de nuevo.");
      }
    } catch (err) {
      console.error(err);
      alert("Error de motor AI.");
    } finally {
      setIsAnalyzing(false);
    }
  }, [webcamRef, cameraMode, processPlate]);

  const getStayProgress = (entryTime: number) => {
    const mins = (Date.now() - entryTime) / 60000;
    return Math.min((mins / 240) * 100, 100);
  };

  return (
    <div className={`min-h-screen transition-colors duration-500 font-sans pb-20 ${isDarkMode ? 'bg-slate-950 text-slate-200' : 'bg-slate-50 text-slate-900'}`}>
      <header className={`sticky top-0 z-30 px-6 py-4 flex items-center justify-between border-b backdrop-blur-md transition-all ${isDarkMode ? 'bg-slate-900/80 border-indigo-500/30' : 'bg-white/80 border-slate-200 shadow-sm'}`}>
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-500/30">
            <Car className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="text-2xl font-black bg-clip-text text-transparent bg-gradient-to-r from-indigo-500 to-purple-600">
              Central Parking
            </h1>
            <div className="flex items-center gap-2 mt-0.5">
              <span className={`w-2 h-2 rounded-full ${process.env.NEXT_PUBLIC_API_URL ? 'bg-emerald-500' : 'bg-yellow-500'}`} />
              <span className="text-[10px] font-bold uppercase opacity-60">Terminal MVP</span>
            </div>
          </div>
        </div>
        
        <div className="flex items-center gap-4">
          <nav className={`hidden md:flex bg-slate-800/20 p-1 rounded-xl gap-0.5 border ${isDarkMode ? 'border-slate-800' : 'border-slate-100'}`}>
            {["actions", "monitor", "stats"].map(tab => (
              <button 
                key={tab}
                onClick={() => setActiveTab(tab as any)}
                className={`px-4 py-1.5 rounded-lg font-bold text-[10px] uppercase tracking-widest transition-all ${activeTab === tab ? 'bg-indigo-600 text-white' : 'opacity-40 hover:opacity-100'}`}
              >
                {tab === 'actions' ? 'Control' : tab === 'monitor' ? 'Monitor' : 'Cierre'}
              </button>
            ))}
          </nav>
          <button onClick={toggleTheme} className={`p-2.5 rounded-xl transition-all ${isDarkMode ? 'bg-slate-800 text-yellow-400' : 'bg-slate-100 text-slate-600'}`}>
            {isDarkMode ? <Sun size={20} /> : <Moon size={20} />}
          </button>
        </div>
      </header>

      <main className="max-w-6xl mx-auto p-4 mt-6">
        
        <div className="md:hidden flex gap-1 mb-6 bg-slate-800/20 p-1 rounded-2xl">
           {["actions", "monitor", "stats"].map(tab => (
              <button key={tab} onClick={() => setActiveTab(tab as any)} className={`flex-1 py-3 rounded-xl font-black text-[10px] uppercase transition-all ${activeTab === tab ? 'bg-indigo-600 text-white' : 'opacity-40'}`}>
                {tab === 'actions' ? 'Control' : tab === 'monitor' ? 'Monitor' : 'Cierre'}
              </button>
           ))}
        </div>

        {activeTab === "actions" && (
          <div className="lg:grid lg:grid-cols-12 lg:gap-8 animate-in fade-in duration-500">
            <div className="lg:col-span-12 mb-6">
               <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                  <div className={`p-5 rounded-3xl border ${isDarkMode ? 'bg-slate-900 border-slate-800' : 'bg-white border-slate-100 shadow-sm'}`}>
                    <div className="text-emerald-500 mb-2"><TrendingUp size={18} /></div>
                    <div className="text-2xl font-black">${stats.today_income.toLocaleString("es-CL")}</div>
                    <div className="text-[10px] uppercase font-bold opacity-50">Ingresos Hoy</div>
                  </div>
                  <div className={`p-5 rounded-3xl border ${isDarkMode ? 'bg-slate-900 border-slate-800' : 'bg-white border-slate-100 shadow-sm'}`}>
                    <div className="text-indigo-500 mb-2"><LogIn size={18} /></div>
                    <div className="text-2xl font-black">{stats.today_entries}</div>
                    <div className="text-[10px] uppercase font-bold opacity-50">Entradas Hoy</div>
                  </div>
                  <div className={`p-5 rounded-3xl border ${isDarkMode ? 'bg-slate-900 border-slate-800' : 'bg-white border-slate-100 shadow-sm'}`}>
                    <div className="text-purple-500 mb-2"><LogOut size={18} /></div>
                    <div className="text-2xl font-black">{stats.today_exits}</div>
                    <div className="text-[10px] uppercase font-bold opacity-50">Salidas Hoy</div>
                  </div>
                  <div className={`p-5 rounded-3xl border ${isDarkMode ? 'bg-slate-900 border-slate-800' : 'bg-white border-slate-100 shadow-sm'}`}>
                    <div className="text-blue-500 mb-2"><Users size={18} /></div>
                    <div className="text-2xl font-black">{stats.parked_now}</div>
                    <div className="text-[10px] uppercase font-bold opacity-50">En el Recinto</div>
                  </div>
               </div>
            </div>

            <div className="lg:col-span-7 space-y-6">
               {actionResult && (
                 <div className={`p-6 rounded-[2rem] border-2 shadow-2xl flex items-center gap-5 scale-in-center ${actionResult.action === 'entered' ? 'bg-emerald-500/10 border-emerald-500/30' : actionResult.action === 'deleted' ? 'bg-red-500/10 border-red-500/30' : 'bg-indigo-500/10 border-indigo-500/30'}`}>
                    <div className={`p-4 rounded-2xl ${actionResult.action === 'entered' ? 'bg-emerald-500/20 text-emerald-400' : actionResult.action === 'deleted' ? 'bg-red-500/20 text-red-400' : 'bg-indigo-500/20 text-indigo-400'}`}>
                      {actionResult.action === 'entered' ? <LogIn size={32} /> : actionResult.action === 'deleted' ? <Trash2 size={32} /> : <LogOut size={32} />}
                    </div>
                    <div className="flex-1">
                      <span className="text-[10px] font-black uppercase tracking-[0.2em] opacity-50">
                        {actionResult.action === 'entered' ? 'Ingreso Registrado' : actionResult.action === 'deleted' ? 'Registro Eliminado' : 'Salida Registrada'}
                      </span>
                      <h3 className="font-black text-3xl tracking-tight">{actionResult.plate}</h3>
                    </div>
                    {actionResult.fee !== undefined && (
                      <div className="text-right">
                        <p className="text-xs font-bold opacity-60">Total</p>
                        <p className="text-4xl font-black">${actionResult.fee.toLocaleString("es-CL")}</p>
                      </div>
                    )}
                 </div>
               )}

               <section className={`p-8 rounded-[2.5rem] border shadow-2xl ${isDarkMode ? 'bg-slate-900 border-slate-800' : 'bg-white border-slate-200'}`}>
                  <h2 className="font-black text-xl uppercase tracking-tight mb-6 flex items-center gap-2">
                    <CalendarDays className="text-indigo-500" size={20} /> Tarifado
                  </h2>
                  <div className="grid grid-cols-2 gap-3">
                    {EVENT_FEES.map(fee => (
                      <button key={fee.id} onClick={() => setSelectedEvent(fee)} className={`p-4 rounded-2xl text-left border-2 transition-all group ${selectedEvent.id === fee.id ? 'bg-indigo-600 border-indigo-500 text-white shadow-xl shadow-indigo-500/20' : isDarkMode ? 'bg-slate-800/50 border-transparent' : 'bg-slate-50 border-transparent'}`}>
                        <div className="font-bold text-sm">{fee.name}</div>
                        <div className="text-[10px] opacity-70">{fee.amount ? `$${fee.amount.toLocaleString("es-CL")}` : "Precio Variable"}</div>
                      </button>
                    ))}
                  </div>
               </section>

               <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <button onClick={() => { setCameraMode("entry"); setIsCameraOpen(true); }} className={`p-8 rounded-[2.5rem] border-2 flex items-center justify-between transition-all active:scale-95 ${isDarkMode ? 'bg-emerald-500/5 border-emerald-500/20' : 'bg-emerald-50 border-emerald-100'}`}>
                    <div className="flex flex-col text-left">
                      <span className="text-[10px] font-black opacity-50 mb-1">CÁMARA</span>
                      <span className="font-black text-2xl">ENTRADA</span>
                    </div>
                    <div className="p-4 rounded-3xl bg-emerald-500 text-white shadow-lg shadow-emerald-500/20"><LogIn size={32} /></div>
                  </button>
                  <button onClick={() => { setCameraMode("exit"); setIsCameraOpen(true); }} className={`p-8 rounded-[2.5rem] border-2 flex items-center justify-between transition-all active:scale-95 ${isDarkMode ? 'bg-indigo-500/5 border-indigo-500/20' : 'bg-indigo-50 border-indigo-100'}`}>
                    <div className="flex flex-col text-left">
                      <span className="text-[10px] font-black opacity-50 mb-1">CÁMARA</span>
                      <span className="font-black text-2xl">SALIDA</span>
                    </div>
                    <div className="p-4 rounded-3xl bg-indigo-500 text-white shadow-lg shadow-indigo-500/20"><LogOut size={32} /></div>
                  </button>
               </div>
            </div>

            <div className={`lg:col-span-5 mt-8 lg:mt-0 p-8 rounded-[2.5rem] border shadow-2xl relative ${isDarkMode ? 'bg-slate-900 border-slate-800' : 'bg-white border-slate-100'}`}>
               <div className="flex items-center justify-between mb-8">
                  <h2 className="text-xs font-black uppercase tracking-widest opacity-50">Ingresos Recientes</h2>
                  <Activity className="text-emerald-500 animate-pulse" size={16} />
               </div>
               <div className="space-y-4">
                  {Object.values(cars).length === 0 ? (
                    <div className="text-center py-20 opacity-20">Ningún vehículo</div>
                  ) : (
                    Object.values(cars).reverse().slice(0, 10).map(car => (
                      <div key={car.plate} className={`p-4 rounded-2xl flex justify-between items-center ${isDarkMode ? 'bg-slate-800/40 border border-white/5' : 'bg-slate-50 border border-slate-100'}`}>
                        <div className="font-bold font-mono tracking-widest text-lg">{car.plate}</div>
                        <div className="flex items-center gap-3">
                           <span className="text-[10px] font-bold opacity-30">{format(car.entryTime, "HH:mm")}</span>
                           <button onClick={() => deleteCar(car.plate)} className="p-2 text-red-400/50 hover:text-red-500 hover:bg-red-500/10 rounded-lg transition-colors">
                              <Trash2 size={16} />
                           </button>
                        </div>
                      </div>
                    ))
                  )}
               </div>
            </div>
          </div>
        )}

        {activeTab === "monitor" && (
          <div className="animate-in slide-in-from-right-10 duration-500 space-y-6">
             <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
                {Object.values(cars).map((car) => {
                  const progress = getStayProgress(car.entryTime);
                  const mins = Math.floor((Date.now() - car.entryTime) / 60000);
                  return (
                    <div key={car.plate} className={`group p-8 rounded-[2.5rem] border-2 transition-all hover:-translate-y-2 ${isDarkMode ? 'bg-slate-900 border-slate-800 hover:border-indigo-500/50' : 'bg-white border-slate-200'}`}>
                      <div className="flex justify-between items-start mb-6">
                        <div className="font-black text-3xl font-mono tracking-widest leading-none">{car.plate}</div>
                        <button onClick={() => deleteCar(car.plate)} className="p-2 rounded-xl text-red-500/30 hover:bg-red-500/10 hover:text-red-500 transition-all opacity-0 group-hover:opacity-100"><Trash2 size={18} /></button>
                      </div>
                      <div className="space-y-5">
                        <div className="flex justify-between items-end">
                           <div>
                             <p className="text-[10px] font-black uppercase tracking-widest opacity-40">Estadía</p>
                             <p className="font-bold text-xl">{Math.floor(mins / 60)}h {mins % 60}m</p>
                           </div>
                           <div className="text-right">
                             <p className="text-[10px] font-black uppercase tracking-widest opacity-40">Tarifa Acum.</p>
                             <p className="font-black text-2xl text-indigo-500">${calculateFee(car.entryTime, Date.now(), car.isEvent, car.eventFee).toLocaleString("es-CL")}</p>
                           </div>
                        </div>
                        {!car.isEvent && (
                          <div className="space-y-2">
                             <div className="h-3 bg-slate-800 rounded-full overflow-hidden border border-white/5">
                                <div className={`h-full transition-all duration-1000 ${progress > 90 ? 'bg-red-500 shadow-[0_0_15px_rgba(239,68,68,0.5)]' : progress > 60 ? 'bg-orange-500' : 'bg-emerald-500 shadow-[0_0_15px_rgba(16,185,129,0.3)]'}`} style={{ width: `${progress}%` }} />
                             </div>
                          </div>
                        )}
                        <button onClick={() => processPlate(car.plate, "exit")} className="w-full py-4 mt-2 rounded-2xl bg-indigo-600 hover:bg-indigo-500 text-white font-black text-sm tracking-widest transition-all shadow-lg shadow-indigo-600/20 active:scale-95">COBRAR SALIDA</button>
                      </div>
                    </div>
                  );
                })}
             </div>
          </div>
        )}

        {activeTab === "stats" && (
           <div className="animate-in zoom-in-95 duration-500 max-w-4xl mx-auto space-y-8">
              <div className={`p-10 rounded-[3rem] border-2 text-center space-y-6 ${isDarkMode ? 'bg-slate-900 border-indigo-500/20 shadow-2xl' : 'bg-white border-slate-100 shadow-xl'}`}>
                 <h2 className="text-xs font-black uppercase tracking-[0.4em] opacity-40">Resumen Financiero Hoy</h2>
                 <div className="text-7xl font-black italic tracking-tighter text-indigo-500">${stats.today_income.toLocaleString("es-CL")}</div>
                 <div className="flex justify-center gap-12 pt-6 border-t border-dashed border-slate-800">
                    <div className="text-center">
                       <p className="text-2xl font-black">{stats.today_entries}</p>
                       <p className="text-[10px] font-bold uppercase opacity-40">Entradas</p>
                    </div>
                    <div className="text-center">
                       <p className="text-2xl font-black">{stats.today_exits}</p>
                       <p className="text-[10px] font-bold uppercase opacity-40">Salidas</p>
                    </div>
                    <div className="text-center">
                       <p className="text-2xl font-black">{stats.parked_now}</p>
                       <p className="text-[10px] font-bold uppercase opacity-40">En Recinto</p>
                    </div>
                 </div>
              </div>
              
              <div className="grid grid-cols-2 gap-4">
                 <button className={`p-10 rounded-[2.5rem] border-2 font-black tracking-widest uppercase text-xs transition-style active:scale-95 ${isDarkMode ? 'bg-slate-900 border-slate-800' : 'bg-white border-slate-200 shadow-md'}`}>Descargar Reporte (CSV)</button>
                 <button onClick={() => window.print()} className={`p-10 rounded-[2.5rem] border-2 font-black tracking-widest uppercase text-xs transition-style active:scale-95 ${isDarkMode ? 'bg-slate-900 border-slate-800' : 'bg-white border-slate-200 shadow-md'}`}>Imprimir Cierre</button>
              </div>
           </div>
        )}
      </main>

      {isCameraOpen && (
        <div className="fixed inset-0 z-[100] bg-black flex flex-col font-sans">
          <div className="p-8 flex justify-between items-center absolute top-0 inset-x-0 z-20 bg-gradient-to-b from-black via-black/80 to-transparent">
            <h2 className="text-white font-black text-2xl tracking-tight uppercase">{cameraMode === "entry" ? "Ingresando Auto" : "Cobrando Salida"}</h2>
            <button onClick={() => setIsCameraOpen(false)} className="w-14 h-14 bg-white/10 rounded-[1.5rem] flex items-center justify-center text-white backdrop-blur-2xl border border-white/20 active:scale-90 transition-all"><X size={32} /></button>
          </div>
          <div className="flex-1 relative flex items-center justify-center">
            <Webcam audio={false} ref={webcamRef} screenshotFormat="image/jpeg" videoConstraints={{ facingMode: "environment" }} className="h-full w-full object-cover" />
            <div className="absolute inset-0 flex items-center justify-center p-12 pointer-events-none">
               <div className="w-full max-w-sm aspect-[3/2] border-2 border-emerald-400/30 rounded-[3rem] shadow-[0_0_0_2000px_rgba(0,0,0,0.7)] relative">
                  <div className="absolute inset-x-0 top-0 h-[3px] bg-emerald-400 shadow-[0_0_20px_emerald] animate-[scan_4s_infinite]" />
                  <div className="absolute -top-4 -left-4 w-12 h-12 border-t-8 border-l-8 border-emerald-400 rounded-tl-3xl" />
                  <div className="absolute -bottom-4 -right-4 w-12 h-12 border-b-8 border-r-8 border-emerald-400 rounded-br-3xl" />
               </div>
            </div>
            {showManualInput && (
              <div className="absolute bottom-40 inset-x-0 px-8 z-20 animate-in slide-in-from-bottom-5">
                <form onSubmit={handleManualEntry} className="bg-white p-2.5 rounded-[2.5rem] flex shadow-2xl">
                  <input autoFocus type="text" value={manualPlate} onChange={e => setManualPlate(e.target.value)} placeholder="ABC-123" className="flex-1 bg-slate-100 rounded-[2rem] px-8 py-5 font-mono font-black text-2xl uppercase text-slate-900 outline-none" />
                  <button type="submit" className="bg-slate-900 text-white w-20 rounded-[2rem] flex items-center justify-center active:scale-95"><Check size={32} /></button>
                </form>
              </div>
            )}
          </div>
          <div className="h-44 bg-black px-12 flex items-center justify-between pb-10">
            <button onClick={() => setShowManualInput(!showManualInput)} className={`w-18 h-18 rounded-[2rem] flex items-center justify-center transition-all ${showManualInput ? 'bg-indigo-600 text-white' : 'bg-white/10 text-white border border-white/20'}`}><Search size={32} /></button>
            <button onClick={captureAndAnalyze} disabled={isAnalyzing} className="group relative w-24 h-24 rounded-full flex items-center justify-center transition-all">
               <div className={`absolute inset-0 rounded-full border-4 border-emerald-400/30 ${isAnalyzing ? 'animate-spin border-t-emerald-400' : ''}`} />
               <div className={`w-20 h-20 rounded-full flex items-center justify-center transition-all ${isAnalyzing ? 'bg-slate-900 scale-90' : 'bg-white shadow-[0_0_30px_rgba(255,255,255,0.2)] active:scale-90 active:bg-slate-100'}`}>
                  {isAnalyzing && <Activity className="text-emerald-400 animate-pulse" size={24} />}
               </div>
            </button>
            <div className="w-18" />
          </div>
        </div>
      )}

      <style jsx global>{`
        @keyframes scan { 0%, 100% { top: 0; } 50% { top: 100%; } }
        .scale-in-center { animation: scale-in-center 0.4s cubic-bezier(0.250, 0.460, 0.450, 0.940) both; }
        @keyframes scale-in-center { 0% { transform: scale(0.9); opacity: 0; } 100% { transform: scale(1); opacity: 1; } }
      `}</style>
    </div>
  );
}
