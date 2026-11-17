# Aceite do piloto documental

O piloto cobre hidrogênio, ar comprimido respirável e ar ambiente. É uma base para
ampliar o programa com dados completos; não é validação de produção ou certificação.

## Fluxo implementado

1. Abrir PDF e selecionar arquivos de evidência opcionais.
2. Extrair texto local, registrar hash e executar regras versionadas.
3. Exibir achados com regra, severidade, página, evidência e conferência esperada.
4. Conferir a página original, associar evidências e registrar decisões justificadas.
5. Salvar/reabrir revisões e exportar parecer PDF/JSON com trilha de decisões.
6. Manter a consulta ChatGPT opcional, com consentimento separado para o envio.

## Critérios de aceite e verificações

- Comparadores inclusivos aceitam igualdade; comparadores estritos não aceitam.
- Valor de pureza no limite gera alerta; valor fora do critério gera bloqueante.
- Unidade suspeita de oxigênio gera bloqueio para conferência; não é corrigida sozinha.
- Anexo citado sem arquivo de evidência selecionado gera pendência bloqueante.
  Selecionar um arquivo reduz a certeza de ausência, mas não resolve a pendência:
  é necessária associação e conferência humana do laudo e dos certificados.
- Resultado explicitamente informativo não vira aprovação nem reprovação numérica.
- Contradições entre objeto, seção e procedimento são localizadas por página.
- Edição/ano da Farmacopeia são confrontados com metadados públicos consultados;
  as regras não alegam leitura integral da norma nem atualização contínua pela internet.
- Campos de aprovação sem texto são sinalizados, com aviso sobre assinaturas gráficas.
- Data declarada de calibração anterior ao mês da coleta é sinalizada. O certificado
  original ainda precisa de conferência; a tabela do relatório não o substitui.
- Não há caminho de valores de imagens/IA para decisões numéricas automáticas.
- Decisões exigem revisor e justificativa; cada alteração fica na trilha local.
- Exportação não sobrescreve originais e recusa arquivos alterados desde a revisão.
- PDF sem texto ou tabela não interpretada gera aviso, sem inferir valores.

## Resultado da rodada local com os três exemplos

Os 14 pontos do gabarito preliminar foram encontrados por regra e página.
O motor retornou 19 achados no total; os cinco adicionais são avisos que ainda
precisam ser avaliados pela Qualidade. Isso não mede sensibilidade/especificidade
em dados novos. Os relatórios reais e os pareceres derivados ficam fora do Git.

Os testes públicos usam documentos sintéticos e cobrem comportamento positivo e
negativo, persistência, integridade, confirmação de envio e exportação.

## Pendências antes de produção

- Validação interativa do login ChatGPT e da inferência com conta elegível.
- Revisão/aprovação do gabarito pela Qualidade, incluindo severidades e falsos positivos.
- Laudos, certificados, contratos e valores de referência completos para cruzamentos.
- Parsers de outras famílias e tabelas normativas completas revisadas.
- OCR/valores de imagens com confirmação por campo e medição de taxa de erro.
- Testes do pacote Windows em outra máquina, política de backup e assinatura do executável.

O programa auxilia a revisão; nenhum botão emite aprovação técnica ou declara
o sistema seguro para uso.
