import { useEffect, useState, type ReactNode } from "react";
import { deleteCustomer, fetchCustomers, sortLabels, type Customer, type CustomerPage, type CustomerSort } from "../../lib/customers.ts";
import { ApiRequestError } from "../../lib/http.ts";
import { readOnly, type WorkspaceModule } from "../../lib/modules.ts";
import { Alert, Button, Spinner } from "../forms/Controls.tsx";
import { ConfirmDialog } from "../ui/ConfirmDialog.tsx";
import { Icon } from "../ui/Icon.tsx";
import { Pagination } from "../ui/Pagination.tsx";
import { ModuleIcon } from "../workspace/ModuleIcon.tsx";
import { useSearchParams } from "react-router";
import { CustomerDetail } from "./CustomerDetail.tsx";
import { CustomerEditor } from "./CustomerEditor.tsx";
import { ImportSheet } from "./ImportSheet.tsx";

const PAGE_SIZE = 20;
const dateFormat = new Intl.DateTimeFormat("tr-TR", { day: "numeric", month: "short", year: "numeric" });

type Load = { status: "loading" } | { status: "ready"; data: CustomerPage } | { status: "failed"; message: string };
type Editing = { customer: Customer | null } | null;

export function CustomersView({ module, switcher }: { module: WorkspaceModule; switcher?: ReactNode }) {
  const [input, setInput] = useState("");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<CustomerSort>("-created_at");
  const [page, setPage] = useState(1);
  const [reload, setReload] = useState(0);
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [editing, setEditing] = useState<Editing>(null);
  const [removing, setRemoving] = useState<Customer | null>(null);
  const [notice, setNotice] = useState("");
  const [importing, setImporting] = useState(false);
  const [params, setParams] = useSearchParams();
  const selected = params.get("musteri");

  function open(id: string | null) {
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        if (id) next.set("musteri", id);
        else next.delete("musteri");
        return next;
      },
      { replace: true },
    );
  }

  useEffect(() => {
    const next = input.trim();
    if (next === search) return;
    const timer = window.setTimeout(() => {
      setSearch(next);
      setPage(1);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [input, search]);

  useEffect(() => {
    let cancelled = false;
    fetchCustomers({ q: search, sort, page, pageSize: PAGE_SIZE })
      .then((data) => {
        if (cancelled) return;
        if (data.items.length === 0 && data.page > 1) {
          setPage(data.page - 1);
          return;
        }
        setLoad({ status: "ready", data });
      })
      .catch((error: unknown) => {
        if (!cancelled) setLoad({ status: "failed", message: error instanceof ApiRequestError ? error.message : "Müşteriler yüklenemedi." });
      });
    return () => {
      cancelled = true;
    };
  }, [search, sort, page, reload]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(""), 4000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  function refresh() {
    setReload((value) => value + 1);
  }

  const data = load.status === "ready" ? load.data : null;
  const emptyWorkspace = data !== null && data.total === 0 && search === "";

  return (
    <div className="space-y-6">
      <section className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex min-w-0 items-center gap-4">
          <div className="min-w-0">
            <h1 className="font-display text-[22px] font-semibold tracking-[-0.02em] text-midnight sm:text-[24px]">{module.name}</h1>
            <p className="mt-0.5 text-[14px] text-slate">
              {data ? `${data.total} müşteri kaydı` : module.summary}
            </p>
          </div>
        </div>
        <div className={`flex gap-2 ${readOnly(module) ? "hidden" : ""}`}>
          <Button variant="quiet" size="lg" onClick={() => setImporting(true)}>
            İçe aktar
          </Button>
          {emptyWorkspace ? null : (
            <Button size="lg" onClick={() => setEditing({ customer: null })}>
              <Icon name="plus" className="h-4 w-4" strokeWidth={2} />
              Müşteri ekle
            </Button>
          )}
        </div>
      </section>
      {switcher}

      {notice ? <Alert tone="success">{notice}</Alert> : null}

      {emptyWorkspace ? (
        <section className="rounded-2xl border border-mist/80 bg-surface px-6 py-16 text-center">
          <span className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-paper text-ink-soft ring-1 ring-inset ring-mist">
            <ModuleIcon name="customers" className="h-6 w-6" />
          </span>
          <h2 className="mt-5 text-[16px] font-semibold">İlk müşterinizi ekleyin.</h2>
          <p className="mx-auto mt-2 max-w-md text-[14px] leading-6 text-slate">
            Müşteri kartlarında iletişim bilgilerini ve notlarınızı tek yerde tutun. Kayıtlar yalnızca bu çalışma alanında görünür.
          </p>
          <Button className="mt-6" onClick={() => setEditing({ customer: null })}>
            <Icon name="plus" className="h-4 w-4" strokeWidth={2} />
            Müşteri ekle
          </Button>
        </section>
      ) : (
        <section className="overflow-hidden rounded-2xl border border-mist/80 bg-surface">
          <div className="flex flex-col gap-3 border-b border-mist/70 px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-5">
            <label className="relative block w-full sm:max-w-xs">
              <span className="sr-only">Müşteri ara</span>
              <Icon name="search" className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate" />
              <input
                type="search"
                value={input}
                onChange={(event) => setInput(event.target.value)}
                placeholder="Ad, e-posta veya telefon ara"
                className="h-10 w-full rounded-lg border border-mist bg-surface pl-9 pr-3 text-[14px] outline-none transition-[border-color,box-shadow] placeholder:text-slate/70 hover:border-stone focus:border-violet focus:shadow-[0_0_0_4px_rgba(91,71,214,0.14)]"
              />
            </label>
            <label className="flex items-center gap-2 text-[13px] text-slate">
              Sırala
              <select
                aria-label="Sırala"
                value={sort}
                onChange={(event) => {
                  setSort(event.target.value as CustomerSort);
                  setPage(1);
                }}
                className="h-10 rounded-lg border border-mist bg-surface px-3 text-[14px] text-graphite outline-none hover:border-stone focus:border-violet"
              >
                {(Object.keys(sortLabels) as CustomerSort[]).map((key) => (
                  <option key={key} value={key}>
                    {sortLabels[key]}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {load.status === "failed" ? (
            <div className="px-5 py-10">
              <Alert tone="error">
                {load.message}{" "}
                <button type="button" onClick={refresh} className="font-semibold underline">
                  Tekrar dene
                </button>
              </Alert>
            </div>
          ) : !data ? (
            <p role="status" className="flex items-center gap-2.5 px-5 py-12 text-[14px] text-slate">
              <Spinner className="h-4 w-4 text-violet" /> Müşteriler yükleniyor.
            </p>
          ) : data.items.length === 0 ? (
            <div className="px-5 py-14 text-center">
              <p className="text-[15px] font-semibold">“{search}” ile eşleşen müşteri yok.</p>
              <p className="mt-1 text-[13px] text-slate">Farklı bir ad, e-posta veya telefon deneyin.</p>
              <button type="button" onClick={() => setInput("")} className="mt-4 text-[14px] font-semibold text-violet hover:underline">
                Aramayı temizle
              </button>
            </div>
          ) : (
            <>
              <table className="hidden w-full text-left md:table">
                <thead className="bg-cloud/60 text-[12px] font-medium text-slate">
                  <tr>
                    <th scope="col" className="px-5 py-2.5 font-medium">Müşteri</th>
                    <th scope="col" className="px-3 py-2.5 font-medium">E-posta</th>
                    <th scope="col" className="px-3 py-2.5 font-medium">Telefon</th>
                    <th scope="col" className="px-3 py-2.5 font-medium">Eklenme</th>
                    <th scope="col" className="px-5 py-2.5 text-right font-medium">
                      <span className="sr-only">İşlemler</span>
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-mist/60 text-[14px]">
                  {data.items.map((customer) => (
                    <tr key={customer.id} onClick={() => open(customer.id)} className="group cursor-pointer transition-colors hover:bg-paper">
                      <td className="max-w-[280px] px-5 py-3">
                        <button type="button" onClick={(event) => { event.stopPropagation(); open(customer.id); }} className="block max-w-full truncate text-left font-semibold hover:underline">
                          {customer.name}
                        </button>
                        {customer.note ? <p className="truncate text-[12px] text-slate">{customer.note}</p> : null}
                      </td>
                      <td className="max-w-[240px] truncate px-3 py-3 text-graphite/85">
                        {customer.email ? (
                          <a href={`mailto:${customer.email}`} className="hover:text-violet hover:underline">
                            {customer.email}
                          </a>
                        ) : (
                          <span className="text-slate/70">—</span>
                        )}
                      </td>
                      <td className="whitespace-nowrap px-3 py-3 tabular-nums text-graphite/85">
                        {customer.phone ?? <span className="text-slate/70">—</span>}
                      </td>
                      <td className="whitespace-nowrap px-3 py-3 text-slate">{dateFormat.format(new Date(customer.created_at))}</td>
                      <td className="px-5 py-3" onClick={(event) => event.stopPropagation()}>
                        <RowActions customer={customer} onEdit={() => setEditing({ customer })} onRemove={() => setRemoving(customer)} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <ul className="divide-y divide-mist/60 md:hidden">
                {data.items.map((customer) => (
                  <li key={customer.id} className="flex items-start gap-3 px-4 py-3.5">
                    <div className="min-w-0 flex-1">
                      <button type="button" onClick={() => open(customer.id)} className="block max-w-full truncate text-left text-[14px] font-semibold">
                        {customer.name}
                      </button>
                      <p className="mt-0.5 truncate text-[13px] text-slate">{[customer.email, customer.phone].filter(Boolean).join(" · ") || "İletişim bilgisi yok"}</p>
                    </div>
                    <RowActions customer={customer} onEdit={() => setEditing({ customer })} onRemove={() => setRemoving(customer)} />
                  </li>
                ))}
              </ul>

              <Pagination page={data.page} pageSize={data.page_size} total={data.total} noun="müşteri" onPage={setPage} />
            </>
          )}
        </section>
      )}

      {editing ? (
        <CustomerEditor
          key={editing.customer?.id ?? "new"}
          customer={editing.customer}
          onOpenExisting={(id) => {
            setEditing(null);
            open(id);
          }}
          onClose={() => setEditing(null)}
          onSaved={(customer, created) => {
            setEditing(null);
            setNotice(created ? `${customer.name} eklendi.` : `${customer.name} güncellendi.`);
            if (created) {
              setInput("");
              setSearch("");
              setSort("-created_at");
              setPage(1);
            }
            refresh();
          }}
        />
      ) : null}

      {selected && !editing ? (
        <CustomerDetail
          key={selected}
          customerId={selected}
          onClose={() => open(null)}
          onEdit={(customer) => setEditing({ customer })}
        />
      ) : null}

      {importing ? (
        <ImportSheet
          onClose={() => setImporting(false)}
          onImported={(created) => {
            setNotice(created > 0 ? `${created} müşteri aktarıldı.` : "Yeni müşteri eklenmedi.");
            refresh();
          }}
        />
      ) : null}

      {removing ? (
        <ConfirmDialog
          title="Müşteri silinsin mi?"
          confirmLabel="Müşteriyi sil"
          pendingLabel="Siliniyor"
          onClose={() => setRemoving(null)}
          onConfirm={async () => {
            await deleteCustomer(removing.id);
            setNotice(`${removing.name} silindi.`);
            setRemoving(null);
            refresh();
          }}
        >
          <span className="font-medium text-graphite">{removing.name}</span> listeden kaldırılır ve aramalarda görünmez. Denetim kaydı korunur.
        </ConfirmDialog>
      ) : null}
    </div>
  );
}

function RowActions({ customer, onEdit, onRemove }: { customer: Customer; onEdit: () => void; onRemove: () => void }) {
  const button = "grid h-8 w-8 place-items-center rounded-lg text-slate transition-colors hover:bg-cloud hover:text-graphite";
  return (
    <div className="flex justify-end gap-1">
      <button type="button" onClick={onEdit} aria-label={`${customer.name} düzenle`} className={button}>
        <Icon name="pencil" className="h-4 w-4" />
      </button>
      <button type="button" onClick={onRemove} aria-label={`${customer.name} sil`} className={`${button} hover:bg-error/[0.06] hover:text-error-text`}>
        <Icon name="trash" className="h-4 w-4" />
      </button>
    </div>
  );
}
