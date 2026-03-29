"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import Webcam from "react-webcam";
import { Camera, Search, LogOut, LogIn, CalendarDays, X, Check, Car, History } from "lucide-react";
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
  
  const [actionResult, setActionResult] = useState<{
    plate: string;
    action: "entered" | "exited";
    fee?: number;
    time?: string;
  } | null>(null);

  const webcamRef = useRef<Webcam>(null);

  useEffect(() => {
    const saved = localStorage.getItem("parked_cars");
    if (saved) {
      setCars(JSON.parse(saved));
    }
  }, []);

  const saveCars = (newCars: Record<string, ParkedCar>) => {
    setCars(newCars);
    localStorage.setItem("parked_cars", JSON.stringify(newCars));
  };

  const handleManualEntry = (e: React.FormEvent) => {
    e.preventDefault();
    if (!manualPlate) return;
    const cleanPlate = manualPlate.toUpperCase().trim();
    processPlate(cleanPlate, cameraMode);
    setShowManualInput(false);
    setManualPlate("");
  };

  const processPlate = (plateNumber: string, mode: "entry" | "exit") => {
    const now = Date.now();
    
    if (mode === "entry") {
      if (cars[plateNumber]) {
        alert("¡Ese auto ya está registrado en el estacionamiento!");
        setIsCameraOpen(false);
        return;
      }
      
      const newCar: ParkedCar = {
        plate: plateNumber,
        entryTime: now,
        isEvent: selectedEvent.amount !== null,
        eventFee: selectedEvent.amount || undefined
      };
      saveCars({ ...cars, [plateNumber]: newCar });
      
      setActionResult({
        plate: plateNumber,
        action: "entered",
        time: format(now, "HH:mm")
      });
      
    } else {
      const existingCar = cars[plateNumber];
      if (!existingCar) {
        alert("Auto no encontrado. Quizás nunca se registró el ingreso.");
        setIsCameraOpen(false);
        return;
      }
      
      const fee = calculateFee(existingCar.entryTime, now, existingCar.isEvent, existingCar.eventFee);
      
      const newCars = { ...cars };
      delete newCars[plateNumber];
      saveCars(newCars);
      
      setActionResult({
        plate: plateNumber,
        action: "exited",
        fee: fee,
        time: format(now - existingCar.entryTime, "HH:mm")
      });
    }
    
    setIsCameraOpen(false);
    
    setTimeout(() => {
      setActionResult(null);
    }, 6000);
  };

  const captureAndAnalyze = useCallback(async () => {
    if (!webcamRef.current) return;
    
    setIsAnalyzing(true);
    const imageSrc = webcamRef.current.getScreenshot();
    
    if (!imageSrc) {
      alert("Error al acceder a la captura");
      setIsAnalyzing(false);
      return;
    }

    try {
      const res = await fetch(imageSrc);
      const blob = await res.blob();
      
      const formData = new FormData();
      formData.append("image", blob, "capture.jpg");

      const response = await fetch("/api/detect", {
        method: "POST",
        body: formData
      });

      const data = await response.json();
      
      if (data.plate && data.plate !== "None") {
        processPlate(data.plate, cameraMode);
      } else {
        alert("No se pudo detectar ninguna patente. Intenta acercarte o usa el modo manual.");
      }

    } catch (err) {
      console.error(err);
      alert("Error conectando con el analizador de patentes. El servidor AI podría no estar disponible.");
    } finally {
      setIsAnalyzing(false);
    }
  }, [webcamRef, cameraMode, processPlate]);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200 font-sans pb-20">
      <header className="bg-slate-900 border-b border-indigo-500/30 sticky top-0 z-10 px-6 py-4 flex items-center justify-between shadow-xl">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-500/30">
            <Car className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-indigo-400 to-purple-400">
              Central Parking
            </h1>
            <p className="text-xs text-slate-400">Terminal MVP</p>
          </div>
        </div>
        <div className="text-right">
          <p className="font-mono text-sm text-indigo-300">{format(new Date(), "dd/MM/yyyy")}</p>
          <p className="text-xs text-slate-500">{Object.keys(cars).length} Vehículos</p>
        </div>
      </header>

      <main className="max-w-5xl mx-auto p-4 mt-4 lg:grid lg:grid-cols-12 lg:gap-8 items-start">
        {/* Left Column (Actions) */}
        <div className="lg:col-span-7 space-y-6">

        {actionResult && (
          <div className={`animate-in fade-in slide-in-from-top-4 p-4 rounded-2xl border backdrop-blur-md flex items-start gap-4 shadow-2xl ${actionResult.action === 'entered' ? 'bg-emerald-500/10 border-emerald-500/50' : 'bg-indigo-500/10 border-indigo-500/50'}`}>
             <div className={`p-3 rounded-full ${actionResult.action === 'entered' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-indigo-500/20 text-indigo-400'}`}>
               {actionResult.action === 'entered' ? <LogIn size={24} /> : <LogOut size={24} />}
             </div>
             <div>
               <h3 className="font-bold text-lg text-white">
                 Patente {actionResult.plate}
               </h3>
               {actionResult.action === 'entered' ? (
                 <p className="text-emerald-300/80">Ingreso registrado a las {actionResult.time}</p>
               ) : (
                 <>
                   <p className="text-indigo-300/80">Salida registrada exitosamente</p>
                   {actionResult.fee !== undefined && (
                     <p className="text-2xl font-black text-white mt-1">${actionResult.fee.toLocaleString("es-CL")}</p>
                   )}
                 </>
               )}
             </div>
          </div>
        )}

        <section className="bg-slate-900/50 p-5 rounded-3xl border border-slate-800 shadow-xl">
          <div className="flex items-center gap-2 mb-4">
            <CalendarDays className="w-5 h-5 text-purple-400" />
            <h2 className="text-slate-300 font-medium">Modo de Operación</h2>
          </div>
          
          <div className="grid grid-cols-2 gap-3">
            {EVENT_FEES.map((mode) => (
              <button
                key={mode.id}
                onClick={() => setSelectedEvent(mode)}
                className={`p-3 rounded-2xl text-left transition-all duration-300 ${selectedEvent.id === mode.id ? 'bg-indigo-500/20 border-indigo-500 text-indigo-300 border shadow-inner shadow-indigo-500/20' : 'bg-slate-800/50 border-transparent text-slate-400 border hover:bg-slate-800'}`}
              >
                <div className="font-semibold text-sm">{mode.name}</div>
                <div className="text-xs opacity-70">
                  {mode.amount ? `$${mode.amount.toLocaleString("es-CL")}` : "Por minuto"}
                </div>
              </button>
            ))}
          </div>
        </section>

        <section className="grid grid-cols-2 gap-4">
          <button
            onClick={() => { setCameraMode("entry"); setIsCameraOpen(true); }}
            className="group relative overflow-hidden flex flex-col items-center justify-center gap-3 p-6 rounded-3xl bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/30 transition-all active:scale-95"
          >
            <div className="p-4 rounded-full bg-emerald-500/20 text-emerald-400 ring-4 ring-emerald-500/10">
              <Camera size={32} />
            </div>
            <span className="font-semibold text-emerald-300">Dar Entrada</span>
          </button>

          <button
            onClick={() => { setCameraMode("exit"); setIsCameraOpen(true); }}
            className="group relative overflow-hidden flex flex-col items-center justify-center gap-3 p-6 rounded-3xl bg-indigo-500/10 hover:bg-indigo-500/20 border border-indigo-500/30 transition-all active:scale-95"
          >
            <div className="p-4 rounded-full bg-indigo-500/20 text-indigo-400 ring-4 ring-indigo-500/10">
              <LogOut size={32} />
            </div>
            <span className="font-semibold text-indigo-300">Cobrar Salida</span>
          </button>
        </section>

        <section className="pt-4">
          <h2 className="text-slate-400 text-sm font-semibold mb-3 px-2 uppercase tracking-wider">Vehículos Ingresados</h2>
          {Object.keys(cars).length === 0 ? (
            <div className="text-center p-8 bg-slate-900/30 rounded-3xl border border-slate-800/50 border-dashed">
              <History className="w-8 h-8 mx-auto text-slate-600 mb-2" />
              <p className="text-slate-500 text-sm">No hay vehículos ingresados</p>
            </div>
          ) : (
            <ul className="space-y-3">
              {Object.values(cars).reverse().map((car) => (
                <li key={car.plate} className="bg-slate-900/50 p-4 rounded-2xl flex items-center justify-between border border-slate-800 backdrop-blur-sm">
                  <div className="flex items-center gap-4">
                    <div className="font-mono text-lg font-bold bg-slate-800/80 px-3 py-1.5 rounded-xl border-l-4 border-indigo-500 tracking-widest text-white shadow-inner">
                      {car.plate}
                    </div>
                    <div className="flex flex-col">
                      <span className="text-xs text-slate-400">
                        {format(car.entryTime, "HH:mm")}
                      </span>
                      {car.isEvent && (
                        <span className="text-[10px] text-purple-400 uppercase tracking-widest font-bold">
                          Evento vip
                        </span>
                      )}
                    </div>
                  </div>
                  <button 
                    onClick={() => processPlate(car.plate, "exit")}
                    className="p-2.5 rounded-xl bg-slate-800 hover:bg-indigo-500/20 text-slate-400 hover:text-indigo-400 transition-colors"
                  >
                    <LogOut size={18} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </main>

      {isCameraOpen && (
        <div className="fixed inset-0 z-50 bg-black flex flex-col">
          <div className="p-4 flex justify-between items-center absolute top-0 left-0 right-0 z-10 bg-gradient-to-b from-black/80 to-transparent">
            <h2 className="text-white font-semibold text-lg drop-shadow-md">
              {cameraMode === "entry" ? "Escanear Ingreso" : "Escanear Salida"}
            </h2>
            <button 
              onClick={() => setIsCameraOpen(false)}
              className="p-2 bg-white/10 rounded-full backdrop-blur text-white hover:bg-white/20 transition-colors"
            >
              <X size={24} />
            </button>
          </div>
          
          <div className="flex-1 relative bg-black flex items-center justify-center overflow-hidden">
            <Webcam
              audio={false}
              ref={webcamRef}
              screenshotFormat="image/jpeg"
              videoConstraints={{ facingMode: "environment" }}
              className="object-cover h-full w-full"
            />
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <div className="w-64 h-32 border-2 border-white/50 rounded-xl relative">
                  <div className="absolute -top-1 -left-1 w-6 h-6 border-t-4 border-l-4 border-emerald-400 rounded-tl-lg" />
                  <div className="absolute -top-1 -right-1 w-6 h-6 border-t-4 border-r-4 border-emerald-400 rounded-tr-lg" />
                  <div className="absolute -bottom-1 -left-1 w-6 h-6 border-b-4 border-l-4 border-emerald-400 rounded-bl-lg" />
                  <div className="absolute -bottom-1 -right-1 w-6 h-6 border-b-4 border-r-4 border-emerald-400 rounded-br-lg" />
              </div>
            </div>
            
            {showManualInput && (
              <div className="absolute inset-x-0 bottom-40 px-6 animate-in slide-in-from-bottom-4 z-20">
                <form onSubmit={handleManualEntry} className="bg-slate-900/90 backdrop-blur p-4 rounded-3xl border border-slate-700 shadow-2xl flex gap-2">
                   <input
                     autoFocus
                     type="text"
                     value={manualPlate}
                     onChange={(e) => setManualPlate(e.target.value)}
                     placeholder="Ingresa Patente (Ej: ABCD12)"
                     className="flex-1 bg-black/50 border border-slate-700 rounded-xl px-4 py-3 text-white font-mono uppercase focus:ring-2 ring-indigo-500 outline-none placeholder:text-slate-500 placeholder:normal-case font-bold tracking-widest text-lg"
                   />
                   <button type="submit" className="bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl px-4 font-bold flex items-center justify-center transition-all">
                     <Check />
                   </button>
                </form>
              </div>
            )}
          </div>
          
          <div className="h-40 bg-black p-6 flex items-center justify-around pb-10">
            <button 
               onClick={() => setShowManualInput(!showManualInput)}
               className="p-4 rounded-full bg-slate-800 text-slate-300 hover:bg-slate-700 transition"
            >
              <Search size={24} />
            </button>
            <button
              onClick={captureAndAnalyze}
              disabled={isAnalyzing}
              className={`w-20 h-20 rounded-full border-4 flex items-center justify-center transition-all ${isAnalyzing ? 'border-slate-600 bg-slate-800 scale-95' : 'border-emerald-400 bg-emerald-400/20 active:scale-90 active:bg-emerald-400/40'}`}
            >
              {isAnalyzing ? (
                <div className="w-8 h-8 border-4 border-white/20 border-t-white rounded-full animate-spin" />
              ) : (
                <div className="w-16 h-16 rounded-full bg-white transition-transform" />
              )}
            </button>
            <div className="w-14" />
          </div>
        </div>
      )}
    </div>
  );
}
