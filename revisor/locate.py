"""Localiza evidências literais; nunca estima coordenadas de um problema."""
import re


def locate_finding(page, finding):
    evidence = finding.evidence.removeprefix("Sugestão de IA não confirmada: ").strip()
    candidates = [getattr(finding, "excerpt", "").strip(), evidence]
    for text in candidates:
        if 6 <= len(text) <= 1500:
            quads = page.search_for(text, quads=True)
            if quads:
                return quads, "trecho literal"
    # Somente citações explícitas, sem procurar números soltos ou inventar recortes.
    quotes = re.findall(r'["“]([^"”\n]{6,300})["”]', evidence)
    quads, seen = [], set()
    for text in quotes:
        for quad in page.search_for(text, quads=True):
            key = tuple(quad.rect)
            if key not in seen:
                seen.add(key)
                quads.append(quad)
    return quads, "citação literal" if quads else "não localizado"
