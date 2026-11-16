# Revisor de Relatórios de Qualificação — Design

> Celacanto Análises Ambientais · uso interno · Rascunho para aprovação · 2026-11-16
> Base: 22 relatórios de exemplo (HVAC, fluxo unidirecional, CSB, capela, salas limpas, gases, ar climatizado), um anexo
> escaneado com fitas do contador + 13 fotos HEIC, planilha ADR (critérios internos) e logos Celacanto.
> Os relatórios de exemplo são confidenciais e ficam fora deste repositório; aqui aparecem com códigos anonimizados
> (REL-H1, REL-F1…) e sem nome de cliente.

---

## 1. Intenção

Antes de emitir um relatório de qualificação, a Celacanto precisa conferir que **cada número declarado bate com a
evidência, com a conta e com o critério**. Hoje isso é feito a olho. Nos exemplos, a revisão manual deixou passar
erros de vários tipos:

- um instrumento usado e não declarado (contador "B" no teste de partículas do REL-H1);
- critérios contraditórios no mesmo documento (recuperação ≤ 15 min no protocolo e ≤ 20 min no anexo, REL-H2);
- unidade errada (O₂ em "ppm" no ar respirável);
- texto copiado de outro modelo (procedimento de "gás" num relatório de sala limpa);
- transcrição divergente da fita (gerada 6.694.026 na fita, 6.694.025 no relatório).

O app é um **revisor desktop** que lê o relatório (PDF) e as evidências (fotos e escaneados de fitas e folhas de
campo), extrai os valores, refaz as contas e devolve uma **lista de achados** para a pessoa que revisa.
**A decisão de emitir continua humana.**

## 2. Quem usa e como

- **Revisor(a) da Qualidade** (ex.: analista da Qualidade): abre um relatório, anexa as fotos/escaneados, roda a
  revisão, confirma os valores lidos das imagens, analisa os achados e exporta o parecer.
- **Elaborador(a)** recebe o parecer e corrige o Word de origem. O app **não edita** o relatório.

Fluxo:

```
[Abrir relatório PDF] → [Anexar evidências: fotos/HEIC/escaneado]
   → Extração (texto local; IA só nas imagens, se ligada)
   → Confirmação humana dos valores vindos de imagem
   → Motor de regras → Lista de achados (bloqueante / alerta / informativo)
   → Revisor(a) marca cada achado: aceito / corrigir / falso positivo + comentário
   → Exporta parecer de revisão (PDF Celacanto + JSON)
```

## 3. Objetivos, não objetivos e anti-objetivos

**Objetivos**
1. Ler relatórios CCR em PDF com texto e montar um modelo estruturado: testes, instrumentos, pontos, valores, critérios e resultados.
2. Ler evidências em imagem (JPG, PNG, HEIC, PDF escaneado), incluindo fitas térmicas de contador de partículas e tabelas preenchidas à mão.
3. Refazer todas as contas que o relatório declara e cruzar relatório × evidência × critério × norma.
4. Apresentar cada achado com a origem: página e recorte da imagem, valor lido, valor esperado e regra aplicada.
5. Exportar um parecer de revisão com a identidade visual da Celacanto.

**Não objetivos (fase 1)**
- Editar ou gerar o relatório (isso é do Word / da ADR).
- Ler .doc/.docx diretamente: o relatório entra como PDF exportado. Ler .docx fica como fase 2 (ver §14).
- Calcular incerteza de medição.
- Laudos de laboratório de terceiros (microbiologia, cromatografia): só se confere a transcrição, quando o laudo vier anexo.
- Integração com outros sistemas (Trello, ADR, app de campo).

**Anti-objetivos (seria falha mesmo funcionando)**
- Declarar "Conforme" ou "Reprovado" no lugar da pessoa: o app aponta, não decide.
- Usar um valor lido de imagem (OCR ou IA) numa conta sem confirmação humana.
- Tratar critério de norma como bloqueante quando o relatório traz outro critério: **o critério do relatório é mandatório; a norma só gera alerta**.
- Recalcular e "corrigir" um resultado consolidado pelo instrumento (média da fita, UCL), em vez de só conferir a transcrição.
- Enviar relatório de cliente para fora da máquina sem a pessoa saber e consentir.
- Esconder um achado por ser "pequeno": diferença de 1 partícula também aparece, classificada.

