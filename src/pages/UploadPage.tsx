import React, { useRef, useState, useEffect } from "react";
import { UPLOAD_DELAY_MS } from "../config";
import { sleep } from "../utils/sleep"; // o define el helper en el mismo archivo
import { fetchWithAuth } from "../utils/fetchWithAuth";

type Props = { token: string | null; onLogout?: () => void };
type DocType = "factura" | "venta";

/** /api/uploads/historico */
type UploadStatus =
  | "UPLOADED"
  | "PROCESSING"
  | "PROCESSED"
  | "FAILED"
  | "DUPLICATED";

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

// ===== formulario manual =====
type ManualForm = {
  fecha: string;
  proveedor: string;
  total: string;
  categoria: string;
  importe_sin_iva_local: string;
  iva_local: string;
  total_moneda_local: string;
  moneda: string;
  tarifa_cambio: string;
  importe_sin_iva_euro: string;
  importe_total_euro: string;
  pais_origen: string;
  notas: string;
  descripcion: string;
  id_ext: string;
  fecha_dt: string;
  supplier_vat_number: string;
  ubicacion_factura: string;
};

const initialManualForm: ManualForm = {
  fecha: new Date().toISOString().split('T')[0], // Fecha de hoy en formato YYYY-MM-DD
  proveedor: "",
  total: "",
  categoria: "",
  importe_sin_iva_local: "",
  iva_local: "",
  total_moneda_local: "",
  moneda: "EUR",
  tarifa_cambio: "",
  importe_sin_iva_euro: "",
  importe_total_euro: "",
  pais_origen: "ES",
  notas: "",
  descripcion: "",
  id_ext: "",
  fecha_dt: new Date().toISOString().split('T')[0],
  supplier_vat_number: "",
  ubicacion_factura: "tbd",
};

// Lista abreviada de monedas y países (puedes ampliarla)
const CURRENCY_CODES = [
  "EUR",
  "USD",
  "GBP",
  "JPY",
  "CHF",
  "CAD",
  "AUD",
  "NZD",
  "MXN",
  "BRL",
  "CNY",
  "SEK",
  "NOK",
  "DKK",
  "PLN",
  "CZK",
  "HUF",
  "INR",
  "ZAR",
];

const COUNTRY_CODES = [
  "ES",
  "FR",
  "DE",
  "IT",
  "PT",
  "NL",
  "BE",
  "IE",
  "GB",
  "US",
  "CA",
  "MX",
  "BR",
  "AR",
  "CL",
  "CN",
  "JP",
  "AU",
  "NZ",
  "SE",
  "NO",
  "DK",
];

