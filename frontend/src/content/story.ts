export type StoryScene = {
  id: string;
  index: string;
  title: string;
  body: string;
};

export const scenes: readonly StoryScene[] = [
  {
    id: "meet",
    index: "01",
    title: "İşletmenizin tüm gücü, tek bir merkezde.",
    body: "Satıştan stoğa, projelerden iş süreçlerine kadar işletmenizi tek bir platformda yönetin.",
  },
  {
    id: "modules",
    index: "02",
    title: "İhtiyacınız olan her şey. Kendi düzeninizde.",
    body: "İşletmenizin ihtiyaç duyduğu modülleri seçin. İş süreçlerinizi tek bir platformda bir araya getirin.",
  },
  {
    id: "center",
    index: "03",
    title: "Tüm iş süreçleriniz. Tek bir bakışta.",
    body: "Dağınık verileri bir araya getirin, işlerinizi takip edin ve işletmenizde neler olup bittiğini daha net görün.",
  },
  {
    id: "action",
    index: "04",
    title: "Verilerinizi anlayın. Doğru adımları daha kolay belirleyin.",
    body: "Raporlarınızı takip edin, önemli değişiklikleri fark edin ve işletmenizin ihtiyaçlarına göre aksiyon alın.",
  },
  {
    id: "close",
    index: "05",
    title: "İşletmenizi kendi kurallarınızla yönetin.",
    body: "LUMINOVA ile iş süreçlerinizi tek bir merkezde toplayın ve ihtiyaçlarınıza uygun bir çalışma alanı oluşturun.",
  },
];

export const storyModules = ["Satış", "Stok", "Finans", "Müşteri", "Projeler", "Raporlama", "Üretim", "Otomasyon"] as const;

export const sceneBreaks = [0.15, 0.4, 0.62, 0.84] as const;

export function sceneIndex(value: number): 0 | 1 | 2 | 3 | 4 {
  const index = sceneBreaks.findIndex((edge) => value < edge);
  return (index === -1 ? 4 : index) as 0 | 1 | 2 | 3 | 4;
}
