"""Contexto reproduzível de revisão, sem consultar dados de outros clientes."""
from .profiles import applicable, load_skill
from .review import normalized


def infer_family(packet):
    principal = next(d for d in packet["documents"] if d["kind"] == "pdf")
    header = normalized(next(p["text"] for p in packet["pages"] if p["document"] == principal["id"]))
    return ("ar_comprimido_respiravel" if "ar comprimido respiravel" in header else
            "hidrogenio" if "hidrogenio" in header else "ar_ambiente" if "ar ambiente" in header else "desconhecida")


def prepare_context(packet, scope, profile, examples=None):
    family = scope["family"] if scope["family"] != "automatico" else infer_family(packet)
    scope = dict(scope, family=family)
    applicable(profile, scope["client_id"], scope["contract"], family, scope["reference_date"])
    packet["scope"] = scope
    packet["criteria_profile"] = profile
    packet["skill"] = load_skill(family)
    packet["examples"] = []
    if examples is not None and scope["client_id"]:
        query = "\n".join(p["text"] for p in packet["pages"])[:60000]
        selected = examples.examples(family, client_id=scope["client_id"], contract=scope["contract"], query=query)
        # Mantém os exemplos inteiros ou os exclui; nunca corta silenciosamente a evidência.
        import json
        for item in selected:
            if len(json.dumps(packet["examples"] + [item], ensure_ascii=False)) <= 12000:
                packet["examples"].append(item)
    return packet


def snapshot(packet):
    from .version import APP_VERSION
    skill = packet.get("skill", {})
    return {"scope": packet.get("scope", {}), "criteria_profile": packet.get("criteria_profile"),
            "app_version": APP_VERSION,
            "provider": "OpenAI", "configuration": {"store": False, "stream": True, "max_images_per_batch": 4},
            "ai_execution": packet.get("ai_execution", {}),
            "skill": {k: v for k, v in skill.items() if k != "instructions"},
            "examples": packet.get("examples", []),
            "pages": [{k: p[k] for k in ("document", "sha256", "page")} for p in packet["pages"]]}