## 4. Restrições

- **Confidencialidade:** os relatórios trazem a cláusula "caráter confidencial… pertence à [cliente]". Qualquer envio a serviço externo precisa ser opcional, explícito e registrado.
- **Windows** (máquinas da Qualidade); funciona offline, exceto a etapa opcional de IA.
- **Integridade (ISO/IEC 17025):** o arquivo original nunca é alterado. Cada arquivo de entrada recebe um hash SHA-256 registrado no parecer, e o parecer registra a versão das regras usadas.
- **HEIC:** fotos de iPhone são a evidência mais legível. O Windows não decodifica HEIC sem codec, então o app embarca o próprio leitor (pillow-heif).

## 5. Abordagens consideradas

| | Extração | A favor | Contra |
|---|---|---|---|
| A | Tudo local (texto do PDF + OCR local) | Nenhum dado sai; sem custo | OCR local erra em fita térmica desbotada e caneta → muita digitação |
| B | IA de visão para tudo | Lê fita, foto torta e escrita à mão | Todo relatório sai da máquina; custo por página; exige internet |
| **C** | **Híbrido: PDF com texto lido localmente; IA de visão só em imagens/escaneados, acionada pela pessoa** | O grosso fica local; a IA só onde faz diferença; valor da IA sempre confirmado | Dois caminhos de extração para manter |

**Escolhida pelo usuário (2026-11-16): C.**

**Plataforma (decisão minha, a confirmar):** Python 3.12 + **PySide6 (Qt)**, empacotado como executável único
(PyInstaller). PyMuPDF, pillow-heif e o SDK `anthropic` são Python, e não há ganho em pôr uma interface web por cima.
Electron + React reaproveitaria o stack do app de campo, mas exigiria um processo Python à parte.

## 6. Arquitetura

```
revisor/
  ingestao/      abre PDF/imagens, HEIC→RGB, corrige rotação (EXIF), hash SHA-256, renderiza páginas
  extracao/
    texto_pdf.py   PyMuPDF: blocos de texto com posição → tabelas
    parsers/       um parser por família de modelo CCR (equipamento, HVAC, gases, sala limpa, ar climatizado)
    visao_ia.py    (opcional) envia página/recorte ao Claude e recebe JSON validado por schema
    ocr_local.py   (opcional, fase 2) fallback sem internet
  modelo/        dataclasses do relatório canônico (§7)
  regras/        motor + catálogo de regras versionado (§8), tabelas normativas (§9)
  revisao/       achados, decisão humana, trilha
  saida/         parecer PDF (identidade Celacanto) + JSON
  ui/            telas Qt (§10)
dados/           SQLite local: revisões, achados, decisões, cadastro de instrumentos
```

### 6.1 Extração local (PDF com texto)

Os relatórios CCR seguem poucos modelos fixos: cabeçalho, tabela "DADOS DOS INSTRUMENTOS", tabela de pontos,
critério, "RESULTADO GERAL", "Executado por / Data". Cada família ganha um parser por âncoras de texto ("ANEXO n",
"TESTE n", "Critério de aceitação", "Valores Máximos Encontrados" / "Média Encontrada").

Quando o parser não reconhece um bloco, não adivinha: gera um achado **"trecho não interpretado"** com a página, e a
pessoa decide.

### 6.2 Extração por IA (imagens e escaneados), opcional

- **Desligada por padrão.** Liga por revisão, com aviso: "estas N páginas serão enviadas à Anthropic".
- Modelo `claude-opus-5-5` (padrão atual), saída estruturada via `client.messages.parse()` com schema Pydantic por tipo de evidência:
  - fita de contador (Rel. Amostra Final, Plano de Amostragem, Certificação Sala Limpa);
  - tabela de teste preenchida à mão;
  - cabeçalho do anexo (cliente, sala, estado marcado, data, REF CCR).
