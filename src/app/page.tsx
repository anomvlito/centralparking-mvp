"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { format, addDays, subDays, isToday, parseISO } from "date-fns";
import { es } from "date-fns/locale";
import {
  Car, AlertTriangle, CheckCircle2, HelpCircle, Upload,
  Calendar, RefreshCw, Image as ImageIcon, X,
  ChevronLeft, ChevronRight, LogIn, LogOut, Eye, EyeOff, User,
} from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "https://2.24.69.49.nip.io";

// ─── Types ────────────────────────────────────────────────────────────────────

type HistoryEntry = {
  session_id: number; timestamp: string; plate: string; action: string;
  status: string; fee: number; confidence: number; image_url: string | null;
};
type Stats = {
  today_income: number; today_entries: number;
  today_exits: number; parked_now: number;
};
type ReconcileResult = {
  date: string;
  summary: { camera_total: number; excel_total: number; matched: number; camera_only: number; excel_only: number; excel_revenue: number; };
  camera_only: any[]; matched: any[]; excel_only: any[];
};
type AuthState = { token: string; username: string; role: string } | null;

// ─── Auth helpers ─────────────────────────────────────────────────────────────

function getAuth(): AuthState {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem("cp_auth");
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}

function setAuth(auth: AuthState) {
  if (auth) localStorage.setItem("cp_auth", JSON.stringify(auth));
  else localStorage.removeItem("cp_auth");
}

function apiFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const auth = getAuth();
  return fetch(url, {
    ...options,
    headers: {
      ...(options.headers || {}),
      ...(auth ? { Authorization: `Bearer ${auth.token}` } : {}),
    },
  });
}

// ─── Login page ───────────────────────────────────────────────────────────────

