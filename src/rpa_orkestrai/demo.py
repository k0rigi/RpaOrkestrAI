from .models import Step, Workflow


def demo_workflow() -> Workflow:
    return Workflow(
        name="Sipariş kontrolü ve departman raporu",
        department="Finans",
        description="Örnek siparişleri inceler, 1.000 TL ve üzeri kayıtları ayırır ve Finans için CSV üretir. "
                    "Harici bağlantı gerektirmez; kendi akışınız için düzenleyebilirsiniz.",
        steps=[
            Step(action="data.sample", title="Siparişleri hazırla", params={"output": "orders"}),
            Step(action="core.set", title="Rapor listesini oluştur", params={"name": "approved", "value": []}),
            Step(action="control.for_each", title="Her siparişi incele",
                 params={"items": "${orders}", "item_name": "item"}, children=[
                     Step(action="control.if", title="Tutar 1.000 TL ve üzeri mi?",
                          params={"left": "${item.amount}", "operator": "gte", "right": 1000}, children=[
                              Step(action="data.append", title="Finans raporuna ekle",
                                   params={"name": "approved", "value": "${item}"}),
                          ], otherwise=[
                              Step(action="core.log", title="Küçük siparişi atla",
                                   params={"message": "Alt limitteki sipariş rapor dışında bırakıldı."}),
                          ]),
                 ]),
            Step(action="data.export_csv", title="Finans raporunu oluştur",
                 params={"rows": "${approved}", "filename": "finans-siparis-raporu.csv"}),
        ],
    )
