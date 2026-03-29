"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import Webcam from "react-webcam";
import { Camera, Search, LogOut, LogIn, CalendarDays, X, Check, Car, History, Sun, Moon, MapPin, MousePointer2, Clock, DollarSign, Activity } from "lucide-react";
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
  const [selectedEvent, setSelectedEvent] = useState(EVENT_FEES[0]);
  const [isCameraOpen, setIsCameraOpen] = useState(false);
  const [cameraMode, setCameraMode] = useState<"entry" | "exit">("entry");
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [manualPlate, setManualPlate] = useState("");
  const [showManualInput, setShowManualInput] = useState(false);
  const [isDarkMode, setIsDarkMode] = useState(true);
  const [activeTab, setActiveTab] = useState<"actions" | "monitor">("actions");
  
  const [actionResult, setActionResult] = useState<{
    plate: string;
    action: "entered" | "exited";
    fee?: number;
    time?: string;
  } | null>(null);

  const webcamRef = useRef<Webcam>(null);

  const fetchCars = async () => {
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "/api";
      const response = await fetch(`${apiUrl}/cars`);
      if (response.ok) {
        const data = await response.json();
        setCars(data);
      }
    } catch (err) {
      console.warn("Backend local not reachable for sync, using localStorage fallback.");
      const saved = localStorage.getItem("parked_cars");
      if (saved) setCars(JSON.parse(saved));
    }
  };

  useEffect(() => {
    fetchCars();
    const interval = setInterval(fetchCars, 10000); // Sync every 10s
    const savedTheme = localStorage.getItem("theme");
    if (savedTheme === "light") setIsDarkMode(false);
    return () => clearInterval(interval);
  }, []);

  const toggleTheme = () => {
    const newTheme = !isDarkMode;
    setIsDarkMode(newTheme);
    localStorage.setItem("theme", newTheme ? "dark" : "light");
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

        if (!res.ok) throw new Error("Failed to register entry on backend");
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
        
        const res = await fetch(`${apiUrl}/exit/${plateNumber}`, { method: "POST" });
        if (!res.ok) throw new Error("Failed to register exit on backend");

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
    } catch (err) {
      console.error(err);
      alert("Error sincronizando con el backend. Operación cancelada.");
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
      alert("Error al capturar");
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
        alert("Sin detección.");
      }
    } catch (err) {
      console.error(err);
      alert("Error de conexión AI.");
    } finally {
      setIsAnalyzing(false);
    }
  }, [webcamRef, cameraMode, processPlate]);

  // Stay percentage for progress bars (max 4h = 240 min)
  const getStayProgress = (entryTime: number) => {
    const mins = (Date.now() - entryTime) / 60000;
    return Math.min((mins / 240) * 100, 100);
  };

  return (
    <div className={`min-h-screen transition-colors duration-500 font-sans pb-20 ${isDarkMode ? 'bg-slate-950 text-slate-200' : 'bg-slate-50 text-slate-900'}`}>
      <header className={`sticky top-0 z-30 px-6 py-4 flex items-center justify-between border-b backdrop-blur-md transition-all ${isDarkMode ? 'bg-slate-900/80 border-indigo-500/30 shadow-2xl shadow-black/50' : 'bg-white/80 border-slate-200 shadow-sm'}`}>
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-indigo-500 via-indigo-600 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-500/30">
            <Car className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="text-2xl font-black bg-clip-text text-transparent bg-gradient-to-r from-indigo-500 to-purple-500">
              Central Parking
            </h1>
            <div className="flex items-center gap-2 mt-0.5">
              <div className={`w-2 h-2 rounded-full ${process.env.NEXT_PUBLIC_API_URL ? 'bg-emerald-500 animate-pulse' : 'bg-yellow-500'}`} />
              <span className="text-[10px] font-bold uppercase opacity-60 tracking-tighter">
                {process.env.NEXT_PUBLIC_API_URL ? "Local Link Active" : "Internal Mock"}
              </span>
            </div>
          </div>
        </div>
        
        <div className="flex items-center gap-6">
          <nav className={`hidden md:flex bg-slate-800/20 p-1.5 rounded-2xl gap-1 border ${isDarkMode ? 'border-slate-800' : 'border-slate-200'}`}>
            <button 
              onClick={() => setActiveTab("actions")}
              className={`px-4 py-2 rounded-xl font-bold text-xs uppercase tracking-widest transition-all ${activeTab === 'actions' ? 'bg-indigo-600 text-white shadow-lg' : 'opacity-50 hover:opacity-80'}`}
            >
              Control
            </button>
            <button 
              onClick={() => setActiveTab("monitor")}
              className={`px-4 py-2 rounded-xl font-bold text-xs uppercase tracking-widest transition-all ${activeTab === 'monitor' ? 'bg-indigo-600 text-white shadow-lg' : 'opacity-50 hover:opacity-80'}`}
            >
              Monitor
            </button>
          </nav>

          <button onClick={toggleTheme} className={`p-2.5 rounded-xl transition-all ${isDarkMode ? 'bg-slate-800 text-yellow-400' : 'bg-slate-100 text-slate-600'}`}>
            {isDarkMode ? <Sun size={20} /> : <Moon size={20} />}
          </button>
        </div>
      </header>

      <main className="max-w-6xl mx-auto p-4 mt-6">
        
        {/* Mobile Nav */}
        <div className="md:hidden flex gap-2 mb-6">
           <button onClick={() => setActiveTab("actions")} className={`flex-1 py-3 rounded-2xl font-black text-xs uppercase ${activeTab === 'actions' ? 'bg-indigo-600 text-white' : 'bg-slate-800/40 text-slate-500'}`}>Control</button>
           <button onClick={() => setActiveTab("monitor")} className={`flex-1 py-3 rounded-2xl font-black text-xs uppercase ${activeTab === 'monitor' ? 'bg-indigo-600 text-white' : 'bg-slate-800/40 text-slate-500'}`}>Monitor</button>
        </div>

        {activeTab === "actions" ? (
          <div className="lg:grid lg:grid-cols-12 lg:gap-8 items-start animate-in fade-in duration-500">
            <div className="lg:col-span-7 space-y-6">
               {actionResult && (
                 <div className={`p-6 rounded-[2rem] border-2 shadow-2xl flex items-center gap-5 ${actionResult.action === 'entered' ? 'bg-emerald-500/10 border-emerald-500/30' : 'bg-indigo-500/10 border-indigo-500/30'}`}>
                    <div className={`p-4 rounded-2xl ${actionResult.action === 'entered' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-indigo-500/20 text-indigo-400'}`}>
                      {actionResult.action === 'entered' ? <LogIn size={32} /> : <LogOut size={32} />}
                    </div>
                    <div className="flex-1">
                      <span className="text-[10px] font-black uppercase tracking-[0.2em] opacity-50">Vehículo Procesado</span>
                      <h3 className="font-black text-3xl tracking-tight">{actionResult.plate}</h3>
                    </div>
                    {actionResult.fee !== undefined && (
                      <div className="text-right">
                        <p className="text-xs font-bold opacity-60">Total Tarifa</p>
                        <p className="text-4xl font-black">${actionResult.fee.toLocaleString("es-CL")}</p>
                      </div>
                    )}
                 </div>
               )}

               <section className={`p-8 rounded-[2.5rem] border shadow-2xl ${isDarkMode ? 'bg-slate-900 border-slate-800' : 'bg-white border-slate-200'}`}>
                  <div className="flex justify-between items-center mb-6">
                    <h2 className="font-black text-xl uppercase tracking-tight">Tarifado Activo</h2>
                    <DollarSign className="text-indigo-500" />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    {EVENT_FEES.map(fee => (
                      <button 
                        key={fee.id} 
                        onClick={() => setSelectedEvent(fee)}
                        className={`p-4 rounded-2xl text-left border-2 transition-all group ${selectedEvent.id === fee.id ? 'bg-indigo-600 border-indigo-500 text-white scale-[1.02] shadow-xl shadow-indigo-500/20' : isDarkMode ? 'bg-slate-800/50 border-transparent hover:border-slate-700' : 'bg-slate-50 border-transparent hover:border-slate-200'}`}
                      >
                        <div className="font-bold text-sm">{fee.name}</div>
                        <div className="text-[10px] font-mono opacity-80">{fee.amount ? `$${fee.amount.toLocaleString("es-CL")}` : "x Minuto"}</div>
                      </button>
                    ))}
                  </div>
               </section>

               <div className="grid grid-cols-2 gap-4">
                  <button onClick={() => { setCameraMode("entry"); setIsCameraOpen(true); }} className={`p-8 rounded-[2.5rem] border-2 flex flex-col items-center gap-4 transition-all hover:scale-[1.02] active:scale-95 ${isDarkMode ? 'bg-emerald-500/5 border-emerald-500/20 shadow-xl' : 'bg-emerald-50 border-emerald-200 shadow-md'}`}>
                    <div className="p-4 rounded-3xl bg-emerald-500 text-white shadow-lg"><LogIn size={32} /></div>
                    <span className="font-black text-lg">ENTRADA</span>
                  </button>
                  <button onClick={() => { setCameraMode("exit"); setIsCameraOpen(true); }} className={`p-8 rounded-[2.5rem] border-2 flex flex-col items-center gap-4 transition-all hover:scale-[1.02] active:scale-95 ${isDarkMode ? 'bg-indigo-500/5 border-indigo-500/20 shadow-xl' : 'bg-indigo-50 border-indigo-200 shadow-md'}`}>
                    <div className="p-4 rounded-3xl bg-indigo-500 text-white shadow-lg"><LogOut size={32} /></div>
                    <span className="font-black text-lg">SALIDA</span>
                  </button>
               </div>
            </div>

            <div className={`lg:col-span-5 mt-8 lg:mt-0 p-8 rounded-[2.5rem] border shadow-2xl overflow-hidden relative ${isDarkMode ? 'bg-slate-900 border-slate-800' : 'bg-white border-slate-200'}`}>
               <div className="flex items-center gap-3 mb-6">
                  <Activity className="text-emerald-500" size={20} />
                  <h2 className="text-sm font-black uppercase tracking-[0.2em] opacity-60">Estado Estacionamiento</h2>
               </div>
               
               <div className="space-y-3">
                  {Object.values(cars).length === 0 ? (
                    <div className="text-center py-20 opacity-30 italic">No hay vehículos ingresados</div>
                  ) : (
                    Object.values(cars).reverse().slice(0, 8).map(car => (
                      <div key={car.plate} className={`p-4 rounded-2xl flex justify-between items-center transition-all ${isDarkMode ? 'bg-slate-800/40 hover:bg-slate-800 shadow-sm' : 'bg-slate-50'}`}>
                        <div className="font-bold font-mono text-lg tracking-widest">{car.plate}</div>
                        <div className="text-xs font-bold opacity-40">{format(car.entryTime, "HH:mm")}</div>
                      </div>
                    ))
                  )}
               </div>
            </div>
          </div>
        ) : (
          /* Monitor Tab */
          <div className="animate-in slide-in-from-right-10 duration-500 space-y-6">
             <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {Object.values(cars).map((car) => {
                  const progress = getStayProgress(car.entryTime);
                  const mins = Math.floor((Date.now() - car.entryTime) / 60000);
                  
                  return (
                    <div key={car.plate} className={`p-6 rounded-[2rem] border-2 shadow-2xl relative overflow-hidden transition-all hover:translate-y-[-4px] ${isDarkMode ? 'bg-slate-900 border-slate-800 shadow-black' : 'bg-white border-slate-200 shadow-slate-200'}`}>
                      <div className="flex justify-between items-start mb-6">
                        <div className="font-black text-3xl font-mono tracking-widest">{car.plate}</div>
                        <div className={`px-2 py-1 rounded-lg text-[10px] font-bold uppercase ${car.isEvent ? 'bg-purple-500 text-white' : 'bg-indigo-500 text-white'}`}>
                          {car.isEvent ? "Evento" : "Normal"}
                        </div>
                      </div>
                      
                      <div className="space-y-4">
                        <div className="flex justify-between text-xs font-bold opacity-60">
                          <div className="flex items-center gap-1"><Clock size={12} /> {format(car.entryTime, "HH:mm")}</div>
                          <div>Estadía: {Math.floor(mins / 60)}h {mins % 60}m</div>
                        </div>
                        
                        {!car.isEvent && (
                          <div className="space-y-1.5">
                            <div className="h-4 w-full bg-slate-800 rounded-full overflow-hidden border border-slate-700 shadow-inner">
                              <div 
                                className={`h-full transition-all duration-1000 ${progress > 90 ? 'bg-red-500 animate-pulse' : progress > 60 ? 'bg-orange-500' : 'bg-emerald-500'}`} 
                                style={{ width: `${progress}%` }} 
                              />
                            </div>
                            <div className="flex justify-between text-[10px] font-black opacity-30">
                              <span>0h</span>
                              <span>4h Max p/Min</span>
                            </div>
                          </div>
                        )}

                        <div className="pt-4 border-t border-dashed border-slate-800 mt-4 flex justify-between items-center">
                           <div className="font-bold text-lg">${calculateFee(car.entryTime, Date.now(), car.isEvent, car.eventFee).toLocaleString("es-CL")}</div>
                           <button onClick={() => processPlate(car.plate, "exit")} className={`p-2 rounded-xl ${isDarkMode ? 'bg-slate-800 text-slate-400 hover:text-white hover:bg-red-500/20' : 'bg-slate-100 text-slate-500 hover:bg-slate-200'}`}>
                              <LogOut size={16} />
                           </button>
                        </div>
                      </div>
                    </div>
                  );
                })}
             </div>
          </div>
        )}
      </main>

      {isCameraOpen && (
        <div className="fixed inset-0 z-[100] bg-black flex flex-col">
          <div className="p-6 flex justify-between items-center absolute top-0 inset-x-0 z-10 bg-gradient-to-b from-black via-black/80 to-transparent">
            <h2 className="text-white font-black text-2xl tracking-tighter uppercase italic">{cameraMode === "entry" ? "Check-In" : "Check-Out"}</h2>
            <button onClick={() => setIsCameraOpen(false)} className="w-12 h-12 bg-white/10 rounded-2xl flex items-center justify-center text-white backdrop-blur-xl border border-white/20"><X /></button>
          </div>
          <div className="flex-1 relative flex items-center justify-center">
            <Webcam audio={false} ref={webcamRef} screenshotFormat="image/jpeg" videoConstraints={{ facingMode: "environment" }} className="h-full w-full object-cover" />
            <div className="absolute inset-0 flex items-center justify-center p-10 pointer-events-none">
               <div className="w-full max-w-sm aspect-[16/9] border-2 border-emerald-400/50 rounded-3xl shadow-[0_0_0_1000px_rgba(0,0,0,0.6)] relative">
                  <div className="absolute inset-x-0 top-0 h-[2px] bg-emerald-400 shadow-[0_0_15px_emerald] animate-[scan_3s_infinite]" />
               </div>
            </div>
            {showManualInput && (
              <div className="absolute bottom-40 inset-x-0 px-6 z-20 animate-in slide-in-from-bottom-5">
                <form onSubmit={handleManualEntry} className="bg-white p-2 rounded-3xl flex shadow-2xl">
                  <input autoFocus type="text" value={manualPlate} onChange={e => setManualPlate(e.target.value)} placeholder="ABC-123" className="flex-1 bg-slate-100 rounded-2xl px-6 py-4 font-mono font-black text-xl uppercase text-slate-900 outline-none" />
                  <button type="submit" className="bg-slate-950 text-white px-6 rounded-2xl"><Check /></button>
                </form>
              </div>
            )}
          </div>
          <div className="h-44 bg-black px-10 flex items-center justify-between pb-8">
            <button onClick={() => setShowManualInput(!showManualInput)} className={`w-16 h-16 rounded-2xl flex items-center justify-center ${showManualInput ? 'bg-indigo-600 text-white' : 'bg-white/10 text-white'}`}><Search /></button>
            <button onClick={captureAndAnalyze} disabled={isAnalyzing} className="w-24 h-24 rounded-full border-4 border-emerald-400 flex items-center justify-center relative">
               {isAnalyzing ? <div className="w-6 h-6 border-4 border-white/20 border-t-white rounded-full animate-spin" /> : <div className="w-18 h-18 bg-white rounded-full shadow-lg" />}
            </button>
            <div className="w-16" />
          </div>
        </div>
      )}

      <style jsx global>{`
        @keyframes scan { 0%, 100% { top: 0; } 50% { top: 100%; } }
      `}</style>
    </div>
  );
}
