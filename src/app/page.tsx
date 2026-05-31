"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { format } from "date-fns";
import { es } from "date-fns/locale";
import {
  Car, AlertTriangle, CheckCircle2, HelpCircle,
  Upload, Calendar, RefreshCw, Image as ImageIcon, X,
} from "lucide-react";

const API = "";

type HistoryEntry = {
  timestamp: string; plate: string; action: string;
  status: string; fee: number; confidence: number; image_url: string | null;
};
type Stats = {
  today_income: number; today_entries: number;
  today_exits: number; parked_now: number;
};
type ReconcileResult = {
  date: string;
  summary: {
    camera_total: number; excel_total: number; matched: number;
    camera_only: number; excel_only: number; excel_revenue: number;
  };
  camera_only: any[]; matched: any[]; excel_only: any[];
};

// ─── components ──────────────────────────────────────────────────────────────

function StatCard({ label, value, sub, accent = "text-slate-900" }: {
  label: string; value: string | number; sub?: string; accent?: string;
}) {
  return (
    <div className="bg-white rounded-2xl border border-slate-200 p-4 flex flex-col gap-1">
      <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest">{label}</p>
      <p className={`text-3xl font-black tabular-nums ${accent}`}>{value}</p>
      {sub && <p className="text-xs text-slate-400">{sub}</p>}
    </div>
  );
}

function PhotoThumb({ url, plate }: { url: string | null; plate: string }) {
  const [open, setOpen] = useState(false);
  if (!url) return (
    <div className="w-14 h-10 rounded-lg bg-slate-100 flex items-center justify-center shrink-0">
      <ImageIcon size={16} className="text-slate-300" />
    </div>
  );
  return (
    <>
      <button onClick={() => setOpen(true)} className="shrink-0">
        <img src={url} alt={plate}
          className="w-14 h-10 object-cover rounded-lg border border-slate-200 hover:scale-105 transition-transform" />
      </button>
      {open && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4"
          onClick={() => setOpen(false)}>
          <div className="relative max-w-2xl w-full" onClick={e => e.stopPropagation()}>
            <button onClick={() => setOpen(false)}
              className="absolute -top-3 -right-3 bg-white rounded-full p-1 shadow-lg">
              <X size={18} />
            </button>
            <img src={url} alt={plate} className="w-full rounded-2xl shadow-2xl" />
            <p className="text-center text-white font-black text-xl mt-3 tracking-widest">{plate}</p>
          </div>
        </div>
      )}
    </>
  );
}

