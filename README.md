# Analisador de Relatórios de Qualificação

Aplicativo desktop (Windows) de uso interno da **Celacanto Análises Ambientais** para conferir relatórios de
qualificação antes da emissão: HVAC, fluxo unidirecional, cabines de segurança biológica, capelas, salas limpas e
gases.

O objetivo do projeto é ler o relatório (PDF) e as evidências, refazer as contas e cruzar
**relatório × evidência × critério × norma**. Nesta primeira implementação, o aplicativo oferece
consulta assistida por IA com referências selecionadas. **A decisão de emitir continua humana.**

## Situação

Piloto executável: revisão documental local, histórico, decisões justificadas,
parecer PDF/JSON, login ChatGPT opcional e biblioteca de referências.
O motor atual cobre verificações selecionadas de hidrogênio, ar comprimido respirável e ar ambiente.
Na versão 0.5, a IA recebe uma skill versionada, perfis de critérios por cliente/contrato e exemplos confirmados do mesmo escopo.
Consulte [cadastro, histórico e limites da skill](docs/skill-e-clientes.md).
Outras famílias, validação normativa integral e liberação para produção permanecem pendentes.

### Executar no Windows

Instale Python 3.12 e execute `Iniciar.ps1` no PowerShell. Ou:

```powershell
py -3.12 -m venv "$env:LOCALAPPDATA\Celacanto\ar-venv"
& "$env:LOCALAPPDATA\Celacanto\ar-venv\Scripts\python.exe" -m pip install -r requirements.txt
& "$env:LOCALAPPDATA\Celacanto\ar-venv\Scripts\python.exe" -m revisor
```

### Fluxo único de revisão

1. Use **Adicionar documentos** para receber o relatório completo e os anexos no mesmo conjunto. O primeiro PDF é o principal; as opções do conjunto permitem alterá-lo.
2. Clique em **Conectar ChatGPT** se quiser IA. Após o login, os modelos são verificados automaticamente e a tela informa se a IA está pronta ou qual etapa falhou.
3. Clique em **Iniciar revisão**. Com IA ligada, confirme o envio do conjunto: todas as páginas entram como texto e imagem, em lotes. Em seguida são executadas as regras locais. Sem IA, a revisão local funciona normalmente.
4. Clique num apontamento para abrir o arquivo e a página correspondentes. Marque os pontos pertinentes, informe revisor e decisão quando quiser confirmar ou descartar, e registre a justificativa.
5. Adicione documentos faltantes pelo mesmo botão e execute uma nova rodada. O histórico anterior permanece preservado.
6. Selecione uma revisão anterior e use **Comparar com a revisão selecionada**. Pontos não redetectados exigem confirmação humana; o sistema não declara a correção como comprovada.
7. **PDF comentado** exporta cópia do conjunto, com destaques amarelos nos trechos localizáveis, comentários e lista de apontamentos ao final. **Dados para melhoria** exporta JSON com a revisão e os exemplos confirmados.
8. **Contribuir para a base local** cadastra somente exemplos confirmados ou descartados com revisor e justificativa. O uso desses exemplos na IA depende de seleção explícita e confirmação de envio. Não há treinamento automático do ChatGPT.

O parecer não autoriza emissão ou uso do sistema. Nenhum valor de imagem/IA é usado nas contas.
Consulte [critérios de aceite e limites do piloto](docs/aceite-piloto.md).

### Uso da IA e limites

A IA faz uma primeira leitura; as regras locais conferem em seguida. A origem de cada apontamento aparece na lista.
Sugestões da IA permanecem não confirmadas e não autorizam cálculos a partir de imagens nem aprovação do relatório.
Falha da IA fica visível; os resultados locais continuam disponíveis. Nenhuma página é omitida silenciosamente.
As comparações entre lotes e versões exigem validação humana, assim como referências normativas não fornecidas.

Os dados ficam em `%LOCALAPPDATA%\Celacanto\AnalisadorRelatorios`.
Use `python -m revisor --data-dir CAMINHO` para outra biblioteca.
Importação local não treina o ChatGPT. Consulte [detalhes e limitações](docs/integracao-chatgpt.md).

Testes: `python -m unittest discover -s tests -v`.
Verificação de abertura: `python -m revisor --smoke --data-dir CAMINHO_TEMPORARIO`.

Revisão por linha de comando: `python -m revisor.cli RELATORIO.pdf --output PASTA_PARECER`.
Adicione `--evidence LAUDO.pdf` por arquivo de evidência disponível.

### Pacote Windows

A partir da versão 0.4, use **Atualizações** no próprio programa para consultar
novas releases no GitHub e baixar o pacote. A aplicação fecha, troca os arquivos
do programa e reabre, preservando banco, revisões e credenciais fora da instalação.
As versões anteriores precisam de um download manual para receber o atualizador.
Consulte [publicação, integridade e recuperação](docs/atualizacoes.md).

Execute `Empacotar.ps1` para gerar uma pasta distribuível, sem exigir Python na máquina de destino.
O executável fica em `dist/RevisorCelacanto/RevisorCelacanto.exe`; distribua a pasta inteira.
O pacote ainda requer testes em outra máquina e não possui assinatura digital.

- Design: [docs/superpowers/specs/2026-11-16-revisor-relatorios-design.md](docs/superpowers/specs/2026-11-16-revisor-relatorios-design.md)

## Princípios

- Divergências entre critérios do relatório e perfil aprovado são apresentadas ao revisor, com suas fontes, sem escolha silenciosa.
- Nenhum valor lido de imagem entra nas contas sem confirmação humana.
- Os arquivos originais nunca são alterados: cada um tem hash SHA-256 registrado no catálogo local e no registro de envio.
- A IA de visão (ChatGPT nesta implementação) é opcional; o conjunto de páginas é enviado apenas após confirmação explícita, incluindo perfil e exemplos selecionados.

## Stack

Python 3.12 · PySide6 (Qt) · PyMuPDF · pillow-heif · SDK `openai` · PyJWT · DPAPI Windows · SQLite.
Empacotamento com PyInstaller; dados e credenciais permanecem fora da pasta do executável.

## Dados de clientes

Relatórios, fotos e laudos de clientes **não** entram neste repositório (veja `.gitignore`). O corpus de teste fica
fora do Git, numa pasta local ou de rede controlada.
