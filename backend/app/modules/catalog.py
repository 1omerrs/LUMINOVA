from dataclasses import dataclass


@dataclass(frozen=True)
class ModuleDefinition:
    key: str
    name: str
    summary: str
    requires: tuple[str, ...] = ()


CATALOG: tuple[ModuleDefinition, ...] = (
    ModuleDefinition("sales", "Satış ve Siparişler", "Siparişlerinizi ve satış süreçlerinizi takip edin.", ("customers", "inventory")),
    ModuleDefinition("inventory", "Stok ve Depo", "Stok seviyelerini ve ürün hareketlerini yönetin."),
    ModuleDefinition("production", "Üretim", "Üretim süreçlerini, iş emirlerini ve malzeme kullanımını takip edin.", ("inventory",)),
    ModuleDefinition("customers", "Müşteri ve Teklifler", "Müşterilerinizi, iletişim bilgilerini ve tekliflerinizi yönetin."),
    ModuleDefinition("finance", "Finansal Takip", "Gelir, gider, alacak ve borçlarınızı izleyin."),
    ModuleDefinition("tasks", "Görev ve İş Yönetimi", "Yapılacak işleri, sorumluları ve görev durumlarını takip edin."),
    ModuleDefinition("projects", "Proje Yönetimi", "Projelerinizi, aşamalarını ve ilerlemelerini yönetin.", ("tasks",)),
    ModuleDefinition("reporting", "Raporlama ve Analiz", "İşletmenizin temel göstergelerini ve performansını inceleyin."),
    ModuleDefinition("automation", "Otomasyonlar", "İş akışlarını ve bildirimleri otomatikleştirin."),
)

MODULES: dict[str, ModuleDefinition] = {module.key: module for module in CATALOG}


def with_requirements(keys: set[str]) -> set[str]:
    selected = set(keys)
    pending = list(keys)
    while pending:
        for required in MODULES[pending.pop()].requires:
            if required not in selected:
                selected.add(required)
                pending.append(required)
    return selected