function LoginPage({ onLogin }: { onLogin: (auth: AuthState) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw]     = useState(false);
  const [error, setError]       = useState("");
  const [loading, setLoading]   = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true); setError("");
    try {
      const r = await fetch(`${API}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      if (!r.ok) { setError("Usuario o contraseña incorrectos"); return; }
      const data = await r.json();
      const auth = { token: data.access_token, username: data.username, role: data.role };
      setAuth(auth);
      onLogin(auth);
    } catch { setError("Error de conexión con el servidor"); }
    finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen bg-slate-100 flex items-center justify-center p-4">
      <div className="bg-white rounded-3xl shadow-xl w-full max-w-sm p-8">
        <div className="flex flex-col items-center gap-3 mb-8">
          <div className="bg-indigo-600 rounded-2xl p-3">
            <Car size={32} className="text-white" />
          </div>
          <h1 className="text-2xl font-black text-slate-900">CentralParking</h1>
          <p className="text-sm text-slate-400">Ingresá con tu cuenta</p>
        </div>

        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="text-xs font-bold text-slate-500 uppercase tracking-widest block mb-1.5">
              Usuario
            </label>
            <div className="flex items-center gap-2 border border-slate-200 rounded-xl px-3 py-2.5 focus-within:border-indigo-400 transition-colors">
              <User size={16} className="text-slate-400 shrink-0" />
              <input
                type="text" value={username} onChange={e => setUsername(e.target.value)}
                placeholder="admin" autoComplete="username" required
                className="flex-1 outline-none text-sm font-semibold text-slate-800 bg-transparent placeholder:text-slate-300"
              />
            </div>
          </div>

          <div>
            <label className="text-xs font-bold text-slate-500 uppercase tracking-widest block mb-1.5">
              Contraseña
            </label>
            <div className="flex items-center gap-2 border border-slate-200 rounded-xl px-3 py-2.5 focus-within:border-indigo-400 transition-colors">
              <LogIn size={16} className="text-slate-400 shrink-0" />
              <input
                type={showPw ? "text" : "password"} value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="••••••••" autoComplete="current-password" required
                className="flex-1 outline-none text-sm font-semibold text-slate-800 bg-transparent placeholder:text-slate-300"
              />
              <button type="button" onClick={() => setShowPw(!showPw)} className="text-slate-300 hover:text-slate-500">
                {showPw ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </div>
          </div>

          {error && <p className="text-sm text-rose-500 font-semibold text-center">{error}</p>}

          <button type="submit" disabled={loading}
            className="w-full bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white font-black py-3 rounded-xl transition-colors text-sm">
            {loading ? "Ingresando..." : "Ingresar"}
          </button>
        </form>
      </div>
    </div>
  );
}

// ─── Shared components ────────────────────────────────────────────────────────

function PhotoThumb({ url, plate, status, size = "sm" }: {
  url: string | null; plate: string; status?: string; size?: "sm" | "lg";
}) {
  const [open, setOpen] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const cls = size === "lg"
    ? "w-20 h-14 lg:w-24 lg:h-16"
    : "w-14 h-10";

  useEffect(() => {
    setLoaded(false);
    setFailed(false);
    setAttempt(0);
  }, [url]);

  if (!url) return (
    <div title={status === "AUTO_CLOSED" ? "Cierre automático sin captura" : "Sin imagen asociada"}
      className={`${cls} rounded-xl bg-slate-100 flex flex-col items-center justify-center shrink-0 px-1`}>
      <ImageIcon size={size === "lg" ? 18 : 14} className="text-slate-300" />
      {size === "lg" && (
        <span className="text-[8px] leading-tight text-slate-400 text-center mt-0.5">
          {status === "AUTO_CLOSED" ? "Cierre automático" : "Sin captura"}
        </span>
      )}
    </div>
  );

  if (failed) return (
    <button type="button" title="Reintentar cargar imagen"
      onClick={() => { setFailed(false); setLoaded(false); setAttempt(value => value + 1); }}
      className={`${cls} rounded-xl bg-rose-50 border border-rose-100 flex flex-col items-center justify-center shrink-0`}>
      <AlertTriangle size={size === "lg" ? 17 : 14} className="text-rose-400" />
      {size === "lg" && <span className="text-[8px] text-rose-500 mt-0.5">Reintentar</span>}
    </button>
  );

  return (
    <>
      <button onClick={() => loaded && setOpen(true)} className={`${cls} relative shrink-0`} disabled={!loaded}>
        {!loaded && <span className="absolute inset-0 rounded-xl bg-slate-100 animate-pulse" aria-label="Cargando imagen" />}
        <img key={attempt} src={url} alt={`Captura de patente ${plate}`} loading="lazy" decoding="async"
          onLoad={() => setLoaded(true)} onError={() => setFailed(true)}
          className={`${cls} object-cover rounded-xl border border-slate-200 hover:scale-105 transition-all cursor-zoom-in ${loaded ? "opacity-100" : "opacity-0"}`} />
      </button>
      {open && (
        <div className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4"
          onClick={() => setOpen(false)}>
          <div className="relative max-w-3xl w-full" onClick={e => e.stopPropagation()}>
            <button onClick={() => setOpen(false)}
              className="absolute -top-4 -right-4 bg-white rounded-full p-1.5 shadow-lg z-10">
              <X size={18} />
            </button>
            <img src={url} alt={plate} className="w-full rounded-2xl shadow-2xl" />
            <p className="text-center text-white font-black text-2xl mt-4 tracking-widest font-mono">{plate}</p>
          </div>
        </div>
      )}
    </>
  );
}

function ActionBadge({ action }: { action: string }) {
  const styles: Record<string, string> = {
    ENTRY: "bg-emerald-100 text-emerald-700", EXIT: "bg-rose-100 text-rose-700",
    VOID: "bg-slate-100 text-slate-500", DETECTION: "bg-sky-100 text-sky-700",
  };
  const labels: Record<string, string> = {
    ENTRY: "Entrada", EXIT: "Salida", VOID: "Anulado", DETECTION: "Detección",
  };
  return (
    <span className={`px-2.5 py-0.5 rounded-full text-xs font-bold uppercase ${styles[action] ?? "bg-slate-100 text-slate-500"}`}>
      {labels[action] ?? action}
    </span>
  );
}

function PlateEditor({ row, onSaved }: { row: HistoryEntry; onSaved?: () => void }) {
  const [chars, setChars] = useState(() => row.plate.split(""));
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const inputs = useRef<Array<HTMLInputElement | null>>([]);
  const slots = Math.min(8, Math.max(6, chars.length));

  useEffect(() => { setChars(row.plate.split("")); setMessage(""); }, [row.plate]);

  const setPlate = (value: string) => {
    setChars(value.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 8).split(""));
    setMessage("");
  };

  const changeAt = (index: number, value: string) => {
    const clean = value.toUpperCase().replace(/[^A-Z0-9]/g, "");
    const next = [...chars];
    next[index] = clean.slice(-1);
    setChars(next);
    setMessage("");
    if (clean && index < slots - 1) inputs.current[index + 1]?.focus();
  };

  const save = async () => {
    const plate = chars.join("");
    if (plate === row.plate || plate.length < 4) return;
    setSaving(true); setMessage("");
    try {
      const response = await apiFetch(`${API}/api/history/${row.session_id}/plate`, {
        method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ plate }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || "No se pudo actualizar");
      }
      setMessage("Guardado");
      onSaved?.();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Error al guardar");
    } finally { setSaving(false); }
  };

  return (
    <div className="ml-auto flex flex-col items-end gap-1 shrink-0">
      <div className="flex items-center gap-1" onPaste={(event) => {
        event.preventDefault(); setPlate(event.clipboardData.getData("text"));
      }}>
        {Array.from({ length: slots }, (_, index) => (
          <input key={index} ref={(element) => { inputs.current[index] = element; }}
            value={chars[index] ?? ""} maxLength={1} inputMode="text"
            aria-label={`Carácter ${index + 1} de la patente`}
            onChange={(event) => changeAt(index, event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Backspace" && !chars[index] && index > 0) inputs.current[index - 1]?.focus();
              if (event.key === "Enter") save();
              if (event.key === "Escape") setPlate(row.plate);
            }}
            className="w-7 h-8 lg:w-8 lg:h-9 rounded-md border border-slate-300 bg-white text-center font-black font-mono text-sm lg:text-base uppercase focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 outline-none" />
        ))}
        <button type="button" onClick={save}
          disabled={saving || chars.join("") === row.plate || chars.join("").length < 4}
          className="h-8 lg:h-9 px-2.5 rounded-md bg-indigo-600 text-white text-[10px] lg:text-xs font-bold disabled:opacity-30">
          {saving ? "..." : "Guardar"}
        </button>
      </div>
      {message && <span className={`text-[10px] ${message === "Guardado" ? "text-emerald-600" : "text-rose-500"}`}>{message}</span>}
    </div>
  );
}

function StatCard({ label, value, sub, accent = "text-slate-900" }: {
  label: string; value: string | number; sub?: string; accent?: string;
}) {
  return (
    <div className="bg-white rounded-2xl border border-slate-200 p-4 lg:p-5">
      <p className="text-xs font-bold text-slate-400 uppercase tracking-widest">{label}</p>
      <p className={`text-3xl lg:text-4xl font-black tabular-nums mt-1 ${accent}`}>{value}</p>
      {sub && <p className="text-xs text-slate-400 mt-1">{sub}</p>}
    </div>
  );
}

// ─── Feed row (shared by Dashboard and Historial) ─────────────────────────────

function FeedRow({ r, showDate = false, onPlateSaved }: {
  r: HistoryEntry; showDate?: boolean; onPlateSaved?: () => void;
}) {
  const today = format(new Date(), "yyyy-MM-dd");
  return (
    <div className="flex items-center gap-3 lg:gap-4 px-4 lg:px-5 py-3 lg:py-4">
      <PhotoThumb url={r.image_url} plate={r.plate} status={r.status} size="lg" />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-black text-slate-900 tracking-widest text-base lg:text-xl font-mono">
            {r.plate}
          </span>
          <ActionBadge action={r.action} />
          {r.status && r.status !== "REAL" && (
            <span className="text-[10px] text-slate-400 bg-slate-50 px-1.5 py-0.5 rounded hidden sm:inline">
              {r.status === "AUTO_CLOSED" ? "Cierre automático" : r.status}
            </span>
          )}
        </div>
        <p className="text-sm lg:text-base text-slate-400 font-mono mt-0.5">
          {(showDate || r.timestamp.split(" ")[0] !== today) && (
            <span className="text-slate-300 mr-1.5">{r.timestamp.split(" ")[0]}</span>
          )}
          {r.timestamp.split(" ")[1]}
        </p>
      </div>
      {r.fee > 0 && (
        <span className="text-base lg:text-lg font-bold text-slate-700 tabular-nums shrink-0">
          ${r.fee.toLocaleString("es-CL")}
        </span>
      )}
      <PlateEditor row={r} onSaved={onPlateSaved} />
      <span className="text-xs text-slate-300 tabular-nums shrink-0 hidden md:block w-10 text-right">
        {(r.confidence * 100).toFixed(0)}%
      </span>
    </div>
  );
}

// ─── Dashboard ────────────────────────────────────────────────────────────────

function Dashboard({ stats, history, loading, onPlateSaved }: {
  stats: Stats; history: HistoryEntry[]; loading: boolean; onPlateSaved: () => void;
}) {
  return (
    <div className="space-y-5 lg:space-y-0 lg:grid lg:grid-cols-[300px_1fr] lg:gap-6">

      {/* Left: stats */}
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <StatCard label="Entradas hoy"  value={stats.today_entries} accent="text-emerald-600" />
          <StatCard label="Salidas hoy"   value={stats.today_exits}   accent="text-rose-600" />
          <StatCard label="En parking"    value={stats.parked_now}    accent="text-indigo-600" />
          <StatCard label="Recaudado"
            value={`$${stats.today_income.toLocaleString("es-CL")}`} accent="text-amber-600" />
        </div>
        <div className="bg-white rounded-2xl border border-slate-200 p-4 hidden lg:block">
          <p className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-3">Estado</p>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-slate-500">Cámara</span>
              <span className="font-bold text-emerald-600">● Activa</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Staging</span>
              <span className="font-bold text-emerald-600">● Activo</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Actualización</span>
              <span className="font-bold text-slate-400">cada 15s</span>
            </div>
          </div>
        </div>
      </div>

      {/* Right: feed */}
      <div className="bg-white rounded-2xl border border-slate-200 lg:overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b border-slate-100">
          <h2 className="font-bold text-slate-700">Feed en vivo</h2>
          {loading && <RefreshCw size={15} className="animate-spin text-slate-400" />}
        </div>
        <div className="divide-y divide-slate-50 lg:max-h-[calc(100vh-220px)] lg:overflow-y-auto">
          {history.filter(r => r.status !== "AUTO_CLOSED").slice(0, 50).map((r) => (
            <FeedRow key={`${r.session_id}-${r.action}`} r={r} onPlateSaved={onPlateSaved} />
          ))}
          {history.length === 0 && !loading && (
            <p className="text-center text-slate-400 py-16">Sin actividad registrada</p>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Historial ────────────────────────────────────────────────────────────────

function Historial() {
  const [date, setDate]     = useState(() => format(new Date(), "yyyy-MM-dd"));
  const [filter, setFilter] = useState<"ALL" | "ENTRY" | "EXIT">("ALL");
  const [rows, setRows]     = useState<HistoryEntry[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await apiFetch(`${API}/api/history?limit=2000`);
      if (r.ok) setRows((await r.json()).filter((e: HistoryEntry) => e.timestamp.startsWith(date)));
    } finally { setLoading(false); }
  }, [date]);

  useEffect(() => { load(); }, [load]);

  const visible = filter === "ALL" ? rows : rows.filter(r => r.action === filter);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 sm:gap-3">
        {/* Nav fecha */}
        <div className="flex items-center bg-white border border-slate-200 rounded-xl overflow-hidden shrink-0">
          <button onClick={() => setDate(format(subDays(parseISO(date), 1), "yyyy-MM-dd"))}
            className="p-2.5 hover:bg-slate-50 text-slate-400 hover:text-slate-700 transition-colors">
            <ChevronLeft size={16} />
          </button>
          <div className="flex items-center gap-1.5 px-1">
            <Calendar size={14} className="text-slate-400" />
            <input type="date" value={date} onChange={e => setDate(e.target.value)}
              className="text-sm font-semibold text-slate-700 outline-none bg-transparent w-32 lg:w-36" />
          </div>
          <button onClick={() => setDate(format(addDays(parseISO(date), 1), "yyyy-MM-dd"))}
            disabled={isToday(parseISO(date))}
            className="p-2.5 hover:bg-slate-50 text-slate-400 hover:text-slate-700 disabled:opacity-30 transition-colors">
            <ChevronRight size={16} />
          </button>
        </div>
        {/* Filtro */}
        <div className="flex rounded-xl overflow-hidden border border-slate-200 bg-white shrink-0">
          {(["ALL", "ENTRY", "EXIT"] as const).map(f => (
            <button key={f} onClick={() => setFilter(f)}
              className={`px-3 lg:px-4 py-2.5 text-xs lg:text-sm font-bold transition-colors ${filter === f ? "bg-indigo-600 text-white" : "text-slate-500 hover:bg-slate-50"}`}>
              {f === "ALL" ? "Todos" : f === "ENTRY" ? "Entradas" : "Salidas"}
            </button>
          ))}
        </div>
        <button onClick={load} className="p-2.5 rounded-xl border border-slate-200 bg-white hover:bg-slate-50">
          <RefreshCw size={15} className={`text-slate-500 ${loading ? "animate-spin" : ""}`} />
        </button>
        {visible.length > 0 && (
          <span className="ml-auto text-xs text-slate-400">{visible.length} registros</span>
        )}
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
        <div className="divide-y divide-slate-50">
          {visible.map((r) => <FeedRow key={`${r.session_id}-${r.action}`} r={r} showDate onPlateSaved={load} />)}
          {visible.length === 0 && !loading && (
            <p className="text-center text-slate-400 py-16">Sin registros para {date}</p>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Reconciliación ───────────────────────────────────────────────────────────

function Reconciliacion() {
  const [date, setDate]           = useState(() => format(new Date(), "yyyy-MM-dd"));
  const [result, setResult]       = useState<ReconcileResult | null>(null);
  const [uploading, setUploading] = useState(false);
  const [reconciling, setReconciling] = useState(false);
  const [detailTab, setDetailTab] = useState<"camera_only" | "matched" | "excel_only">("camera_only");
  const [lastImport, setLastImport] = useState<{ id: number; filename: string } | null>(null);
  const [dragOver, setDragOver]   = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const uploadFile = async (file: File) => {
    setUploading(true);
    try {
      const fd = new FormData(); fd.append("file", file);
      const r = await apiFetch(`${API}/api/excel/upload`, { method: "POST", body: fd });
      if (!r.ok) { alert((await r.json()).detail); return; }
      const data = await r.json();
      setLastImport({ id: data.import_id, filename: data.filename });
      if (data.date_from) setDate(data.date_from);
    } finally { setUploading(false); }
  };

  const reconcile = async () => {
    setReconciling(true);
    try {
      const p = new URLSearchParams({ date });
      if (lastImport) p.set("import_id", String(lastImport.id));
      const r = await apiFetch(`${API}/api/excel/reconcile?${p}`);
      if (r.ok) setResult(await r.json());
    } finally { setReconciling(false); }
  };

  const s = result?.summary;

  return (
    <div className="space-y-5">
      <div
        onDragOver={e => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={e => { e.preventDefault(); setDragOver(false); const f = e.dataTransfer.files[0]; if (f) uploadFile(f); }}
        onClick={() => fileRef.current?.click()}
        className={`border-2 border-dashed rounded-2xl p-8 lg:p-10 flex flex-col items-center gap-3 cursor-pointer transition-colors
          ${dragOver ? "border-indigo-400 bg-indigo-50" : "border-slate-200 bg-white hover:border-indigo-300 hover:bg-slate-50"}`}
      >
        <Upload size={32} className={uploading ? "animate-bounce text-indigo-500" : "text-slate-400"} />
        <div className="text-center">
          <p className="font-semibold text-slate-600">
            {uploading ? "Subiendo..." : "Arrastrá el Excel aquí o hacé click"}
          </p>
          {lastImport
            ? <p className="text-sm text-indigo-600 mt-1 font-semibold">✓ {lastImport.filename}</p>
            : <p className="text-sm text-slate-400 mt-1">ventas_DD-MM-YYYY HH_MM_SS.xlsx</p>
          }
        </div>
        <input ref={fileRef} type="file" accept=".xlsx,.xls" className="hidden"
          onChange={e => { const f = e.target.files?.[0]; if (f) uploadFile(f); }} />
      </div>

      <div className="flex gap-3">
        <div className="flex items-center gap-2 bg-white border border-slate-200 rounded-xl px-3 py-2.5 flex-1">
          <Calendar size={15} className="text-slate-400 shrink-0" />
          <input type="date" value={date} onChange={e => setDate(e.target.value)}
            className="text-sm font-semibold text-slate-700 outline-none bg-transparent w-full" />
        </div>
        <button onClick={reconcile} disabled={reconciling || uploading}
          className="bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-bold px-6 rounded-xl text-sm transition-colors">
          {reconciling ? "Comparando..." : "Comparar"}
        </button>
      </div>

      {s && (
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-2 lg:gap-4">
            <div className="bg-rose-50 border border-rose-200 rounded-2xl p-3 lg:p-5">
              <p className="text-[10px] lg:text-xs font-bold text-rose-500 uppercase tracking-widest">Solo cámara</p>
              <p className="text-2xl lg:text-4xl font-black text-rose-600 mt-1">{s.camera_only}</p>
              <p className="text-[10px] lg:text-xs text-rose-400 mt-1 hidden sm:block">operador no registró</p>
            </div>
            <div className="bg-emerald-50 border border-emerald-200 rounded-2xl p-3 lg:p-5">
              <p className="text-[10px] lg:text-xs font-bold text-emerald-600 uppercase tracking-widest">Coinciden</p>
              <p className="text-2xl lg:text-4xl font-black text-emerald-700 mt-1">{s.matched}</p>
              <p className="text-[10px] lg:text-xs text-emerald-500 mt-1 hidden sm:block">${s.excel_revenue.toLocaleString("es-CL")}</p>
            </div>
            <div className="bg-amber-50 border border-amber-200 rounded-2xl p-3 lg:p-5">
              <p className="text-[10px] lg:text-xs font-bold text-amber-600 uppercase tracking-widest">Solo Excel</p>
              <p className="text-2xl lg:text-4xl font-black text-amber-700 mt-1">{s.excel_only}</p>
              <p className="text-[10px] lg:text-xs text-amber-500 mt-1 hidden sm:block">cámara no detectó</p>
            </div>
          </div>

          <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
            <div className="flex border-b border-slate-100">
              {([
                ["camera_only", "🔴 Solo cámara", "🔴"],
                ["matched",     "✅ Coinciden",   "✅"],
                ["excel_only",  "🟡 Solo Excel",  "🟡"],
              ] as const).map(([t, label, icon]) => (
                <button key={t} onClick={() => setDetailTab(t)}
                  className={`flex-1 py-3 lg:py-4 text-xs lg:text-sm font-bold transition-colors ${detailTab === t ? "bg-slate-50 text-slate-900 border-b-2 border-indigo-500" : "text-slate-400 hover:text-slate-600"}`}>
                  <span className="hidden sm:inline">{label}</span>
                  <span className="sm:hidden">{icon}</span>
                </button>
              ))}
            </div>

            <div className="divide-y divide-slate-50 max-h-[480px] lg:max-h-[560px] overflow-y-auto">
              {detailTab === "camera_only" && result!.camera_only.map((r) => (
                <div key={`camera_${r.plate}_${r.camera_time}`} className="flex items-center gap-3 lg:gap-4 px-4 lg:px-5 py-3 lg:py-4">
                  <PhotoThumb url={r.image_url} plate={r.plate} size="lg" />
                  <div className="flex-1 min-w-0">
                    <p className="font-black text-slate-900 tracking-widest text-base lg:text-xl font-mono">{r.plate}</p>
                    <p className="text-sm text-slate-400">{r.camera_time} · {(r.confidence * 100).toFixed(0)}% conf</p>
                  </div>
                  <AlertTriangle size={18} className="text-rose-400 shrink-0" />
                </div>
              ))}

              {detailTab === "matched" && result!.matched.map((r) => (
                <div key={`matched_${r.plate}_${r.camera_time}`} className="flex items-center gap-3 lg:gap-4 px-4 lg:px-5 py-3 lg:py-4">
                  <PhotoThumb url={r.image_url} plate={r.plate} size="lg" />
                  <div className="flex-1 min-w-0">
                    <p className="font-black text-slate-900 tracking-widest text-base lg:text-xl font-mono">{r.plate}</p>
                    <p className="text-sm text-slate-400">
                      cámara {r.camera_time} · Excel {r.excel_ingreso} · Δ{r.diff_minutes}min · {r.operador}
                    </p>
                  </div>
                  <div className="text-right shrink-0">
                    <p className="font-bold text-emerald-600 lg:text-lg">${r.valor.toLocaleString("es-CL")}</p>
                    <CheckCircle2 size={14} className="text-emerald-400 ml-auto mt-0.5" />
                  </div>
                </div>
              ))}

              {detailTab === "excel_only" && result!.excel_only.map((r) => (
                <div key={`excel_${r.plate}_${r.excel_ingreso}`} className="flex items-center gap-3 lg:gap-4 px-4 lg:px-5 py-3 lg:py-4">
                  <div className="w-20 h-14 lg:w-24 lg:h-16 rounded-xl bg-amber-50 flex items-center justify-center shrink-0">
                    <HelpCircle size={20} className="text-amber-400" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-black text-slate-900 tracking-widest text-base lg:text-xl font-mono">{r.plate}</p>
                    <p className="text-sm text-slate-400">{r.excel_ingreso} → {r.excel_salida ?? "?"} · {r.operador}</p>
                  </div>
                  <div className="text-right shrink-0">
                    <p className="font-bold text-amber-600 lg:text-lg">${r.valor.toLocaleString("es-CL")}</p>
                    <p className={`text-xs mt-0.5 ${r.estado === "Pagado" ? "text-emerald-500" : "text-rose-500"}`}>{r.estado}</p>
                  </div>
                </div>
              ))}

              {result![detailTab].length === 0 && (
                <p className="text-center text-slate-400 py-12">Sin registros en esta categoría</p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── App ──────────────────────────────────────────────────────────────────────

export default function App() {
  const [auth, setAuthState]  = useState<AuthState>(null);
  const [tab, setTab]         = useState<"dashboard" | "historial" | "reconciliacion">("dashboard");
  const [stats, setStats]     = useState<Stats>({ today_income: 0, today_entries: 0, today_exits: 0, parked_now: 0 });
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const today = format(new Date(), "d 'de' MMMM yyyy", { locale: es });

  // Hydrate auth from localStorage
  useEffect(() => { setAuthState(getAuth()); }, []);

  const refresh = useCallback(async () => {
    if (!getAuth()) return;
    setLoading(true);
    try {
      const ts = Date.now();
      const [s, h] = await Promise.all([
        apiFetch(`${API}/api/stats?t=${ts}`),
        apiFetch(`${API}/api/history?t=${ts}&limit=50`),
      ]);
      if (s.ok) setStats(await s.json());
      if (h.ok) setHistory(await h.json());
      if (s.status === 401 || h.status === 401) { setAuth(null); setAuthState(null); }
    } finally { setLoading(false); }
  }, []);

  useEffect(() => {
    if (!auth) return;
    refresh();
    const id = setInterval(refresh, 15_000);
    return () => clearInterval(id);
  }, [auth, refresh]);

  const logout = () => { setAuth(null); setAuthState(null); };
  const handleLogin = (a: AuthState) => { setAuthState(a); };

  if (!auth) return <LoginPage onLogin={handleLogin} />;

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-white border-b border-slate-200 sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 lg:px-8 py-3 flex items-center gap-4">
          <div className="flex items-center gap-2.5 shrink-0">
            <div className="bg-indigo-600 rounded-xl p-1.5 lg:p-2">
              <Car size={18} className="text-white lg:hidden" />
              <Car size={22} className="text-white hidden lg:block" />
            </div>
            <span className="font-black text-slate-900 text-base lg:text-lg">CentralParking</span>
          </div>
          <p className="text-sm text-slate-400 hidden lg:block capitalize flex-1">{today}</p>
          <nav className="ml-auto flex gap-1 lg:gap-2">
            {([
              ["dashboard",      "Dashboard"],
              ["historial",      "Historial"],
              ["reconciliacion", "Excel"],
            ] as const).map(([t, label]) => (
              <button key={t} onClick={() => setTab(t)}
                className={`px-3 lg:px-4 py-1.5 lg:py-2 rounded-lg text-xs lg:text-sm font-bold transition-colors ${tab === t ? "bg-indigo-600 text-white" : "text-slate-500 hover:bg-slate-100"}`}>
                {label}
              </button>
            ))}
          </nav>
          <button onClick={logout} title="Cerrar sesión"
            className="ml-2 p-2 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors">
            <LogOut size={18} />
          </button>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 lg:px-8 py-5 lg:py-8">
        {tab === "dashboard"      && <Dashboard stats={stats} history={history} loading={loading} onPlateSaved={refresh} />}
        {tab === "historial"      && <Historial />}
        {tab === "reconciliacion" && <Reconciliacion />}
      </main>
    </div>
  );
}
