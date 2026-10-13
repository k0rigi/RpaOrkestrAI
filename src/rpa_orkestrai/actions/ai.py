"""Yapay zekâ adımı: çalıştırma yetkisi Studio'nun ajan hizmetinden gelir."""

from ..errors import WorkflowError
from . import handler


@handler("ai.ask")
def ask(ctx, parameters):
    from ..engine import UNKNOWN, variable_name

    output = variable_name(parameters.get("output"))
    if output in {"sistem", "sifre", "loop_index"}:
        raise WorkflowError("Yapay zekâ sonucu ayrılmış bir sistem değişkenine yazılamaz.")
    if ctx.run.dry_run:
        return UNKNOWN
    if ctx.ai_service is None:
        raise WorkflowError("Yapay zekâ hizmeti hazır değil; ajan lisansını ve sağlayıcı bağlantısını kontrol edin.")
    return ctx.ai_service.complete(ctx, parameters)