function ActionBadge({ action }: { action: string }) {
  const styles: Record<string, string> = {
    ENTRY:     "bg-emerald-100 text-emerald-700",
    EXIT:      "bg-rose-100 text-rose-700",
    VOID:      "bg-slate-100 text-slate-500",
    DETECTION: "bg-sky-100 text-sky-700",
  };
  const labels: Record<string, string> = {
    ENTRY: "Entrada", EXIT: "Salida", VOID: "Anulado", DETECTION: "Detección",
  };
  return (
    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${styles[action] ?? "bg-slate-100 text-slate-500"}`}>
      {labels[action] ?? action}
    </span>
  );
}

// ─── Dashboard ────────────────────────────────────────────────────────────────

function Dashboard({ stats, history, loading }: { stats: Stats; history: HistoryEntry[]; loading: boolean }) {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Entradas hoy"  value={stats.today_entries} accent="text-emerald-600" />
        <StatCard label="Salidas hoy"   value={stats.today_exits}   accent="text-rose-600" />
        <StatCard label="En parking"    value={stats.parked_now}    accent="text-indigo-600" />
        <StatCard label="Recaudado"     value={`$${stats.today_income.toLocaleString("es-CL")}`} accent="text-amber-600" />
      </div>

      <div className="bg-white rounded-2xl border border-slate-200">
        <div className="flex items-center justify-between px-5 py-3 border-b border-slate-100">
          <h2 className="font-bold text-slate-700 text-sm">Feed en vivo</h2>
          {loading && <RefreshCw size={14} className="animate-spin text-slate-400" />}
        </div>
        <div className="divide-y divide-slate-50">
          {history.slice(0, 40).map((r, i) => (
            <div key={i} className="flex items-center gap-3 px-4 py-2.5">
              <PhotoThumb url={r.image_url} plate={r.plate} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-black text-slate-900 tracking-widest text-sm font-mono">{r.plate}</span>
                  <ActionBadge action={r.action} />
                </div>
                <p className="text-xs text-slate-400 font-mono">{r.timestamp.split(" ")[1]}</p>
              </div>
              {r.fee > 0 && (
                <span className="text-sm font-bold text-slate-600 tabular-nums shrink-0">
                  ${r.fee.toLocaleString("es-CL")}
                </span>
              )}
              <span className="text-[10px] text-slate-300 tabular-nums shrink-0 hidden sm:block">
                {(r.confidence * 100).toFixed(0)}%
              </span>
            </div>
          ))}
          {history.length === 0 && !loading && (
            <p className="text-center text-slate-400 text-sm py-12">Sin actividad registrada</p>
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
      const r = await fetch(`${API}/api/history?limit=1000`);
      if (r.ok) {
        const all: HistoryEntry[] = await r.json();
        setRows(all.filter(e => e.timestamp.startsWith(date)));
      }
    } finally { setLoading(false); }
  }, [date]);

  useEffect(() => { load(); }, [load]);

  const visible = filter === "ALL" ? rows : rows.filter(r => r.action === filter);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 bg-white border border-slate-200 rounded-xl px-3 py-2">
          <Calendar size={15} className="text-slate-400" />
          <input type="date" value={date} onChange={e => setDate(e.target.value)}
            className="text-sm font-semibold text-slate-700 outline-none bg-transparent" />
        </div>
        <div className="flex rounded-xl overflow-hidden border border-slate-200 bg-white">
          {(["ALL", "ENTRY", "EXIT"] as const).map(f => (
            <button key={f} onClick={() => setFilter(f)}
              className={`px-3 py-2 text-xs font-bold transition-colors ${filter === f ? "bg-indigo-600 text-white" : "text-slate-500 hover:bg-slate-50"}`}>
              {f === "ALL" ? "Todos" : f === "ENTRY" ? "Entradas" : "Salidas"}
            </button>
          ))}
        </div>
        <button onClick={load} className="ml-auto p-2 rounded-xl border border-slate-200 bg-white hover:bg-slate-50">
          <RefreshCw size={15} className={`text-slate-500 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
        <div className="divide-y divide-slate-50">
          {visible.map((r, i) => (
            <div key={i} className="flex items-center gap-3 px-4 py-2.5">
              <PhotoThumb url={r.image_url} plate={r.plate} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-black text-slate-900 tracking-widest text-sm font-mono">{r.plate}</span>
                  <ActionBadge action={r.action} />
                  {r.status && r.status !== "REAL" && (
                    <span className="text-[10px] text-slate-400 bg-slate-50 px-1.5 py-0.5 rounded">
                      {r.status}
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-400 font-mono">{r.timestamp}</p>
              </div>
              {r.fee > 0 && (
                <span className="text-sm font-bold text-emerald-600 tabular-nums shrink-0">
                  ${r.fee.toLocaleString("es-CL")}
                </span>
              )}
              <span className="text-[10px] text-slate-300 tabular-nums shrink-0 hidden sm:block">
                {(r.confidence * 100).toFixed(0)}%
              </span>
            </div>
          ))}
          {visible.length === 0 && !loading && (
            <p className="text-center text-slate-400 text-sm py-12">Sin registros para {date}</p>
          )}
        </div>
      </div>
      {visible.length > 0 && (
        <p className="text-xs text-slate-400 text-right">{visible.length} registros</p>
      )}
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
      const fd = new FormData();
      fd.append("file", file);
      const r = await fetch(`${API}/api/excel/upload`, { method: "POST", body: fd });
      if (!r.ok) { alert((await r.json()).detail); return; }
      const data = await r.json();
      setLastImport({ id: data.import_id, filename: data.filename });
      if (data.date_from) setDate(data.date_from);
    } finally { setUploading(false); }
  };

  const reconcile = async () => {
    setReconciling(true);
    try {
      const params = new URLSearchParams({ date });
      if (lastImport) params.set("import_id", String(lastImport.id));
      const r = await fetch(`${API}/api/excel/reconcile?${params}`);
      if (r.ok) setResult(await r.json());
    } finally { setReconciling(false); }
  };

  const s = result?.summary;

  return (
    <div className="space-y-5">
      {/* Upload zone */}
      <div
        onDragOver={e => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={e => { e.preventDefault(); setDragOver(false); const f = e.dataTransfer.files[0]; if (f) uploadFile(f); }}
        onClick={() => fileRef.current?.click()}
        className={`border-2 border-dashed rounded-2xl p-8 flex flex-col items-center gap-3 cursor-pointer transition-colors
          ${dragOver ? "border-indigo-400 bg-indigo-50" : "border-slate-200 bg-white hover:border-indigo-300 hover:bg-slate-50"}`}
      >
        <Upload size={28} className={uploading ? "animate-bounce text-indigo-500" : "text-slate-400"} />
        <div className="text-center">
          <p className="font-semibold text-slate-600 text-sm">
            {uploading ? "Subiendo..." : "Arrastrá el Excel aquí o hacé click"}
          </p>
          {lastImport
            ? <p className="text-xs text-indigo-600 mt-1 font-semibold">✓ {lastImport.filename}</p>
            : <p className="text-xs text-slate-400 mt-1">ventas_DD-MM-YYYY HH_MM_SS.xlsx</p>
          }
        </div>
        <input ref={fileRef} type="file" accept=".xlsx,.xls" className="hidden"
          onChange={e => { const f = e.target.files?.[0]; if (f) uploadFile(f); }} />
      </div>

      {/* Fecha + comparar */}
      <div className="flex gap-3">
        <div className="flex items-center gap-2 bg-white border border-slate-200 rounded-xl px-3 py-2 flex-1">
          <Calendar size={15} className="text-slate-400 shrink-0" />
          <input type="date" value={date} onChange={e => setDate(e.target.value)}
            className="text-sm font-semibold text-slate-700 outline-none bg-transparent w-full" />
        </div>
        <button onClick={reconcile} disabled={reconciling || uploading}
          className="bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-bold px-5 rounded-xl text-sm transition-colors">
          {reconciling ? "Comparando..." : "Comparar"}
        </button>
      </div>

      {/* Resultados */}
      {s && (
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-3">
            <div className="bg-rose-50 border border-rose-200 rounded-2xl p-4">
              <p className="text-[10px] font-bold text-rose-500 uppercase tracking-widest">Solo cámara</p>
              <p className="text-3xl font-black text-rose-600 mt-1">{s.camera_only}</p>
              <p className="text-[10px] text-rose-400 mt-1">no registrado por operador</p>
            </div>
            <div className="bg-emerald-50 border border-emerald-200 rounded-2xl p-4">
              <p className="text-[10px] font-bold text-emerald-600 uppercase tracking-widest">Coinciden</p>
              <p className="text-3xl font-black text-emerald-700 mt-1">{s.matched}</p>
              <p className="text-[10px] text-emerald-500 mt-1">${s.excel_revenue.toLocaleString("es-CL")}</p>
            </div>
            <div className="bg-amber-50 border border-amber-200 rounded-2xl p-4">
              <p className="text-[10px] font-bold text-amber-600 uppercase tracking-widest">Solo Excel</p>
              <p className="text-3xl font-black text-amber-700 mt-1">{s.excel_only}</p>
              <p className="text-[10px] text-amber-500 mt-1">cámara no detectó</p>
            </div>
          </div>

          <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
            <div className="flex border-b border-slate-100">
              {([
                ["camera_only", "🔴 Solo cámara"],
                ["matched",     "✅ Coinciden"],
                ["excel_only",  "🟡 Solo Excel"],
              ] as const).map(([t, label]) => (
                <button key={t} onClick={() => setDetailTab(t)}
                  className={`flex-1 py-3 text-xs font-bold transition-colors ${detailTab === t ? "bg-slate-50 text-slate-900 border-b-2 border-indigo-500" : "text-slate-400 hover:text-slate-600"}`}>
                  {label}
                </button>
              ))}
            </div>

            <div className="divide-y divide-slate-50 max-h-[420px] overflow-y-auto">
              {detailTab === "camera_only" && result!.camera_only.map((r, i) => (
                <div key={i} className="flex items-center gap-3 px-4 py-3">
                  <PhotoThumb url={r.image_url} plate={r.plate} />
                  <div className="flex-1 min-w-0">
                    <p className="font-black text-slate-900 tracking-widest text-sm font-mono">{r.plate}</p>
                    <p className="text-xs text-slate-400">{r.camera_time} · {(r.confidence * 100).toFixed(0)}% conf</p>
                  </div>
                  <AlertTriangle size={16} className="text-rose-400 shrink-0" />
                </div>
              ))}

              {detailTab === "matched" && result!.matched.map((r, i) => (
                <div key={i} className="flex items-center gap-3 px-4 py-3">
                  <PhotoThumb url={r.image_url} plate={r.plate} />
                  <div className="flex-1 min-w-0">
                    <p className="font-black text-slate-900 tracking-widest text-sm font-mono">{r.plate}</p>
                    <p className="text-xs text-slate-400">
                      cámara {r.camera_time} · Excel {r.excel_ingreso} · Δ{r.diff_minutes}min · {r.operador}
                    </p>
                  </div>
                  <div className="text-right shrink-0">
                    <p className="text-sm font-bold text-emerald-600">${r.valor.toLocaleString("es-CL")}</p>
                    <CheckCircle2 size={13} className="text-emerald-400 ml-auto mt-0.5" />
                  </div>
                </div>
              ))}

              {detailTab === "excel_only" && result!.excel_only.map((r, i) => (
                <div key={i} className="flex items-center gap-3 px-4 py-3">
                  <div className="w-14 h-10 rounded-lg bg-amber-50 flex items-center justify-center shrink-0">
                    <HelpCircle size={16} className="text-amber-400" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-black text-slate-900 tracking-widest text-sm font-mono">{r.plate}</p>
                    <p className="text-xs text-slate-400">
                      {r.excel_ingreso} → {r.excel_salida ?? "?"} · {r.operador}
                    </p>
                  </div>
                  <div className="text-right shrink-0">
                    <p className="text-sm font-bold text-amber-600">${r.valor.toLocaleString("es-CL")}</p>
                    <p className={`text-[10px] mt-0.5 ${r.estado === "Pagado" ? "text-emerald-500" : "text-rose-500"}`}>
                      {r.estado}
                    </p>
                  </div>
                </div>
              ))}

              {result![detailTab].length === 0 && (
                <p className="text-center text-slate-400 text-sm py-10">Sin registros en esta categoría</p>
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
  const [tab, setTab]         = useState<"dashboard" | "historial" | "reconciliacion">("dashboard");
  const [stats, setStats]     = useState<Stats>({ today_income: 0, today_entries: 0, today_exits: 0, parked_now: 0 });
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const today = format(new Date(), "d 'de' MMMM yyyy", { locale: es });

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const ts = Date.now();
      const [s, h] = await Promise.all([
        fetch(`${API}/api/stats?t=${ts}`),
        fetch(`${API}/api/history?t=${ts}&limit=50`),
      ]);
      if (s.ok) setStats(await s.json());
      if (h.ok) setHistory(await h.json());
    } finally { setLoading(false); }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 15_000);
    return () => clearInterval(id);
  }, [refresh]);

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-white border-b border-slate-200 sticky top-0 z-40">
        <div className="max-w-4xl mx-auto px-4 py-3 flex items-center gap-4">
          <div className="flex items-center gap-2 shrink-0">
            <div className="bg-indigo-600 rounded-xl p-1.5">
              <Car size={18} className="text-white" />
            </div>
            <span className="font-black text-slate-900">CentralParking</span>
          </div>
          <p className="text-xs text-slate-400 hidden sm:block capitalize flex-1">{today}</p>
          <nav className="flex gap-1">
            {([
              ["dashboard",      "Dashboard"],
              ["historial",      "Historial"],
              ["reconciliacion", "Excel"],
            ] as const).map(([t, label]) => (
              <button key={t} onClick={() => setTab(t)}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-colors ${tab === t ? "bg-indigo-600 text-white" : "text-slate-500 hover:bg-slate-100"}`}>
                {label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-6">
        {tab === "dashboard"      && <Dashboard stats={stats} history={history} loading={loading} />}
        {tab === "historial"      && <Historial />}
        {tab === "reconciliacion" && <Reconciliacion />}
      </main>
    </div>
  );
}
