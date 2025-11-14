import React, { useRef, useState, useEffect } from "react";
import { UPLOAD_DELAY_MS } from "../config";
import { sleep } from "../utils/sleep"; // o define el helper en el mismo archivo

type Props = { token: string | null };
type DocType = "factura" | "venta";

/** /api/uploads/historico */
type UploadStatus = "UPLOADED" | "PROCESSING" | "PROCESSED" | "FAILED" | "DUPLICATED";
type Operacion = {
  id: string;
  fecha: string;
  tipo: "FACTURA" | "VENTA";
  original_filename: string;
  descripcion: string;
  tam_bytes?: number | null;
  storage_path?: string | null;
  status?: UploadStatus | null;
};

const ALLOWED_TYPES = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
];

export default function UploadPage({ token }: Props) {
  const [docType, setDocType] = useState<DocType | null>(null);

  // 🔄 multi-archivo
  const [files, setFiles] = useState<File[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadingIndex, setUploadingIndex] = useState<number | null>(null);

  const [retryingId, setRetryingId] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [showSuccess, setShowSuccess] = useState(false);

  console.log("⏱️ Delay entre subidas configurado:", UPLOAD_DELAY_MS, "ms");

  // ====== HISTÓRICO (uploads) ======
  const [ops, setOps] = useState<Operacion[]>([]);
  const [opsError, setOpsError] = useState<string | null>(null);

  const loadHistorico = () => {
    fetch("http://localhost:8000/api/uploads/historico?limit=20", {
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    })
      .then(r => (r.ok ? r.json() : Promise.reject("Error cargando histórico")))
      .then(data => {
        console.debug("Respuesta /api/uploads/historico:", data);
        setOps(data.items || []);
      })
      .catch(e => setOpsError(typeof e === "string" ? e : "Error desconocido"));
  };

  useEffect(() => {
    loadHistorico();
  }, [token]);
  // ==================================

  // Helpers multi-archivo
  const isAllowed = (f: File) => {
    const name = f.name.toLowerCase();
    return (
      ALLOWED_TYPES.includes(f.type) ||
      name.endsWith(".pdf") ||
      name.endsWith(".xlsx")
    );
  };

  const addFiles = (list: FileList | File[]) => {
    const incoming = Array.from(list);
    const valid = incoming.filter(isAllowed);
    if (valid.length !== incoming.length) {
      alert("Algunos archivos fueron ignorados (solo PDF o XLSX).");
    }
    // dedupe por nombre+tamaño
    const dedup = [...files];
    for (const f of valid) {
      const exists = dedup.some(d => d.name === f.name && d.size === f.size);
      if (!exists) dedup.push(f);
    }
    setFiles(dedup);
  };

  const removeFile = (name: string, size: number) => {
    setFiles(prev => prev.filter(f => !(f.name === name && f.size === size)));
  };

  const clearFiles = () => setFiles([]);

  // Eventos
  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) addFiles(e.target.files);
    // permite volver a seleccionar el mismo archivo si se borra
    e.target.value = "";
  };

  const handleDrop: React.DragEventHandler<HTMLDivElement> = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
    if (e.dataTransfer.files?.length) addFiles(e.dataTransfer.files);
  };

  const startUpload = () => {
    if (!token) return alert("Sesión caducada. Inicia sesión de nuevo.");
    if (!docType) return alert("Selecciona si es Factura o Venta");
    if (files.length === 0) return alert("Selecciona al menos un archivo");
    setShowConfirm(true);
  };

  const confirmUpload = async () => {
    if (!token || !docType || files.length === 0) return;
    setUploading(true);
    setUploadingIndex(0);
    try {
      // Secuencial
      for (let i = 0; i < files.length; i++) {
        setUploadingIndex(i);
        const fd = new FormData();
        fd.append("file", files[i]);
        fd.append("tipo", docType);
        const res = await fetch("/api/upload/", {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
          body: fd,
        });
        if (!res.ok) {
          const t = await res.text();
          console.error(`Fallo subiendo ${files[i].name}:`, t);
          alert(`Fallo subiendo ${files[i].name}: ${t}`);
          // si prefieres continuar con el resto, no hagas return
          // y sigue el bucle. Aquí continúo:
          continue;
        }
        // refrescamos histórico tras cada subida (o al final si prefieres)
        loadHistorico();
        // ⏳ espera entre peticiones según config externa
        if (UPLOAD_DELAY_MS > 0) {
          await sleep(UPLOAD_DELAY_MS);
        }
      }
      setShowConfirm(false);
      clearFiles();
      setShowSuccess(true);
    } catch (err: any) {
      alert("Error subiendo archivos: " + (err?.message ?? String(err)));
    } finally {
      setUploading(false);
      setUploadingIndex(null);
    }
  };

  // Reintento webhook n8n cuando status === 'FAILED'
  const retryWebhook = async (op: Operacion) => {
    if (!token) return alert("Sesión caducada");
    setRetryingId(op.id);

    console.info("🔁 Reintentando webhook para:", op);

    try {
      const body = { tipo: op.tipo === "FACTURA" ? "factura" : "venta" };
      const r = await fetch(`/api/upload/${op.id}/retry`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(body),
      });

      console.info("📡 Respuesta backend (status):", r.status);

      if (!r.ok) {
        const errText = await r.text();
        console.error("❌ Error en retryWebhook:", errText);
        throw new Error(errText);
      }

      const data = await r.json();
      console.info("✅ Respuesta JSON backend:", data);

      await loadHistorico();
    } catch (e: any) {
      console.error("⚠️ No se pudo reintentar:", e);
      alert("No se pudo reintentar: " + (e?.message ?? String(e)));
    } finally {
      setRetryingId(null);
      console.info("🔚 Finalizó retryWebhook para:", op.id);
    }
  };

  const disabled = !docType;

  return (
    <div className="max-w-3xl mx-auto">
      <div className="rounded-2xl shadow-soft bg-white/80 backdrop-blur p-6 border border-gray-100">
        <h1 className="text-2xl font-semibold text-center text-gray-900" style={{ marginBottom: 32 }}>
          Subir factura o fichero de ventas
        </h1>

        {/* Selector tipo */}
        <div className="text-center mb-3 text-sm text-gray-600">
          Selecciona el tipo de fichero a subir
        </div>
        <div className="flex items-center justify-center gap-4 mb-6" style={{ marginBottom: 8 }}>
          <button
            type="button"
            className={`seg-option ${docType === "factura" ? "seg-selected" : ""}`}
            style={{ marginRight: "6px" }}
            onClick={() => setDocType("factura")}
          >
            Factura
          </button>
          <button
            type="button"
            className={`seg-option ${docType === "venta" ? "seg-selected" : ""}`}
            style={{ marginLeft: "6px" }}
            onClick={() => setDocType("venta")}
          >
            Venta
          </button>
        </div>

        {/* input oculto (multiple) */}
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".pdf,.xlsx,application/pdf,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          style={{ display: "none" }}
          onChange={handleInputChange}
        />

        {/* Dropzone */}
        <div
          onDragOver={(e) => {
            if (disabled) return;
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => {
            if (disabled) return;
            setDragOver(false);
          }}
          onDrop={(e) => {
            if (disabled) return;
            handleDrop(e);
          }}
          onClick={() => {
            if (disabled) return;
            inputRef.current?.click();
          }}
          style={{
            maxWidth: 720,
            margin: "12px auto 16px",
            background: "#fff",
            border: `2px dashed ${dragOver && !disabled ? "#1d4ed8" : "#cbd5e1"}`,
            borderRadius: 12,
            minHeight: 260,
            padding: 24,
            textAlign: "center" as const,
            cursor: disabled ? "not-allowed" : "pointer",
            opacity: disabled ? 0.5 : 1,
            filter: disabled ? "grayscale(0.1)" : "none",
            boxShadow: dragOver && !disabled ? "0 6px 20px rgba(29,78,216,.15)" : "none",
            transition: "border-color 120ms ease, box-shadow 120ms ease, opacity 120ms ease",
            position: "relative",
          }}
        >
          {disabled && (
            <div
              style={{
                color: "#1f2937",
                fontWeight: 700,
                fontSize: "1rem",
                background: "rgba(255,255,255,0.85)",
                padding: "12px 16px",
                borderRadius: 8,
                textAlign: "center",
              }}
            >
              Elige <strong style={{ color: "#1d4ed8" }}>Factura</strong> <br />
              o <strong style={{ color: "#1d4ed8" }}>Venta</strong> para habilitar
            </div>
          )}

          <p style={{ fontWeight: 600, color: "#111827", margin: "4px 0 6px" }}>
            Arrastra y suelta archivos aquí
          </p>
          <p style={{ color: "#6b7280", fontSize: "0.95rem", margin: 0 }}>
            o haz clic para seleccionar PDF o XLSX (múltiples)
          </p>

          {/* Lista de archivos seleccionados */}
          {files.length > 0 && (
            <div style={{ marginTop: 14, display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "center" }}>
              {files.map((f) => (
                <div
                  key={f.name + f.size}
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 8,
                    padding: "6px 10px",
                    borderRadius: 999,
                    background: "#eff6ff",
                    color: "#1e40af",
                    border: "1px solid #bfdbfe",
                    fontSize: ".9rem",
                  }}
                  title={f.name}
                >
                  <span
                    className="font-medium"
                    style={{
                      maxWidth: 220,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {f.name}
                  </span>
                  <span style={{ opacity: 0.7 }}>
                    {(f.size / 1024).toFixed(0)} KB
                  </span>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      removeFile(f.name, f.size);
                    }}
                    aria-label="Quitar archivo"
                    title="Quitar archivo"
                    style={{
                      background: "transparent",
                      border: 0,
                      fontSize: 16,
                      cursor: "pointer",
                      color: "inherit",
                    }}
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* Botón limpiar selección */}
          {files.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  clearFiles();
                }}
                className="px-3 py-1 rounded-lg border"
                title="Vaciar selección"
              >
                Limpiar selección
              </button>
            </div>
          )}
        </div>

        {/* CTA Subir */}
        <div className="flex justify-center mt-4" style={{ minHeight: 60 }}>
          {files.length > 0 && !disabled && (
            <button
              onClick={startUpload}
              disabled={uploading}
              className={`seg-option ${uploading ? "opacity-50 cursor-not-allowed" : "seg-selected"}`}
              style={{ opacity: uploading ? 0.6 : 1 }}
            >
              {uploading
                ? `Subiendo… ${uploadingIndex !== null ? `${uploadingIndex + 1}/${files.length}` : ""}`
                : `Subir ${files.length} archivo${files.length > 1 ? "s" : ""}`}
            </button>
          )}
        </div>
      </div>

      {/* Modal confirmación */}
      {showConfirm && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl p-6 w-full max-w-md shadow-xl border border-gray-100">
            <h2 className="text-lg font-semibold mb-2 text-gray-900">
              Confirmar subida
            </h2>
            <p className="text-sm text-gray-700">
              Vas a subir <strong>{files.length}</strong> archivo{files.length > 1 ? "s" : ""} como{" "}
              <strong>{docType}</strong>. ¿Confirmas?
            </p>
            {/* Muestra hasta 5 nombres */}
            <ul className="text-xs text-gray-600 mt-2 max-h-28 overflow-auto">
              {files.slice(0, 5).map(f => <li key={f.name + f.size}>• {f.name}</li>)}
              {files.length > 5 && <li>… y {files.length - 5} más</li>}
            </ul>
            <div className="mt-6 flex justify-end gap-4">
              <button
                className="modal-btn modal-btn-cancel"
                onClick={() => setShowConfirm(false)}
                disabled={uploading}
                style={{ marginRight: "6px" }}
              >
                Cancelar
              </button>
              <button
                className="modal-btn modal-btn-confirm"
                onClick={confirmUpload}
                disabled={uploading}
                style={{ marginLeft: "6px" }}
              >
                Confirmar
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal de éxito */}
      {showSuccess && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl p-6 w-full max-w-md shadow-xl border border-gray-100 text-center">
            <h2 className="text-lg font-semibold text-gray-900 mb-3">
              ✅ Archivo{files.length > 1 ? "s" : ""} subido{files.length > 1 ? "s" : ""} correctamente
            </h2>
            <p className="text-gray-700 text-sm mb-6">
              Tus archivos se han guardado y serán procesados en breve.
            </p>
            <button
              onClick={() => setShowSuccess(false)}
              className="px-4 py-2 bg-blue-700 text-white rounded-lg hover:bg-blue-800"
            >
              Cerrar
            </button>
          </div>
        </div>
      )}

      {/* ========= Histórico de ficheros subidos ========= */}
      <section
        style={{
          background: "#fff",
          borderRadius: 12,
          boxShadow: "0 8px 20px #0001",
          padding: "1.5rem",
          marginTop: "2rem",
        }}
      >
        <h3 style={{ margin: 0, color: "#163a63", textAlign: "center" }}>
          Histórico de ficheros subidos
        </h3>
        <p style={{ margin: "0.25rem 0 1rem", color: "#5b667a", textAlign: "center" }}>
          Facturas (1:1) y ventas (por lote)
        </p>

        {opsError && (
          <div style={{ color: "red", marginBottom: "0.75rem" }}>{opsError}</div>
        )}

        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "separate", borderSpacing: 0 }}>
            <thead>
              <tr style={{ background: "#f6f8fa", color: "#163a63" }}>
                <th style={{ ...th, textAlign: "center" }}>Fecha</th>
                <th style={{ ...th, textAlign: "center" }}>Tipo</th>
                <th style={{ ...th, textAlign: "center" }}>Nombre Fichero</th>
                <th style={{ ...th, textAlign: "center" }}>Descripción</th>
                <th style={{ ...th, textAlign: "right" }}>Tamaño (KB)</th>
                <th style={{ ...th, textAlign: "center" }}>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {ops.map((op) => (
                <tr key={op.id} style={{ borderBottom: "1px solid #eef2f7" }}>
                  <td style={{ ...td, textAlign: "center" }}>
                    {new Date(op.fecha).toLocaleString("es-ES")}
                  </td>
                  <td style={{ ...td, textAlign: "center" }}>
                    <span
                      style={{
                        fontSize: 12,
                        padding: "2px 8px",
                        borderRadius: 999,
                        background: op.tipo === "FACTURA" ? "#eef2ff" : "#ecfdf5",
                        color: op.tipo === "FACTURA" ? "#3730a3" : "#065f46",
                        fontWeight: 600,
                      }}
                    >
                      {op.tipo}
                    </span>
                  </td>
                  <td style={td}>{op.original_filename}</td>
                  <td style={td}>{op.descripcion}</td>
                  <td
                    style={{
                      ...td,
                      textAlign: "right",
                      fontVariantNumeric: "tabular-nums",
                    }}
                  >
                    {op.tam_bytes != null ? (op.tam_bytes / 1024).toFixed(0) : "-"}
                  </td>
                  <td style={{ ...td, textAlign: "center" }}>
                    {op.status === "FAILED" ? (
                      <button
                        onClick={() => retryWebhook(op)}
                        disabled={retryingId === op.id}
                        className="px-3 py-1 rounded-lg text-white"
                        style={{
                          backgroundColor: retryingId === op.id ? "#94a3b8" : "#1d4ed8",
                          cursor: retryingId === op.id ? "not-allowed" : "pointer",
                        }}
                        title="Reintentar envío al procesador"
                      >
                        {retryingId === op.id ? "Reintentando…" : "Reintentar"}
                      </button>
                    ) : (
                      <span style={{ color: "#94a3b8" }}>—</span>
                    )}
                  </td>
                </tr>
              ))}
              {ops.length === 0 && !opsError && (
                <tr>
                  <td colSpan={5} style={{ ...td, textAlign: "center", color: "#667085" }}>
                    Sin subidas recientes.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

/* estilos tabla histórico */
const th: React.CSSProperties = {
  padding: "10px 12px",
  fontWeight: 700,
  textAlign: "left",
  borderBottom: "1px solid #e5e7eb",
};
const td: React.CSSProperties = {
  padding: "10px 12px",
  whiteSpace: "nowrap",
};