# Fluxo unificado e identidade Celacanto

Incremento 0.3 do piloto: uma entrada de documentos, leitura no centro e apontamentos à direita.
A paleta clara mantém verde nos destaques e azul da marca. O material Glass Green fornecido
foi usado como referência visual, sem executar seus scripts. O logotipo original fornecido
pelo usuário é exibido no aplicativo e empacotado como recurso local.

## Comportamentos verificáveis

- Documentos e anexos entram pelo mesmo botão ou por arrastar arquivos. A ordem de seleção é preservada.
- A conexão da IA e os erros de login/permissão são visíveis. Os modelos são carregados após o login.
- A IA recebe texto e imagem de todas as páginas, em lotes de até quatro imagens. Há confirmação por rodada.
- As regras locais rodam depois da IA. Falha de IA não é apresentada como análise concluída.
- Cada apontamento tem origem e vínculo com arquivo/página. Coordenadas de destaque não são inventadas.
- A cópia PDF comentada preserva os originais, reúne o conjunto e inclui a lista de apontamentos.
- O revisor pode acompanhar pontos pertinentes e confrontá-los com outra versão do mesmo relatório.
- A comparação usa regra e título, não comprova correção ou eficácia e pode precisar de correspondência manual para sugestões da IA.
- Contribuições para a base local exigem decisão, revisor e justificativa; pendências não viram exemplos confirmados.
- A base local fornece contexto opcional à IA, sujeito à confirmação de envio, e não ajusta pesos do modelo.

## Validação

Testes sintéticos cobrem consentimento, cancelamento, ausência de permissão de IA,
primeira leitura antes das regras locais, anexos posteriores, navegação de achados,
preservação de originais, comparações e contribuição de exemplos. A revisão dos
três relatórios de referência continua sendo confrontada com o gabarito preliminar.

O teste de login e consulta com a conta real do titular permanece pendente.