- Envia só as páginas/recortes de evidência, não o relatório inteiro.
- Fallback de recusa ligado (`fallbacks: "default"`) e erros tratados por tipo: limite de taxa, conexão, requisição inválida.
- Cada valor extraído guarda o recorte de onde veio e uma marca de confiança. **Nenhum valor de IA entra no motor de regras antes de a pessoa confirmar** (tela §10.3).
- A chave da API fica no cofre de credenciais do Windows, nunca no arquivo de revisão.

### 6.3 Associação evidência → teste

1. Cabeçalho do anexo: REF CCR, sala, estado marcado (repouso / operação / queda de energia / recuperação), data.
2. Conteúdo da fita: "ID do Lote" (sala), "Local" (#001… ou INICIAL / GERADA / RECUPERAÇÃO), horários.
3. Um dicionário de sinônimos de salas por relatório (ex.: "Esterilidade" = "Sala Teste de Esterilidade 1234" = "ESTERILIDA 1234"), montado na primeira revisão e confirmado pela pessoa.

Se a associação for ambígua, a evidência fica em "não associada" e a pessoa liga à mão.

## 7. Modelo canônico (resumo)

```
Revisao(id, arquivos[sha256], versao_regras, revisor, data, situacao)
Relatorio(numero CCR, cliente, objeto/TAG, tipo [equipamento|HVAC|gas|sala_limpa|ar_climatizado],
          revisao R0/V0, datas: execucao, elaboracao, revisao; elaborador, revisor, aprovador)
Instrumento(tag, descricao, serie, certificado, validade)          ← declarado no relatório
Teste(numero/anexo, nome, criterio_texto, criterio_parse, resultado_declarado, executado_por, data, pagina)
  Medicao(ponto/local, grandeza, valor, unidade, estado, origem[texto|ia|digitado], confirmado_por)
  ValorCalculado(nome: media|dpr|vazao|angulo|tempo_recuperacao..., declarado, recalculado)
Evidencia(arquivo, pagina, recorte, tipo[fita_contador|tabela_manual|foto], associado_a_teste)
  LeituraFita(instrumento_id, serie, calibrado_em, operador, sala, local, inicio, fim,
              linhas[{um, delta, sigma}], volume_m3, vazao, status)
Achado(regra_id, severidade, mensagem, esperado, encontrado, localizacao[], decisao, comentario)
```

## 8. Motor de regras

Cada regra tem um código, uma versão, uma severidade, a referência (relatório ou norma) e um teste automatizado.

**Severidades:**
- **Bloqueante:** viola o critério escrito no próprio relatório, é conta errada, ou o valor do relatório diverge da evidência.
- **Alerta:** diverge de norma ou de boa prática, é inconsistência editorial com impacto técnico, ou o valor está no limite.
- **Informativo:** erro de digitação, numeração ou formatação sem impacto técnico.

### 8.1 Catálogo inicial (cada regra nasceu de um caso real dos exemplos)

| Código | Regra | Severidade | Caso real |
|---|---|---|---|
| CRT-01 | Resultado declarado (Conforme/Cumpre) × critério do relatório × valor | Bloqueante | — (base) |
| CRT-02 | O mesmo critério aparece com valores diferentes no documento | Bloqueante | Recuperação ≤15 × ≤20 (REL-H2) |
| CRT-03 | Critério ilegível ou mal formado | Alerta | "0,36 ± 0,54 m/s" (REL-F2) |
| CRT-04 | Critério ausente para um analito medido | Alerta | Fungos sem critério (REL-G1) |
| CRT-05 | Critérios diferentes entre pontos do mesmo sistema sem justificativa | Alerta | REL-G2: <1 × ≤200 UFC/m³ |
| CRT-06 | Grau em operação incoerente com o grau em repouso | Alerta | REL-C1: A repouso / C operação |
| CAL-01 | Média, DPR, vazão (média × área × 3600), ângulo (atan X/L) e trocas (Q/V) recalculados com valores sem arredondar; tolerância de arredondamento configurável | Bloqueante se fora da tolerância | Capela 739 m³/h só bate sem arredondar |
| CAL-02 | Área declarada × dimensões × quantidade de filtros | Bloqueante | REL-F1: 1,67 m² = 3 filtros, mas tabelas listam 1 |
| CAL-03 | Tempo de recuperação recalculado pelos horários das fitas (fim da geração → 1ª leitura ≤ inicial; e 100:1, ISO 14644-3) | Alerta se divergir | Sala "PTS-A": 5 min 41 s × "5" |
| INS-01 | Instrumento que aparece na evidência (fita: ID/série) e não está declarado no teste | Bloqueante | Contador "B" na fita, só o "A" declarado (REL-H1) |
| INS-02 | Calibração vencida na data de execução; formato de certificado inconsistente para o mesmo instrumento | Bloqueante / Informativo | Cromatógrafo: "210726" × "21/07/2026" (REL-G1 × REL-G3) |
| INS-03 | Ensaio sem instrumento compatível declarado | Alerta | Viáveis sem amostrador (REL-G1) |
| EVD-01 | Valor da tabela do relatório × Σ da fita (não Δ) | Bloqueante | 6.694.026 × 6.694.025 |
| EVD-02 | Média do relatório × média dos locais da fita; tolerância para valor consolidado pelo instrumento | Alerta | 5,0 µm: 6,25 × 7 |
| EVD-03 | Relatório declara "fita em anexo", mas não há evidência para o teste/sala | Alerta | — |
| EVD-04 | Documento incompleto (páginas faltando pela numeração "x de N") | Bloqueante | Escaneado com 13 de 30 págs |
| PAR-01 | Volume mínimo por amostra: Vs ≥ 20 / Cn,m (ISO 14644-1:2015 A.4.4) | Alerta | Grau B 5,0 µm → 0,69 m³ ✓ |
| PAR-02 | Nº mínimo de locais pela área (ISO 14644-1:2015 Tab. A.1); área ausente → alerta | Alerta | Sala limpa sem áreas |
| PAR-03 | Relatório informa só a "média" dos locais; a norma exige cada local ≤ limite | Alerta | REL-H1 × REL-H2 |
| PAR-04 | Limites de grau/classe do relatório × tabela normativa selecionada | Alerta | Grau A 5,0 µm: 20 (IN 35) × Anexo 1/2022 |
| NRM-01 | Critério do relatório menos rígido que a norma de referência | Alerta | — |
| NRM-02 | Critério mais rígido que a norma (informar, é válido) | Informativo | Viáveis Grau D ≤100 × 200 |
| NRM-03 | Ensaio esperado pela norma ausente para o tipo de equipamento | Alerta | CSB sem inflow (NSF 49 / EN 12469) |
| NRM-04 | Referência normativa incorreta ou inexistente | Alerta | "ISO 14644-1:2019" para viáveis; RDC 658 "22/03" |
| LIM-01 | Resultado no limite exato do critério sem regra de decisão/incerteza | Alerta | REL-G3: pureza 99,999% ≥ 99,999% |
| UNI-01 | Unidade incompatível com a grandeza | Bloqueante | O₂ em ppm; luminosidade em dB |
| TXT-01 | Texto de outro modelo (termos de gás em relatório de sala; "interior da capela" em fluxo) | Alerta | REL-S1; REL-F1 |
| TXT-02 | Identidade do objeto incoerente (nome × tipo × critério) | Alerta | REL-F2: "Horizontal" × "vertical" |
| ED-01 | Datas inválidas ou fora de ordem (execução ≤ elaboração ≤ revisão; validade = execução + período) | Bloqueante / Informativo | "13/08/20226" |
| ED-02 | Numeração de testes/seções saltada ou inconsistente | Informativo | Testes 1–5, 7–9 |
| ED-03 | Campos de assinatura/aprovação vazios no momento da revisão | Informativo | "Aprovado por" vazio |
| PLA-01 | Dados repetidos de forma implausível (mesmos intervalos em todas as salas) | Alerta | Queda de energia REL-H2 |
| ESC-01 | Escopo contratado (orçamento, quando anexado) × ensaios executados | Alerta | ISO 8573-1 orçada × não medida |
| IE-01 | Coerência de valores derivados entre si (ex.: relação I/E × fungos interno/externo) | Bloqueante | NBR 17037 ✓ |

### 8.2 Tabelas normativas (versionadas e selecionáveis por revisão)

Cada relatório declara uma referência. O app guarda as tabelas com **edição e data** e a pessoa escolhe qual vale
para os alertas, se a detecção automática não bastar:

- **Partículas por grau:** IN 35/2019 + RDC 658/2022 (A 3.520/20; B 3.520/29 – 352.000/2.900; C 352.000/2.900 – 3.520.000/29.000; D 3.520.000/29.000) e EU GMP Anexo 1 (2022), que tem limites de 5,0 µm diferentes.
- **Classes ISO 14644-1:2015:** fórmula Cn = 10^N × (0,1/D)^2,08, Tab. A.1 (locais) e A.4.4 (volume).
- **Viáveis por grau:** IN 35 / Anexo 1.
- **Equipamentos:**
  - fluxo unidirecional 0,36–0,54 m/s, DPR ≤ 15%;
  - integridade ≤ 0,01%;
  - ΔP HEPA conforme relatório; a ADR interna usa ≤ 600 Pa e os relatórios ≤ 500 Pa, e isso fica como tabela "critério interno" separada;
  - paralelismo ≤ 14°;
  - CSB: NSF/ANSI 49 e EN 12469 (inflow, downflow);
  - capela: faixas declaradas.
- **Gases:**
  - ar comprimido: ISO 8573-1/-2/-6 e Ph. Eur.;
  - ar respirável: NBR 12543;
  - N₂/H₂: monografias citadas.
- **Ar climatizado:** NBR 17037:2023 (fungos ≤ 750, I/E ≤ 1,5, CO₂, T, UR, velocidade, PM10, PM2,5).
- **Ruído e iluminância:** NR-15 / NBR ISO 8995-1 como alerta; o critério do relatório prevalece.

As tabelas são dados (JSON/YAML) revisados pela Qualidade, e não código. Toda alteração gera nova versão, e o parecer
registra a versão usada.

## 9. Saída: parecer de revisão

- **PDF com a identidade Celacanto:**
  - capa com relatório, cliente, objeto, hashes dos arquivos, versão das regras, revisor(a) e data;
  - resumo por severidade;
  - tabela de achados com página e recorte;
  - decisões e comentários;
  - lista de evidências e associação de cada uma a seu teste.
- **JSON** com o mesmo conteúdo, para histórico e indicadores (achados mais frequentes por modelo e por elaborador).

## 10. Telas (rascunho)

### 10.1 Início
```
┌ CELACANTO · Revisor de Relatórios ───────────────────────────────┐
│ [+ Nova revisão]   Recentes: REL-H1  REL-S1  ...                   │
│ Arraste o PDF do relatório e as fotos/escaneados aqui            │
└──────────────────────────────────────────────────────────────────┘
```

### 10.2 Revisão (principal)
```
┌ REL-H1 · Cliente X · HVAC CQ ───────────────── IA: desligada [ligar] ┐
│ Testes            │ Documento / evidência        │ Achados (12)       │
│ ▸ T6 Partículas ⚠ │ [página 26 + fita lado a lado│ ● INS-01 Bloqueante│
│ ▸ T7 Recuperação ✓│  com destaque no valor]      │   Contador B na    │
│ ▸ Instrumentos  ⚠ │                              │   fita, não decl.  │
│ ▸ Evidências 13/13│                              │   [aceito][corrigir]│
│                   │                              │   [falso positivo] │
└───────────────────┴──────────────────────────────┴────────────────────┘
```

### 10.3 Confirmação de valores lidos de imagem
```
┌ Fita · PTS-A · Recuperação #GERADA ─────────────────────────────────┐
│ [recorte da fita]          0,5 µm Σ  [6.694.026]  ✓   confiança alta│
│                            5,0 µm Σ  [  192.765]  ✓                 │
│                            Início 13:17:34  Fim 13:18:34  ✓         │
│ [Confirmar tudo]  [Editar]   Próxima fita →                         │
└─────────────────────────────────────────────────────────────────────┘
```

## 11. Identidade visual (logos Celacanto)

| Papel | Cor |
|---|---|
| Texto, cabeçalho, barra superior | Azul-marinho `#123C6D` |
| Primária, botões, links | Azul `#00489C` → `#2484C0` (gradiente do símbolo) |
| Conforme / sucesso / destaque | Verde `#6C9C24` → `#78A824` |
| Secundário, bordas, texto auxiliar | Cinza `#8B8B8B` |
| Modo escuro | Fundo `#211F20` + logo negativo |
| Alerta *(proposta minha)* | Âmbar `#C98A12` |
| Bloqueante *(proposta minha)* | Vermelho `#B3261E` |

- Logo colorido sobre fundo claro; logo negativo no modo escuro; a versão cinza vai no rodapé do parecer.
- Tipografia geométrica sem serifa, próxima do logotipo (ex.: Montserrat ou similar embarcada), e uma tipografia neutra para tabelas.
- A severidade sempre vem com ícone e texto, nunca só pela cor (acessibilidade).

## 12. Dados e segurança

- Uma pasta por revisão com cópias somente-leitura dos arquivos de entrada e os hashes.
- SQLite local com achados, decisões, sinônimos de salas e cadastro de instrumentos (opcional, para conferir validade e série independentemente do relatório).
- Log de envios à IA: quando, quem, quais páginas e o modelo usado.

## 13. Como saber que funciona

- **Corpus de aceitação:** os 22 relatórios de exemplo (mantidos fora do Git; uma ficha cadastral e um orçamento entram só como "não é relatório" e como insumo de ESC-01), mais as evidências, viram casos de teste com **gabarito** dos achados já identificados nesta análise (§8.1, coluna "caso real"). Critério de pronto da fase 1: cada achado do gabarito é encontrado, e um falso positivo novo só é aceito se fizer sentido para a Qualidade.
- **Regras:** testes unitários com valores-limite (no limite, logo acima, unidade errada).
- **IA:** um conjunto de ~30 recortes de fita com valores transcritos à mão. Mede-se a taxa de acerto por campo antes de liberar a IA para uso. A confirmação humana continua obrigatória mesmo com acerto alto.

## 14. Fases

1. **Fase 1:** PDF com texto (todas as famílias) + motor de regras + parecer; evidência em imagem só com digitação manual assistida (o recorte ao lado do campo).
2. **Fase 2:** IA de visão para fitas e tabelas manuscritas, HEIC/rotação, associação automática evidência → teste.
3. **Fase 3 (opcional):** ler .docx direto (antes de exportar), OCR local de fallback, painel de indicadores.

## 15. Decisões tomadas por mim (para conferir)

- PySide6 + PyInstaller (§5).
- IA desligada por padrão e com consentimento por revisão, até a Celacanto confirmar a política de confidencialidade.
- Modelo de IA `claude-opus-5-5`, pelo custo/benefício atual. Trocar para um modelo mais barato é decisão da Celacanto, depois de medir com o corpus.
- Fase 1 sem IA (entrega valor sem depender da decisão de confidencialidade).
- Cores de alerta e bloqueante fora do logo.
- Divergência ADR × relatórios (ΔP 600/500 Pa, lux 480/500) tratada como tabela "critério interno" separada, só informativa.

## 16. Deixado para quem constrói

Estrutura interna dos parsers, layout fino das telas, formato dos arquivos de tabela normativa, estratégia de
empacotamento e atualização, e tolerâncias numéricas iniciais (ajustadas com o corpus).
