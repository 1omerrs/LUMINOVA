import { createCustomer } from "./customers.ts";
import { createProduct, unitShort, type Unit } from "./inventory.ts";

const ASCII: Record<string, string> = { ç: "C", ğ: "G", ı: "I", i: "I", ö: "O", ş: "S", ü: "U" };

export function suggestSku(name: string): string {
  const base = name
    .toLocaleLowerCase("tr")
    .split("")
    .map((char) => ASCII[char] ?? char.toUpperCase())
    .join("")
    .replace(/[^A-Z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 18);
  const tail = Math.random().toString(36).slice(2, 6).toUpperCase();
  return `${base || "URUN"}-${tail}`;
}

export const quickCustomer = {
  label: (term: string) => `“${term}” adıyla yeni müşteri ekle`,
  run: async (term: string) => {
    const customer = await createCustomer({ name: term, email: "", phone: "", note: "" });
    return { id: customer.id, label: customer.name, meta: "Yeni müşteri · bilgilerini sonra tamamlayabilirsiniz" };
  },
};

export function quickProduct(unit: Unit = "adet") {
  return {
    label: (term: string) => `“${term}” adıyla stok ürünü ekle (${unitShort(unit)})`,
    run: async (term: string) => {
      const product = await createProduct({ sku: suggestSku(term), name: term, unit, min_stock: "0", description: "" });
      return { id: product.id, label: product.name, meta: `${product.sku} · stok 0`, unit: product.unit };
    },
  };
}
