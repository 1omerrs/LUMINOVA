import { useState, type ChangeEvent } from "react";
import { previewImport, readImportFile, runImport, type ImportFile, type ImportMapping, type ImportPreview, type ImportReport } from "../../lib/customers.ts";
import { ApiRequestError } from "../../lib/http.ts";
import { Alert, Button, Spinner } from "../forms/Controls.tsx";
import { Sheet } from "../ui/Sheet.tsx";

const fields: { key: keyof ImportMapping; label: string; required?: boolean }[] = [
  { key: "name", label: "Müşteri adı", required: true },
  { key: "email", label: "E-posta" },
  { key: "phone", label: "Telefon" },
  { key: "note", label: "Not" },
];
const select =
  "h-9 w-full rounded-lg border border-mist bg-surface px-2.5 text-[13px] text-graphite outline-none hover:border-stone focus:border-violet";

export function ImportSheet({ onClose, onImported }: { onClose: () => void; onImported: (created: number) => void }) {
  const [file, setFile] = useState<ImportFile | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [mapping, setMapping] = useState<ImportMapping | null>(null);
  const [report, setReport] = useState<ImportReport | null>(null);
  const [busy, setBusy] = useState<"read" | "check" | "import" | null>(null);
  const [error, setError] = useState("");

  async function onFile(event: ChangeEvent<HTMLInputElement>) {
    const chosen = event.target.files?.[0];
    if (!chosen) return;
    setBusy("read");
    setError("");
    setReport(null);
    try {
      const encoded = await readImportFile(chosen);
      const next = await previewImport(encoded);
      setFile(encoded);
      setPreview(next);
      setMapping(next.mapping);
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Dosya okunamadı.");
      setFile(null);
      setPreview(null);
    } finally {
      setBusy(null);
    }
  }

  async function run(dryRun: boolean) {
    if (!file || !mapping) return;
    setBusy(dryRun ? "check" : "import");
    setError("");
    try {
      const result = await runImport(file, mapping, dryRun);
      setReport(result);
      if (!dryRun) onImported(result.created);
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Aktarım tamamlanamadı.");
    } finally {
      setBusy(null);
    }
  }

  const checked = report?.dry_run ? report : null;
  const finished = report && !report.dry_run ? report : null;

  return (
    <Sheet
      wide
      title="Müşteri listesi aktar"
      description="CSV veya Excel (.xlsx) dosyası; ilk satır sütun başlıkları olmalı. En çok 2000 satır."
      busy={busy !== null}
      onClose={onClose}
      footer={
        finished ? (
          <Button onClick={onClose}>Kapat</Button>
        ) : (
          <>
            <Button variant="quiet" onClick={onClose} disabled={busy !== null}>
              Vazgeç
            </Button>
            <Button variant="quiet" onClick={() => void run(true)} disabled={!file || mapping?.name == null} pending={busy === "check"} pendingLabel="Kontrol ediliyor">
              Kontrol et
            </Button>
            <Button onClick={() => void run(false)} disabled={!checked || checked.valid === 0} pending={busy === "import"} pendingLabel="Aktarılıyor">
              {checked ? `${checked.valid} müşteriyi aktar` : "Aktar"}
            </Button>
          </>
        )
      }
    >
      <div className="space-y-6">
        <label className="flex cursor-pointer items-center justify-between gap-4 rounded-lg border border-dashed border-stone bg-paper px-4 py-4 hover:border-ink-soft">
          <span>
            <span className="block text-[14px] font-medium">{file ? file.filename : "Dosya seçin"}</span>
            <span className="block text-[12px] text-slate">{preview ? `${preview.total_rows} satır bulundu` : "Ayraç (; , sekme) ve Türkçe karakter kodlaması kendiliğinden algılanır."}</span>
          </span>
          {busy === "read" ? <Spinner /> : <span className="text-[12.5px] font-medium text-graphite">Gözat</span>}
          <input type="file" accept=".csv,.txt,.xlsx" onChange={(event) => void onFile(event)} className="sr-only" />
        </label>

        {error ? <Alert tone="error">{error}</Alert> : null}

        {preview && mapping ? (
          <section>
            <h3 className="text-[12px] font-medium uppercase tracking-[0.08em] text-slate">Sütun eşleştirme</h3>
            <div className="mt-2 grid gap-3 sm:grid-cols-4">
              {fields.map((field) => (
                <label key={field.key} className="block">
                  <span className="text-[12.5px] font-medium">
                    {field.label}
                    {field.required ? <span className="text-error-text"> *</span> : null}
                  </span>
                  <select
                    value={mapping[field.key] ?? ""}
                    onChange={(event) => {
                      setReport(null);
                      setMapping({ ...mapping, [field.key]: event.target.value === "" ? null : Number(event.target.value) });
                    }}
                    className={`${select} mt-1`}
                  >
                    <option value="">Kullanma</option>
                    {preview.headers.map((header, index) => (
                      <option key={index} value={index}>
                        {header || `Sütun ${index + 1}`}
                      </option>
                    ))}
                  </select>
                </label>
              ))}
            </div>
            <div className="mt-4 overflow-x-auto">
              <table className="w-full min-w-[520px] text-left text-[12.5px]">
                <thead className="text-slate">
                  <tr className="border-b border-hairline">
                    {fields.map((field) => (
                      <th key={field.key} className="py-1.5 pr-3 font-medium">
                        {field.label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-hairline">
                  {preview.sample.map((row, index) => (
                    <tr key={index}>
                      {fields.map((field) => (
                        <td key={field.key} className="max-w-[200px] truncate py-1.5 pr-3">
                          {mapping[field.key] != null ? row[mapping[field.key] as number] || <span className="text-slate/60">—</span> : <span className="text-slate/60">—</span>}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="mt-1.5 text-[11.5px] text-slate">İlk {preview.sample.length} satır önizleniyor.</p>
            </div>
          </section>
        ) : null}

        {report ? (
          <section aria-live="polite">
            <h3 className="text-[12px] font-medium uppercase tracking-[0.08em] text-slate">{report.dry_run ? "Kontrol sonucu" : "Aktarım tamamlandı"}</h3>
            <dl className="mt-2 grid grid-cols-3 border-y border-hairline">
              <Count label={report.dry_run ? "Aktarılacak" : "Eklendi"} value={report.dry_run ? report.valid : report.created} />
              <Count label="Mükerrer, atlanacak" value={report.duplicates.length} />
              <Count label="Hatalı satır" value={report.errors.length} alert={report.errors.length > 0} />
            </dl>
            {report.duplicates.length > 0 ? (
              <details className="mt-3" open={report.duplicates.length <= 8}>
                <summary className="cursor-pointer text-[13px] font-medium">Mükerrer kayıtlar</summary>
                <ul className="mt-1.5 space-y-1 text-[12.5px]">
                  {report.duplicates.map((item) => (
                    <li key={item.row}>
                      <span className="tabular-nums text-slate">{item.row}. satır</span> {item.name} — {item.reason}
                      {item.existing_name ? <span className="text-slate"> (mevcut: {item.existing_name})</span> : null}
                    </li>
                  ))}
                </ul>
              </details>
            ) : null}
            {report.errors.length > 0 ? (
              <details className="mt-3" open>
                <summary className="cursor-pointer text-[13px] font-medium text-error-text">Hatalı satırlar aktarılmaz</summary>
                <ul className="mt-1.5 space-y-1 text-[12.5px]">
                  {report.errors.map((item) => (
                    <li key={item.row}>
                      <span className="tabular-nums text-slate">{item.row}. satır</span> {item.message}
                    </li>
                  ))}
                </ul>
              </details>
            ) : null}
          </section>
        ) : null}
      </div>
    </Sheet>
  );
}

function Count({ label, value, alert = false }: { label: string; value: number; alert?: boolean }) {
  return (
    <div className="py-3 pr-3">
      <dt className="text-[11.5px] text-slate">{label}</dt>
      <dd className={`text-[18px] font-semibold tabular-nums ${alert ? "text-error-text" : "text-midnight"}`}>{value}</dd>
    </div>
  );
}
