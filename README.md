# Analisador de Relatórios de Qualificação

Aplicativo desktop (Windows) de uso interno da **Celacanto Análises Ambientais** para conferir relatórios de
qualificação antes da emissão: HVAC, fluxo unidirecional, cabines de segurança biológica, capelas, salas limpas e
gases.

O objetivo do projeto é ler o relatório (PDF) e as evidências, refazer as contas e cruzar
**relatório × evidência × critério × norma**. Nesta primeira implementação, o aplicativo oferece
consulta assistida por IA com referências selecionadas. **A decisão de emitir continua humana.**

## Situação

Primeira implementação: aplicativo desktop com login ChatGPT e biblioteca local de referências.
O motor de regras e o parecer previstos no design ainda não estão implementados.

### Executar no Windows

Instale Python 3.12 e execute `Iniciar.ps1` no PowerShell. Ou:

```powershell
py -3.12 -m venv "$env:LOCALAPPDATA\Celacanto\ar-venv"
& "$env:LOCALAPPDATA\Celacanto\ar-venv\Scripts\python.exe" -m pip install -r requirements.txt
& "$env:LOCALAPPDATA\Celacanto\ar-venv\Scripts\python.exe" -m revisor
```

1. Importe os PDFs/fotos/ZIPs em **Biblioteca local**.
2. Clique em **Continue with ChatGPT**, conclua o login no navegador e autorize o uso do plano, quando disponível.
3. Clique em **Carregar modelos** e escolha um dos modelos da sua conta.
4. Selecione um arquivo e uma página, visualize e clique em **Adicionar ao envio**.
5. Descreva a consulta e confirme os itens que serão enviados à OpenAI.
6. Confira as sugestões nos originais. Valores de imagens permanecem não confirmados.

Os dados ficam em `%LOCALAPPDATA%\Celacanto\AnalisadorRelatorios`.
Use `python -m revisor --data-dir CAMINHO` para outra biblioteca.
Importação local não treina o ChatGPT. Consulte [detalhes e limitações](docs/integracao-chatgpt.md).

Testes: `python -m unittest discover -s tests -v`.
Verificação de abertura: `python -m revisor --smoke --data-dir CAMINHO_TEMPORARIO`.

- Design: [docs/superpowers/specs/2026-11-16-revisor-relatorios-design.md](docs/superpowers/specs/2026-11-16-revisor-relatorios-design.md)

## Princípios

- O critério escrito no relatório é mandatório; a norma de referência gera alerta.
- Nenhum valor lido de imagem entra nas contas sem confirmação humana.
- Os arquivos originais nunca são alterados: cada um tem hash SHA-256 registrado no catálogo local e no registro de envio.
- A IA de visão (ChatGPT nesta implementação) é opcional, desligada por padrão e usada só nas imagens que a pessoa escolher.

## Stack

Python 3.12 · PySide6 (Qt) · PyMuPDF · pillow-heif · SDK `openai` · PyJWT · DPAPI Windows · SQLite.
Empacotamento PyInstaller previsto.

## Dados de clientes

Relatórios, fotos e laudos de clientes **não** entram neste repositório (veja `.gitignore`). O corpus de teste fica
fora do Git, numa pasta local ou de rede controlada.
