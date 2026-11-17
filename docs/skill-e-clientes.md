# Skill, critérios e histórico por cliente

A partir da versão 0.5, a revisão por IA recebe a skill incorporada ao programa, a orientação da família, o perfil selecionado e exemplos confirmados do mesmo cliente e contrato. Login, fornecedor e transporte da IA são os existentes. Alteramos o contexto enviado, sem instalar outra IA.

## Operação

1. Abra **Critérios e análise crítica**. Cadastre identificador estável do cliente, nome, contrato/escopo, família, versão e vigência. Registre a análise crítica e os critérios estruturados; é possível importar/exportar JSON.
2. Salve como rascunho para continuar depois. Para aprovar, informe o responsável e marque a confirmação. Aprovar rascunho ou alterar conteúdo exige uma nova versão; o perfil anterior permanece preservado.
3. Selecione o perfil na tela principal. Cliente, contrato e família são preenchidos; confirme a **Data dos critérios** segundo a data pertinente ao ensaio/contrato. Não é inferida do relatório.
4. Ative a IA e, opcionalmente, os exemplos confirmados. O consentimento informa o perfil e a quantidade de exemplos. Texto, imagens, critérios, análise crítica e exemplos selecionados serão enviados ao fornecedor da IA.
5. Confira apontamentos e registre decisões justificadas. **Contribuir para a base local** inclui somente decisões confirmadas. **Histórico do cliente** mostra revisões e recorrências do cliente/contrato informados.
6. Selecione a revisão anterior do mesmo relatório, cliente e contrato para comparar. A ausência de redetecção não comprova correção. Após conferir a página atual, use **Confirmar correção no ponto selecionado**, com revisor e justificativa. A página exibida fica registrada como evidência.

Sem perfil, a revisão documental continua disponível e declara que critérios contratuais não foram verificados. Sem IA, o perfil é guardado para rastreabilidade, mas critérios personalizados não são executados pelo motor local; continuam valendo as regras limitadas do piloto.

## Estrutura dos critérios

Cada item tem `id`, `parameter`, `requirement`, `source`, `section` e `applicability`. A fonte identifica contrato/norma, edição e seção; o programa não verifica automaticamente autenticidade ou aplicabilidade da fonte cadastrada. Requisitos numéricos acrescentam `operator`, `limit` (decimal com ponto) e `unit`. Operadores: `>`, `>=`, `<`, `<=`, `=`, `informativo`. Critérios documentais podem omitir operador e limite.

Exemplo apenas sintético, sem estabelecer limite técnico:

```json
{
  "client_id": "cliente-teste",
  "client_name": "Cliente sintético",
  "contract": "escopo-teste",
  "family": "hidrogenio",
  "version": "1",
  "status": "rascunho",
  "approved_by": "",
  "valid_from": "2026-01-01",
  "valid_until": "",
  "critical_analysis": "Conferir vínculo entre relatório e laudo.",
  "criteria": [{
    "id": "DOC-01",
    "parameter": "Identificação do ensaio",
    "requirement": "O identificador do laudo deve corresponder ao citado no relatório.",
    "source": "Contrato sintético v1",
    "section": "2",
    "applicability": "Conjunto de teste com laudo externo"
  }]
}
```

## Arquivos mantidos pela equipe

- Procedimento: [SKILL.md](../revisor/skills/revisar-relatorios/SKILL.md).
- Cuidados por família: pasta `references` da skill. Carrega-se somente a família aplicável.
- Perfis reais: `criterios.sqlite3` na biblioteca do usuário, fora do repositório.
- Exemplos: `exemplos.sqlite3`; a migração é compatível com a tabela existente. Registros antigos sem cliente permanecem locais e não são enviados como exemplos de um cliente identificado.
- Revisões: JSON existentes, com novos campos opcionais. O `review_context` registra cliente, perfil completo, versão/hash da skill, exemplos selecionados, páginas, configuração e lotes de IA tentados/concluídos. Os logs não contêm credenciais nem imagens em base64.

Alterações de skill devem incrementar sua versão e passar pelos testes. O hash diferencia também a referência da família carregada. Uma versão do executável não sobrescreve os perfis de cliente. Importações de perfis não ficam aprovadas automaticamente na interface.

## Aproveitamento dos três exemplos

Hidrogênio, ar respirável e ar ambiente orientam os cuidados das referências e os testes sintéticos. O gabarito real com catorze pontos continua preliminar até aprovação da Qualidade; os cinco avisos adicionais também exigem avaliação. Documentos originais e resultados derivados não entram no GitHub e não são promovidos automaticamente a critérios.

Antes de produção, a Qualidade deve confirmar o gabarito e os perfis. Comparar a IA anterior e a skill com os mesmos documentos e modelo, usando também relatórios não usados para ajuste. Medir erros relevantes omitidos, falsos positivos, cobertura, custo e duração. Testes automatizados com IA simulada verificam o fluxo e o isolamento, não comprovam ganho de precisão de um modelo real.

Limitações atuais: busca de exemplos por palavras relevantes, cliente, contrato e família, com limite de contexto; sem banco vetorial nem treinamento. A recorrência contabiliza decisões `corrigir` por rodada, podendo repetir o mesmo problema em versões do relatório. Cruzamentos entre lotes e a abrangência técnica permanecem sujeitos à conferência humana.