export default function UploadPage({ token, onLogout }: Props) {
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

  // overlay formulario manual
  const [showManualModal, setShowManualModal] = useState(false);
  const [showTypeSelectionModal, setShowTypeSelectionModal] = useState(false);
  const [manualForm, setManualForm] = useState<ManualForm>(initialManualForm);
  const [manualFile, setManualFile] = useState<File | null>(null);
  const manualFileInputRef = useRef<HTMLInputElement>(null);

  console.log("⏱️ Delay entre subidas configurado:", UPLOAD_DELAY_MS, "ms");

  // ====== HISTÓRICO (uploads) ======
  const [ops, setOps] = useState<Operacion[]>([]);
  const [opsError, setOpsError] = useState<string | null>(null);

  const loadHistorico = () => {
    fetchWithAuth("http://localhost:8000/api/uploads/historico?limit=20", {
      token: token || undefined,
      onLogout,
    })
      .then((r) => (r.ok ? r.json() : Promise.reject("Error cargando histórico")))
      .then((data) => {
        console.debug("Respuesta /api/uploads/historico:", data);
        setOps(data.items || []);
      })
      .catch((e) =>
        setOpsError(typeof e === "string" ? e : "Error desconocido"),
      );
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
      const exists = dedup.some((d) => d.name === f.name && d.size === f.size);
      if (!exists) dedup.push(f);
    }
    setFiles(dedup);
  };

  const removeFile = (name: string, size: number) => {
    setFiles((prev) => prev.filter((f) => !(f.name === name && f.size === size)));
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
        const res = await fetchWithAuth("/api/upload/", {
          method: "POST",
          token: token || undefined,
          onLogout,
          body: fd,
        });
        if (!res.ok) {
          const t = await res.text();
          console.error(`Fallo subiendo ${files[i].name}:`, t);
          alert(`Fallo subiendo ${files[i].name}: ${t}`);
          continue;
        }
        loadHistorico();
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
      const r = await fetchWithAuth(`/api/upload/${op.id}/retry`, {
        method: "POST",
        token: token || undefined,
        onLogout,
        headers: {
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

  // helpers formulario manual
  const setManualField = <K extends keyof ManualForm>(
    field: K,
    value: string,
  ) => {
    setManualForm((prev) => ({ ...prev, [field]: value }));
  };

  const openManualModal = () => {
    if (!docType) {
      setShowTypeSelectionModal(true);
      return;
    }
    setManualForm(initialManualForm); // reseteamos
    setManualFile(null);
    setShowManualModal(true);
  };

  const handleTypeSelection = (type: DocType) => {
    setDocType(type);
    setShowTypeSelectionModal(false);
    setManualForm(initialManualForm);
    setManualFile(null);
    setShowManualModal(true);
  };

  // Cerrar modal con Esc
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (showManualModal) {
          setShowManualModal(false);
          setManualForm(initialManualForm);
          setManualFile(null);
        }
        if (showTypeSelectionModal) {
          setShowTypeSelectionModal(false);
        }
      }
    };
    window.addEventListener("keydown", handleEsc);
    return () => window.removeEventListener("keydown", handleEsc);
  }, [showManualModal, showTypeSelectionModal]);

  const handleManualSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!docType) {
      alert("Falta el tipo (Factura/Venta).");
      return;
    }
    
    if (!token) {
      alert("Sesión caducada. Inicia sesión de nuevo.");
      return;
    }
    
    // Validar campos obligatorios
    if (!manualForm.fecha_dt || !manualForm.proveedor || !manualForm.importe_sin_iva_local || !manualForm.iva_local) {
      alert("Por favor, completa todos los campos obligatorios (marcados con *)");
      return;
    }

    setUploading(true);
    try {
      // Preparar FormData con todos los campos
      const fd = new FormData();
      
      // Campos obligatorios
      fd.append("fecha", manualForm.fecha || "");
      fd.append("fecha_dt", manualForm.fecha_dt || "");
      fd.append("proveedor", manualForm.proveedor);
      fd.append("importe_sin_iva_local", manualForm.importe_sin_iva_local || "");
      fd.append("iva_local", manualForm.iva_local || "");
      
      // Campos opcionales
      if (manualForm.supplier_vat_number) fd.append("supplier_vat_number", manualForm.supplier_vat_number);
      if (manualForm.total_moneda_local) fd.append("total_moneda_local", manualForm.total_moneda_local);
      if (manualForm.moneda) fd.append("moneda", manualForm.moneda);
      if (manualForm.tarifa_cambio) fd.append("tarifa_cambio", manualForm.tarifa_cambio);
      if (manualForm.importe_sin_iva_euro) fd.append("importe_sin_iva_euro", manualForm.importe_sin_iva_euro);
      if (manualForm.importe_total_euro) fd.append("importe_total_euro", manualForm.importe_total_euro);
      if (manualForm.pais_origen) fd.append("pais_origen", manualForm.pais_origen);
      if (manualForm.id_ext) fd.append("id_ext", manualForm.id_ext);
      if (manualForm.notas) fd.append("notas", manualForm.notas);
      if (manualForm.descripcion) fd.append("descripcion", manualForm.descripcion);
      if (manualForm.categoria) fd.append("categoria", manualForm.categoria);
      
      // Archivo opcional
      if (manualFile) {
        fd.append("file", manualFile);
      }
      
      // Llamar al endpoint del backend
      const res = await fetchWithAuth("/api/facturas/manual", {
        method: "POST",
        token: token || undefined,
        onLogout,
        body: fd,
      });
      
      if (!res.ok) {
        const errorText = await res.text();
        console.error("Error guardando factura manual:", errorText);
        alert(`Error guardando factura: ${errorText}`);
        return;
      }
      
      const result = await res.json();
      console.log("✅ Factura manual guardada:", result);
      
      // Recargar histórico si hay archivo
      if (manualFile) {
        loadHistorico();
      }
      
      setShowManualModal(false);
      setManualForm(initialManualForm);
      setManualFile(null);
      setShowSuccess(true);
    } catch (err: any) {
      console.error("Error en handleManualSubmit:", err);
      alert("Error guardando factura: " + (err?.message ?? String(err)));
    } finally {
      setUploading(false);
    }
  };

  const manualLabelStyle: React.CSSProperties = {
    fontSize: "0.875rem",
    fontWeight: 600,
    marginBottom: 6,
    color: "#374151",
  };

  const manualInputStyle: React.CSSProperties = {
    width: "100%",
    padding: "10px 12px",
    borderRadius: 8,
    border: "1px solid #d1d5db",
    fontSize: "0.95rem",
    boxSizing: "border-box",
    transition: "border-color 0.2s, box-shadow 0.2s",
  };

  return (
    <div className="w-full sm:max-w-[75%] mx-auto px-4 sm:px-6 lg:px-8">
      <div className="rounded-2xl shadow-soft bg-white/80 backdrop-blur p-6 border border-gray-100">
        <h1
          className="text-3xl sm:text-4xl font-bold text-center mb-2"
          style={{
            background: "linear-gradient(135deg, #092342 0%, #1a335a 100%)",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
            backgroundClip: "text",
            marginBottom: 32,
            letterSpacing: "-0.02em",
          }}
        >
          Subir factura o fichero de ventas
        </h1>

        {/* Selector tipo */}
        <div className="text-center mb-3 text-sm text-gray-600">
          Selecciona el tipo de fichero a subir
        </div>
        <div
          className="flex items-center justify-center gap-4 mb-6"
          style={{ marginBottom: 8 }}
        >
          <button
            type="button"
            className="px-4 py-2 rounded-lg text-white"
            style={{
              marginRight: "6px",
              backgroundColor: docType === "factura" ? "#071a2e" : "#0875bb",
            }}
            onMouseEnter={(e) => {
              if (docType !== "factura") {
                e.currentTarget.style.backgroundColor = "#071a2e";
              }
            }}
            onMouseLeave={(e) => {
              if (docType !== "factura") {
                e.currentTarget.style.backgroundColor = "#0875bb";
              }
            }}
            onClick={() => setDocType("factura")}
          >
            Factura
          </button>
          <button
            type="button"
            className="px-4 py-2 rounded-lg text-white"
            style={{
              marginLeft: "6px",
              backgroundColor: docType === "venta" ? "#071a2e" : "#0875bb",
            }}
            onMouseEnter={(e) => {
              if (docType !== "venta") {
                e.currentTarget.style.backgroundColor = "#071a2e";
              }
            }}
            onMouseLeave={(e) => {
              if (docType !== "venta") {
                e.currentTarget.style.backgroundColor = "#0875bb";
              }
            }}
            onClick={() => setDocType("venta")}
          >
            Venta
          </button>
          <button
            type="button"
            onClick={openManualModal}
            className="px-4 py-2 rounded-lg bg-[#0875bb] text-white hover:bg-[#071a2e]"
          >
            ➕ Añadir manualmente
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
            border: `2px dashed ${
              dragOver && !disabled ? "#1d4ed8" : "#cbd5e1"
            }`,
            borderRadius: 12,
            minHeight: 260,
            padding: 24,
            textAlign: "center" as const,
            cursor: disabled ? "not-allowed" : "pointer",
            opacity: disabled ? 0.5 : 1,
            filter: disabled ? "grayscale(0.1)" : "none",
            boxShadow:
              dragOver && !disabled ? "0 6px 20px rgba(29,78,216,.15)" : "none",
            transition:
              "border-color 120ms ease, box-shadow 120ms ease, opacity 120ms ease",
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
              o <strong style={{ color: "#1d4ed8" }}>Venta</strong> para
              habilitar
            </div>
          )}

          <p
            style={{
              fontWeight: 600,
              color: "#111827",
              margin: "4px 0 6px",
            }}
          >
            Arrastra y suelta archivos aquí
          </p>
          <p
            style={{
              color: "#6b7280",
              fontSize: "0.95rem",
              margin: 0,
            }}
          >
            o haz clic para seleccionar PDF o XLSX (múltiples)
          </p>

          {/* Lista de archivos seleccionados */}
          {files.length > 0 && (
            <div
              style={{
                marginTop: 14,
                display: "flex",
                gap: 8,
                flexWrap: "wrap",
                justifyContent: "center",
              }}
            >
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
              className={`seg-option ${
                uploading ? "opacity-50 cursor-not-allowed" : "seg-selected"
              }`}
              style={{ opacity: uploading ? 0.6 : 1 }}
            >
              {uploading
                ? `Subiendo… ${
                    uploadingIndex !== null
                      ? `${uploadingIndex + 1}/${files.length}`
                      : ""
                  }`
                : `Subir ${files.length} archivo${
                    files.length > 1 ? "s" : ""
                  }`}
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
              Vas a subir <strong>{files.length}</strong> archivo
              {files.length > 1 ? "s" : ""} como{" "}
              <strong>{docType}</strong>. ¿Confirmas?
            </p>
            {/* Muestra hasta 5 nombres */}
            <div className="flex justify-center mt-2">
              <ul className="text-xs text-gray-600 max-h-28 overflow-auto text-left">
                {files.slice(0, 5).map((f) => (
                  <li key={f.name + f.size}>• {f.name}</li>
                ))}
                {files.length > 5 && (
                  <li>… y {files.length - 5} más</li>
                )}
              </ul>
            </div>
            
            {/* Mensaje de progreso animado */}
            {uploading && (
              <div 
                className="mt-6 flex flex-col items-center justify-center gap-2"
                style={{
                  opacity: 0,
                  animation: "fadeIn 0.3s ease-in forwards",
                }}
              >
                <div className="flex items-center gap-2">
                  <div 
                    style={{
                      width: "20px",
                      height: "20px",
                      border: "2px solid #0875bb",
                      borderTopColor: "transparent",
                      borderRadius: "50%",
                      animation: "spin 1s linear infinite",
                    }}
                  />
                  <span className="text-sm font-medium text-[#0875bb]">
                    Subiendo archivos, por favor espere...
                  </span>
                </div>
                {uploadingIndex !== null && (
                  <span className="text-xs text-gray-500">
                    {uploadingIndex + 1} de {files.length} archivos
                  </span>
                )}
              </div>
            )}
            
            {/* Botones - ocultos cuando está subiendo */}
            {!uploading && (
              <div className="mt-6 flex justify-center gap-4">
                <button
                  className="modal-btn modal-btn-cancel"
                  onClick={() => setShowConfirm(false)}
                  disabled={uploading}
                >
                  Cancelar
                </button>
                <button
                  className="modal-btn modal-btn-confirm"
                  onClick={confirmUpload}
                  disabled={uploading}
                >
                  Confirmar
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Modal de éxito */}
      {showSuccess && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl p-6 w-full max-w-md shadow-xl border border-gray-100 text-center">
            <h2 className="text-lg font-semibold text-gray-900 mb-3">
              ✅ Archivo
              {files.length > 1 ? "s" : ""} subido
              {files.length > 1 ? "s" : ""} correctamente
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

      {/* Modal de selección de tipo */}
      {showTypeSelectionModal && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
          onClick={(e) => {
            if (e.target === e.currentTarget) {
              setShowTypeSelectionModal(false);
            }
          }}
        >
          <div
            className="bg-white rounded-2xl shadow-2xl w-full max-w-md overflow-hidden"
            style={{
              boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.25)",
            }}
          >
            {/* Header con botón X */}
            <div className="flex items-center justify-between p-6 border-b border-gray-200">
              <h2 
                className="text-xl font-bold"
                style={{
                  background: "linear-gradient(135deg, #3631a3 0%, #092342 100%)",
                  WebkitBackgroundClip: "text",
                  WebkitTextFillColor: "transparent",
                  backgroundClip: "text",
                }}
              >
                Selecciona el tipo
              </h2>
              <button
                onClick={() => setShowTypeSelectionModal(false)}
                className="text-gray-400 hover:text-gray-600 transition-colors"
                style={{
                  fontSize: "24px",
                  lineHeight: "1",
                  padding: "4px",
                  cursor: "pointer",
                }}
                aria-label="Cerrar"
              >
                ×
              </button>
            </div>

            {/* Contenido */}
            <div className="p-6">
              <p className="text-sm text-gray-600 mb-6 text-center">
                Por favor, selecciona si quieres añadir una factura o una venta manualmente.
              </p>
              
              <div className="flex flex-col gap-4">
                <button
                  type="button"
                  onClick={() => handleTypeSelection("factura")}
                  className="seg-option seg-selected text-center py-4 px-6"
                  style={{
                    fontSize: "16px",
                    fontWeight: 700,
                  }}
                >
                  Factura
                </button>
                <button
                  type="button"
                  onClick={() => handleTypeSelection("venta")}
                  className="seg-option seg-selected text-center py-4 px-6"
                  style={{
                    fontSize: "16px",
                    fontWeight: 700,
                  }}
                >
                  Venta
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Modal formulario manual */}
      {showManualModal && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
          style={{ paddingTop: "80px" }}
          onClick={(e) => {
            if (e.target === e.currentTarget) {
              setShowManualModal(false);
              setManualForm(initialManualForm);
              setManualFile(null);
            }
          }}
        >
          <div
            className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl max-h-[calc(90vh-80px)] overflow-hidden flex flex-col"
            style={{
              boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.25)",
            }}
          >
            {/* Header con botón X */}
            <div className="flex items-center justify-between p-6 border-b border-gray-200">
              <h2 
                className="text-2xl font-bold"
                style={{
                  background: "linear-gradient(135deg, #3631a3 0%, #092342 100%)",
                  WebkitBackgroundClip: "text",
                  WebkitTextFillColor: "transparent",
                  backgroundClip: "text",
                }}
              >
                Añadir {docType === "venta" ? "venta" : "factura"} manualmente
              </h2>
              <button
                onClick={() => {
                  setShowManualModal(false);
                  setManualForm(initialManualForm);
                  setManualFile(null);
                }}
                className="text-gray-400 hover:text-gray-600 transition-colors"
                style={{
                  fontSize: "24px",
                  lineHeight: "1",
                  padding: "4px",
                  cursor: "pointer",
                }}
                aria-label="Cerrar"
              >
                ×
              </button>
            </div>

            {/* Contenido scrolleable */}
            <div className="overflow-y-auto p-6" style={{ maxHeight: "calc(90vh - 200px)" }}>
              <p className="text-sm text-gray-600 mb-6">
                Completa los campos obligatorios (marcados con <span className="text-red-500">*</span>) y opcionalmente sube el archivo de la factura.
              </p>

            <form
              id="manual-form"
              onSubmit={handleManualSubmit}
            >
              {/* Sección 1: Datos generales */}
              <div className="mb-6">
                <h3 className="text-lg font-semibold text-gray-800 mb-4 pb-2 border-b border-gray-200">
                  1. Datos generales
                </h3>
                <div style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
                  gap: "1.25rem 1.5rem",
                }}>
                  {/* Fecha */}
                  <div>
                    <label style={manualLabelStyle}>
                      Fecha <span className="text-red-500">*</span>
                    </label>
                    <input
                      type="date"
                      required
                      value={manualForm.fecha_dt}
                      onChange={(e) => {
                        setManualField("fecha_dt", e.target.value);
                        setManualField("fecha", e.target.value);
                      }}
                      style={manualInputStyle}
                      onFocus={(e) => {
                        e.currentTarget.style.borderColor = "#0875bb";
                        e.currentTarget.style.boxShadow = "0 0 0 3px rgba(8, 117, 187, 0.1)";
                      }}
                      onBlur={(e) => {
                        e.currentTarget.style.borderColor = "#d1d5db";
                        e.currentTarget.style.boxShadow = "none";
                      }}
                    />
                  </div>

                  {/* Proveedor */}
                  <div>
                    <label style={manualLabelStyle}>
                      Nombre de proveedor <span className="text-red-500">*</span>
                    </label>
                    <input
                      type="text"
                      required
                      value={manualForm.proveedor}
                      onChange={(e) => setManualField("proveedor", e.target.value)}
                      style={manualInputStyle}
                      onFocus={(e) => {
                        e.currentTarget.style.borderColor = "#0875bb";
                        e.currentTarget.style.boxShadow = "0 0 0 3px rgba(8, 117, 187, 0.1)";
                      }}
                      onBlur={(e) => {
                        e.currentTarget.style.borderColor = "#d1d5db";
                        e.currentTarget.style.boxShadow = "none";
                      }}
                    />
                  </div>

                  {/* VAT proveedor */}
                  <div style={{ gridColumn: "1 / -1" }}>
                    <label style={manualLabelStyle}>VAT del proveedor</label>
                    <input
                      type="text"
                      value={manualForm.supplier_vat_number}
                      onChange={(e) =>
                        setManualField("supplier_vat_number", e.target.value)
                      }
                      style={manualInputStyle}
                      onFocus={(e) => {
                        e.currentTarget.style.borderColor = "#0875bb";
                        e.currentTarget.style.boxShadow = "0 0 0 3px rgba(8, 117, 187, 0.1)";
                      }}
                      onBlur={(e) => {
                        e.currentTarget.style.borderColor = "#d1d5db";
                        e.currentTarget.style.boxShadow = "none";
                      }}
                    />
                  </div>
                </div>
              </div>

              {/* Sección 2: Coste */}
              <div className="mb-6">
                <h3 className="text-lg font-semibold text-gray-800 mb-4 pb-2 border-b border-gray-200">
                  2. Coste
                </h3>
                <div style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
                  gap: "1.25rem 1.5rem",
                }}>

                  {/* Importe sin IVA local */}
                  <div>
                    <label style={manualLabelStyle}>
                      Importe local sin IVA <span className="text-red-500">*</span>
                    </label>
                    <input
                      type="number"
                      step="0.01"
                      required
                      value={manualForm.importe_sin_iva_local}
                      onChange={(e) =>
                        setManualField("importe_sin_iva_local", e.target.value)
                      }
                      style={manualInputStyle}
                      onFocus={(e) => {
                        e.currentTarget.style.borderColor = "#0875bb";
                        e.currentTarget.style.boxShadow = "0 0 0 3px rgba(8, 117, 187, 0.1)";
                      }}
                      onBlur={(e) => {
                        e.currentTarget.style.borderColor = "#d1d5db";
                        e.currentTarget.style.boxShadow = "none";
                      }}
                    />
                  </div>

                  {/* IVA local */}
                  <div>
                    <label style={manualLabelStyle}>
                      % IVA local <span className="text-red-500">*</span>
                    </label>
                    <input
                      type="number"
                      step="0.01"
                      required
                      value={manualForm.iva_local}
                      onChange={(e) => setManualField("iva_local", e.target.value)}
                      style={manualInputStyle}
                      onFocus={(e) => {
                        e.currentTarget.style.borderColor = "#0875bb";
                        e.currentTarget.style.boxShadow = "0 0 0 3px rgba(8, 117, 187, 0.1)";
                      }}
                      onBlur={(e) => {
                        e.currentTarget.style.borderColor = "#d1d5db";
                        e.currentTarget.style.boxShadow = "none";
                      }}
                    />
                  </div>

                  {/* Moneda */}
                  <div>
                    <label style={manualLabelStyle}>Moneda</label>
                    <select
                      value={manualForm.moneda}
                      onChange={(e) => setManualField("moneda", e.target.value)}
                      style={manualInputStyle}
                    >
                      {CURRENCY_CODES.map((c) => (
                        <option key={c} value={c}>
                          {c}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Total moneda local */}
                  <div>
                    <label style={manualLabelStyle}>Total en moneda local</label>
                    <input
                      type="number"
                      step="0.01"
                      value={manualForm.total_moneda_local}
                      onChange={(e) =>
                        setManualField("total_moneda_local", e.target.value)
                      }
                      style={manualInputStyle}
                      onFocus={(e) => {
                        e.currentTarget.style.borderColor = "#0875bb";
                        e.currentTarget.style.boxShadow = "0 0 0 3px rgba(8, 117, 187, 0.1)";
                      }}
                      onBlur={(e) => {
                        e.currentTarget.style.borderColor = "#d1d5db";
                        e.currentTarget.style.boxShadow = "none";
                      }}
                    />
                  </div>

                  {/* Tarifa de cambio */}
                  <div>
                    <label style={manualLabelStyle}>Tarifa de cambio €/moneda local</label>
                    <input
                      type="number"
                      step="0.0001"
                      value={manualForm.tarifa_cambio}
                      onChange={(e) =>
                        setManualField("tarifa_cambio", e.target.value)
                      }
                      style={manualInputStyle}
                      onFocus={(e) => {
                        e.currentTarget.style.borderColor = "#0875bb";
                        e.currentTarget.style.boxShadow = "0 0 0 3px rgba(8, 117, 187, 0.1)";
                      }}
                      onBlur={(e) => {
                        e.currentTarget.style.borderColor = "#d1d5db";
                        e.currentTarget.style.boxShadow = "none";
                      }}
                    />
                  </div>

                  {/* Importe sin IVA (EUR) */}
                  <div>
                    <label style={manualLabelStyle}>Importe sin IVA (EUR)</label>
                    <input
                      type="number"
                      step="0.01"
                      value={manualForm.importe_sin_iva_euro}
                      onChange={(e) =>
                        setManualField("importe_sin_iva_euro", e.target.value)
                      }
                      style={manualInputStyle}
                      onFocus={(e) => {
                        e.currentTarget.style.borderColor = "#0875bb";
                        e.currentTarget.style.boxShadow = "0 0 0 3px rgba(8, 117, 187, 0.1)";
                      }}
                      onBlur={(e) => {
                        e.currentTarget.style.borderColor = "#d1d5db";
                        e.currentTarget.style.boxShadow = "none";
                      }}
                    />
                  </div>

                  {/* Importe total (EUR) */}
                  <div>
                    <label style={manualLabelStyle}>Importe total (EUR)</label>
                    <input
                      type="number"
                      step="0.01"
                      value={manualForm.importe_total_euro}
                      onChange={(e) =>
                        setManualField("importe_total_euro", e.target.value)
                      }
                      style={manualInputStyle}
                      onFocus={(e) => {
                        e.currentTarget.style.borderColor = "#0875bb";
                        e.currentTarget.style.boxShadow = "0 0 0 3px rgba(8, 117, 187, 0.1)";
                      }}
                      onBlur={(e) => {
                        e.currentTarget.style.borderColor = "#d1d5db";
                        e.currentTarget.style.boxShadow = "none";
                      }}
                    />
                  </div>
                </div>
              </div>

              {/* Sección 3: Datos adicionales */}
              <div className="mb-6">
                <h3 className="text-lg font-semibold text-gray-800 mb-4 pb-2 border-b border-gray-200">
                  3. Datos adicionales
                </h3>
                <div style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
                  gap: "1.25rem 1.5rem",
                }}>
                  {/* País origen */}
                  <div>
                    <label style={manualLabelStyle}>País de origen</label>
                    <select
                      value={manualForm.pais_origen}
                      onChange={(e) =>
                        setManualField("pais_origen", e.target.value)
                      }
                      style={manualInputStyle}
                    >
                      {COUNTRY_CODES.map((c) => (
                        <option key={c} value={c}>
                          {c}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* ID externo */}
                  <div>
                    <label style={manualLabelStyle}>ID externo de factura</label>
                    <input
                      type="text"
                      value={manualForm.id_ext}
                      onChange={(e) => setManualField("id_ext", e.target.value)}
                      style={manualInputStyle}
                      onFocus={(e) => {
                        e.currentTarget.style.borderColor = "#0875bb";
                        e.currentTarget.style.boxShadow = "0 0 0 3px rgba(8, 117, 187, 0.1)";
                      }}
                      onBlur={(e) => {
                        e.currentTarget.style.borderColor = "#d1d5db";
                        e.currentTarget.style.boxShadow = "none";
                      }}
                    />
                  </div>

                  {/* Notas */}
                  <div style={{ gridColumn: "1 / -1" }}>
                    <label style={manualLabelStyle}>Notas</label>
                    <textarea
                      value={manualForm.notas}
                      onChange={(e) => setManualField("notas", e.target.value)}
                      style={{ ...manualInputStyle, minHeight: 60, resize: "vertical" }}
                      onFocus={(e) => {
                        e.currentTarget.style.borderColor = "#0875bb";
                        e.currentTarget.style.boxShadow = "0 0 0 3px rgba(8, 117, 187, 0.1)";
                      }}
                      onBlur={(e) => {
                        e.currentTarget.style.borderColor = "#d1d5db";
                        e.currentTarget.style.boxShadow = "none";
                      }}
                    />
                  </div>

                  {/* Descripción */}
                  <div style={{ gridColumn: "1 / -1" }}>
                    <label style={manualLabelStyle}>Descripción</label>
                    <textarea
                      value={manualForm.descripcion}
                      onChange={(e) =>
                        setManualField("descripcion", e.target.value)
                      }
                      style={{ ...manualInputStyle, minHeight: 60, resize: "vertical" }}
                      onFocus={(e) => {
                        e.currentTarget.style.borderColor = "#0875bb";
                        e.currentTarget.style.boxShadow = "0 0 0 3px rgba(8, 117, 187, 0.1)";
                      }}
                      onBlur={(e) => {
                        e.currentTarget.style.borderColor = "#d1d5db";
                        e.currentTarget.style.boxShadow = "none";
                      }}
                    />
                  </div>
                </div>
              </div>

              {/* Sección 4: Archivo de factura */}
              <div className="mb-6">
                <h3 className="text-lg font-semibold text-gray-800 mb-4 pb-2 border-b border-gray-200">
                  4. Archivo de factura (opcional)
                </h3>
                <div className="flex items-center gap-3">
                  <input
                    ref={manualFileInputRef}
                    type="file"
                    accept=".pdf,.xlsx,application/pdf,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    onChange={(e) => {
                      if (e.target.files && e.target.files[0]) {
                        setManualFile(e.target.files[0]);
                      }
                    }}
                    style={{ display: "none" }}
                  />
                  <button
                    type="button"
                    onClick={() => manualFileInputRef.current?.click()}
                    className="px-4 py-2 rounded-lg border border-gray-300 hover:bg-gray-50 transition-colors"
                    style={{ fontSize: "0.875rem" }}
                  >
                    {manualFile ? "Cambiar archivo" : "Seleccionar archivo"}
                  </button>
                  {manualFile && (
                    <span className="text-sm text-gray-600">
                      {manualFile.name} ({(manualFile.size / 1024).toFixed(0)} KB)
                    </span>
                  )}
                </div>
              </div>

            </form>
            </div>

            {/* Footer con botones */}
            <div className="flex justify-end gap-3 p-6 border-t border-gray-200 bg-gray-50">
              <button
                type="button"
                onClick={() => {
                  setShowManualModal(false);
                  setManualForm(initialManualForm);
                  setManualFile(null);
                }}
                className="px-5 py-2 rounded-lg border border-gray-300 bg-white hover:bg-gray-50 transition-colors font-medium"
                disabled={uploading}
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={handleManualSubmit}
                className="px-5 py-2 rounded-lg bg-[#0875bb] text-white hover:bg-[#065a8f] transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                disabled={uploading}
              >
                {uploading ? (
                  <span className="flex items-center gap-2">
                    <div 
                      style={{
                        width: "16px",
                        height: "16px",
                        border: "2px solid #ffffff",
                        borderTopColor: "transparent",
                        borderRadius: "50%",
                        animation: "spin 1s linear infinite",
                      }}
                    />
                    Guardando...
                  </span>
                ) : (
                  "Guardar"
                )}
              </button>
            </div>
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
        <p
          style={{
            margin: "0.25rem 0 1rem",
            color: "#5b667a",
            textAlign: "center",
          }}
        >
          Facturas (1:1) y ventas (por lote)
        </p>

        {opsError && (
          <div style={{ color: "red", marginBottom: "0.75rem" }}>
            {opsError}
          </div>
        )}

        <div style={{ overflowX: "auto" }}>
          <table
            style={{
              width: "100%",
              borderCollapse: "separate",
              borderSpacing: 0,
            }}
          >
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
                        background:
                          op.tipo === "FACTURA" ? "#eef2ff" : "#ecfdf5",
                        color:
                          op.tipo === "FACTURA" ? "#3730a3" : "#065f46",
                        fontWeight: 600,
                      }}
                    >
                      {op.tipo}
                    </span>
                  </td>
                  <td
                    style={{
                      ...td,
                      textAlign: "left",
                      maxWidth: "200px",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                    title={op.original_filename}
                  >
                    {op.original_filename.length > 30
                      ? op.original_filename.substring(0, 30) + "..."
                      : op.original_filename}
                  </td>
                  <td
                    style={{
                      ...td,
                      textAlign: "left",
                      maxWidth: "200px",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                    title={op.descripcion}
                  >
                    {op.descripcion.length > 30
                      ? op.descripcion.substring(0, 30) + "..."
                      : op.descripcion}
                  </td>
                  <td
                    style={{
                      ...td,
                      textAlign: "right",
                      fontVariantNumeric: "tabular-nums",
                    }}
                  >
                    {op.tam_bytes != null
                      ? (op.tam_bytes / 1024).toFixed(0)
                      : "-"}
                  </td>
                  <td style={{ ...td, textAlign: "center" }}>
                    {op.status === "FAILED" ? (
                      <button
                        onClick={() => retryWebhook(op)}
                        disabled={retryingId === op.id}
                        className="px-3 py-1 rounded-lg text-white"
                        style={{
                          backgroundColor:
                            retryingId === op.id ? "#94a3b8" : "#1d4ed8",
                          cursor:
                            retryingId === op.id
                              ? "not-allowed"
                              : "pointer",
                        }}
                        title="Reintentar envío al procesador"
                      >
                        {retryingId === op.id
                          ? "Reintentando…"
                          : "Reintentar"}
                      </button>
                    ) : (
                      <span style={{ color: "#94a3b8" }}>—</span>
                    )}
                  </td>
                </tr>
              ))}
              {ops.length === 0 && !opsError && (
                <tr>
                  <td
                    colSpan={5}
                    style={{
                      ...td,
                      textAlign: "center",
                      color: "#667085",
                    }}
                  >
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