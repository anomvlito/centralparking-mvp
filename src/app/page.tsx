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
  
  // Advanced Camera States
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
      alert("Error con el backend.");
    } finally {
      setIsCameraOpen(false);
      setTimeout(() => setActionResult(null), 8000);
    }
  };

  const captureAndAnalyze = useCallback(async () => {
    if (!webcamRef.current) return;
    setIsAnalyzing(true);
    
    // Get high-res canvas with digital zoom
    const video = webcamRef.current.video;
    if (!video) return;

    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // We can use Full HD or the natural resolution
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;

    // Apply digital zoom and center crop logic
    const sw = video.videoWidth / zoomLevel;
    const sh = video.videoHeight / zoomLevel;
    const sx = (video.videoWidth - sw) / 2;
    const sy = (video.videoHeight - sh) / 2;

    ctx.drawImage(video, sx, sy, sw, sh, 0, 0, canvas.width, canvas.height);
    
    canvas.toBlob(async (blob) => {
      if (!blob) {
        setIsAnalyzing(false);
        return;
      }
      
      const formData = new FormData();
      formData.append("image", blob, "capture.jpg");

      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || "/api";
        const response = await fetch(`${apiUrl}/detect`, { method: "POST", body: formData });
        const data = await response.json();
        
        if (data.plate && data.plate !== "None") {
          processPlate(data.plate, cameraMode);
        } else {
          alert("No se detectó la patente. Prueba con más ZOOM o moviendo el celular.");
        }
      } catch (err) {
        console.error(err);
        alert("Error de motor AI.");
      } finally {
        setIsAnalyzing(false);
      }
    }, "image/jpeg", 0.95);

  }, [webcamRef, cameraMode, zoomLevel, processPlate]);

  return (
    <div className={`min-h-screen transition-colors duration-500 font-sans pb-20 ${isDarkMode ? 'bg-slate-950 text-slate-200' : 'bg-slate-50 text-slate-900'}`}>
      <header className={`sticky top-0 z-30 px-6 py-4 flex items-center justify-between border-b backdrop-blur-md transition-all ${isDarkMode ? 'bg-slate-900/80 border-indigo-500/30 shadow-2xl shadow-black/30' : 'bg-white/80 border-slate-200 shadow-sm'}`}>
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-500/30">
            <Car className="w-6 h-6 text-white" />
          </div>
          <div className="hidden sm:block">
            <h1 className="text-2xl font-black bg-clip-text text-transparent bg-gradient-to-r from-indigo-500 to-purple-600">
              Central Parking
            </h1>
            <div className="flex items-center gap-2 mt-0.5">
              <span className={`w-2 h-2 rounded-full ${process.env.NEXT_PUBLIC_API_URL ? 'bg-emerald-500' : 'bg-yellow-500'}`} />
              <span className="text-[10px] font-bold uppercase opacity-60">Control AI v2.1</span>
            </div>
          </div>
        </div>
        
        <div className="flex items-center gap-4">
          <nav className={`flex bg-slate-800/10 p-1 rounded-xl gap-0.5 border ${isDarkMode ? 'border-slate-800' : 'border-slate-100'}`}>
            {["actions", "monitor", "stats"].map(tab => (
              <button 
                key={tab}
                onClick={() => setActiveTab(tab as any)}
                className={`px-3 sm:px-4 py-1.5 rounded-lg font-bold text-[9px] sm:text-[10px] uppercase tracking-widest transition-all ${activeTab === tab ? 'bg-indigo-600 text-white shadow-lg' : 'opacity-40 hover:opacity-100'}`}
              >
                {tab === 'actions' ? (window.innerWidth < 640 ? <Activity size={14}/> : 'Control') : tab === 'monitor' ? (window.innerWidth < 640 ? <Users size={14}/> : 'Monitor') : (window.innerWidth < 640 ? <TrendingUp size={14}/> : 'Cierre')}
              </button>
            ))}
          </nav>
          <button onClick={toggleTheme} className={`p-2.5 rounded-xl transition-all ${isDarkMode ? 'bg-slate-800 text-yellow-400' : 'bg-slate-100 text-slate-600'}`}>
            {isDarkMode ? <Sun size={20} /> : <Moon size={20} />}
          </button>
        </div>
      </header>

      <main className="max-w-6xl mx-auto p-4 mt-6">
        
        {activeTab === "actions" && (
          <div className="lg:grid lg:grid-cols-12 lg:gap-8 animate-in fade-in duration-500">
            {/* Quick Stats Summary */}
            <div className="lg:col-span-12 mb-8 hidden sm:grid grid-cols-4 gap-4">
              {[
                { label: 'Ingresos', val: `$${stats.today_income.toLocaleString("es-CL")}`, icon: TrendingUp, color: 'text-emerald-500' },
                { label: 'Entradas', val: stats.today_entries, icon: LogIn, color: 'text-indigo-500' },
                { label: 'Salidas', val: stats.today_exits, icon: LogOut, color: 'text-purple-500' },
                { label: 'Ocupación', val: stats.parked_now, icon: Car, color: 'text-blue-500' }
              ].map((s, i) => (
                <div key={i} className={`p-6 rounded-[2rem] border transition-all ${isDarkMode ? 'bg-slate-900 border-slate-800' : 'bg-white border-slate-100 shadow-sm'}`}>
                   <s.icon className={`${s.color} mb-3`} size={20} />
                   <div className="text-2xl font-black">{s.val}</div>
                   <div className="text-[10px] uppercase font-bold opacity-40">{s.label} Hoy</div>
                </div>
              ))}
            </div>

            <div className="lg:col-span-7 space-y-6">
               {actionResult && (
                 <div className={`p-8 rounded-[2.5rem] border-2 shadow-2xl flex items-center gap-6 scale-in-center ${actionResult.action === 'entered' ? 'bg-emerald-500/10 border-emerald-500/30' : actionResult.action === 'deleted' ? 'bg-red-500/10 border-red-500/30' : 'bg-indigo-500/10 border-indigo-500/30'}`}>
                    <div className={`p-5 rounded-2xl shadow-lg ${actionResult.action === 'entered' ? 'bg-emerald-500 text-white' : actionResult.action === 'deleted' ? 'bg-red-500 text-white' : 'bg-indigo-500 text-white'}`}>
                      {actionResult.action === 'entered' ? <LogIn size={32} /> : actionResult.action === 'deleted' ? <Trash2 size={32} /> : <LogOut size={32} />}
                    </div>
                    <div className="flex-1">
                      <p className="text-[10px] font-black uppercase tracking-[0.3em] opacity-40 mb-1">Operación Exitosa</p>
                      <h3 className="font-black text-4xl tracking-tighter">{actionResult.plate}</h3>
                    </div>
                    {actionResult.fee !== undefined && (
                      <div className="text-right">
                        <p className="text-xl font-black text-indigo-500">${actionResult.fee.toLocaleString("es-CL")}</p>
                        <p className="text-[10px] opacity-40 uppercase font-black">Cobro Final</p>
                      </div>
                    )}
                 </div>
               )}

               <section className={`p-8 rounded-[2.5rem] border shadow-2xl relative overflow-hidden group ${isDarkMode ? 'bg-slate-900 border-slate-800' : 'bg-white border-slate-200'}`}>
                  <div className="flex items-center gap-3 mb-6">
                    <div className={`p-2 rounded-lg ${isDarkMode ? 'bg-indigo-500/10 text-indigo-400' : 'bg-indigo-100 text-indigo-600'}`}>
                      <DollarSign size={20} />
                    </div>
                    <h2 className="font-black text-xl tracking-tight uppercase">Modo de Tarifado</h2>
                  </div>
                  <div className="grid grid-cols-2 gap-3 relative z-10">
                    {EVENT_FEES.map(fee => (
                      <button 
                        key={fee.id} 
                        onClick={() => setSelectedEvent(fee)} 
                        className={`p-4 rounded-2xl text-left border-2 transition-all relative overflow-hidden ${selectedEvent.id === fee.id ? 'bg-indigo-600 border-indigo-500 text-white shadow-xl shadow-indigo-600/30' : isDarkMode ? 'bg-slate-800/50 border-transparent hover:border-slate-700' : 'bg-slate-50 border-transparent hover:border-slate-200 shadow-sm'}`}
                      >
                        <div className="font-bold text-sm">{fee.name}</div>
                        <div className="text-[10px] font-mono opacity-80 mt-1">{fee.amount ? `$${fee.amount.toLocaleString("es-CL")}` : "Precio x Minuto"}</div>
                        {selectedEvent.id === fee.id && <Check className="absolute top-2 right-2 opacity-50" size={12} />}
                      </button>
                    ))}
                  </div>
                  <div className="absolute top-0 right-0 w-32 h-32 bg-indigo-500/5 rounded-full blur-3xl -mr-10 -mt-10 group-hover:scale-110 transition-transform" />
               </section>

               <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <button onClick={() => { setCameraMode("entry"); setIsCameraOpen(true); }} className={`group p-8 rounded-[2.5rem] border-2 flex items-center justify-between transition-all active:scale-[0.98] ${isDarkMode ? 'bg-emerald-500/5 border-emerald-500/20 hover:bg-emerald-500/10' : 'bg-emerald-50 border-emerald-100'}`}>
                    <div className="text-left">
                      <span className="text-[10px] font-black opacity-40 uppercase block mb-1">Cámara Pro</span>
                      <span className={`font-black text-2xl ${isDarkMode ? 'text-emerald-400' : 'text-emerald-700'}`}>ENTRADA</span>
                    </div>
                    <div className="p-5 rounded-[1.5rem] bg-emerald-500 text-white shadow-lg transition-transform group-hover:rotate-6"><LogIn size={28} /></div>
                  </button>
                  <button onClick={() => { setCameraMode("exit"); setIsCameraOpen(true); }} className={`group p-8 rounded-[2.5rem] border-2 flex items-center justify-between transition-all active:scale-[0.98] ${isDarkMode ? 'bg-indigo-500/5 border-indigo-500/20 hover:bg-indigo-500/10' : 'bg-indigo-50 border-indigo-100 shadow-sm'}`}>
                    <div className="text-left">
                      <span className="text-[10px] font-black opacity-40 uppercase block mb-1">Cámara Pro</span>
                      <span className={`font-black text-2xl ${isDarkMode ? 'text-indigo-400' : 'text-indigo-700'}`}>SALIDA</span>
                    </div>
                    <div className="p-5 rounded-[1.5rem] bg-indigo-500 text-white shadow-lg transition-transform group-hover:-rotate-6"><LogOut size={28} /></div>
                  </button>
               </div>
            </div>

            {/* Recent History Sidebar */}
            <div className={`lg:col-span-12 xl:col-span-5 mt-8 lg:mt-0 p-8 rounded-[2.5rem] border shadow-2xl relative overflow-hidden h-[fit-content] ${isDarkMode ? 'bg-slate-900 border-slate-800' : 'bg-white border-slate-100'}`}>
               <div className="flex items-center justify-between mb-8 pb-4 border-b border-dashed border-slate-800">
                  <h2 className="text-xs font-black uppercase tracking-[0.3em] opacity-40">Actividad Reciente</h2>
                  <div className="flex gap-1.5">
                     <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-[pulse_1.5s_infinite]" />
                     <div className="w-1.5 h-1.5 rounded-full bg-emerald-500/60 animate-[pulse_1.5s_infinite_0.2s]" />
                     <div className="w-1.5 h-1.5 rounded-full bg-emerald-500/30 animate-[pulse_1.5s_infinite_0.4s]" />
                  </div>
               </div>
               <div className="space-y-3 max-h-[500px] overflow-y-auto pr-2 custom-scrollbar">
                  {Object.values(cars).length === 0 ? (
                    <div className="text-center py-20 bg-slate-800/10 rounded-3xl border border-dashed border-slate-800/40 opacity-30 italic text-sm">Escanea un vehículo para comenzar</div>
                  ) : (
                    Object.values(cars).reverse().map(car => (
                      <div key={car.plate} className={`group p-4 rounded-2xl flex justify-between items-center transition-all ${isDarkMode ? 'bg-slate-800/30 hover:bg-slate-800' : 'bg-slate-50 border border-slate-100 hover:shadow-md'}`}>
                        <div className="flex items-center gap-4">
                           <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${isDarkMode ? 'bg-slate-700 text-indigo-400' : 'bg-white text-indigo-500 border border-slate-100 shadow-sm'}`}>
                              <Car size={16} />
                           </div>
                           <div>
                              <div className="font-black font-mono tracking-[0.15em] text-lg">{car.plate}</div>
                              <div className="text-[10px] font-bold opacity-30 mt-0.5 uppercase tracking-widest">{format(car.entryTime, "HH:mm")} • Entró</div>
                           </div>
                        </div>
                        <button onClick={() => deleteCar(car.plate)} className="p-2.5 text-red-500/30 hover:text-red-500 hover:bg-red-500/10 rounded-xl transition-all opacity-0 group-hover:opacity-100">
                           <Trash2 size={16} />
                        </button>
                      </div>
                    ))
                  )}
               </div>
            </div>
          </div>
        )}

        {activeTab === "monitor" && (
          <div className="animate-in slide-in-from-right-10 duration-500">
             <div className="flex items-center justify-between mb-8 px-4">
                <h2 className="text-2xl font-black uppercase tracking-tight italic border-l-4 border-indigo-500 pl-4">Monitor de Estadía</h2>
                <div className="text-[10px] font-bold uppercase tracking-widest bg-indigo-500 text-white px-3 py-1 rounded-full">{Object.values(cars).length} Vehículos</div>
             </div>
             <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                {Object.values(cars).map((car) => {
                  const progress = getStayProgress(car.entryTime);
                  const mins = Math.floor((Date.now() - car.entryTime) / 60000);
                  const fee = calculateFee(car.entryTime, Date.now(), car.isEvent, car.eventFee);
                  
                  return (
                    <div key={car.plate} className={`group p-8 rounded-[2.5rem] border-2 transition-all hover:-translate-y-2 hover:shadow-2xl ${isDarkMode ? 'bg-slate-900 border-slate-800 shadow-black/40' : 'bg-white border-slate-100 shadow-xl shadow-slate-200/50'}`}>
                      <div className="flex justify-between items-start mb-6">
                        <div className="space-y-1">
                           <div className="font-black text-4xl font-mono tracking-tighter leading-none">{car.plate}</div>
                           <div className={`px-2 py-0.5 rounded text-[8px] font-black uppercase inline-block ${car.isEvent ? 'bg-purple-600 text-white' : 'bg-indigo-600 text-white'}`}>
                             {car.isEvent ? "Evento" : "Tarifa Normal"}
                           </div>
                        </div>
                        <button onClick={() => deleteCar(car.plate)} className="p-2 rounded-xl text-red-500/20 hover:text-red-500 hover:bg-red-500/10 transition-all"><Trash2 size={16} /></button>
                      </div>
                      
                      <div className="space-y-6">
                        <div className="grid grid-cols-2 gap-4">
                           <div className="space-y-0.5">
                             <p className="text-[9px] font-black uppercase tracking-widest opacity-40">Tiempo</p>
                             <p className="font-bold text-xl tabular-nums">{Math.floor(mins / 60)}h {mins % 60}m</p>
                           </div>
                           <div className="text-right space-y-0.5">
                             <p className="text-[9px] font-black uppercase tracking-widest opacity-40">Monto</p>
                             <p className={`font-black text-2xl text-indigo-500 tabular-nums`}>${fee.toLocaleString("es-CL")}</p>
                           </div>
                        </div>
                        
                        {!car.isEvent && (
                          <div className="space-y-1.5">
                             <div className="h-2.5 bg-slate-800/10 rounded-full overflow-hidden border border-white/5 relative">
                                <div className={`absolute inset-0 opacity-20 bg-gradient-to-r from-transparent via-white to-transparent animate-[shimmer_2s_infinite]`} style={{ width: '40%' }} />
                                <div className={`h-full transition-all duration-1000 ${progress > 90 ? 'bg-red-500' : progress > 60 ? 'bg-orange-500' : 'bg-emerald-500'}`} style={{ width: `${progress}%` }} />
                             </div>
                             <div className="flex justify-between text-[8px] font-black opacity-30 uppercase tracking-tighter">
                                <span>Entrada {format(car.entryTime, "HH:mm")}</span>
                                <span>Max 4H p/Min Control</span>
                             </div>
                          </div>
                        )}
                        <button onClick={() => processPlate(car.plate, "exit")} className="w-full py-4 rounded-2xl bg-indigo-600 hover:bg-indigo-500 text-white font-black text-xs tracking-[0.2em] transition-all shadow-lg shadow-indigo-600/20 active:scale-95">COBRAR SALIDA</button>
                      </div>
                    </div>
                  );
                })}
             </div>
          </div>
        )}

        {activeTab === "stats" && (
           <div className="animate-in zoom-in-95 duration-700 max-w-4xl mx-auto space-y-10">
              <div className={`p-12 sm:p-20 rounded-[4rem] border-2 text-center relative overflow-hidden ${isDarkMode ? 'bg-slate-900 border-white/5 shadow-[0_0_100px_rgba(79,70,229,0.15)]' : 'bg-white border-slate-100 shadow-2xl'}`}>
                 <div className="absolute inset-0 bg-gradient-to-br from-indigo-500/5 via-transparent to-transparent pointer-events-none" />
                 <h2 className="text-xs font-black uppercase tracking-[0.5em] opacity-40 mb-8">Cuadratura Diaria ({format(new Date(), "dd/MM")})</h2>
                 <div className="text-8xl sm:text-9xl font-black italic tracking-tighter text-indigo-500 mb-4 drop-shadow-2xl tabular-nums">
                    ${stats.today_income.toLocaleString("es-CL")}
                 </div>
                 <div className="h-px w-24 bg-indigo-500/50 mx-auto my-10" />
                 <div className="flex justify-center gap-8 sm:gap-20 items-center">
                    <div className="text-center group">
                       <p className="text-3xl sm:text-4xl font-black group-hover:scale-110 transition-transform">{stats.today_entries}</p>
                       <p className="text-[10px] font-bold uppercase opacity-40 mt-1 tracking-widest">Entradas</p>
                    </div>
                    <div className="text-center group">
                       <p className="text-3xl sm:text-4xl font-black group-hover:scale-110 transition-transform">{stats.today_exits}</p>
                       <p className="text-[10px] font-bold uppercase opacity-40 mt-1 tracking-widest">Salidas</p>
                    </div>
                    <div className="text-center group">
                       <p className="text-3xl sm:text-4xl font-black group-hover:scale-110 transition-transform text-emerald-500">{stats.parked_now}</p>
                       <p className="text-[10px] font-bold uppercase opacity-40 mt-1 tracking-widest">Presentes</p>
                    </div>
                 </div>
              </div>
              
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
                 <button className={`p-12 rounded-[3rem] border-2 font-black tracking-[0.3em] uppercase text-[10px] transition-all hover:border-indigo-500/50 hover:bg-slate-800/20 active:scale-95 ${isDarkMode ? 'bg-slate-900 border-slate-800' : 'bg-white border-slate-100 shadow-md'}`}>Generar Reporte Excel</button>
                 <button onClick={() => window.print()} className={`p-12 rounded-[3rem] border-2 font-black tracking-[0.3em] uppercase text-[10px] transition-all hover:border-indigo-500/50 hover:bg-slate-800/20 active:scale-95 ${isDarkMode ? 'bg-slate-900 border-slate-800' : 'bg-white border-slate-100 shadow-md'}`}>Imprimir Resumen Cierre</button>
              </div>
           </div>
        )}
      </main>

      {/* Advanced Camera Pro Interface */}
      {isCameraOpen && (
        <div className="fixed inset-0 z-[100] bg-black flex flex-col font-sans select-none overflow-hidden">
          {/* Top Info Bar */}
          <div className="p-8 pb-12 flex justify-between items-start absolute top-0 inset-x-0 z-20 bg-gradient-to-b from-black via-black/90 to-transparent">
            <div className="flex flex-col gap-1">
              <div className="flex items-center gap-3">
                <div className={`w-3 h-3 rounded-full ${cameraMode === 'entry' ? 'bg-emerald-500' : 'bg-indigo-500'} animate-pulse shadow-[0_0_10px_rgba(16,185,129,0.8)]`} />
                <h2 className="text-white font-black text-2xl tracking-[0.1em] uppercase italic underline underline-offset-8 decoration-white/20">
                  {cameraMode === "entry" ? "Check-In" : "Check-Out"} MODE
                </h2>
              </div>
              <p className="text-white/40 text-[10px] font-bold uppercase tracking-widest pl-6">Sensor de Precisión AI • {zoomLevel.toFixed(1)}x Zoom</p>
            </div>
            <button onClick={() => setIsCameraOpen(false)} className="w-16 h-16 rounded-3xl bg-white/5 border border-white/10 flex items-center justify-center text-white active:scale-90 transition-all hover:bg-white/10 group">
              <X size={32} className="group-hover:rotate-90 transition-transform" />
            </button>
          </div>
          
          <div className="flex-1 relative flex items-center justify-center bg-slate-950">
            {cameraError ? (
               <div className="text-center p-10 text-white space-y-4">
                  <AlertCircle size={48} className="mx-auto text-red-500" />
                  <p className="font-bold text-xl">{cameraError}</p>
                  <button onClick={() => setIsCameraOpen(false)} className="bg-white text-black px-6 py-2 rounded-xl font-black">CERRAR</button>
               </div>
            ) : (
              <Webcam 
                audio={false} 
                ref={webcamRef} 
                screenshotFormat="image/jpeg" 
                videoConstraints={{ 
                  facingMode: "environment",
                  width: { ideal: 1920 },
                  height: { ideal: 1080 } 
                }} 
                onUserMediaError={() => setCameraError("No se pudo acceder a la cámara trasera")}
                className="h-full w-full object-cover transition-transform duration-300" 
                style={{ transform: `scale(${zoomLevel})` }}
              />
            )}
            
            {/* Viewfinder Layer */}
            <div className="absolute inset-0 flex flex-col items-center justify-center p-12 pointer-events-none">
               <div className="w-full max-w-lg aspect-[3/1] rounded-[2.5rem] relative">
                  <div className="absolute -inset-[2px] border-2 border-white/10 rounded-[inherit]" />
                  <div className="absolute -inset-1 border border-emerald-400 opacity-20 rounded-[inherit]" />
                  
                  {/* Scanning Laser */}
                  <div className="absolute inset-x-0 top-0 h-[2px] bg-emerald-400 shadow-[0_0_20px_emerald] animate-[scan_3s_ease-in-out_infinite]" />
                  
                  {/* Corners */}
                  <div className="absolute -top-6 -left-6 w-16 h-16 border-t-[10px] border-l-[10px] border-emerald-400 rounded-tl-4xl shadow-[-10px_-10px_20px_rgba(52,211,153,0.3)]" />
                  <div className="absolute -top-6 -right-6 w-16 h-16 border-t-[10px] border-r-[10px] border-emerald-400 rounded-tr-4xl shadow-[10px_-10px_20px_rgba(52,211,153,0.3)]" />
                  <div className="absolute -bottom-6 -left-6 w-16 h-16 border-b-[10px] border-l-[10px] border-emerald-400 rounded-bl-4xl shadow-[-10px_10px_20px_rgba(52,211,153,0.3)]" />
                  <div className="absolute -bottom-6 -right-6 w-16 h-16 border-b-[10px] border-r-[10px] border-emerald-400 rounded-br-4xl shadow-[10px_10px_20px_rgba(52,211,153,0.3)]" />
                  
                  <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 flex items-center gap-2 bg-black/40 backdrop-blur px-3 py-1 rounded-full border border-white/10 scale-90 opacity-40">
                    <Activity size={14} className="text-emerald-400" />
                    <span className="text-white text-[10px] font-black uppercase tracking-[0.2em]">Encuadre Activo</span>
                  </div>
               </div>
            </div>

            {/* Manual Controls Toolbar */}
            <div className="absolute inset-x-0 bottom-44 px-8 flex justify-between items-center z-20">
               <div className="flex bg-black/60 backdrop-blur p-2 rounded-2xl border border-white/10 gap-x-2">
                 <button onClick={() => setZoomLevel(prev => Math.max(1, prev - 0.5))} className="w-12 h-12 flex items-center justify-center rounded-xl bg-white/5 hover:bg-white/15 text-white transition-all active:scale-90"><ZoomOut size={20} /></button>
                 <div className="flex items-center px-4 font-black text-white text-xs tabular-nums">{zoomLevel.toFixed(1)}x</div>
                 <button onClick={() => setZoomLevel(prev => Math.min(3, prev + 0.5))} className="w-12 h-12 flex items-center justify-center rounded-xl bg-white/5 hover:bg-white/15 text-white transition-all active:scale-90"><ZoomIn size={20} /></button>
               </div>
               
               <button onClick={() => setShowManualInput(!showManualInput)} className={`w-14 h-14 rounded-2xl flex items-center justify-center transition-all border border-white/20 ${showManualInput ? 'bg-indigo-600 text-white' : 'bg-black/60 text-white backdrop-blur'}`}>
                 <Search size={24} />
               </button>
            </div>

            {showManualInput && (
              <div className="absolute bottom-60 inset-x-0 px-10 z-30 animate-in slide-in-from-bottom-10 duration-300">
                <form onSubmit={handleManualEntry} className="bg-white p-2.5 rounded-[2.5rem] flex shadow-2xl scale-110">
                  <input autoFocus type="text" value={manualPlate} onChange={e => setManualPlate(e.target.value)} placeholder="ABCD-12" className="flex-1 bg-slate-100 rounded-[2rem] px-8 py-5 font-mono font-black text-2xl uppercase text-slate-900 outline-none tracking-widest" />
                  <button type="submit" className="bg-slate-950 text-white w-20 rounded-[2rem] flex items-center justify-center active:scale-95 shadow-xl"><Check size={32} /></button>
                </form>
              </div>
            )}
          </div>

          <div className="h-48 bg-slate-950 px-12 flex items-center justify-center pb-12 relative">
            <div className="absolute top-4 inset-x-12 h-px bg-gradient-to-r from-transparent via-white/10 to-transparent" />
            <div className="w-20 hidden sm:block" />
            
            <button
              onClick={captureAndAnalyze}
              disabled={isAnalyzing}
              className={`relative group w-28 h-28 rounded-full flex items-center justify-center transition-all ${isAnalyzing ? 'scale-90 opacity-50' : 'active:scale-75'}`}
            >
               {/* Shutter Ring */}
               <div className={`absolute -inset-4 rounded-full border-2 border-emerald-400/20 ${isAnalyzing ? 'animate-ping' : ''}`} />
               <div className={`absolute -inset-1 rounded-full border-4 border-emerald-400 ${isAnalyzing ? 'animate-spin border-t-transparent' : 'opacity-30'}`} />
               
               {/* Shutter Button */}
               <div className={`w-24 h-24 rounded-full flex items-center justify-center shadow-2xl transition-all ${isAnalyzing ? 'bg-slate-900' : 'bg-white shadow-[0_0_50px_rgba(255,255,255,0.2)]'}`}>
                  {isAnalyzing ? <div className="w-8 h-8 rounded bg-emerald-400 animate-pulse" /> : <div className="w-20 h-20 rounded-full border-2 border-slate-200" />}
               </div>
            </button>
            <div className="w-20 hidden sm:block" />
          </div>
        </div>
      )}

      <style jsx global>{`
        @keyframes scan { 0%, 100% { top: 10%; opacity: 0.2; } 50% { top: 90%; opacity: 1; } }
        @keyframes shimmer { 0% { left: -100%; } 100% { left: 200%; } }
        .custom-scrollbar::-webkit-scrollbar { width: 4px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(99, 102, 241, 0.2); border-radius: 10px; }
        .scale-in-center { animation: scale-in-center 0.5s cubic-bezier(0.25, 0.46, 0.45, 0.94) both; }
        @keyframes scale-in-center { 0% { transform: scale(0.9); opacity: 0; } 100% { transform: scale(1); opacity: 1; } }
        .tab-button-active { @apply bg-indigo-600 text-white shadow-lg; }
      `}</style>
    </div>
  );
}
